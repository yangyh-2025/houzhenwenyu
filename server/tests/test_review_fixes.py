"""代码交叉评审修复回归测试（R1-R9 对应）。"""
import base64

from app.core.wav_utils import build_test_wav, build_silence_wav


def _audio():
    return base64.b64encode(build_test_wav(0.5)).decode()


def _create(client, vn="35"):
    r = client.post("/api/patient/consultations",
                    json={"visit_number": vn})
    assert r.status_code == 200
    return r.json()


def test_r1_spa_absolute_path_injection_blocked(client):
    """R1：绝对路径注入不得读出 dist 外文件。"""
    for evil in ["C:/windows/win.ini", "D:/x", "/etc/passwd"]:
        r = client.get("/" + evil.lstrip("/"))
        # 要么回退 index.html，要么 404——绝不能返回任意文件内容
        if r.status_code == 200:
            body = r.text
            assert "html" in body.lower()
            assert len(body) < 50000  # index 页面尺寸量级


def test_r2_summary_filter_e2e(client):
    """R2：模型摘要中的建议行不得入库（两段式链路适配）。"""
    async def poisoned_transcribe(audio_b64):
        return "我最近睡得不怎么样，胃口一般，大小便正常。"

    async def poisoned_understand(messages, audio_b64):
        last = messages[-1] if messages else {}
        if ("诊前采集" in str(last.get("content", ""))):
            return ("好的，您的情况我了解得差不多了。"
                    "【问诊结束】" + chr(10) +
                    "【主诉】胃胀" + chr(10) +
                    "【病程】两周" + chr(10) +
                    "治疗原则是健脂化湿" + chr(10) +
                    "【睡眠】正常")
        return "请问您晚上睡得怎么样？"

    prov = client.app.state.service.provider
    orig_u, orig_t = prov.understand, prov.transcribe
    prov.transcribe = poisoned_transcribe
    prov.understand = poisoned_understand
    try:
        data = _create(client)
        sid = data["session_id"]
        r1 = client.post(f"/api/patient/consultations/{sid}/rounds",
                         json={"audio_b64": _audio()})
        assert r1.status_code == 200, r1.text
        r2 = client.post(f"/api/patient/consultations/{sid}/rounds",
                         json={"force_finish": True})
        assert r2.json()["finished"] is True, r2.text

        from app.db import get_session_factory
        from app.models import Consultation
        with get_session_factory()() as db:
            rec = db.get(Consultation, r2.json()["record_id"])
            assert "治疗原则" not in rec.summary_text
            assert "【主诉】胃胀" in rec.summary_text
    finally:
        prov.understand = orig_u
        prov.transcribe = orig_t


def test_r3_busy_session_rejected(client):
    """R3：会话处理中重复提交被拒。"""
    data = _create(client)
    sid = data["session_id"]
    sess = None
    for s in client.app.state.service.store._sessions.values():
        sess = s
    sess.busy = True
    try:
        r = client.post(f"/api/patient/consultations/{sid}/rounds",
                        json={"audio_b64": _audio()})
        assert r.status_code == 429
    finally:
        sess.busy = False


def test_r4_create_no_sync_tts(client):
    """R4(修订)：create 不再同步合成开场音频——TTS 断供不影响建会话。"""
    async def broken_tts(text):
        raise RuntimeError("tts down")

    orig = client.app.state.service.provider.synthesize
    before = len(client.app.state.service.store)
    client.app.state.service.provider.synthesize = broken_tts
    try:
        r = client.post("/api/patient/consultations",
                        json={"visit_number": "77"})
        # 2026-08-24 优化：开场音频改由前端静态/话术接口提供，
        # create 仅建会话（瞬时、不受 TTS 故障影响）
        assert r.status_code == 200
        assert r.json()["first_round"]["audio_b64"] == ""
        sid = r.json()["session_id"]
        assert sid
    finally:
        client.app.state.service.provider.synthesize = orig
    after = len(client.app.state.service.store)
    assert after == before + 1  # 会话正常建立，且无重复孤儿


