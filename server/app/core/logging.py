"""JSON 行日志 + request-id 贯穿 + 脱敏工具。

脱敏红线（D-08）：任何日志不得包含音频字节/base64、病情摘要正文、就诊号全文。
"""
from __future__ import annotations

import json
import logging
import sys
from contextvars import ContextVar

_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

_fmt_fields = ("asctime", "levelname", "name", "message", "request_id")


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": _request_id_ctx.get(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level_str: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level_str.upper())
    # uvicorn 日志也并入统一格式
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True


def set_request_id(value: str) -> None:
    _request_id_ctx.set(value)


def get_request_id() -> str | None:
    return _request_id_ctx.get()


def mask_visit_number(vn: str) -> str:
    """就诊号掩码：只留后四位，不足四位全掩码。"""
    if not vn or len(vn) < 4:
        return "****"
    return "****" + vn[-4:]
