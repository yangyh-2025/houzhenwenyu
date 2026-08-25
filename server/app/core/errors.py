"""业务异常与统一错误 envelope。"""
from __future__ import annotations

from typing import Dict

CODE_HTTP: Dict[str, int] = {
    "PATIENT_RATE_LIMITED": 429,
    "VISIT_NUMBER_INVALID": 400,
    "PARAM_INVALID": 400,
    "PAYLOAD_TOO_LARGE": 413,
    "CONSULT_SESSION_NOT_FOUND": 404,
    "PHRASE_NOT_FOUND": 404,
    "AUDIO_INVALID": 400,
    "AI_PROVIDER_ERROR": 502,
    "AI_QUOTA_EXCEEDED": 503,
    "AUTH_REQUIRED": 401,
    "AUTH_LOCKED": 423,
    "AUTH_BAD_CREDENTIALS": 401,
    "RECORD_NOT_FOUND": 404,
    "INTERNAL_ERROR": 500,
}


class AppError(Exception):
    """业务错误：携带 code / message / http_status，由全局 handler 输出统一 envelope。"""

    def __init__(self, code: str, message: str = "", http_status: int | None = None) -> None:
        self.code = code
        self.message = message or DEFAULT_MESSAGES.get(code, "系统有点小问题，请稍后再试")
        self.http_status = http_status or CODE_HTTP.get(code, 500)
        super().__init__(self.message)


DEFAULT_MESSAGES: Dict[str, str] = {
    "PATIENT_RATE_LIMITED": "操作有点频繁啦，请休息一下再试",
    "VISIT_NUMBER_INVALID": "就诊号好像不对哦，请检查后重新输入",
    "PARAM_INVALID": "填的内容格式好像不对，请检查一下再试",
    "PAYLOAD_TOO_LARGE": "内容太大了，请重新录一次",
    "CONSULT_SESSION_NOT_FOUND": "问诊已经中断啦，请重新扫码开始问诊",
    "PHRASE_NOT_FOUND": "内容不见了，请返回重新操作",
    "AUDIO_INVALID": "没有听清您刚才的录音，请再试一次",
    "AI_PROVIDER_ERROR": "网络有点慢，请稍等片刻再试一次",
    "AI_QUOTA_EXCEEDED": "系统有点忙啦，请稍后再试一次",
    "AUTH_REQUIRED": "请先登录",
    "AUTH_LOCKED": "错误次数太多，账号已临时锁定，请稍后再来",
    "AUTH_BAD_CREDENTIALS": "账号或密码错误",
    "RECORD_NOT_FOUND": "该记录不存在或已按保留策略清理",
    "INTERNAL_ERROR": "系统有点小问题，请稍后再试",
}
