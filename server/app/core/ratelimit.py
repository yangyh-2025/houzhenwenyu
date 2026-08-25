"""进程内滑动窗口限流器（单实例部署；多实例时换 Redis 后端，见 D-10）。"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict


class SlidingWindowRateLimiter:
    def __init__(self, max_events: int, window_seconds: float) -> None:
        self.max_events = max_events
        self.window = window_seconds
        self._events: Dict[str, Deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> bool:
        """允许返回 True 并记录事件；超限返回 False（不记录被拒事件）。"""
        now = time.time()
        dq = self._events[key]
        while dq and now - dq[0] > self.window:
            dq.popleft()
        if len(dq) >= self.max_events:
            return False
        dq.append(now)
        return True

    def _prune_key(self, key: str) -> None:
        dq = self._events.get(key)
        if dq is not None and not dq:
            self._events.pop(key, None)
