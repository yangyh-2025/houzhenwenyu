"""ORM 模型（SQLAlchemy 2.0 声明式）。

持久化白名单：consultations 仅含 PRD F9 四字段；doctor_users 为运维账号表。
"""
from __future__ import annotations

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Consultation(Base):
    __tablename__ = "consultations"
    # 2026-08-24：SQLite AUTOINCREMENT 防 ID 复用（一号一条 upsert 场景下
    # 避免新记录复用已删除记录 ID 导致医生侧历史串行）
    __table_args__ = {"sqlite_autoincrement": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    visit_number: Mapped[str] = mapped_column(String(12), index=True)
    submitted_at: Mapped[int] = mapped_column(Integer)  # UTC epoch 秒
    rounds: Mapped[int] = mapped_column(Integer)
    summary_text: Mapped[str] = mapped_column(Text)


class DoctorUser(Base):
    __tablename__ = "doctor_users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(256))
    created_at: Mapped[int] = mapped_column(Integer)
