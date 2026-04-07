"""
Bepors Bot — Telegram search bot with Gemini + Google Search grounding.
Entry point that wires i18n, db, ratelimit, filters, formatting, ai, admin, health.

Per PRD §5.1–5.10.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Awaitable, Callable

from dotenv import load_dotenv
from telegram import (
    BotCommand,
    BotCommandScopeChat,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters as tg_filters,
)

from ai import GeminiClient
from admin import Admin
from db import Database
from filters import (
    censor_badwords,
    detect_prefix,
    is_jailbreak,
    is_unsafe_output,
    merge_filters,
    parse_flags,
)
from formatting import parse_mode_for, render
from health import HealthServer
from i18n import detect_lang, t
from ratelimit import LimitConfig, RateLimiter, is_spam_block_active, spam_until_iso

# ---- config -----------------------------------------------------------------

load_dotenv()

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

DAILY_LIMIT = int(os.environ.get("DAILY_LIMIT", "20"))
BURST_LIMIT = int(os.environ.get("BURST_LIMIT", "5"))
GLOBAL_LIMIT = int(os.environ.get("GLOBAL_LIMIT", "10000"))

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
DB_PATH = os.environ.get("DB_PATH", "data/bepors.db")

ADMIN_IDS = {
    int(x) for x in os.environ.get("ADMIN_IDS", "").split(",") if x.strip().isdigit()
}
BLOCKED_USER_IDS = {
    int(x) for x in os.environ.get("BLOCKED_USER_IDS", "").split(",") if x.strip().isdigit()
}

HEALTH_HOST = os.environ.get("HEALTH_HOST", "127.0.0.1")
HEALTH_PORT = int(os.environ.get("HEALTH_PORT", "8088"))
METRICS_ENABLED = os.environ.get("METRICS_ENABLED", "false").lower() == "true"
METRICS_SECRET = os.environ.get("METRICS_SECRET") or None

# Salt for hashing user_ids in logs / events. Persisted across restarts via a
# file under data/, so hashes are stable but still not reversible to a raw ID.
_SALT_FILE = Path(DB_PATH).parent / ".log_salt"


def _load_salt() -> str:
    _SALT_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _SALT_FILE.exists():
        return _SALT_FILE.read_text().strip()
    salt = secrets.token_hex(16)
    _SALT_FILE.write_text(salt)
    try:
        os.chmod(_SALT_FILE, 0o600)
    except OSError:
        pass
    return salt


LOG_SALT = os.environ.get("LOG_SALT") or _load_salt()


def uhash(user_id: int) -> str:
    return hashlib.sha256(f"{LOG_SALT}:{user_id}".encode()).hexdigest()[:12]


# ---- logging: structured JSON, no question/answer text ---------------------


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            base["exc"] = self.formatException(record.exc_info)
        # Any dict passed via `extra={"data": {...}}`
        extras = getattr(record, "data", None)
        if isinstance(extras, dict):
            base.update(extras)
        return json.dumps(base, ensure_ascii=False)


def _configure_logging() -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)


_configure_logging()
log = logging.getLogger("bepors")


# ---- shared singletons (attached to Application.bot_data) ------------------

db = Database(DB_PATH)
limiter = RateLimiter(
    db,
    LimitConfig(
        daily_limit=DAILY_LIMIT,
        burst_limit=BURST_LIMIT,
        global_limit=GLOBAL_LIMIT,
    ),
)
gemini = GeminiClient(api_key=GEMINI_API_KEY, model=GEMINI_MODEL)
admin = Admin(ADMIN_IDS, db, limiter)


# ---- helpers ----------------------------------------------------------------

async def _get_user_ctx(update: Update) -> tuple[int, str, dict]:
    """Ensure the user row exists and return (user_id, lang, user_row)."""
    tg_user = update.effective_user
    initial_lang = detect_lang(getattr(tg_user, "language_code", None))
    row = await db.ensure_user(tg_user.id, initial_lang)
    return tg_user.id, row["lang"], row


def _event(user_id: int, event: str, **meta) -> None:
    """Fire-and-forget structured log line. NEVER include question/answer text."""
    log.info(
        event,
        extra={"data": {"uh": uhash(user_id), "event": event, **meta}},
    )


async def _is_blocked(user_id: int, user_row: dict) -> bool:
    if user_id in BLOCKED_USER_IDS:
        return True
    if user_row.get("blocked"):
        return True
    if is_spam_block_active(user_row.get("spam_until")):
        return True
    return False


def _hours_to_utc_midnight() -> int:
    """How many whole hours until the next UTC midnight (for quota-reset messages)."""
    now = datetime.now(timezone.utc)
    tomorrow = (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    delta = tomorrow - now
    return max(1, int(delta.total_seconds() // 3600) + (1 if delta.total_seconds() % 3600 else 0))


# Example starter prompts shown on /start. Keys are referenced from callback_data.
# The actual question text is pulled from the locale file so examples follow
# the user's language. Do not hard-code questions here.
EXAMPLE_KEYS = ("dollar", "weather", "news")


def _welcome_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(t("example_dollar_btn", lang), callback_data="ex:dollar"),
                InlineKeyboardButton(t("example_weather_btn", lang), callback_data="ex:weather"),
            ],
            [
                InlineKeyboardButton(t("example_news_btn", lang), callback_data="ex:news"),
            ],
        ]
    )


async def _typing_loop(chat) -> None:
    """
    Telegram's typing action only lasts ~5s; loop it every 4.5s so the user
    sees a continuous "typing" indicator during multi-second Gemini calls.
    Cancelled by the caller once the answer is ready.
    """
    try:
        while True:
            try:
                await chat.send_action(ChatAction.TYPING)
            except Exception:
                return
            await asyncio.sleep(4.5)
    except asyncio.CancelledError:
        pass


# ---- feedback buttons ------------------------------------------------------

def _feedback_keyboard(lang: str) -> InlineKeyboardMarkup:
    """Attached to the last chunk of every answer — gives the user an outlet."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👍", callback_data="fb:up"),
                InlineKeyboardButton("👎", callback_data="fb:down"),
            ]
        ]
    )


