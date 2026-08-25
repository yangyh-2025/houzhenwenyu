"""问诊全链路集成测试（PRD F2/F3/F4 核心验收）。"""
import base64
import os

from app.core.wav_utils import build_test_wav


def _audio():
    return base64.b64encode(build_test_wav(1.0)).decode()


def _create(client):
    r = client.post("/api/patient/consultations",
                    json={"visit_number": "35"})
    assert r.status_code == 200, r.text
    return r.json()


def test_happy_path_full_flow(client):
    data = _create(client)
    sid = data["session_id"]
    assert data["rounds_limit"] == 30
    assert "您好" in data["first_round"]["text"]

    body = None
    for i in range(12):
        r = client.post(
            f"/api/patient/consultations/{sid}/rounds",
            json={"audio_b64": _audio()})
        assert r.status_code == 200, r.text
        body = r.json()
        if body.get("finished"):
            assert body["text"]
            break
        assert body["text"], "每轮应有问题文本"
        assert body["audio_b64"]
    assert body and body["finished"] is True
    assert "record_id" in body

    # 入库四字段 + 九栏目
    from app.db import get_session_factory
    with get_session_factory()() as db:
        from app.models import Consultation
        recs = list(db.query(Consultation))
        assert len(recs) == 1
        rec = recs[0]
        assert rec.visit_number == "35"
        assert rec.rounds == 11
        for lb in ["主诉", "病程", "刻下主要症状", "饮食", "睡眠",
                   "二便", "既往病史", "当前用药"]:
            assert lb in rec.summary_text



def test_rounds_cap_force_finish():
    os.environ["AI_MAX_ROUNDS"] = "3"
    try:
        from app.core.config import reset_settings_cache
        reset_settings_cache()
        import tempfile
        from pathlib import Path
        from fastapi.testclient import TestClient
        d = tempfile.mkdtemp(prefix="hwy_cap_")
        from app.db import init_engine
        init_engine("sqlite:///" + Path(d).as_posix() + "/cap.db")
        from app.main import create_app
        app = create_app()
        with TestClient(app) as tc:
            r = tc.post("/api/patient/consultations",
                        json={"visit_number": "9"})
            assert r.status_code == 200, r.text
            sid = r.json()["session_id"]
            last_body = None
            for i in range(3):
                rr = tc.post(
                    f"/api/patient/consultations/{sid}/rounds",
                    json={"audio_b64": _audio()})
                assert rr.status_code == 200, rr.text
                last_body = rr.json()
            assert last_body["finished"] is True
    finally:
        os.environ.pop("AI_MAX_ROUNDS", None)


def test_failed_round_not_counted(client):
    data = _create(client)
    sid = data["session_id"]
    # 第一轮成功
    r1 = client.post(f"/api/patient/consultations/{sid}/rounds",
                     json={"audio_b64": _audio()})
    assert r1.status_code == 200
    # 强制 provider 失败一轮
    app_state = None

    def _boom(messages, audio_b64):
        raise RuntimeError("upstream down")

    class BoomProvider:
        understand = staticmethod(_boom)

        async def understand(self, messages, audio_b64):  # noqa
            raise AppErrorShim("AI_PROVIDER_ERROR")

    from app.core.errors import AppError
    orig = client.app.state.service.provider.understand

    async def failing(messages, audio_b64):
        raise AppError("AI_PROVIDER_ERROR")
    client.app.state.service.provider.understand = failing
    try:
        rf = client.post(
            f"/api/patient/consultations/{sid}/rounds",
            json={"audio_b64": _audio()})
        assert rf.status_code == 502
        assert rf.json()["code"] == "AI_PROVIDER_ERROR"
    finally:
        client.app.state.service.provider.understand = orig
    # 恢复后继续脚本不乱序（失败轮不计入）
    r2 = client.post(f"/api/patient/consultations/{sid}/rounds",
                     json={"audio_b64": _audio()})
    body = r2.json()
    assert body["finished"] is False
    assert body["text"].startswith("开始不舒服之前")  # 新八类第2问=诱因



def test_invalid_wav_and_visit_number(client):
    for bad in ["", "abc", "1" * 13, "-5"]:
        r = client.post("/api/patient/consultations",
                        json={"visit_number": bad})
        assert r.status_code == 400
        assert r.json()["code"] == "VISIT_NUMBER_INVALID"
    data = _create(client)
    sid = data["session_id"]
    garbage = base64.b64encode(b"\x00" * 100).decode()
    r = client.post(f"/api/patient/consultations/{sid}/rounds",
                    json={"audio_b64": garbage})
    assert r.status_code == 400
    assert r.json()["code"] == "AUDIO_INVALID"


