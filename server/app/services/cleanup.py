"""保留期清理线程：每日 CLEANUP_AT 本地时刻删除过期摘要记录。"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta

from sqlalchemy import delete

from app.models import Consultation

logger = logging.getLogger(__name__)


class CleanupWorker(threading.Thread):
    """每日定时清理：submitted_at 早于保留期的记录删除并留痕（只记条数）。"""

    def __init__(self, settings) -> None:
        super().__init__(daemon=True, name="cleanup-worker")
        self._settings = settings
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                wait = self._seconds_until_next_run()
                if self._stop_event.wait(timeout=wait):
                    break
                n = self.run_once()
                logger.info("保留期清理完成 deleted=%d", n)
            except Exception:
                # 配置异常/上游错误不得杀死线程（评审 R8）
                logger.exception("保留期清理循环异常，60秒后重试")
                self._stop_event.wait(timeout=60)

    def _seconds_until_next_run(self) -> float:
        hh, mm = self._settings.cleanup_at.split(":")
        now = datetime.now()
        target = now.replace(hour=int(hh), minute=int(mm), second=0,
                             microsecond=0)
        if target <= now:
            target += timedelta(days=1)
        return max((target - now).total_seconds(), 1)

    def run_once(self, now=None) -> int:
        """日清模式（2026-08-24）：每日 2 点清空前一天及以前全部记录，
        保证"挂号每天重置，一号对应当日一人"。"""
        import datetime as _dt
        d = _dt.datetime.now()
        day_start = d.replace(hour=0, minute=0, second=0, microsecond=0)
        cutoff = int(day_start.timestamp())
        from app.db import get_session_factory
        with get_session_factory()() as db:
            res = db.execute(
                delete(Consultation).where(
                    Consultation.submitted_at < cutoff))
            db.commit()
            return res.rowcount or 0
