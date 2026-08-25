"""MiMo 开放平台 Provider（R3 已证实 schema 实现）。

对话与 TTS 共用 /chat/completions 端点：
- 对话响应取 choices[0].message.content（文本）
- TTS 响应取 choices[0].message.audio.data（base64 wav）
"""
from __future__ import annotations

import asyncio
import base64
import logging
import time
from collections import deque
from typing import List, Optional

import httpx

from app.core.config import Settings
from app.core.errors import AppError
from app.providers.base import BaseProvider

logger = logging.getLogger(__name__)

_TTS_STYLE_INSTRUCTION = "语速偏慢、吐字清晰、亲切温和"


class MiMoProvider(BaseProvider):
    def __init__(self, settings: Settings) -> None:
        self._cfg = settings
        if not settings.ai_api_key:
            raise RuntimeError("AI_PROVIDER=mimo 需配置 AI_API_KEY")
        self._client = httpx.AsyncClient(
            base_url=settings.ai_base_url,
            timeout=httpx.Timeout(settings.ai_timeout_seconds),
        )
        # RPM 客户端节流（安全加固：防超官方 100/session 封顶引发 429/风控）
        self._rpm_sem = asyncio.Semaphore(16)
        self._rpm_calls = deque()
        self._rpm_max = max(settings.ai_rpm_limit, 1)

    async def transcribe(self, audio_b64: str) -> str:
        """两段式链路：ASR 转写（mimo-v2.5-asr，多方言）。"""
        payload = {
            "model": "mimo-v2.5-asr",
            "messages": [{
                "role": "user",
                "content": [{
                    "type": "input_audio",
                    "input_audio": {"data":
                                    "data:audio/wav;base64," + audio_b64},
                }],
            }],
            "max_completion_tokens": 256,
            "extra_body_marker": None,
        }
        # asr_options 走 extra_body（OpenAI 兼容透传）
        payload["asr_options"] = {"language": "auto"}
        data = await self._post(payload)
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            logger.warning("ASR 响应缺 content")
            raise AppError("AI_PROVIDER_ERROR")
        return str(content).strip()

    async def understand(self, messages: List[dict],
                         audio_b64: Optional[str]) -> str:
        payload = {
            "model": self._cfg.ai_chat_model,
            "messages": messages,
            "max_completion_tokens": 512,
            "temperature": 0.3,
            "thinking": {"type": "disabled"},
            "stream": False,
        }
        data = await self._post(payload)
        try:
            content = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            logger.warning("MiMo 响应缺 content 字段")
            raise AppError("AI_PROVIDER_ERROR")
        if not str(content).strip():
            logger.warning("MiMo 返回空内容")
            raise AppError("AI_PROVIDER_ERROR")
        return str(content)

    async def synthesize(self, text: str, style: str = None) -> bytes:
        payload = {
            "model": self._cfg.ai_tts_model,
            "messages": [
                {"role": "user",
                 "content": style or _TTS_STYLE_INSTRUCTION},
                {"role": "assistant", "content": text},
            ],
            "audio": {"format": self._cfg.ai_tts_format,
                      "voice": self._cfg.ai_tts_voice},
        }
        data = await self._post(payload)
        try:
            b64 = data["choices"][0]["message"]["audio"]["data"]
        except (KeyError, IndexError, TypeError):
            logger.warning("MiMo TTS 响应缺 audio.data 字段")
            raise AppError("AI_PROVIDER_ERROR")
        return base64.b64decode(b64)

    async def _rpm_door(self) -> None:
        """滑动 60s 窗口节流；等窗口有空位才放行（排队而非拒绝）。"""
        while True:
            now = time.time()
            while self._rpm_calls and now - self._rpm_calls[0] > 60:
                self._rpm_calls.popleft()
            if len(self._rpm_calls) < self._rpm_max:
                self._rpm_calls.append(now)
                return
            await asyncio.sleep(0.5)

    async def _post(self, payload: dict):
        async with self._rpm_sem:
            await self._rpm_door()
            try:
                resp = await self._client.post(
                    "/chat/completions",
                    json=payload,
                    headers={"Authorization": "Bearer " + self._cfg.ai_api_key},
                )
            except httpx.TimeoutException:
                logger.warning("MiMo 调用超时 model=%s", payload.get("model"))
                raise AppError("AI_PROVIDER_ERROR")
            except httpx.HTTPError as exc:
                logger.warning("MiMo 网络异常: %s", type(exc).__name__)
                raise AppError("AI_PROVIDER_ERROR")
            if resp.status_code != 200:
                logger.warning("MiMo HTTP %s", resp.status_code)
                raise AppError("AI_PROVIDER_ERROR")
            try:
                return resp.json()
            except ValueError:
                logger.warning("MiMo 响应非 JSON")
                raise AppError("AI_PROVIDER_ERROR")

    async def aclose(self) -> None:
        await self._client.aclose()
