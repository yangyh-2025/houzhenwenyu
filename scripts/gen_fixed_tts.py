"""固定话术静态化生成脚本（带宽优化 A3）。

用法（在仓库根目录）:
  python scripts/gen_fixed_tts.py                  # 读取 .env 或环境变量
  AI_PROVIDER=mock python scripts/gen_fixed_tts.py  # 无Key，生成静音占位(wav)

产物: web/public/tts/{key}.mp3（真实 MiMo）或 .wav（mock 占位）。
前端优先播放 /tts/{key}.mp3|wav（Nginx 静态直出，不经过后端进程），
失败自动回退后端动态接口。
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "server"))
os.environ.setdefault("AI_PROVIDER", "mimo")

from app.core.config import Settings, get_settings  # noqa: E402
from app.services.fixed_phrases import PHRASES  # noqa: E402

# 按键与确认播报语音（2026-08-24）：数字0-9 + 核对引导语
# 数字用中文汉字（阿拉伯数字会被读成英文）；统一昂扬语气
_CN_DIGITS = ["零", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
DIGIT_STYLE = "语气昂扬、声音明亮、吐字清晰，像叫号报号一样响亮利落"
EXTRA_PHRASES = {
    "CONFIRM_PREFIX": "请核对您的就诊号，您的就诊号是",
    **{f"NUM_{d}": _CN_DIGITS[d] for d in range(10)},
}

OUT = os.path.join(os.path.dirname(__file__), "..", "web", "public", "tts")


def main() -> int:
    s = get_settings()
    os.makedirs(OUT, exist_ok=True)
    if s.ai_provider == "mimo":
        from app.providers.mimo import MiMoProvider
        provider = MiMoProvider(s)
        ext = "mp3"
    else:
        from app.providers.mock import ScriptedMockProvider
        provider = ScriptedMockProvider()
        ext = "wav"

    import asyncio

    async def run():
        n = 0
        for key, text in list(PHRASES.items()) + list(EXTRA_PHRASES.items()):
            if key.startswith("NUM_"):
                raw = await provider.synthesize(text, style=DIGIT_STYLE)
            else:
                raw = await provider.synthesize(text)
            path = os.path.join(OUT, f"{key}.{ext}")
            with open(path, "wb") as f:
                f.write(raw)
            print(f"  {key}: {len(raw)} bytes -> {path}")
            n += 1
        await provider.aclose()
        return n

    n = asyncio.run(run())
    print(f"完成: {n} 条固定话术静态化到 web/public/tts/")
    print("提示: 生产上线前用真实 MiMo Key 重新生成 mp3，前端会自动优先静态资源。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
