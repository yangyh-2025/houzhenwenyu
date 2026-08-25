"""Provider 工厂：按配置选择真实 MiMo 或 Mock。"""
from __future__ import annotations

from app.core.config import Settings
from app.providers.base import BaseProvider


def create_provider(settings: Settings) -> BaseProvider:
    if settings.ai_provider == "mimo":
        from app.providers.mimo import MiMoProvider
        return MiMoProvider(settings)
    from app.providers.mock import ScriptedMockProvider
    return ScriptedMockProvider()
