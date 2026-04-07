"""Tests for db.py async SQLite layer."""
import os
import tempfile

import pytest

from db import Database


@pytest.fixture
async def db():
    path = tempfile.mktemp(suffix=".db")
    d = Database(path)
    d.connect()
    yield d
    d.close()
    for ext in ("", "-wal", "-shm"):
        try:
            os.unlink(path + ext)
        except FileNotFoundError:
            pass


@pytest.mark.asyncio
async def test_ensure_user_creates_and_returns_row(db):
    row = await db.ensure_user(42, "fa")
    assert row["user_id"] == 42
    assert row["lang"] == "fa"
    assert row["search_enabled"] == 1
    assert row["format"] == "compact"
    assert row["blocked"] == 0
    assert row["tips_shown"] == 0
    assert row["total_answers"] == 0


@pytest.mark.asyncio
async def test_ensure_user_idempotent(db):
    r1 = await db.ensure_user(42, "fa")
    r2 = await db.ensure_user(42, "en")  # second call won't overwrite lang
    assert r2["lang"] == "fa"
    assert r1["user_id"] == r2["user_id"]


@pytest.mark.asyncio
async def test_set_user_field_whitelist(db):
    await db.ensure_user(1, "fa")
    await db.set_user_field(1, "lang", "en")
    row = await db.get_user(1)
    assert row["lang"] == "en"


@pytest.mark.asyncio
async def test_set_user_field_rejects_unknown(db):
    await db.ensure_user(1, "fa")
    with pytest.raises(ValueError):
        await db.set_user_field(1, "user_id", 999)  # not whitelisted
    with pytest.raises(ValueError):
        await db.set_user_field(1, "'; DROP TABLE users; --", "haha")


@pytest.mark.asyncio
async def test_daily_usage_increment(db):
    await db.ensure_user(1, "fa")
    assert await db.incr_usage(1, "2026-04-07") == 1
    assert await db.incr_usage(1, "2026-04-07") == 2
    assert await db.get_usage(1, "2026-04-07") == 2


@pytest.mark.asyncio
async def test_global_usage(db):
    assert await db.incr_global_usage("2026-04-07") == 1
    assert await db.incr_global_usage("2026-04-07") == 2
    assert await db.get_global_usage("2026-04-07") == 2


@pytest.mark.asyncio
async def test_filters_json_roundtrip(db):
    import json
    await db.ensure_user(1, "fa")
    await db.set_user_filters(1, {"site": "bbc.com", "time": "day"})
    row = await db.get_user(1)
    assert json.loads(row["filters_json"]) == {"site": "bbc.com", "time": "day"}


@pytest.mark.asyncio
async def test_total_answers_increment(db):
    await db.ensure_user(1, "fa")
    assert await db.incr_total_answers(1) == 1
    assert await db.incr_total_answers(1) == 2
    row = await db.get_user(1)
    assert row["total_answers"] == 2


@pytest.mark.asyncio
async def test_tips_shown_bitfield(db):
    await db.ensure_user(1, "fa")
    await db.set_user_field(1, "tips_shown", 0b011)
    row = await db.get_user(1)
    assert row["tips_shown"] == 0b011


@pytest.mark.asyncio
async def test_delete_user_wipes_usage(db):
    await db.ensure_user(1, "fa")
    await db.incr_usage(1, "2026-04-07")
    await db.delete_user(1)
    assert await db.get_user(1) is None
    assert await db.get_usage(1, "2026-04-07") == 0


@pytest.mark.asyncio
async def test_list_user_ids_excludes_blocked(db):
    await db.ensure_user(1, "fa")
    await db.ensure_user(2, "fa")
    await db.set_user_field(2, "blocked", 1)
    ids = await db.list_user_ids()
    assert 1 in ids
    assert 2 not in ids


@pytest.mark.asyncio
async def test_log_event_never_stores_raw_text(db):
    """Privacy invariant: log_event takes a user_hash, not user_id."""
    await db.log_event("abcdef123456", "ask", {"q_len": 42})
    # We don't have a query API for events in production; just make sure it didn't crash.


@pytest.mark.asyncio
async def test_migration_idempotent(db):
    """Running _migrate twice should be safe (ALTER TABLE ADD COLUMN is not)."""
    # First migration already ran in connect(); rerun it manually.
    db._migrate(db._conn)  # should be a no-op
    row = await db.ensure_user(1, "fa")
    assert "tips_shown" in row


# ---- admin queries ---------------------------------------------------------

@pytest.mark.asyncio
async def test_count_total_users(db):
    assert await db.count_total_users() == 0
    await db.ensure_user(1, "fa")
    await db.ensure_user(2, "en")
    await db.ensure_user(3, "fa")
    assert await db.count_total_users() == 3


@pytest.mark.asyncio
async def test_top_users_orders_by_total_answers_desc(db):
    await db.ensure_user(1, "fa")
    await db.ensure_user(2, "fa")
    await db.ensure_user(3, "fa")
    # User 2 has the most answers
    for _ in range(5):
        await db.incr_total_answers(2)
    for _ in range(3):
        await db.incr_total_answers(3)
    await db.incr_total_answers(1)

    top = await db.top_users(limit=10)
    assert [r["user_id"] for r in top] == [2, 3, 1]
    assert top[0]["total_answers"] == 5
    assert top[1]["total_answers"] == 3


@pytest.mark.asyncio
async def test_top_users_includes_today_count(db):
    await db.ensure_user(42, "fa")
    for _ in range(7):
        await db.incr_total_answers(42)
    # Bump today's quota
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await db.incr_usage(42, today)
    await db.incr_usage(42, today)

    top = await db.top_users(limit=10)
    assert len(top) == 1
    assert top[0]["user_id"] == 42
    assert top[0]["total_answers"] == 7
    assert top[0]["today_count"] == 2


@pytest.mark.asyncio
async def test_top_users_respects_limit(db):
    for i in range(10):
        await db.ensure_user(i, "fa")
        await db.incr_total_answers(i)
    top = await db.top_users(limit=3)
    assert len(top) == 3


@pytest.mark.asyncio
async def test_user_with_today_returns_full_row(db):
    await db.ensure_user(99, "en")
    await db.set_user_field(99, "format", "detailed")
    await db.incr_total_answers(99)
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await db.incr_usage(99, today)

    row = await db.user_with_today(99)
    assert row is not None
    assert row["user_id"] == 99
    assert row["lang"] == "en"
    assert row["format"] == "detailed"
    assert row["total_answers"] == 1
    assert row["today_count"] == 1


@pytest.mark.asyncio
async def test_user_with_today_returns_none_for_missing(db):
    assert await db.user_with_today(404) is None