# ---- progressive tips ------------------------------------------------------

# Tip N fires on the user's Nth successful answer, if its bit isn't already set.
# Keep this list short — too many tips become annoying.
_TIP_TRIGGERS: tuple[tuple[int, int, str], ...] = (
    (2, 1 << 0, "tip_prefix"),
    (5, 1 << 1, "tip_filters"),
    (10, 1 << 2, "tip_format"),
)


async def _maybe_send_tip(
    chat, user_id: int, lang: str, total_answers: int, tips_shown: int
) -> None:
    for trigger_count, bit, key in _TIP_TRIGGERS:
        if total_answers >= trigger_count and not (tips_shown & bit):
            try:
                await chat.send_message(t(key, lang), disable_web_page_preview=True)
            except Exception:
                log.debug("tip send failed", exc_info=True)
            await db.set_user_field(user_id, "tips_shown", tips_shown | bit)
            # Only fire at most one tip per answer so we don't spam.
            return


# ---- admin error alerting --------------------------------------------------

_ERROR_WINDOW: list[float] = []
_ERROR_WINDOW_SEC = 600     # 10 minutes
_ERROR_THRESHOLD = 5
_ERROR_ALERT_COOLDOWN = 1800  # 30 minutes between alerts
_last_error_alert: float = 0.0


