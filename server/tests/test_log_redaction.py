"""日志脱敏回归测试（ADD-4）：全流程日志不得含敏感内容。"""
import base64
import logging

from app.core.wav_utils import build_test_wav


def test_no_sensitive_data_in_logs(client, caplog):
    import os
    os.environ["DOCTOR_PASSWORD"] = "test123"
    r = client.post("/api/patient/consultations",
                    json={"visit_number": "12345678"})
    assert r.status_code == 200
    sid = r.json()["session_id"]
    audio = base64.b64encode(build_test_wav(0.8)).decode()
    for i in range(9):
        rr = client.post(f"/api/patient/consultations/{sid}/rounds",
                         json={"audio_b64": audio})
        assert rr.status_code == 200
    client.post("/api/doctor/login",
                json={"username": "admin", "password": "test123"})
    client.get("/api/doctor/consultations")

    blob = "\n".join(rec.getMessage() + "|" +
                     (rec.exc_text or "")
                     for rec in caplog.records)
    # 音频 base64 片段（WAV 头特征）绝不可出现在日志
    assert "UklGRg" not in blob          # RIFF base64 前缀
    assert "data:audio/wav" not in blob
    # 就诊号全文不可出现（掩码除外）
    assert "12345678" not in blob
    # 密码明文不可出现
    # 登录请求体从不入日志（FastAPI/uvicorn 默认不记 body）
    assert blob.count("test123") == 0
