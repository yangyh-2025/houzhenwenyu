"""请求 ID 与安全响应头中间件。"""
from __future__ import annotations

import re
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging import get_request_id, set_request_id


class RequestIDMiddleware(BaseHTTPMiddleware):
    _RID_OK = re.compile(r"^[A-Za-z0-9-]{1,64}$")

    async def dispatch(self, request: Request, call_next):
        rid_in = request.headers.get("x-request-id", "")
        rid = rid_in if self._RID_OK.match(rid_in) else secrets.token_hex(8)
        set_request_id(rid)
        try:
            response = await call_next(request)
        finally:
            pass
        response.headers["X-Request-ID"] = rid
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """安全响应头。CSP 允许 blob: 媒体（TTS 音频 Blob URL 播放）。"""

    CSP = (
        "default-src 'self'; "
        "media-src 'self' blob: data:; "
        "img-src 'self' data:; "
        "style-src 'self' 'unsafe-inline'; "
        "script-src 'self'; "
        "connect-src 'self'"
    )

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Content-Security-Policy", self.CSP)
        response.headers.setdefault("Permissions-Policy", "microphone=(self)")
        return response


def get_client_ip(request, app) -> str:
    """真实客户端 IP：仅当 trust_proxy 且命中数据库时信X-Real-IP（Nginx后），
    其余一律用直连地址——防伪造头绕过限流（安全加固）。"""
    cfg = getattr(app.state, "settings", None)
    trust = bool(getattr(cfg, "trust_proxy", False))
    if trust:
        xip = request.headers.get("x-real-ip")
        if xip and xip.strip() and "." in xip:
            return xip.strip()
    return request.client.host if request.client else "unknown"