def test_expired_or_unknown_session(client):
    r = client.post(
        "/api/patient/consultations/does-not-exist/rounds",
        json={"audio_b64": _audio()})
    assert r.status_code == 404
    assert r.json()["code"] == "CONSULT_SESSION_NOT_FOUND"


def test_force_finish_persists_record(client):
    data = _create(client)
    sid = data["session_id"]
    r1 = client.post(f"/api/patient/consultations/{sid}/rounds",
                     json={"audio_b64": _audio()})
    assert r1.status_code == 200
    r2 = client.post(f"/api/patient/consultations/{sid}/rounds",
                     json={"force_finish": True})
    body = r2.json()
    assert body["finished"] is True
    assert "record_id" in body
    from app.db import get_session_factory
    from app.models import Consultation
    with get_session_factory()() as db:
        rec = db.get(Consultation, body["record_id"])
        assert rec is not None
        assert rec.rounds == 1


def test_fixed_phrase_audio(client):
    data = _create(client)
    sid = data["session_id"]
    r_ok = client.post(
        f"/api/patient/consultations/{sid}/fixed-phrase-audio",
        json={"phrase_key": "REMINDER_SILENT"})
    assert r_ok.status_code == 200
    assert r_ok.json()["audio_b64"]
    r_bad = client.post(
        f"/api/patient/consultations/{sid}/fixed-phrase-audio",
        json={"phrase_key": "HACKED"})
    assert r_bad.status_code == 404
    assert r_bad.json()["code"] == "PHRASE_NOT_FOUND"


def test_rate_limit_429(client, monkeypatch):
    from app.core.ratelimit import SlidingWindowRateLimiter
    monkeypatch.setattr(
        client.app.state, "patient_limiter",
        SlidingWindowRateLimiter(2, 60))
    ok = 0
    for i in range(3):
        r = client.post("/api/patient/consultations",
                        json={"visit_number": "7"})
        if r.status_code == 200:
            ok += 1
    assert r.status_code == 429 and ok == 2


def test_safety_hook_e2e(client):
    data = _create(client)
    sid = data["session_id"]
    # 第1问正常
    client.post(f"/api/patient/consultations/{sid}/rounds",
                json={"audio_b64": _audio()})
    # 第2轮发超短音频触发 mock 安全钩子（step==1）
    from app.core.wav_utils import build_test_wav
    short = base64.b64encode(build_test_wav(0.55)).decode()
    r = client.post(f"/api/patient/consultations/{sid}/rounds",
                    json={"audio_b64": short})
    assert r.status_code == 200
    text = r.json()["text"]
    assert "服用" not in text
    assert text.startswith("明白了")  # FALLBACK_QUESTION 前缀


def test_restart_loss_guidance(client):
    data = _create(client)
    sid = data["session_id"]
    # 模拟重启：重建 app（新内存 store）
    import tempfile
    from pathlib import Path
    from fastapi.testclient import TestClient
    d = tempfile.mkdtemp(prefix="hwy_rs_")
    from app.db import init_engine
    init_engine("sqlite:///" + Path(d).as_posix() + "/rs.db")
    from app.main import create_app
    app2 = create_app()
    with TestClient(app2) as tc:
        r = tc.post(
            f"/api/patient/consultations/{sid}/rounds",
            json={"audio_b64": _audio()})
        assert r.status_code == 404
        assert r.json()["code"] == "CONSULT_SESSION_NOT_FOUND"


def test_model_led_finish_transition(client):
    """语义强化：结束轮带模型过渡收尾语并被播报；摘要九栏目仍完整。"""
    data = _create(client)
    sid = data["session_id"]
    last = None
    for i in range(13):
        r = client.post(f"/api/patient/consultations/{sid}/rounds",
                        json={"audio_b64": _audio()})
        assert r.status_code == 200, r.text
        last = r.json()
        if last.get("finished"):
            break
    assert last["finished"] is True
    assert "了解得差不多了" in last["text"]  # 模型主动收尾的过渡语成为播报文本
    assert last["audio_b64"]  # 合成音频随行
    from app.db import get_session_factory
    from app.models import Consultation
    with get_session_factory()() as db:
        recs = list(db.query(Consultation))
        assert len(recs) == 1
        for lb in ["主诉", "病程", "刻下主要症状", "饮食", "睡眠",
                   "二便", "既往病史", "当前用药"]:
            assert lb in recs[0].summary_text
