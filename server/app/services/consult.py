"""问诊会话核心逻辑：内存状态机 + 收尾入库。

隐私白名单（PRD F9）：轮次文本仅存内存，完成时只落库四字段；
音频处理完即弃。
"""
from __future__ import annotations

import base64
import logging
import re
import threading
import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import delete

from app.core.config import Settings
from app.core.errors import AppError
from app.core.wav_utils import (pcm_rms,
                                 validate_speech_energy,
                                 validate_wav_16k_mono)
from app.providers.base import BaseProvider
from app.providers import safety
from app.providers.safety import filter_question_reply, filter_summary
from app.core.logging import mask_visit_number as mask_vn
from app.models import Consultation
from app.services.fixed_phrases import PHRASE_KEYS, SYSTEM_PROMPT, get_text

logger = logging.getLogger(__name__)

MARKER_RE = re.compile(r"【问诊结束】")
STAGE_RE = re.compile("【(\d{1,2})/8】")

# 强制收尾的显式总结指令（2026-08-24 修复：真实模型无指令会继续引导而非出摘要）
SUMMARY_INSTRUCTION = (    "刚刚您已经和患者完成了诊前采集。现在请立刻根据以上全部对话内容，"
    "输出【问诊结束】，紧接着输出八栏结构化摘要："
    "【主诉】【病程】【刻下主要症状】【饮食】【睡眠】【二便】"
    "【既往病史】【当前用药】。每个栏目给已获得的信息；没有的信息写「未提及」。"
    "不要再问任何问题。"
)
VISIT_RE = re.compile(r"^\d{1,12}$")

# 2026-08-24 用户修订：摘要八个栏目（删除【寒热出汗】）
NINE_LABELS = [
    "主诉", "病程", "刻下主要症状", "饮食", "睡眠",
    "二便", "既往病史", "当前用药",
]


@dataclass
class ConsultSession:
    session_id: str
    visit_number: str
    ip: str
    created_at: float
    last_active: float
    expires_at: float = 0.0
    rounds_used: int = 0
    busy: bool = False
    messages: Optional[List[dict]] = None
    replay_cache: Optional[dict] = None
    last_round_id: Optional[str] = None

    def __post_init__(self):
        if self.messages is None:
            self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]


class ConsultSessionStore:
    """内存会话存储：TTL 滑动过期 + 每 IP 上限 + 全局上限。"""

    def __init__(self, ttl_minutes: int = 30,
                 max_per_ip: int = 5, max_total: int = 500,
                 daily_reset_at: str = "02:00") -> None:
        # 2026-08-24：会话寿命=当日挂号有效（次日 CLEANUP_AT 起作废），
        # 支持"中途退出重扫码续问"；ttl_minutes 字段仅保留兼容
        self.max_per_ip = max_per_ip
        self.max_total = max_total
        self._daily_reset_at = daily_reset_at
        self._sessions: Dict[str, ConsultSession] = {}
        self._ip_index: Dict[str, set] = {}

    def _next_reset_epoch(self, now: float) -> float:
        """当日 CLEANUP_AT（默认02:00）的下一次时间点（UTC epoch；服务器时区）。"""
        import datetime as _dt
        hh, mm = (self._daily_reset_at or "02:00").split(":")
        d = _dt.datetime.now()
        target = d.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        if target <= d:
            target += _dt.timedelta(days=1)
        return target.timestamp()

    def create(self, visit_number: str, ip: str) -> ConsultSession:
        # 一号一人（当日有效）：同号已有活跃会话直接复用（中途退出重扫码续问）
        for sid, existing in list(self._sessions.items()):
            if (existing.visit_number == visit_number
                    and existing.expires_at > time.time()):
                existing.last_active = time.time()
                self._ip_index.setdefault(ip, set()).add(sid)
                return existing
        ip_sids = self._ip_index.setdefault(ip, set())
        if len(ip_sids) >= self.max_per_ip or len(self._sessions) >= self.max_total:
            raise AppError("PATIENT_RATE_LIMITED")
        sid = uuid.uuid4().hex
        now = time.time()
        sess = ConsultSession(
            session_id=sid, visit_number=visit_number, ip=ip,
            created_at=now, last_active=now,
        )
        if sess.replay_cache is None:
            sess.replay_cache = {}
        sess.expires_at = self._next_reset_epoch(now)
        self._sessions[sid] = sess
        ip_sids.add(sid)
        return sess

    def get(self, sid: str) -> ConsultSession:
        sess = self._sessions.get(sid)
        if not sess or time.time() > sess.expires_at:
            raise AppError("CONSULT_SESSION_NOT_FOUND")
        sess.last_active = time.time()
        return sess

    def drop(self, sid: str) -> None:
        sess = self._sessions.pop(sid, None)
        if sess is not None:
            sids = self._ip_index.get(sess.ip)
            if sids is not None:
                sids.discard(sid)
                if not sids:
                    self._ip_index.pop(sess.ip, None)

    def sweep_expired(self) -> int:
        now = time.time()
        expired = [sid for sid, s in list(self._sessions.items())
                   if now > s.expires_at]
        for sid in expired:
            self.drop(sid)
        return len(expired)

    def __len__(self):
        return len(self._sessions)


