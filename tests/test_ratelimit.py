"""Tests for ratelimit module (the in-memory parts)."""
import time
from datetime import datetime, timedelta, timezone

import pytest

from ratelimit import (
    LimitConfig,
    RateLimiter,
    is_spam_block_active,
    spam_until_iso,
)


class FakeDB:
    """Minimal async stub — all limits are driven by in-memory state for these tests."""
    def __init__(self):
        self._usage = {}
        self._global = {}

    async def get_usage(self, user_id, day):
        return self._usage.get((user_id, day), 0)

    async def incr_usage(self, user_id, day):
        self._usage[(user_id, day)] = self._usage.get((user_id, day), 0) + 1
        return self._usage[(user_id, day)]

    async def get_global_usage(self, day):
        return self._global.get(day, 0)

    async def incr_global_usage(self, day):
        self._global[day] = self._global.get(day, 0) + 1
        return self._global[day]


def _limiter(**overrides):
    cfg = LimitConfig(**{**dict(
        daily_limit=3, burst_limit=3, burst_window_sec=60,
        global_limit=10, spam_threshold=30, spam_window_sec=300,
        spam_block_sec=3600,
    ), **overrides})
    return RateLimiter(FakeDB(), cfg)


# ---- burst -----------------------------------------------------------------

def test_burst_allows_within_limit():
    rl = _limiter(burst_limit=3)
    for _ in range(3):
        ok, wait = rl.check_burst(1)
        assert ok and wait == 0


def test_burst_blocks_over_limit_and_reports_wait():
    rl = _limiter(burst_limit=2, burst_window_sec=60)
    assert rl.check_burst(1)[0]
    assert rl.check_burst(1)[0]
    ok, wait = rl.check_burst(1)
    assert not ok
    assert 1 <= wait <= 60


def test_burst_per_user_isolated():
    rl = _limiter(burst_limit=2)
    assert rl.check_burst(1)[0]
    assert rl.check_burst(1)[0]
    assert not rl.check_burst(1)[0]
    # Different user unaffected
    assert rl.check_burst(2)[0]


# ---- spam sliding window ---------------------------------------------------

def test_spam_block_fires_after_threshold():
    rl = _limiter(spam_threshold=5, spam_window_sec=60)
    fired = False
    for _ in range(10):
        _, blocked = rl.check_spam(1)
        if blocked:
            fired = True
            break
    assert fired


def test_spam_isolated_per_user():
    rl = _limiter(spam_threshold=5)
    for _ in range(6):
        rl.check_spam(1)
    # Second user should still be clean
    ok, blocked = rl.check_spam(2)
    assert ok and not blocked


# ---- spam_until helpers ----------------------------------------------------

def test_spam_until_iso_future():
    iso = spam_until_iso(60)
    assert is_spam_block_active(iso)


def test_spam_until_past_inactive():
    past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    assert not is_spam_block_active(past)


def test_spam_until_none_inactive():
    assert not is_spam_block_active(None)
    assert not is_spam_block_active("")
    assert not is_spam_block_active("not a date")


# ---- daily consumption -----------------------------------------------------

@pytest.mark.asyncio
async def test_daily_consume_until_exhausted():
    rl = _limiter(daily_limit=3)
    for i in range(3):
        ok, rem = await rl.check_and_consume_daily(42)
        assert ok and rem == 3 - (i + 1)
    ok, rem = await rl.check_and_consume_daily(42)
    assert not ok and rem == 0


@pytest.mark.asyncio
async def test_global_consume_until_exhausted():
    rl = _limiter(global_limit=2)
    assert await rl.check_and_consume_global()
    assert await rl.check_and_consume_global()
    assert not await rl.check_and_consume_global()
