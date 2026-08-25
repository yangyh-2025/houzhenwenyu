"""医生端 REST 路由（登录/列表/详情）。"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from app.core.config import get_settings
from app.core.errors import AppError
from app.core.security import dummy_verify, verify_password
from app.models import Consultation, DoctorUser

router = APIRouter(prefix="/api/doctor")

COOKIE_NAME = "hwy_session"
DISCLAIMER_TEXT = "本摘要由AI整理，仅供面诊参考，请以面诊核实为准。"

# 展示时区固定为中国标准时间 UTC+8（与服务器本地时区解耦）
CST = timezone(timedelta(hours=8))


def _store(request: Request):
    return request.app.state.doctor_sessions


def _lockout(request: Request):
    return request.app.state.login_lockout


def _limit_login(request: Request) -> None:
    """ADD-3：登录接口独立限流池。"""
    limiter = request.app.state.login_limiter
    ip = request.client.host if request.client else "unknown"
    if not limiter.allow(ip):
        raise AppError("TOO_MANY_REQUESTS",
                       "操作有点频繁啦，请休息一下再试")


def require_doctor(request: Request) -> str:
    token = request.cookies.get(COOKIE_NAME)
    username = _store(request).validate_and_refresh(token)
    if not username:
        raise AppError("AUTH_REQUIRED")
    return username


class LoginIn(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(body: LoginIn, request: Request,
                response: Response,
                settings=Depends(get_settings)):
    _limit_login(request)
    key = body.username.strip().lower()
    lockout = _lockout(request)
    if not lockout.check(key):
        raise AppError("AUTH_LOCKED")
    from app.db import get_session_factory
    with get_session_factory()() as db:
        user = db.scalar(
            select(DoctorUser).where(DoctorUser.username == key))
        ok = False
        if user is not None:
            ok = verify_password(body.password, user.password_hash)
        else:
            dummy_verify()  # 时序对齐（评审 R11）
        if not ok:
            lockout.register_failure(key)
            raise AppError("AUTH_BAD_CREDENTIALS")
        lockout.reset(key)
        token = _store(request).create(key)
    response.set_cookie(
        COOKIE_NAME, token,
        httponly=True, samesite="lax",
        secure=(settings.app_env == "prod"),
    )
    return {"username": key}


@router.post("/logout")
async def logout(request: Request, response: Response):
    token = request.cookies.get(COOKIE_NAME)
    _store(request).revoke(token)
    response.delete_cookie(COOKIE_NAME, httponly=True,
                           samesite="lax",
                           secure=(get_settings().app_env == "prod"))
    return {"ok": True}


@router.get("/me")
async def me(request: Request):
    return {"username": require_doctor(request)}


@router.get("/consultations")
async def list_consultations(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    q: Optional[str] = None,
):
    require_doctor(request)
    page = max(page, 1)
    page_size = min(max(page_size, 1), 50)
    stmt = select(Consultation)
    if date_from:
        d0 = _parse_date(date_from)
        start = int(datetime(d0.year, d0.month, d0.day,
                             tzinfo=CST).timestamp())
        stmt = stmt.where(Consultation.submitted_at >= start)
    if date_to:
        d1 = _parse_date(date_to)
        end = int(datetime(d1.year, d1.month, d1.day,
                           tzinfo=CST).timestamp()) + 86399
        stmt = stmt.where(Consultation.submitted_at <= end)
    if q:
        like = q.replace("%", "").replace("_", "") + "%"
        stmt = stmt.where(Consultation.visit_number.like(
            like, escape="\\"))
    total = db_count(stmt)
    items = db_list(stmt, (page - 1) * page_size, page_size)
    return {
        "items": [row_to_item(r) for r in items],
        "total": total,
        "page": page,
        "list_meta": {"page_size": page_size},
    }


def _db():
    from app.db import get_session_factory
    return get_session_factory()()


def db_count(stmt) -> int:
    with _db() as db:
        return db.scalar(
            select(func.count()).select_from(stmt.subquery())) or 0


def db_list(stmt, offset: int, limit: int):
    ordered = stmt.order_by(Consultation.submitted_at.desc(),
                            Consultation.id.desc())
    with _db() as db:
        return list(db.scalars(ordered.offset(offset).limit(limit)))


def _parse_date(v: str) -> date:
    try:
        return date.fromisoformat(str(v))
    except ValueError:
        raise AppError("PARAM_INVALID",
                       "日期格式不对，请用 YYYY-MM-DD")


def row_to_item(r: Consultation) -> dict:
    return {
        "id": r.id,
        "visit_number": r.visit_number,
        "submitted_at": r.submitted_at,
        "rounds": r.rounds,
        "summary_preview": (r.summary_text or "")[:50],
    }


@router.get("/consultations/{record_id}")
async def get_consultation(record_id: int, request: Request):
    require_doctor(request)
    with _db() as db:
        rec = db.get(Consultation, record_id)
        if rec is None:
            raise AppError("RECORD_NOT_FOUND")
        return {
            "id": rec.id,
            "visit_number": rec.visit_number,
            "submitted_at": rec.submitted_at,
            "rounds": rec.rounds,
            "summary_text": rec.summary_text,
            "disclaimer": DISCLAIMER_TEXT,
        }
