"""密码哈希、医生端会话与登录锁定。"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Dict, Optional

_ITERATIONS = 600_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return "pbkdf2_sha256$600000$%s$%s" % (salt.hex(), dk.hex())


def verify_password(password: str, stored: str) -> bool:
    """恒时比较校验。stored 格式：pbkdf2_sha256$600000$salt_hex$hash_hex"""
    try:
        algo, iters, salt_hex, hash_hex = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(iters)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except (ValueError, TypeError):
        return False


class SessionStore:
    """医生端服务端会话（内存），滑动续期。"""

    def __init__(self, ttl_minutes: int = 30) -> None:
        self._ttl = ttl_minutes * 60
        self._store: Dict[str, dict] = {}

    def create(self, username: str) -> str:
        token = secrets.token_urlsafe(32)
        self._store[token] = {
            "username": username,
            "expires_at": time.time() + self._ttl,
        }
        return token

    def validate_and_refresh(self, token: Optional[str]) -> Optional[str]:
        if not token:
            return None
        rec = self._store.get(token)
        if not rec:
            return None
        if time.time() >= rec["expires_at"]:
            del self._store[token]
            return None
        rec["expires_at"] = time.time() + self._ttl
        return rec["username"]

    def revoke(self, token: Optional[str]) -> None:
        if token:
            self._store.pop(token, None)


class LoginLockout:
    """登录失败锁定：连续 max_fails 次失败后锁 lockout_seconds 秒。"""

    def __init__(self, max_fails: int = 5, lockout_seconds: int = 600) -> None:
        self._max = max_fails
        self._lock_s = lockout_seconds
        self._fails: Dict[str, list] = {}

    def check(self, key: str) -> bool:
        """True=允许尝试；False=锁定中。"""
        rec = self._fails.get(key)
        if not rec:
            return True
        fails, locked_until = rec
        if locked_until and time.time() < locked_until:
            return False
        if locked_until and time.time() >= locked_until:
            self._fails.pop(key, None)
        return True

    def register_failure(self, key: str) -> None:
        rec = self._fails.setdefault(key, [0, 0.0])
        rec[0] += 1
        if rec[0] >= self._max:
            rec[1] = time.time() + self._lock_s

    def reset(self, key: str) -> None:
        self._fails.pop(key, None)


_DUMMY_HASH = hash_password("timing-alignment-dummy")


def dummy_verify() -> None:
    """恒时防御（评审 R11）：账号不存在时也执行一次等价计算。"""
    verify_password("not-the-password", _DUMMY_HASH)