async def _record_error_and_maybe_alert(bot) -> None:
    """
    Track errors in a 10-minute sliding window. When the count hits the
    threshold, DM every ADMIN_ID once. Cooldown prevents re-alerting.
    """
    global _last_error_alert
    now = time.monotonic()
    cutoff = now - _ERROR_WINDOW_SEC
    # Prune
    _ERROR_WINDOW[:] = [t_ for t_ in _ERROR_WINDOW if t_ >= cutoff]
    _ERROR_WINDOW.append(now)
    if len(_ERROR_WINDOW) < _ERROR_THRESHOLD:
        return
    if now - _last_error_alert < _ERROR_ALERT_COOLDOWN:
        return
    _last_error_alert = now
    msg = (
        f"⚠️ Bepors alert: {len(_ERROR_WINDOW)} errors in the last "
        f"{_ERROR_WINDOW_SEC // 60} minutes. Check `journalctl -u bepors-bot`."
    )
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(chat_id=admin_id, text=msg)
        except Exception:
            log.debug(
                "admin alert send failed",
                exc_info=True,
                extra={"data": {"event": "admin_alert_send_failed"}},
            )


# ---- command handlers -------------------------------------------------------

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _uid, lang, _row = await _get_user_ctx(update)
    body = (
        t("welcome", lang, limit=limiter.cfg.daily_limit)
        + "\n\n"
        + t("welcome_try", lang)
    )
    await update.message.reply_text(
        body,
        reply_markup=_welcome_keyboard(lang),
        disable_web_page_preview=True,
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _uid, lang, _row = await _get_user_ctx(update)
    await update.message.reply_text(
        t("help", lang, limit=limiter.cfg.daily_limit), disable_web_page_preview=True
    )


async def usage_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid, lang, _row = await _get_user_ctx(update)
    used, remaining = await limiter.get_daily(uid)
    await update.message.reply_text(
        t("usage_line", lang, count=used, limit=limiter.cfg.daily_limit, remaining=remaining)
    )


async def privacy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _uid, lang, _row = await _get_user_ctx(update)
    await update.message.reply_text(t("privacy_policy", lang))


async def forget_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Step 1: ask the user to confirm before wiping their data."""
    _uid, lang, _row = await _get_user_ctx(update)
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(t("forget_yes_btn", lang), callback_data="forget:yes"),
                InlineKeyboardButton(t("forget_no_btn", lang), callback_data="forget:no"),
            ]
        ]
    )
    await update.message.reply_text(t("forget_confirm", lang), reply_markup=kb)


async def feedback_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User tapped 👍 or 👎 on an answer."""
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    vote = data.split(":", 1)[1] if ":" in data else ""
    if vote not in ("up", "down"):
        return
    _event(q.from_user.id, "feedback", vote=vote)
    await db.log_event(uhash(q.from_user.id), "feedback", {"vote": vote})
    # Replace the keyboard with a tiny acknowledgement so the user sees it landed.
    try:
        ack = "🙏" if vote == "up" else "📝"
        await q.edit_message_reply_markup(
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(ack, callback_data="fb:done")]])
        )
    except Exception:
        pass