def test_r6_missing_content_length_rejected(client):
    """R6：缺失 Content-Length 的请求体被拒。"""
    data = _create(client)
    sid = data["session_id"]
    r = client.post(
        f"/api/patient/consultations/{sid}/rounds",
        content=b'{"audio_b64":""}',
        headers={
            "Content-Type": "application/json",
            "Content-Length": "",
        })
    assert r.status_code == 413
    assert r.json()["code"] == "PAYLOAD_TOO_LARGE"


def test_r7_invalid_date_returns_400_envelope(authed):
    """R7：非法日期参数走统一 envelope 而非 500。"""
    r = authed.get("/api/doctor/consultations?date_from=nonsense")
    assert r.status_code == 400
    body = r.json()
    assert body["code"] == "PARAM_INVALID"
    assert "trace_id" in body


def test_r8_cleanup_at_invalid_range_rejected():
    from app.core.config import Settings
    import pytest
    with pytest.raises(Exception):
        Settings(cleanup_at="99:99")


def test_phrase_unknown_sid_404(client):
    r = client.post(
        "/api/patient/consultations/no-such-sid/fixed-phrase-audio",
        json={"phrase_key": "OPENING"})
    assert r.status_code == 404


def test_round_id_idempotent_replay(client):
    """F-R5 服务端半：同 round_id 重发返回缓存响应，不重复计轮。"""
    data = _create(client)
    sid = data["session_id"]
    rid = "test-round-0001"
    r1 = client.post(f"/api/patient/consultations/{sid}/rounds",
                     json={"audio_b64": _audio(), "round_id": rid})
    assert r1.status_code == 200
    payload1 = r1.json()
    r2 = client.post(f"/api/patient/consultations/{sid}/rounds",
                     json={"audio_b64": _audio(), "round_id": rid})
    assert r2.status_code == 200
    assert r2.json()["text"] == payload1["text"]
    assert r2.json()["round_index"] == payload1["round_index"]
    sess = list(client.app.state.service.store._sessions.values())[0]
    assert sess.rounds_used == 1  # 未重复计数


def test_silence_audio_rejected(client):
    """安全加固：静音音频被能量检测拒绝（防脚本刷量）。"""
    import base64
    from app.core.wav_utils import build_silence_wav
    data = _create(client)
    sid = data["session_id"]
    r = client.post(f"/api/patient/consultations/{sid}/rounds",
                    json={"audio_b64": base64.b64encode(
                        build_silence_wav(1.0)).decode()})
    assert r.status_code == 400
    assert r.json()["code"] == "AUDIO_INVALID"
    r2 = client.post(f"/api/patient/consultations/{sid}/rounds",
                     json={"audio_b64": _audio()})
    assert r2.status_code == 200  # 正常语音不受影响


def test_ai_budget_hard_limit(client):
    """安全加固：AI 调用预算超限返回 503 并停止消耗。"""
    svc = client.app.state.service
    data = _create(client)
    sid = data["session_id"]
    svc._budget_used = svc.cfg.ai_daily_call_budget  # 触及预算
    r = client.post(f"/api/patient/consultations/{sid}/rounds",
                    json={"audio_b64": _audio()})
    assert r.status_code == 503
    assert r.json()["code"] == "AI_QUOTA_EXCEEDED"
    svc._budget_used = 0  # 复位


def test_rate_limit_uses_trusted_xrealip_only_when_enabled(client):
    """安全加固：trust_proxy=false 时 X-Real-IP 伪造头被忽略。"""
    from app.core.ratelimit import SlidingWindowRateLimiter
    client.app.state.patient_limiter = SlidingWindowRateLimiter(3, 60)
    for i in range(3):
        r = client.post("/api/patient/consultations",
                        json={"visit_number": "66"},
                        headers={"X-Real-IP": "9.9.9.9"})
        assert r.status_code == 200
    # 第4次来自本机 IP 仍按真实 IP 计数 → 429（伪造头未放大额度）
    r = client.post("/api/patient/consultations",
                    json={"visit_number": "66"},
                    headers={"X-Real-IP": "9.9.9.8"})
    assert r.status_code == 429


