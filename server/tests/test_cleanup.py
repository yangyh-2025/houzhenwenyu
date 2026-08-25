"""保留期清理测试。"""
import time

from app.db import get_session_factory
from app.models import Consultation
from app.services.cleanup import CleanupWorker


def _seed_old_and_new():
    now = int(time.time())
    with get_session_factory()() as db:
        db.add(Consultation(visit_number="1",
                            submitted_at=now - 200 * 86400,
                            rounds=3, summary_text="old"))
        db.add(Consultation(visit_number="2", submitted_at=now,
                            rounds=3, summary_text="new"))
        db.commit()


def test_run_once_deletes_only_expired(client):
    class FakeSettings:
        retention_days = 90
        cleanup_at = "03:00"

    worker = CleanupWorker(FakeSettings())
    _seed_old_and_new()
    deleted = worker.run_once()
    assert deleted == 1
    with get_session_factory()() as db:
        remaining = list(db.query(Consultation))
        assert len(remaining) == 1
        assert remaining[0].summary_text == "new"
