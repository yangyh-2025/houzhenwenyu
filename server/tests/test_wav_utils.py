import struct

import pytest

from app.core.errors import AppError
from app.core.wav_utils import (build_test_wav, build_silence_wav,
                                parse_wav, validate_wav_16k_mono)


def _wrap(pcm, sr, ch=1):
    hdr = b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt "
    hdr += struct.pack("<IHHIIHH", 16, 1, ch, sr, sr * ch * 2, ch * 2, 16)
    hdr += b"data" + struct.pack("<I", len(pcm))
    return hdr + pcm


def test_valid_16k_mono_passes():
    data = build_test_wav(seconds=0.5)
    validate_wav_16k_mono(data, max_bytes=10**7)


def test_wrong_rate_rejected():
    pcm = b"\x00\x00" * 8000
    with pytest.raises(AppError) as ei:
        validate_wav_16k_mono(_wrap(pcm, sr=8000), max_bytes=10**7)
    assert ei.value.code == "AUDIO_INVALID"


def test_stereo_rejected():
    pcm = b"\x00\x00" * 16000
    with pytest.raises(AppError):
        validate_wav_16k_mono(_wrap(pcm, sr=16000, ch=2), max_bytes=10**7)


def test_garbage_rejected():
    with pytest.raises(AppError):
        validate_wav_16k_mono(b"\x00" * 100, max_bytes=10**7)


def test_empty_rejected():
    with pytest.raises(AppError):
        validate_wav_16k_mono(b"", max_bytes=10**7)


def test_oversize_rejected():
    data = build_test_wav(seconds=1.0)
    with pytest.raises(AppError):
        validate_wav_16k_mono(data, max_bytes=10)
