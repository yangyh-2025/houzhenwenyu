"""脚本化 Mock Provider：无 Key 全功能开发/测试/演示（D-05）。

v2.2：新八类提问脚本 + 两段式链路支持（transcribe → 文本步进）；
MARKER 常量自带换行，避免拼接转义。
"""
from __future__ import annotations

from typing import List, Optional

from app.core.wav_utils import build_silence_wav, build_test_wav
from app.providers.base import BaseProvider

_STAGE_MAP = [1, 2, 3, 4, 5, 6, 7, 7, 7, 8]  # 10问→8类
LB8 = chr(0x3010)
RB8 = chr(0x3011)


def _tag(step):
    n = _STAGE_MAP[step] if step < len(_STAGE_MAP) else 8
    return LB8 + str(n) + "/8" + RB8


MARKER = "\u3010\u95ee\u8bca\u7ed3\u675f\u3011" + chr(10)

# 新八类信息顺序的口语化提问脚本（2026-08-24 v2）
SCRIPT = [
    "请问您主要是哪里不舒服呀？是怎么开始的，到现在大概多久了？",
    "开始不舒服之前，有什么特别的事情发生吗？比如着凉、吃坏东西或者累着了？",
    "不舒服主要在哪个位置？是疼、胀、麻还是晕呢？厉害吗？",
    "除了这个不舒服，还有没有别的难受？比如恶心、乏力、心慌之类的？",
    "这个情况有没有去其他医院看过？做过什么检查、吃过什么药吗？",
    "那现在这一刻，您还有哪些不舒服的感觉？",
    "最近吃饭胃口怎么样？",
    "晚上睡得着吗？",
    "大小便还正常吗？",
    "您有高血压、糖尿病这些慢性病吗？现在在吃哪些药？中药西药都说一说。",
]

SUMMARY_TEMPLATE = """【主诉】胃部胀满不适，伴反酸
【病程】两周
【刻下主要症状】中上腹胀痛，隐痛为主，程度较轻
【饮食】胃口一般，食后腹胀
【睡眠】入睡尚可，易醒
【二便】大便偏干，小便正常
【既往病史】高血压十年
【当前用药】氨氯地平每日一次"""


class ScriptedMockProvider(BaseProvider):
    def __init__(self, *args, **kwargs) -> None:
        self.calls = 0

    async def transcribe(self, audio_b64: str) -> str:
        """mock ASR：能量低→没说话；极短→简短；否则固定演示转写。"""
        import base64 as _b64
        import io as _io
        import wave as _wave
        try:
            raw = _b64.b64decode(audio_b64)
            w = _wave.open(_io.BytesIO(raw), "rb")
            nf = w.getnframes()
            from app.core.wav_utils import pcm_rms
            rms = pcm_rms(w.readframes(nf))
            w.close()
            if rms < 0.02:
                return "患者没有说话。"
        except Exception:
            pass
        import base64 as _b64
        if len(audio_b64) < 300:
            return "我不太舒服。"
        try:
            if self._tiny(audio_b64):
                # 安全过滤器测试钩子：极短音频→返回空→服务层回退音频直传，
                # understand 直传 tiny 分支产出建议话术（被过滤器拦截替换）
                return ""
        except Exception:
            pass
        return "嗯，我最近睡得不怎么样，胃口也一般，大小便还正常。"

    async def understand(self, messages: List[dict],
                         audio_b64: Optional[str]) -> str:
        self.calls += 1
        if audio_b64 is None:
            last = messages[-1] if messages else {}
            last_c = str(last.get("content", ""))
            if (last.get("role") == "user" and "第一个问题" in last_c):
                return SCRIPT[0] + _tag(0)  # 协议 v2.1：开场介绍后的首问
            if (last.get("role") == "user" and "患者" in last_c):
                # 两段式：该轮用户消息为转写文本 → 按步进正常出下一问
                step2 = (len(messages) - 1) // 2
                if step2 < len(SCRIPT):
                    return SCRIPT[step2] + _tag(step2)
                return "好的，您的情况我了解得差不多了。" + MARKER + SUMMARY_TEMPLATE
            return "好的，您的情况我了解得差不多了。" + MARKER + SUMMARY_TEMPLATE
        step = (len(messages) - 1) // 2
        if step == 1 and self._tiny(audio_b64):
            # 安全过滤器测试钩子：短音频触发建议类话术
            return "建议您服用香砂养胃丸调理。请问您的睡眠怎么样？"
        if step < len(SCRIPT):
            return SCRIPT[step] + _tag(step)
        return "好的，您的情况我了解得差不多了。" + MARKER + SUMMARY_TEMPLATE

    async def synthesize(self, text: str) -> bytes:
        # 预览占位：提示音（无 Key 可感知链路；真实 MiMo 为真人声）
        return build_test_wav(1.0)

    @staticmethod
    def _tiny(audio_b64):
        """测试钩子：帧数<4800(0.3s) 判定极短音频。"""
        import base64 as _b64
        import io as _io
        import wave as _wave
        w = _wave.open(_io.BytesIO(_b64.b64decode(audio_b64)), "rb")
        n = w.getnframes()
        w.close()
        return 8000 < n < 9600  # >0.5s 服务端下限，<0.6s 钩子窗口