def test_binary_audio_negotiation(client):
    """带宽优化：Accept: audio/ 时音频走原始 body + 元数据在 X-Hwy-Meta 头。"""
    data_ctx = client.get("/api/health")
    r = client.post("/api/patient/consultations",
                    json={"visit_number": "55"},
                    headers={"Accept": "audio/mpeg"})
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("audio/")
    assert "X-Hwy-Meta" in r.headers
    import json
    meta = json.loads(r.headers["X-Hwy-Meta"])
    assert meta["rounds_limit"] == 30 and meta["text"]
    sid = meta["session_id"]
    r2 = client.post(f"/api/patient/consultations/{sid}/rounds",
                     json={"audio_b64": _audio()},
                     headers={"Accept": "audio/mpeg"})
    assert r2.status_code == 200
    body = r2.content
    assert body[:4] == b"RIFF"  # mock 返回 wav
    meta2 = json.loads(r2.headers["X-Hwy-Meta"])
    assert meta2["finished"] is False and meta2["text"]
    # JSON 兼容模式不受影响
    r3 = client.post(f"/api/patient/consultations/{sid}/rounds",
                     json={"audio_b64": _audio()})
    assert r3.status_code == 200 and "audio_b64" in r3.json()


def test_ask_first_protocol(client):
    """协议 v2.1：点「明白了」后 AI 主动发出第一问（新八类首问）。"""
    data = _create(client)
    sid = data["session_id"]
    r = client.post(f"/api/patient/consultations/{sid}/ask",
                    headers={"Accept": "audio/mpeg"})
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("audio/")
    import json
    meta = json.loads(r.headers["X-Hwy-Meta"])
    assert "第一个问题" not in meta["text"]
    assert ("哪里不舒服" in meta["text"]) or ("不舒服" in meta["text"])
    # 首问以 assistant 身份记入历史（防止患者答后模型重复首问）
    sess = list(client.app.state.service.store._sessions.values())[0]
    assert sess.rounds_used == 0
    assert len(sess.messages) == 2  # system + assistant(首问)
    assert sess.messages[-1]["role"] == "assistant"


def test_intro_ack_then_rounds(client):
    """介绍→ack→首问→回答问题 完整链路。"""
    data = _create(client)
    sid = data["session_id"]
    ak = client.post(f"/api/patient/consultations/{sid}/ask")
    assert ak.status_code == 200
    assert "audio_b64" in ak.json() or "text" in ak.json()
    r1 = client.post(f"/api/patient/consultations/{sid}/rounds",
                     json={"audio_b64": _audio()})
    assert r1.status_code == 200
    assert r1.json()["text"].startswith("开始不舒服之前")  # 新八类第2问=诱因(第1问已由ask给出)


def test_daily_same_number_resume(client):
    """同日同号：中途退出→再次扫码→复用会话，first_round=上一问并 resumed=True。"""
    d1 = _create(client, vn="777")
    sid1 = d1["session_id"]
    assert d1.get("first_round", {}).get("resumed") in (False, None, True)
    # 答两轮后"退出"（不结束）
    r1 = client.post(f"/api/patient/consultations/{sid1}/rounds",
                     json={"audio_b64": _audio()})
    assert r1.status_code == 200
    r2 = client.post(f"/api/patient/consultations/{sid1}/rounds",
                     json={"audio_b64": _audio()})
    assert r2.status_code == 200
    q2 = r2.json()["text"]
    # 重新扫码同一号码
    d2 = _create(client, vn="777")
    assert d2["session_id"] == sid1, "同号当日应复用原会话"
    assert d2["first_round"]["resumed"] is True
    assert d2["first_round"]["text"] == q2, "续问应重放刚才的问题"
    assert client.app.state.service.store._sessions[sid1].rounds_used == 2