async def forget_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Step 2: actually delete, or acknowledge cancel."""
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    choice = data.split(":", 1)[1] if ":" in data else ""
    uid = q.from_user.id
    row = await db.get_user(uid) or {}
    lang = row.get("lang", detect_lang(getattr(q.from_user, "language_code", None)))
    if choice == "yes":
        await db.delete_user(uid)
        _event(uid, "forget")
        await q.edit_message_text(t("forget_done", lang))
    else:
        await q.edit_message_text(t("forget_cancelled", lang))


# ---- /lang ------------------------------------------------------------------

async def lang_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid, lang, _row = await _get_user_ctx(update)
    if context.args:
        choice = context.args[0].lower()
        if choice in ("fa", "en"):
            await db.set_user_field(uid, "lang", choice)
            label = t(f"lang_{choice}", choice)
            await update.message.reply_text(t("lang_set", choice, lang=label))
            return
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(t("lang_fa", lang), callback_data="lang:fa"),
                InlineKeyboardButton(t("lang_en", lang), callback_data="lang:en"),
            ]
        ]
    )
    await update.message.reply_text(t("lang_prompt", lang), reply_markup=kb)


async def lang_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    if not data.startswith("lang:"):
        return
    choice = data.split(":", 1)[1]
    if choice not in ("fa", "en"):
        return
    await db.set_user_field(q.from_user.id, "lang", choice)
    label = t(f"lang_{choice}", choice)
    await q.edit_message_text(t("lang_set", choice, lang=label))


# ---- /search on|off ---------------------------------------------------------

async def search_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid, lang, _row = await _get_user_ctx(update)
    if not context.args or context.args[0].lower() not in ("on", "off"):
        await update.message.reply_text(t("search_usage", lang))
        return
    new_val = 1 if context.args[0].lower() == "on" else 0
    await db.set_user_field(uid, "search_enabled", new_val)
    await update.message.reply_text(
        t("search_set_on" if new_val else "search_set_off", lang)
    )


# ---- /format ----------------------------------------------------------------

async def format_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid, lang, _row = await _get_user_ctx(update)
    if context.args:
        choice = context.args[0].lower()
        if choice in ("compact", "detailed", "markdown"):
            await db.set_user_field(uid, "format", choice)
            label = t(f"format_{choice}", lang)
            await update.message.reply_text(t("format_set", lang, format=label))
            return
    # Markdown is still settable via the typed command `/format markdown`
    # but intentionally hidden from the keyboard — end users don't need it.
    kb = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(t("format_compact", lang), callback_data="fmt:compact"),
                InlineKeyboardButton(t("format_detailed", lang), callback_data="fmt:detailed"),
            ]
        ]
    )
    await update.message.reply_text(t("format_prompt", lang), reply_markup=kb)


async def format_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    if not data.startswith("fmt:"):
        return
    choice = data.split(":", 1)[1]
    if choice not in ("compact", "detailed", "markdown"):
        return
    await db.set_user_field(q.from_user.id, "format", choice)
    row = await db.get_user(q.from_user.id) or {}
    lang = row.get("lang", "fa")
    label = t(f"format_{choice}", lang)
    await q.edit_message_text(t("format_set", lang, format=label))


# ---- /filters ---------------------------------------------------------------

# Cycle order for the "time" filter button
_TIME_CYCLE = ("off", "day", "week", "month", "year")


def _filters_state_text(filters: dict[str, str], lang: str) -> str:
    """Render the current filter state as a plain-text message body."""
    lines = [t("filters_title", lang), ""]
    # Site (typed-command only)
    site = filters.get("site") or t("filters_val_none", lang)
    lines.append(f"🌐 {t('filters_site_label', lang)}: {site}")
    # Time (cycle)
    time_val = filters.get("time", "off")
    lines.append(f"🕐 {t('filters_time_label', lang)}: {t(f'filters_time_{time_val}', lang)}")
    # News (toggle)
    news_on = filters.get("news") == "true"
    lines.append(f"📰 {t('filters_news_label', lang)}: {t('on' if news_on else 'off', lang)}")
    # Academic (toggle)
    acad_on = filters.get("academic") == "true"
    lines.append(f"🎓 {t('filters_academic_label', lang)}: {t('on' if acad_on else 'off', lang)}")
    lines.append("")
    lines.append(t("filters_site_hint", lang))
    return "\n".join(lines)


def _filters_keyboard(filters: dict[str, str], lang: str) -> InlineKeyboardMarkup:
    time_val = filters.get("time", "off")
    news_on = filters.get("news") == "true"
    acad_on = filters.get("academic") == "true"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    f"🕐 {t(f'filters_time_{time_val}', lang)}",
                    callback_data="filt:time",
                ),
            ],
            [
                InlineKeyboardButton(
                    f"📰 {t('on' if news_on else 'off', lang)}",
                    callback_data="filt:news",
                ),
                InlineKeyboardButton(
                    f"🎓 {t('on' if acad_on else 'off', lang)}",
                    callback_data="filt:academic",
                ),
            ],
            [
                InlineKeyboardButton(
                    f"❌ {t('filters_clear_btn', lang)}",
                    callback_data="filt:clear",
                ),
            ],
        ]
    )


async def filters_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    No args → show interactive keyboard.
    With `set --site:x` → still works (power-user typed path).
    With `clear` → wipe all filters.
    """
    uid, lang, row = await _get_user_ctx(update)
    args = context.args or []
    current = json.loads(row.get("filters_json") or "{}")

    if args and args[0] == "clear":
        await db.set_user_filters(uid, {})
        await update.message.reply_text(t("filters_cleared", lang))
        return

    if args and args[0] == "set":
        rest = " ".join(args[1:])
        _, new_flags = parse_flags(rest)
        if not new_flags:
            await update.message.reply_text(t("filters_usage", lang))
            return
        current.update(new_flags)
        await db.set_user_filters(uid, current)
        await update.message.reply_text(t("filters_set", lang))
        return

    # Default: show interactive keyboard
    await update.message.reply_text(
        _filters_state_text(current, lang),
        reply_markup=_filters_keyboard(current, lang),
    )


