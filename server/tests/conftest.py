"""pytest fixtures: per-test sqlite + mock provider + fresh app."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

# 复用 wav_utils 的测试 WAV 构建器，避免重复实现
from app.core.wav_utils import (  # noqa: E402
    build_test_wav,
    build_silence_wav,
)


@pytest.fixture()
def client():
    from app.core.config import reset_settings_cache
    reset_settings_cache()
    d = tempfile.mkdtemp(prefix="hwy_test_")
    os.environ["DATABASE_URL"] = "sqlite:///" + Path(d).as_posix() + "/t.db"
    os.environ["AI_PROVIDER"] = "mock"
    os.environ["DOCTOR_USERNAME"] = "admin"
    os.environ["DOCTOR_PASSWORD"] = "test123"
    os.environ["APP_ENV"] = "test"
    os.environ["SECRET_KEY"] = "test-secret"
    from app.core.config import get_settings, reset_settings_cache
    reset_settings_cache()
    from app.db import init_engine
    init_engine(os.environ["DATABASE_URL"])
    from app.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def authed(client):
    resp = client.post("/api/doctor/login",
                       json={"username": "admin",
                             "password": "test123"})
    assert resp.status_code == 200, resp.text
    return client
