"""WAV 解析校验与测试辅助。

前端约定上传 16kHz 单声道 16bit PCM WAV（PRD F9/D-04），服务端只做头校验，
不解析音频内容、不落盘。
"""
from __future__ import annotations

import struct
from typing import Dict

from app.core.errors import AppError


def parse_wav(data: bytes) -> dict:
    """用标准库 wave 模块解析，返回格式信息；非法抛 AUDIO_INVALID。"""
    import io as _io
    import wave as _wave
    try:
        w = _wave.open(_io.BytesIO(data), "rb")
    except (_wave.Error, EOFError):
        raise AppError("AUDIO_INVALID", "not a valid wav")
    try:
        return {
            "channels": w.getnchannels(),
            "bits": w.getsampwidth() * 8,
            "sample_rate": w.getframerate(),
            "frames": w.getnframes(),
        }
    finally:
        w.close()


def validate_wav_16k_mono(data: bytes, max_bytes: int) -> None:
    """16kHz 单声道 16bit 校验；违规抛 AUDIO_INVALID。"""
    if not data or len(data) > max_bytes:
        raise AppError("AUDIO_INVALID", "bad length")
    info = parse_wav(data)
    if (info["channels"] != 1 or info["bits"] != 16
            or info["sample_rate"] != 16000):
        raise AppError("AUDIO_INVALID", "bad format")
    if info["frames"] <= 0:
        raise AppError("AUDIO_INVALID", "empty audio")


def build_test_wav(seconds: float = 1.0, freq: int = 440,
                   sample_rate: int = 16000) -> bytes:
    """生成合法 16k 单声道 16bit 正弦 WAV（测试/演示用）。"""
    import math
    n = int(sample_rate * seconds)
    pcm = bytearray()
    for i in range(n):
        v = int(20000 * math.sin(2 * math.pi * freq * i / sample_rate))
        pcm += struct.pack("<h", v)
    return _wrap_wav(bytes(pcm), sample_rate)


def build_silence_wav(seconds: float = 1.0, sample_rate: int = 16000) -> bytes:
    n = int(sample_rate * seconds)
    return _wrap_wav(b"\x00\x00" * n, sample_rate)


def _wrap_wav(pcm: bytes, sample_rate: int) -> bytes:
    hdr = b"RIFF"
    hdr += struct.pack("<I", 36 + len(pcm))
    hdr += b"WAVEfmt "
    hdr += struct.pack("<IHHIIHH", 16, 1, 1, sample_rate,
                       sample_rate * 2, 2, 16)
    hdr += b"data"
    hdr += struct.pack("<I", len(pcm))
    return hdr + pcm


def pcm_rms(data: bytes) -> float:
    """16bit 单声道 PCM 的归一化 RMS（0~1）。用数组计算，无额外依赖。"""
    import array
    if not data or len(data) < 2:
        return 0.0
    n = len(data) // 2
    a = array.array("h")
    a.frombytes(data[: n * 2])
    if not a:
        return 0.0
    s2 = sum( float(v) * v for v in a )
    return (s2 / len(a)) ** 0.5 / 32768.0


def validate_speech_energy(data: bytes, min_rms: float,
                           min_seconds: float) -> None:
    """静音/极短音频拒绝（安全加固：抬高脚本刷量成本）。"""
    import io as _io
    import wave as _wave
    try:
        w = _wave.open(_io.BytesIO(data), "rb")
        sr = w.getframerate()
        total = w.getnframes()
        pcm = w.readframes(total)
        w.close()
    except Exception:
        raise AppError("AUDIO_INVALID", "没有听到声音，请再试一次")
    if total < int(sr * min_seconds):
        raise AppError("AUDIO_INVALID", "说的有点短，请再说一说")
    rms = pcm_rms(pcm)
    if rms < min_rms:
        raise AppError("AUDIO_INVALID", "没有听到声音，请再试一次")