async def filters_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    action = data.split(":", 1)[1] if ":" in data else ""
    uid = q.from_user.id
    row = await db.get_user(uid)
    if not row:
        row = await db.ensure_user(
            uid, detect_lang(getattr(q.from_user, "language_code", None))
        )
    lang = row.get("lang", "fa")
    current = json.loads(row.get("filters_json") or "{}")

    if action == "time":
        now_val = current.get("time", "off")
        try:
            nxt = _TIME_CYCLE[(_TIME_CYCLE.index(now_val) + 1) % len(_TIME_CYCLE)]
        except ValueError:
            nxt = "off"
        if nxt == "off":
            current.pop("time", None)
        else:
            current["time"] = nxt
    elif action == "news":
        if current.get("news") == "true":
            current.pop("news", None)
        else:
            current["news"] = "true"
    elif action == "academic":
        if current.get("academic") == "true":
            current.pop("academic", None)
        else:
            current["academic"] = "true"
    elif action == "clear":
        current = {}
    else:
        return

    await db.set_user_filters(uid, current)
    try:
        await q.edit_message_text(
            _filters_state_text(current, lang),
            reply_markup=_filters_keyboard(current, lang),
        )
    except Exception:
        # Telegram ignores edits where nothing changed — fine.
        log.debug("filters edit ignored", exc_info=True)


# ---- main text handler (the actual Q&A) ------------------------------------
#
# The pipeline lives in `_do_ask()` so that both the text MessageHandler and the
# example-prompt callback (from /start) can reuse it.

ReplyFn = Callable[..., Awaitable]