@dataclass
class _RoundOutcome:
    reply: str
    finished: bool
    summary: str
    closing_text: str = ""


def _extract_stage(text: str):
    """剥离进度标记 【X/8】，返回(干净文本, stage或None)。"""
    stages = STAGE_RE.findall(text or "")
    clean = STAGE_RE.sub("", text or "").strip()
    return clean, (int(stages[-1]) if stages else None)


def normalize_summary(text: str) -> str:
    """九栏目完整性兜底：缺失栏目补 '<栏目>未提及'。"""
    out = (text or "").strip()
    for label in NINE_LABELS:
        tag = "【" + label + "】"
        if tag not in out:
            out += "\n【" + label + "】未提及"
    return out


class ConsultationService:
    def __init__(self, provider: BaseProvider, store: ConsultSessionStore,
                 settings: Settings) -> None:
        self.provider = provider
        self.store = store
        self.cfg = settings
        self._phrase_audio_cache: Dict[str, bytes] = {}
        self._budget_start = time.time()
        self._budget_used = 0
        self._budget_warned = False

    async def create_session(self, visit_number: str, ip: str) -> dict:
        vn = (visit_number or "").strip()
        if not VISIT_RE.match(vn):
            raise AppError("VISIT_NUMBER_INVALID")
        # 2026-08-24 优化：create 不再同步合成开场音频（18s引导语会超时）。
        # 开场白由前端 playStatic(/tts/OPENING.mp3) 或 fixed-phrase-audio 提供。
        sess = self.store.create(vn, ip)
        if sess.rounds_used > 0:
            # 同号续问（当日有效）：播报最后一问并由 AI 继续引导
            last_q = ""
            for m in reversed(sess.messages):
                if m.get("role") == "assistant":
                    last_q = str(m.get("content", ""))
                    break
            tts = await self._tts_question(last_q or get_text("OPENING"))                 if last_q else ""
            return {
                "session_id": sess.session_id,
                "rounds_limit": self.cfg.ai_max_rounds,
                "first_round": {"text": last_q or get_text("OPENING"),
                                "audio_b64": tts, "resumed": True},
            }
        return {
            "session_id": sess.session_id,
            "rounds_limit": self.cfg.ai_max_rounds,
            "first_round": {
                "text": get_text("OPENING"), "audio_b64": "",
                "resumed": False,
            },
        }

    def _count_ai_call(self, kind: str) -> None:
        """上游调用硬预算（安全加固）：24h 窗口，超限 503；80% 时 WARN。"""
        now = time.time()
        if now - self._budget_start > 86400:
            self._budget_start = now
            self._budget_used = 0
            self._budget_warned = False
        self._budget_used += 1
        budget = self.cfg.ai_daily_call_budget
        if self._budget_used > budget:
            logger.warning("AI 调用预算超限 used=%d budget=%d kind=%s",
                           self._budget_used, budget, kind)
            raise AppError("AI_QUOTA_EXCEEDED",
                           "系统有点忙啦，请稍后再试一次")
        if (not self._budget_warned
                and self._budget_used >= int(budget * 0.8)):
            self._budget_warned = True
            logger.warning("AI 调用预算已达80%% used=%d budget=%d",
                           self._budget_used, budget)

    async def _synth_safe(self, text: str) -> bytes:
        self._count_ai_call("tts")
        """TTS 异常统一转业务错误（评审 R4 补充）。"""
        try:
            return await self.provider.synthesize(text)
        except AppError:
            raise
        except Exception as e:
            logger.warning("TTS 异常类型=%s", type(e).__name__)
            raise AppError("AI_PROVIDER_ERROR")

    async def _phrase_audio(self, key: str) -> str:
        """固定话术 TTS：进程级缓存，只合成一次。"""
        text = get_text(key)
        cache_key = self.cfg.ai_tts_voice + "|" + key
        cached = self._phrase_audio_cache.get(cache_key)
        if cached is None:
            raw = await self._synth_safe(text)
            cached = base64.b64encode(raw).decode("ascii")
            self._phrase_audio_cache[cache_key] = cached
        return cached

    def _trim_replay(self, sess) -> None:
        if len(sess.replay_cache) > 4:
            for k in list(sess.replay_cache)[:len(sess.replay_cache) - 4]:
                sess.replay_cache.pop(k, None)

    async def submit_round(self, sid: str, audio_b64: Optional[str],
                           force_finish: bool = False,
                           round_id: Optional[str] = None) -> dict:
        """会话级互斥包装（评审 R3）；round_id 幂等回放（评审 F-R5 服务端半）。"""
        sess = self.store.get(sid)
        if round_id and round_id in sess.replay_cache:
            return dict(sess.replay_cache[round_id])
        if getattr(sess, "busy", False):
            raise AppError("PATIENT_RATE_LIMITED",
                           "上一条还在处理中，请稍等一下下")
        sess.busy = True
        sess.last_round_id = round_id
        try:
            return await self._submit_locked(audio_b64, force_finish, sess)
        finally:
            sess.busy = False

    async def _submit_locked(self, audio_b64, force_finish, sess) -> dict:
        if force_finish:
            return await self._finalize(sess)
        if not audio_b64:
            raise AppError("AUDIO_INVALID")
        try:
            import base64 as _b64
            audio_bytes = _b64.b64decode(audio_b64, validate=True)
        except Exception:
            raise AppError("AUDIO_INVALID", "录音数据无效，请重试一次")

        validate_wav_16k_mono(audio_bytes, self.cfg.max_audio_bytes)
        validate_speech_energy(audio_bytes, self.cfg.min_audio_rms,
                               self.cfg.min_audio_seconds)
        # 音频指标旁路（合规：只记能量/时长，不记内容；排查"模型听不见"）
        import io as _io
        import wave as _wave
        try:
            _w = _wave.open(_io.BytesIO(audio_bytes), "rb")
            _frames = _w.getnframes()
            _rms = pcm_rms(_w.readframes(_frames))
            _w.close()
            logger.info("音频指标 vn=%s frames=%d rms=%.4f",
                        mask_vn(sess.visit_number), _frames, _rms)
        except Exception:
            pass

        # 两段式链路（v2.2，修复反复追问同题）：先 ASR 转写为文本，
        # 以"患者第N轮回答转写：xxx"文本消息进模型；ASR 失败回退音频直传。
        self._count_ai_call("asr")
        transcript = ""
        try:
            transcript = await self.provider.transcribe(audio_b64)
        except Exception:
            logger.warning("ASR 失败，回退音频直传 path")
        logger.info("ASR指标 vn=%s len=%d empty=%s",
                    mask_vn(sess.visit_number),
                    len(transcript or ""), not bool(transcript))
        if transcript:
            round_no = (len(sess.messages) + 1) // 2
            user_msg = {"role": "user",
                        "content": "患者第%d轮回答转写：%s" % (round_no,
                                                           transcript)}
        else:
            user_msg = {
                "role": "user",
                "content": [{
                    "type": "input_audio",
                    "input_audio": {"data": "data:audio/wav;base64," + audio_b64},
                }],
            }
        # 失败不计轮次：历史只在成功后提交（PRD F3-R11）
        self._count_ai_call("understand")
        reply = await self.provider.understand(
            sess.messages + [user_msg], None if transcript else audio_b64)
        outcome = self._parse_reply(reply)

        if not outcome.finished and \
                sess.rounds_used + 1 >= self.cfg.ai_max_rounds:
            # 达到轮次上限强制收尾（PRD F3-R6）
            logger.info("轮次达上限，触发强制收尾 vn=%s",
                        mask_vn(sess.visit_number))
            self._count_ai_call("understand")
            summary_reply = await self.provider.understand(
                sess.messages
                + [{"role": "user", "content": SUMMARY_INSTRUCTION}],
                None)
            outcome = _RoundOutcome(
                reply="", finished=True,
                summary=normalize_summary(
                    filter_summary(self._strip_marker(summary_reply))))
        else:
            pass

        stage = None
        question_text = ""
        tts_b64 = ""
        if outcome.finished:
            closing = outcome.closing_text or get_text("CLOSING")
            question_text = closing
            stage = 8
            if outcome.closing_text:
                tts_b64 = await self._tts_question(closing)
            else:
                tts_b64 = await self._phrase_audio("CLOSING")
        else:
            clean_reply, stage = _extract_stage(outcome.reply)
            question_text = filter_question_reply(
                clean_reply, get_text("FALLBACK_QUESTION"))
            tts_b64 = await self._tts_question(question_text)
        return await self._commit_and_respond(
            sess, user_msg, outcome, question_text, tts_b64, stage=stage)

    async def ask_first(self, sid: str) -> dict:
        """协议 v2.1：开场介绍播毕（用户点【明白了】后）由 AI 主动发出第一问。

        不写入会话历史（患者尚未回答）；consume 一次上游调用并合成提问语音。
        """
        sess = self.store.get(sid)
        self._count_ai_call("understand-first-ask")
        instruction = ("现在请正式开始问诊。只输出你要问的第一个问题，"
                       "不要输出结束标记，也不要输出摘要。")
        reply = await self.provider.understand(
            list(sess.messages) + [{"role": "user", "content": instruction}],
            None)
        question_text = filter_question_reply(
            reply, get_text("FALLBACK_QUESTION"))
        tts_b64 = await self._tts_question(question_text)
        # 首问记入历史（assistant 侧）：防止患者作答后模型重复第1类问题
        sess.messages.append(
            {"role": "assistant", "content": question_text})
        return {"text": question_text, "audio_b64": tts_b64, "stage": 1}

    async def fixed_phrase_audio(self, sid: str, key: str) -> dict:
        self.store.get(sid)  # 校验会话有效
        if key not in PHRASE_KEYS:
            raise AppError("PHRASE_NOT_FOUND")
        audio = await self._phrase_audio(key)
        return {"audio_b64": audio}

    def _parse_reply(self, reply: str):
        m = MARKER_RE.search(reply or "")
        if not m:
            return _RoundOutcome(reply=reply, finished=False, summary="")
        # 评审 R2/R17：二次 marker 清除 + 摘要安全过滤接线
        summary_raw = MARKER_RE.sub("", reply[m.end():]).strip()
        # 2026-08-24 语义强化：标记前的过渡收尾语作为播报文本（模型主动收尾）
        prefix = reply[:m.start()].strip()
        closing = ""
        if prefix and len(prefix) > 3:
            pat, _fam = safety.hit(prefix)
            closing = "" if pat is not None else prefix
        return _RoundOutcome(
            reply="", finished=True,
            summary=normalize_summary(filter_summary(summary_raw)),
            closing_text=closing)

    def _strip_marker(self, reply: str) -> str:
        return MARKER_RE.sub("", reply or "").strip()

    async def _tts_question(self, text: str) -> str:
        raw = await self._synth_safe(text)
        return base64.b64encode(raw).decode("ascii")

    async def _finalize(self, sess: ConsultSession) -> dict:
        """force_finish：按已采集内容直接收尾，不新增轮次（PRD AC10）。"""
        self._count_ai_call("understand")
        summary_reply = await self.provider.understand(
            sess.messages
            + [{"role": "user", "content": SUMMARY_INSTRUCTION}], None)
        outcome = _RoundOutcome(
            reply="", finished=True,
            summary=normalize_summary(
                filter_summary(self._strip_marker(summary_reply))))
        closing = outcome.closing_text or get_text("CLOSING")
        if outcome.closing_text:
            tts_b64 = await self._tts_question(closing)
        else:
            tts_b64 = await self._phrase_audio("CLOSING")
        return await self._commit_and_respond(
            sess, None, outcome, closing, tts_b64, count_round=False,
            stage=8)

    async def _commit_and_respond(self, sess, user_msg, outcome,
                                  question_text: str, tts_b64: str,
                                  count_round: bool = True,
                                  stage=None) -> dict:
        # 成功后才提交历史与轮次（失败不计轮次，PRD F3-R11）
        if user_msg is not None:
            if outcome.reply:
                sess.messages.append(user_msg)
                sess.messages.append(
                    {"role": "assistant", "content": question_text or outcome.reply})
            else:
                sess.messages.append(user_msg)
                sess.messages.append(
                    {"role": "assistant",
                     "content": "【问诊结束】" + outcome.summary})
        if count_round:
            sess.rounds_used += 1
        resp = {
            "finished": bool(outcome.finished),
            "round_index": sess.rounds_used,
            "stage": stage,
            "text": question_text,
            "audio_b64": tts_b64,
        }
        if not outcome.finished:
            remaining = self.cfg.ai_max_rounds - sess.rounds_used
            resp["rounds_remaining"] = max(remaining, 0)
        if outcome.finished:
            record_id = self._persist(sess, outcome.summary)
            resp["record_id"] = record_id
            self.store.drop(sess.session_id)
        self._cache_reply(sess, resp)
        return resp

    def _cache_reply(self, sess, resp) -> None:
        """成功响应短缓存：同 round_id 重发直接回放（评审 F-R5 服务端半）。"""
        if sess.last_round_id:
            import copy as _copy
            sess.replay_cache[sess.last_round_id] = _copy.deepcopy(resp)
            self._trim_replay(sess)

    def _persist(self, sess: ConsultSession, summary: str) -> int:
        from app.db import get_session_factory
        with get_session_factory()() as db:
            db.execute(
                delete(Consultation).where(
                    Consultation.visit_number == sess.visit_number))
            rec = Consultation(
                visit_number=sess.visit_number,
                submitted_at=int(time.time()),
                rounds=sess.rounds_used,
                summary_text=summary,
            )
            db.add(rec)
            db.commit()
            db.refresh(rec)
            logger.info("摘要入库 id=%s vn=%s rounds=%s",
                        rec.id, mask_vn(sess.visit_number), sess.rounds_used)
            return rec.id


class SessionSweeper(threading.Thread):
    """每 60 秒扫描丢弃过期会话（架构 §三）。"""

    def __init__(self, store: ConsultSessionStore, interval: int = 60):
        super().__init__(daemon=True, name="session-sweeper")
        self._store = store
        self._interval = interval
        self._stop_event = threading.Event()

    def stop(self):
        self._stop_event.set()

    def run(self):
        while not self._stop_event.wait(self._interval):
            try:
                n = self._store.sweep_expired()
                if n:
                    logger.info("过期会话清扫 dropped=%d", n)
            except Exception:
                logger.exception("会话清扫异常")
