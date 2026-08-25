import time

from app.core.ratelimit import SlidingWindowRateLimiter


def test_allow_within_limit_then_block():
    rl = SlidingWindowRateLimiter(3, 60)
    assert all(rl.allow("ip1") for _ in range(3))
    assert rl.allow("ip1") is False


def test_window_slide():
    rl = SlidingWindowRateLimiter(1, 0.2)
    assert rl.allow("ip9") is True
    time.sleep(0.25)
    assert rl.allow("ip9") is True


def test_rejected_events_not_counted_against_future():
    rl = SlidingWindowRateLimiter(2, 60)
    rl.allow("k")
    rl.allow("k")
    assert rl.allow("k") is False
    # 被拒事件不入窗
    assert len(rl._events["k"]) == 2