def test_one_number_one_record_upsert(client):
    """一号一条：同号第二次完成提交 → 覆盖旧记录，医生端仅见最新。"""
    data = _create(client)
    sid = data["session_id"]
    # 第一轮完成后 force 提交
    r1 = client.post(f"/api/patient/consultations/{sid}/rounds",
                     json={"audio_b64": _audio()})
    assert r1.status_code == 200
    r2 = client.post(f"/api/patient/consultations/{sid}/rounds",
                     json={"force_finish": True})
    rid1 = r2.json()["record_id"]
    # 同号再来一遍（新会话）并完成
    d2 = _create(client)
    assert d2["session_id"] != sid
    c2 = client.post(f"/api/patient/consultations/{d2['session_id']}/rounds",
                     json={"audio_b64": _audio()})
    assert c2.status_code == 200
    f2 = client.post(f"/api/patient/consultations/{d2['session_id']}/rounds",
                     json={"force_finish": True})
    rid2 = f2.json()["record_id"]
    from app.db import get_session_factory
    from app.models import Consultation
    with get_session_factory()() as db:
        rows = list(db.query(Consultation).where(
            Consultation.visit_number == "35"))
        assert len(rows) == 1
        assert rows[0].id == rid2 != rid1


def test_daily_cleanup_reset(client):
    """每日2点日清：昨日及以前清空，当作次日仅留当天提交。"""
    import time as _t
    from datetime import datetime, timedelta, timezone as _tz
    from app.db import get_session_factory
    from app.models import Consultation
    now = int(_t.time())
    with get_session_factory()() as db:
        db.add(Consultation(visit_number="1",
                            submitted_at=now - 86400 * 2, rounds=3,
                            summary_text="yesterday"))
        db.add(Consultation(visit_number="2", submitted_at=now,
                            rounds=3, summary_text="today"))
        db.commit()
    from app.services.cleanup import CleanupWorker
    class FCfg:
        cleanup_at = "02:00"
        retention_days = 90
    w = CleanupWorker(FCfg())
    w.run_once()
    with get_session_factory()() as db:
        rest = list(db.query(Consultation))
        assert len(rest) == 1 and rest[0].summary_text == "today"


def test_stage_marker_parsed_and_stripped(client):
    """进度标记：响应带 stage，播报文本不含标记。"""
    data = _create(client)
    sid = data["session_id"]
    r = client.post(f"/api/patient/consultations/{sid}/rounds",
                    json={"audio_b64": _audio()})
    body = r.json()
    assert body["stage"] == 2  # 首问已预置，第1轮答后=第2类
    assert "【" not in body["text"] and "/8" not in body["text"]
    # ask 路径 stage=1
    d2 = _create(client, vn="91")
    ak = client.post(f"/api/patient/consultations/{d2['session_id']}/ask")
    assert ak.json()["stage"] == 1


def test_tcm_block_preserved_in_summary(client):
    """辨证参考：摘要中建议行被删但辨证块保留（医生专用）。"""
    async def pt(audio_b64):
        return "我最近睡得不怎么样。"

    async def pu(messages, audio_b64):
        last = str((messages[-1] or {}).get("content", ""))
        if "诊前采集" in last:
            return ("好的，您的情况我了解得差不多了。"
                    "\u3010问诊结束\u3011" + chr(10) +
                    "\u3010主诉\u3011胃胀" + chr(10) +
                    "治疗原则是健脾化湿" + chr(10) +
                    "\u3010辨证参考\u3011肝胃不和，脾虚湿困")
        return "请问您晚上睡得怎么样？"

    prov = client.app.state.service.provider
    ou, ot = prov.understand, prov.transcribe
    prov.transcribe, prov.understand = pt, pu
    try:
        data = _create(client, vn="88")
        sid = data["session_id"]
        client.post(f"/api/patient/consultations/{sid}/rounds",
                    json={"audio_b64": _audio()})
        r2 = client.post(f"/api/patient/consultations/{sid}/rounds",
                         json={"force_finish": True})
        rid = r2.json()["record_id"]
        from app.db import get_session_factory
        from app.models import Consultation
        with get_session_factory()() as db:
            rec = db.get(Consultation, rid)
            assert "治疗原则" not in rec.summary_text
            assert "辨证参考" in rec.summary_text
            assert "肝胃不和" in rec.summary_text
    finally:
        prov.understand, prov.transcribe = ou, ot
