"""应用配置：全部通过环境变量/.env 注入（12-Factor），密钥不入库。"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Tuple

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- 运行环境 ----
    app_env: str = "dev"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: str = "INFO"

    # ---- 数据库 ----
    database_url: str = "sqlite:///./app.db"
    retention_days: int = 90  # 保留字段兼容注释：运行语义已改日清(cleanup_at)
    cleanup_at: str = "02:00"  # 每日2点清空全部问诊数据（挂号日重置）

    # ---- AI Provider ----
    ai_provider: str = "mock"
    ai_base_url: str = "https://api.xiaomimimo.com/v1"
    ai_api_key: str = ""
    ai_chat_model: str = "mimo-v2.5"
    ai_tts_model: str = "mimo-v2.5-tts"
    ai_tts_voice: str = "冰糖"
    ai_tts_format: str = "mp3"  # 带宽优化: mp3≈30KB/min vs wav≈256KB/min
    ai_timeout_seconds: float = 55.0  # 并发排队裕量(20人同刷+上游排队)
    ai_max_rounds: int = 30

    # ---- 安全与限流 ----
    secret_key: str = ""  # 预留字段（评审R20）：当前会话为不透明token，未使用
    doctor_username: str = "admin"
    doctor_password: str = ""
    session_ttl_minutes: int = 30
    login_max_fails: int = 5
    lockout_seconds: int = 600
    patient_rate_limit: str = "200/min"  # 医院共享出口IP20人同刷：每轮约2req/人×20≈120-180/min
    session_max_per_ip: int = 30   # 场景值：共享出口IP最多30人同时问诊
    session_max_total: int = 500

    # ---- 安全加固（额度盗刷防护，2026-08-24）----
    trust_proxy: bool = False       # 仅生产 Nginx 后置 True（信任 X-Real-IP）
    min_audio_rms: float = 0.004    # 有效语音能量下限（静音/噪声刷量拒绝）
    min_audio_seconds: float = 0.5  # 最短有效录音时长
    ai_daily_call_budget: int = 20000  # 进程级 24h 窗口 AI 调用硬预算（超限 503）
    ai_rpm_limit: int = 90          # 上游 RPM 客户端节流（< 官方 100）
    max_audio_bytes: int = 4_000_000

    @field_validator("cleanup_at")
    @classmethod
    def _check_cleanup_at(cls, v: str) -> str:
        parts = str(v).strip().split(":")
        if (len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit()
                and 0 <= int(parts[0]) <= 23 and 0 <= int(parts[1]) <= 59):
            return str(v).strip()
        raise ValueError("CLEANUP_AT needs valid HH:MM")

    def parsed_patient_rate_limit(self):
        """'10/min' -> (10, 60)；'100/s' -> (100, 1)。非法抛 ValueError。"""
        v = str(self.patient_rate_limit).strip().lower()
        if v.endswith("/min"):
            return int(v[:-4]), 60
        if v.endswith("/s"):
            return int(v[:-2]), 1
        raise ValueError(
            "PATIENT_RATE_LIMIT bad: " + repr(self.patient_rate_limit))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
