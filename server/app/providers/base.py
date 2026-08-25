"""AI Provider 抽象接口（决策 D-05）。

约定：
- understand 的 messages 为完整 OpenAI 风格数组（含 system）
- audio_b64 为纯 base64 字符串（无 data URI 前缀）；None 表示"总结收尾"调用
- synthesize 返回 WAV 原始字节
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional


class BaseProvider(ABC):
    @abstractmethod
    async def understand(self, messages: List[dict],
                         audio_b64: Optional[str]) -> str:
        ...

    async def transcribe(self, audio_b64: str) -> str:
        """返回音频转写文本。默认透传（mock 需覆盖）；两段式链路使用。"""
        return ""

    @abstractmethod
    async def synthesize(self, text: str, style: str = None) -> bytes:
        ...

    async def aclose(self) -> None:
        return None
