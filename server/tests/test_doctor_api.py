"""医生端 API 集成测试（PRD F6/F7/F8 验收）。"""
import time
from datetime import datetime, timedelta

from app.db import get_session_factory
from app.models import Consultation


def _CST():
    from datetime import timezone, timedelta as td
    return timezone(td(hours=8))


def _seed(n=25, day_offset=0):
    with get_session_factory()() as db:
        for i in range(n):
            db.add(Consultation(
                visit_number=str(100 + i),
                submitted_at=int(time.time()) - day_offset * 86400 + i,
                rounds=5,
                summary_text="【主诉】测试摘要内容" * 3,
            ))
        db.commit()


def test_login_success_sets_cookie(client):
    r = client.post("/api/doctor/login",
                    json={"username": "admin", "password": "test123"})
    assert r.status_code == 200
    assert "hwy_session" in client.cookies


def test_login_wrong_password(client):
    r = client.post("/api/doctor/login",
                    json={"username": "admin", "password": "nope"})
    assert r.status_code == 401
    assert r.json()["code"] == "AUTH_BAD_CREDENTIALS"


def test_login_lockout(client):
    c = client
    for i in range(5):
        r = c.post("/api/doctor/login",
                   json={"username": "locked", "password": "x"})
        assert r.status_code == 401
    r = c.post("/api/doctor/login",
               json={"username": "locked", "password": "test123"})
    assert r.status_code == 423
    assert r.json()["code"] == "AUTH_LOCKED"


def test_me_and_list_require_auth(client):
    assert client.get("/api/doctor/me").status_code == 401
    assert client.get(
        "/api/doctor/consultations").status_code == 401


def test_list_pagination_and_order(authed):
    _seed(n=25)
    r = authed.get("/api/doctor/consultations?page=1&page_size=20")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 25
    assert len(body["items"]) == 20
    ts = [it["submitted_at"] for it in body["items"]]
    assert ts == sorted(ts, reverse=True)
    item = body["items"][0]
    for k in ["id", "visit_number", "submitted_at", "rounds",
              "summary_preview"]:
        assert k in item
    # 第二页
    r2 = authed.get("/api/doctor/consultations?page=2&page_size=20")
    assert len(r2.json()["items"]) == 5


def test_list_date_filter_cst_boundary(authed):
    _seed(n=3, day_offset=0)
    _seed(n=3, day_offset=2)  # 两天前
    today = datetime.now(tz=_CST()).strftime("%Y-%m-%d")
    old = (datetime.now(tz=_CST()) - timedelta(days=2)).strftime(
        "%Y-%m-%d")
    r_today = authed.get(
        f"/api/doctor/consultations?date_from={today}&date_to={today}")
    r_old = authed.get(
        f"/api/doctor/consultations?date_from={old}&date_to={old}")
    assert r_today.json()["total"] == 3
    assert r_old.json()["total"] == 3


def test_list_q_prefix_filter(authed):
    _seed(n=5)
    r = authed.get("/api/doctor/consultations?q=101")
    items = r.json()["items"]
    assert all(it["visit_number"].startswith("101") for it in items)
    assert any(it["visit_number"] == "101" for it in items)


def test_detail_and_disclaimer(authed):
    _seed(n=1)
    rid = authed.get("/api/doctor/consultations").json()["items"][0]["id"]
    r = authed.get(f"/api/doctor/consultations/{rid}")
    body = r.json()
    assert "【主诉】" in body["summary_text"]
    assert "仅供面诊参考" in body["disclaimer"]
    r404 = authed.get("/api/doctor/consultations/99999")
    assert r404.status_code == 404
    assert r404.json()["code"] == "RECORD_NOT_FOUND"


def test_logout_revokes_session(client):
    client.post("/api/doctor/login",
                json={"username": "admin", "password": "test123"})
    assert client.get("/api/doctor/me").status_code == 200
    client.post("/api/doctor/logout")
    assert client.get("/api/doctor/me").status_code == 401