async def _do_ask(
    *,
    chat,
    user_id: int,
    lang: str,
    row: dict,
    text: str,
    reply: ReplyFn,
) -> None:
    """
    Full ask pipeline. `reply` is an async callable that sends a text message
    back to the user (e.g. message.reply_text or callback query.message.reply_text).
    """
    start_t = time.monotonic()

    # 1. Blocklist / spam
    if await _is_blocked(user_id, row):
        await reply(
            t("spam_blocked" if row.get("spam_until") else "blocked_user", lang)
        )
        _event(user_id, "blocked")
        return

    # 2. Burst rate limit (in-memory sliding window)
    allowed, wait = limiter.check_burst(user_id)
    if not allowed:
        await reply(t("burst_exceeded", lang, seconds=wait))
        _event(user_id, "burst_limit", wait=wait)
        return

    # 3. Anti-spam sustained-flood check
    _, newly_blocked = limiter.check_spam(user_id)
    if newly_blocked:
        await db.set_user_field(
            user_id, "spam_until", spam_until_iso(limiter.cfg.spam_block_sec)
        )
        await reply(t("spam_blocked", lang))
        _event(user_id, "spam_soft_block")
        return

    # 4. Parse input: prefix shortcut, then inline flags
    raw = (text or "").strip()
    if not raw:
        return
    raw, forced_search = detect_prefix(raw)

    # 5. Jailbreak / prompt-injection pre-filter
    if is_jailbreak(raw):
        await reply(t("jailbreak_refused", lang))
        _event(user_id, "jailbreak_refused")
        return

    cleaned_q, inline_flags = parse_flags(raw)
    if not cleaned_q:
        await reply(t("help", lang, limit=limiter.cfg.daily_limit))
        return

    # 6. Resolve search_enabled: inline prefix > user setting
    if forced_search is not None:
        search_enabled = forced_search
    else:
        search_enabled = bool(row.get("search_enabled", 1))

    # 7. Merge persistent default filters + inline flags
    default_filters = json.loads(row.get("filters_json") or "{}")
    merged_filters = merge_filters(default_filters, inline_flags)

    # 8. Global daily cap (check BEFORE expensive Gemini call)
    if not await limiter.check_and_consume_global():
        await reply(t("global_cap_hit", lang))
        _event(user_id, "global_cap_hit")
        return

    # 9. Per-user daily limit
    allowed, remaining = await limiter.check_and_consume_daily(user_id)
    if not allowed:
        await reply(t("quota_exceeded", lang, hours=_hours_to_utc_midnight()))
        _event(user_id, "quota_exceeded")
        return

    # 10. Start typing indicator loop, call Gemini, stop loop
    _event(
        user_id,
        "ask",
        q_len=len(cleaned_q),
        search=search_enabled,
        flags=list(merged_filters.keys()),
    )

    typing_task = asyncio.create_task(_typing_loop(chat))
    try:
        try:
            result = await gemini.ask(
                cleaned_q,
                lang=lang,
                search_enabled=search_enabled,
                filters=merged_filters,
            )
        except Exception:
            _event(user_id, "error", stage="gemini")
            await db.log_event(uhash(user_id), "error", {"stage": "gemini"})
            await reply(t("error_generic", lang))
            # Fire-and-forget admin alert if error rate spikes.
            try:
                await _record_error_and_maybe_alert(chat.get_bot())
            except Exception:
                pass
            return
    finally:
        typing_task.cancel()
        try:
            await typing_task
        except (asyncio.CancelledError, Exception):
            pass

    answer = result.answer or t("empty_answer", lang)

    # 11. Post-filter: unsafe output + badwords censor
    if is_unsafe_output(answer):
        _event(user_id, "unsafe_output_blocked")
        await reply(t("jailbreak_refused", lang))
        return
    answer = censor_badwords(answer, lang)

    # 12. Render and send
    fmt = row.get("format", "compact") or "compact"
    chunks = render(
        answer,
        result.sources,
        format=fmt,
        lang=lang,
        search_used=search_enabled,
        remaining=remaining,
        show_warning=(not search_enabled),
    )

    parse_mode = parse_mode_for(fmt)  # type: ignore[arg-type]
    for i, chunk in enumerate(chunks):
        is_last = i == len(chunks) - 1
        kwargs: dict = {
            "parse_mode": parse_mode,
            "disable_web_page_preview": True,
        }
        # Attach feedback buttons to the last chunk only.
        if is_last:
            kwargs["reply_markup"] = _feedback_keyboard(lang)
        try:
            await reply(chunk, **kwargs)
        except Exception:
            # If the parse_mode ever rejects the chunk (tag mismatch, rogue
            # char), retry as plain text so the user still gets the answer.
            kwargs_plain = {k: v for k, v in kwargs.items() if k != "parse_mode"}
            await reply(chunk, **kwargs_plain)

    # Progressive tips: fire a teaching hint after 2nd / 5th / 10th answer.
    total = await db.incr_total_answers(user_id)
    await _maybe_send_tip(chat, user_id, lang, total, row.get("tips_shown", 0))

    _event(
        user_id,
        "answered",
        ms=int((time.monotonic() - start_t) * 1000),
        sources=len(result.sources),
        remaining=remaining,
    )


