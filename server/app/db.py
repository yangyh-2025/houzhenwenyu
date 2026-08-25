"""数据库引擎与会话管理。"""
from __future__ import annotations

import logging
import time
from typing import Iterator

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.security import hash_password
from app.models import Base, DoctorUser

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_SessionLocal = None


def init_engine(database_url: str) -> None:
    """幂等：同 URL 复用，不同则重建。"""
    global _engine, _SessionLocal
    if _engine is not None and str(_engine.url) == database_url:
        return
    if _engine is not None:
        _engine.dispose()
    _engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False}
        if database_url.startswith("sqlite") else {},
    )
    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def get_engine() -> Engine:
    if _engine is None:
        raise RuntimeError("数据库引擎未初始化")
    return _engine


def get_session() -> Iterator[Session]:
    """FastAPI Depends 用。"""
    if _SessionLocal is None:
        raise RuntimeError("数据库引擎未初始化")
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db(engine: Engine, settings: Settings) -> None:
    """建表 + WAL pragma + 首次启动引导管理员。"""
    from sqlalchemy import event

    if engine.url.get_backend_name() == "sqlite":
        @event.listens_for(engine, "connect")
        def _set_sqlite_pragma(dbapi_conn, _):
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    Base.metadata.create_all(engine)

    with Session(engine) as session:
        exists = session.scalar(select(DoctorUser).limit(1))
        if exists is None:
            if settings.doctor_password:
                user = DoctorUser(
                    username=settings.doctor_username,
                    password_hash=hash_password(settings.doctor_password),
                    created_at=int(time.time()),
                )
                session.add(user)
                session.commit()
                logger.warning(
                    "已创建初始管理员账号(%s)，生产环境请尽快修改密码",
                    mask_user(settings.doctor_username),
                )
            else:
                logger.warning("DOCTOR_PASSWORD 未配置，跳过管理员创建")


def mask_user(username: str) -> str:
    return username[:2] + "***" if len(username) > 2 else "***"


def get_session_factory():
    """供非请求上下文（服务层）使用。"""
    if _SessionLocal is None:
        raise RuntimeError("数据库引擎未初始化")
    return _SessionLocal
