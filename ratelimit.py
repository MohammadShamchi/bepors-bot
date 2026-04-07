"""
Rate limiting, burst throttling, global daily cap, and anti-spam soft-block.
Per PRD §5.6.

Design:
- Daily counter is persisted in SQLite (via db.py) so restarts don't lose state.
- Burst window and anti-spam window are in-memory (restart acceptable).
- Global daily cap is persisted in SQLite.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Deque

from db import Database


@dataclass
class LimitConfig:
    daily_limit: int = 20
    burst_limit: int = 5         # messages per burst_window_sec
    burst_window_sec: int = 60
    global_limit: int = 10_000   # total questions/day across all users
    spam_threshold: int = 30     # messages in spam_window_sec → soft-block
    spam_window_sec: int = 300   # 5 minutes
    spam_block_sec: int = 3600   # 1 hour


class RateLimiter:
    def __init__(self, db: Database, config: LimitConfig):
        self.db = db
        self.cfg = config
        # in-memory sliding windows: deques of timestamps keyed by user_id
        self._burst: dict[int, Deque[float]] = defaultdict(deque)
        self._spam: dict[int, Deque[float]] = defaultdict(deque)

    # ---- helpers ------------------------------------------------------------

    def _prune(self, dq: Deque[float], window: int) -> None:
        cutoff = time.monotonic() - window
        while dq and dq[0] < cutoff:
            dq.popleft()

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def update_config(self, **fields) -> None:
        for k, v in fields.items():
            if hasattr(self.cfg, k):
                setattr(self.cfg, k, v)

    # ---- checks -------------------------------------------------------------

    def check_burst(self, user_id: int) -> tuple[bool, int]:
        """
        Returns (allowed, wait_seconds). When throttled, wait_seconds is the
        time until the oldest message in the window expires (≥1).
        When allowed, wait_seconds is 0.
        """
        dq = self._burst[user_id]
        self._prune(dq, self.cfg.burst_window_sec)
        if len(dq) >= self.cfg.burst_limit:
            wait = int(self.cfg.burst_window_sec - (time.monotonic() - dq[0])) + 1
            return False, max(1, wait)
        dq.append(time.monotonic())
        return True, 0

    def check_spam(self, user_id: int) -> tuple[bool, bool]:
        """
        Track sustained spam. Returns (allowed, newly_blocked).
        If the user crosses spam_threshold within spam_window_sec, they're marked
        as newly_blocked — caller is responsible for persisting spam_until.
        """
        dq = self._spam[user_id]
        self._prune(dq, self.cfg.spam_window_sec)
        dq.append(time.monotonic())
        if len(dq) > self.cfg.spam_threshold:
            dq.clear()
            return False, True
        return True, False

    async def check_and_consume_daily(self, user_id: int) -> tuple[bool, int]:
        """
        Atomically check the user's daily quota and consume one if available.
        Returns (allowed, remaining_after_consume).
        """
        day = self._today()
        current = await self.db.get_usage(user_id, day)
        if current >= self.cfg.daily_limit:
            return False, 0
        new = await self.db.incr_usage(user_id, day)
        remaining = max(0, self.cfg.daily_limit - new)
        return True, remaining

    async def check_and_consume_global(self) -> bool:
        """Global daily cap — return False if the cap is exhausted."""
        day = self._today()
        current = await self.db.get_global_usage(day)
        if current >= self.cfg.global_limit:
            return False
        await self.db.incr_global_usage(day)
        return True

    async def get_daily(self, user_id: int) -> tuple[int, int]:
        """Returns (used_today, remaining)."""
        day = self._today()
        used = await self.db.get_usage(user_id, day)
        return used, max(0, self.cfg.daily_limit - used)

    async def get_global(self) -> tuple[int, int]:
        day = self._today()
        used = await self.db.get_global_usage(day)
        return used, self.cfg.global_limit


def spam_until_iso(seconds_from_now: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds_from_now)).isoformat(
        timespec="seconds"
    )


def is_spam_block_active(spam_until: str | None) -> bool:
    if not spam_until:
        return False
    try:
        until = datetime.fromisoformat(spam_until)
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < until
    except (ValueError, TypeError):
        return False