async def ask_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid, lang, row = await _get_user_ctx(update)
    await _do_ask(
        chat=update.message.chat,
        user_id=uid,
        lang=lang,
        row=row,
        text=update.message.text or "",
        reply=update.message.reply_text,
    )


async def example_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """User tapped one of the /start example prompts."""
    q = update.callback_query
    await q.answer()
    data = q.data or ""
    key = data.split(":", 1)[1] if ":" in data else ""
    if key not in EXAMPLE_KEYS:
        return
    # Resolve user context — the callback may fire in a chat where the user
    # hasn't explicitly sent a message yet, so ensure_user is important.
    tg_user = q.from_user
    initial_lang = detect_lang(getattr(tg_user, "language_code", None))
    row = await db.ensure_user(tg_user.id, initial_lang)
    lang = row["lang"]
    # Dispatch to the same pipeline the text handler uses, with the localized
    # example question text.
    example_text = t(f"example_{key}_q", lang)
    await _do_ask(
        chat=q.message.chat,
        user_id=tg_user.id,
        lang=lang,
        row=row,
        text=example_text,
        reply=q.message.reply_text,
    )


# ---- error handler ----------------------------------------------------------

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.error("update error", exc_info=context.error)


# ---- health stats callback --------------------------------------------------

async def _health_stats() -> dict[str, int]:
    users_today = await db.count_users_today()
    global_used, global_cap = await limiter.get_global()
    errors_today = await db.count_errors_today()
    return {
        "users_today": users_today,
        "questions_today": global_used,
        "global_cap": global_cap,
        "errors_today": errors_today,
    }


# ---- app lifecycle ----------------------------------------------------------

def _bot_commands(lang: str) -> list[BotCommand]:
    """Localized slash-command menu shown in Telegram's native UI for everyone."""
    return [
        BotCommand("start", t("cmd_start_desc", lang)),
        BotCommand("help", t("cmd_help_desc", lang)),
        BotCommand("usage", t("cmd_usage_desc", lang)),
        BotCommand("lang", t("cmd_lang_desc", lang)),
        BotCommand("search", t("cmd_search_desc", lang)),
        BotCommand("filters", t("cmd_filters_desc", lang)),
        BotCommand("format", t("cmd_format_desc", lang)),
        BotCommand("privacy", t("cmd_privacy_desc", lang)),
        BotCommand("forget", t("cmd_forget_desc", lang)),
    ]


def _admin_bot_commands(lang: str) -> list[BotCommand]:
    """Extended menu for admin chats only — regular commands + admin tools."""
    base = _bot_commands(lang)
    return base + [
        BotCommand("stats", t("cmd_stats_desc", lang)),
        BotCommand("users", t("cmd_users_desc", lang)),
        BotCommand("user", t("cmd_user_desc", lang)),
        BotCommand("broadcast", t("cmd_broadcast_desc", lang)),
        BotCommand("setlimit", t("cmd_setlimit_desc", lang)),
        BotCommand("block", t("cmd_block_desc", lang)),
        BotCommand("unblock", t("cmd_unblock_desc", lang)),
    ]


