"""mock provider 与 safety 过滤器单测。"""
import base64
import asyncio

from app.core.wav_utils import build_test_wav
from app.providers.mock import (ScriptedMockProvider, MARKER)
from app.providers.safety import (filter_question_reply,
                                  filter_summary)


def _audio_b64():
    return base64.b64encode(build_test_wav(1.0)).decode()


def test_script_progression_and_summary_labels():
    p = ScriptedMockProvider()
    async def flow():
        msgs = [{"role": "system", "content": "s"}]
        outs = []
        for i in range(10):
            out = await p.understand(msgs, _audio_b64())
            msgs += [user_msg(), {"role": "assistant", "content": out}]
            outs.append(out)
        fin = await p.understand(msgs, _audio_b64())
        assert MARKER in fin
        for lb in ["主诉", "病程", "刻下主要症状", "饮食", "睡眠",
                   "二便", "既往病史", "当前用药"]:
            assert lb in fin
    asyncio.run(flow())


def user_msg():
    return {"role": "user",
            "content": [{"type": "input_audio", "input_audio": {"data": "x"}}]}


def test_summarize_mode_returns_marker_and_summary():
    p = ScriptedMockProvider()
    out = asyncio.run(p.understand([{"role": "system", "content": "s"}],
                                   None))
    assert MARKER in out
    assert "【主诉】" in out


def test_safety_hook_short_audio():
    p = ScriptedMockProvider()
    async def flow():
        msgs = [{"role": "system", "content": "s"}]
        await p.understand(msgs, _audio_b64())
        from app.core.wav_utils import build_silence_wav
        short_b64 = base64.b64encode(build_test_wav(0.55)).decode()
        await p.understand(msgs + [user_msg()], short_b64)
        return await p.understand(
            msgs + [user_msg(),
                    {"role": "assistant", "content": "x"}],
            short_b64)
    reply = asyncio.run(flow())
    from app.services.fixed_phrases import PHRASES
    fallback = PHRASES["FALLBACK_QUESTION"]
    # 短音频在 step==1 触发建议话术；经过滤器应替换为中性追问
    filtered = filter_question_reply(reply, fallback)
    assert "服用" not in filtered


def test_safety_five_families():
    """五族黑名单：命中被替换/删行，正常内容不受影响。"""
    from app.services.fixed_phrases import PHRASES
    fb = PHRASES["FALLBACK_QUESTION"]
    positives = [
        "建议您服用香砂养胃丸调理",
        "可以确诊为脾胃虚寒",
        "开个方剂：党参10克",
        "治疗原则是健脾化湿",
        "建议您去做个胃镜检查",
    ]
    for t in positives:
        out = filter_question_reply(t, fb)
        assert out == fb, t
    negatives = [
        "请问您的饮食胃口怎么样？",
        "平时怕冷还是怕热？出汗多不多？",
        "请问大小便正常吗？",
    ]
    for t in negatives:
        assert filter_question_reply(t, fb) == t


def test_safety_summary_line_removal():
    summary = ("【主诉】胃胀两周\n"
               "【病程】两周\n"
               "治疗原则是健脾化湿\n"
               "【睡眠】易醒\n")
    out = filter_summary(summary)
    assert "治疗原则" not in out
    assert "【主诉】" in out and "【睡眠】" in out
