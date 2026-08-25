"""患者端 REST 路由。"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.errors import AppError

router = APIRouter(prefix="/api/patient")

import base64 as _b64
import json as _json

from fastapi import Response as _Response


def wants_binary_audio(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "audio/" in accept


def audio_response(audio_b64: str, meta: dict) -> _Response:
    """元数据走响应头，音频作原始 body——免 base64 膨胀 33%（带宽优化）。"""
    raw = _b64.b64decode(audio_b64)
    mt = "audio/wav" if raw[:4] == b"RIFF" else "audio/mpeg"
    return _Response(
        content=raw, media_type=mt,
        headers={"X-Hwy-Meta": _json.dumps(meta, ensure_ascii=True)},
    )





def _svc(request: Request):
    return request.app.state.service


def _limit(request: Request) -> None:
    """安全加固：双窗口（分钟+小时）+ 真实客户端 IP。"""
    from app.core.middleware import get_client_ip
    ip = get_client_ip(request, request.app)
    if not request.app.state.patient_limiter.allow(ip):
        raise AppError("PATIENT_RATE_LIMITED")
    if not request.app.state.patient_limiter_hour.allow(ip):
        raise AppError("PATIENT_RATE_LIMITED")


def check_content_length(request: Request, max_bytes: int) -> None:
    """ADD-1：大请求体闸门（业务校验前先拒绝超大 body）。"""
    cl = request.headers.get("content-length")
    if not cl or not cl.isdigit():
        # 缺失/非法 Content-Length（如 chunked 编码）一律拒绝（评审 R6）
        raise AppError("PAYLOAD_TOO_LARGE")
    if int(cl) > int(max_bytes * 1.4) + 1024:
        raise AppError("PAYLOAD_TOO_LARGE")


class CreateConsultIn(BaseModel):
    visit_number: str


class SubmitRoundIn(BaseModel):
    audio_b64: str = ""
    duration_ms: Optional[int] = None
    force_finish: bool = False
    round_id: Optional[str] = None


class FixedPhraseIn(BaseModel):
    phrase_key: str


@router.post("/consultations")
async def create_consultation(body: CreateConsultIn, request: Request):
    _limit(request)
    svc = _svc(request)
    from app.core.middleware import get_client_ip
    ip = get_client_ip(request, request.app)
    data = await svc.create_session(body.visit_number, ip)
    if wants_binary_audio(request):
        meta = {"session_id": data["session_id"],
                "rounds_limit": data["rounds_limit"],
                "text": data["first_round"]["text"],
                "resumed": bool(data["first_round"].get("resumed"))}
        return audio_response(data["first_round"].get("audio_b64") or "", meta)
    return data


@router.post("/consultations/{sid}/rounds")
async def submit_round(sid: str, body: SubmitRoundIn,
                       request: Request,
                       settings=Depends(get_settings)):
    _limit(request)
    check_content_length(request, settings.max_audio_bytes)
    svc = _svc(request)
    data = await svc.submit_round(
        sid, body.audio_b64 or None, force_finish=body.force_finish,
        round_id=body.round_id)
    if wants_binary_audio(request):
        meta = {k: v for k, v in data.items() if k != "audio_b64"}
        meta.setdefault("stage", None)
        return audio_response(data["audio_b64"], meta)
    return data


@router.post("/consultations/{sid}/ask")
async def ask_first(sid: str, request: Request):
    """协议 v2.1：开场介绍后 AI 主动发出第一问（【明白了】触发）。"""
    _limit(request)
    data = await _svc(request).ask_first(sid)
    if wants_binary_audio(request):
        return audio_response(data["audio_b64"],
                              {"text": data["text"], "stage": 1})
    return data


@router.post("/consultations/{sid}/fixed-phrase-audio")
async def fixed_phrase_audio(sid: str, body: FixedPhraseIn,
                             request: Request):
    _limit(request)
    data = await _svc(request).fixed_phrase_audio(sid, body.phrase_key)
    if wants_binary_audio(request):
        return audio_response(data["audio_b64"], {})
    return data