async def _post_init(app: Application) -> None:
    db.connect()
    health = HealthServer(
        _health_stats,
        host=HEALTH_HOST,
        port=HEALTH_PORT,
        metrics_enabled=METRICS_ENABLED,
        metrics_secret=METRICS_SECRET,
    )
    await health.start()
    app.bot_data["health"] = health

    # Register the slash-command menu. Persian is the default for ALL users
    # because the bot's audience is Iranian — even users with English Telegram
    # clients see the menu in Persian. We also explicitly clear any previously
    # registered English commands so cached menus on en clients update.
    try:
        fa_commands = _bot_commands("fa")
        await app.bot.set_my_commands(fa_commands)  # default fallback for every locale
        await app.bot.set_my_commands(fa_commands, language_code="fa")
        # Wipe the previous English registration (if any). This forces English
        # Telegram clients to fall back to the new default (Persian).
        try:
            await app.bot.delete_my_commands(language_code="en")
        except Exception:
            pass

        # Per-admin menus: each ADMIN_ID sees the regular commands PLUS the
        # admin-only ones (stats / users / user / broadcast / etc). Scope is
        # per-chat so regular users still get the clean 9-command menu.
        admin_fa = _admin_bot_commands("fa")
        for admin_id in ADMIN_IDS:
            try:
                await app.bot.set_my_commands(
                    admin_fa,
                    scope=BotCommandScopeChat(chat_id=admin_id),
                )
            except Exception:
                log.warning(
                    "admin menu set failed",
                    exc_info=True,
                    extra={"data": {"event": "admin_menu_set_failed"}},
                )

        # Bot description (shown on the bot's profile in Telegram clients).
        await app.bot.set_my_short_description(t("bot_short_desc", "fa"))
        await app.bot.set_my_short_description(t("bot_short_desc", "fa"), language_code="fa")
        await app.bot.set_my_description(t("bot_long_desc", "fa"))
        await app.bot.set_my_description(t("bot_long_desc", "fa"), language_code="fa")
    except Exception:
        log.warning("set_my_commands/description failed", exc_info=True)

    log.info(
        "bepors started",
        extra={
            "data": {
                "event": "startup",
                "model": GEMINI_MODEL,
                "daily_limit": DAILY_LIMIT,
                "global_limit": GLOBAL_LIMIT,
                "admins": len(ADMIN_IDS),
            }
        },
    )


async def _post_shutdown(app: Application) -> None:
    health: HealthServer | None = app.bot_data.get("health")
    if health:
        await health.stop()
    db.close()
    log.info("bepors stopped", extra={"data": {"event": "shutdown"}})


def main() -> None:
    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .post_init(_post_init)
        .post_shutdown(_post_shutdown)
        .build()
    )

    # user commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("usage", usage_cmd))
    app.add_handler(CommandHandler("lang", lang_cmd))
    app.add_handler(CommandHandler("search", search_cmd))
    app.add_handler(CommandHandler("format", format_cmd))
    app.add_handler(CommandHandler("filters", filters_cmd))
    app.add_handler(CommandHandler("privacy", privacy_cmd))
    app.add_handler(CommandHandler("forget", forget_cmd))

    # admin commands
    app.add_handler(CommandHandler("stats", admin.stats))
    app.add_handler(CommandHandler("broadcast", admin.broadcast))
    app.add_handler(CommandHandler("block", admin.block))
    app.add_handler(CommandHandler("unblock", admin.unblock))
    app.add_handler(CommandHandler("setlimit", admin.setlimit))
    app.add_handler(CommandHandler("users", admin.list_users))
    app.add_handler(CommandHandler("user", admin.user_detail))

    # inline-keyboard callbacks
    app.add_handler(CallbackQueryHandler(lang_callback, pattern=r"^lang:"))
    app.add_handler(CallbackQueryHandler(format_callback, pattern=r"^fmt:"))
    app.add_handler(CallbackQueryHandler(forget_callback, pattern=r"^forget:"))
    app.add_handler(CallbackQueryHandler(example_callback, pattern=r"^ex:"))
    app.add_handler(CallbackQueryHandler(feedback_callback, pattern=r"^fb:"))
    app.add_handler(CallbackQueryHandler(filters_callback, pattern=r"^filt:"))

    # main Q&A handler — DMs only (filters.ChatType.PRIVATE)
    app.add_handler(
        MessageHandler(
            tg_filters.TEXT & ~tg_filters.COMMAND & tg_filters.ChatType.PRIVATE,
            ask_handler,
        )
    )

    app.add_error_handler(error_handler)

    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
