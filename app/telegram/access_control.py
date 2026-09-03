from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable, Iterable


class AccessDenied(PermissionError):
    pass


class WhitelistAccessController:
    def __init__(self, allowed_chat_ids: Iterable[int], *, public_access: bool = False) -> None:
        self.allowed_chat_ids = frozenset(allowed_chat_ids)
        self.public_access = public_access

    def check(self, chat_id: int) -> None:
        if not self.public_access and chat_id not in self.allowed_chat_ids:
            raise AccessDenied("chat_id is not allowlisted")


class RateLimiter:
    def __init__(
        self,
        limit: int,
        *,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self.clock = clock
        self._events: dict[int, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, chat_id: int) -> bool:
        now = self.clock()
        with self._lock:
            events = self._events.setdefault(chat_id, deque())
            while events and now - events[0] >= self.window_seconds:
                events.popleft()
            if len(events) >= self.limit:
                return False
            events.append(now)
            return True

    def require(self, chat_id: int) -> None:
        if not self.allow(chat_id):
            raise AccessDenied("rate limit exceeded")
