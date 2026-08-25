from app.core.security import (hash_password, verify_password,
                               SessionStore, LoginLockout)


def test_password_roundtrip():
    h = hash_password("s3cret!")
    assert verify_password("s3cret!", h) is True
    assert verify_password("wrong", h) is False


def test_password_tamper():
    h = hash_password("abc")
    assert verify_password("abc", h + "0") is False
    bad = h.replace("$", "!")[:20]
    assert verify_password("abc", "garbage") is False


def test_session_store_flow():
    s = SessionStore(ttl_minutes=30)
    tok = s.create("admin")
    assert s.validate_and_refresh(tok) == "admin"
    assert s.validate_and_refresh(tok) == "admin"
    s.revoke(tok)
    assert s.validate_and_refresh(tok) is None


def test_lockout_after_max_fails():
    lk = LoginLockout(max_fails=5, lockout_seconds=600)
    for _ in range(5):
        lk.register_failure("admin")
    assert lk.check("admin") is False
    lk.reset("lockme")
    lk.register_failure("other")
    assert lk.check("other") is True
