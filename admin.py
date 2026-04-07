"""
Admin commands: /stats, /broadcast, /block, /unblock, /setlimit, /users, /user.
Per PRD §5.7. All handlers gate on ADMIN_IDS.

Broadcast is throttled to 25 messages/sec (Telegram's global bot limit).
/users and /user are extensions added in v1.2 for per-user activity inspection.
"""
from __future__ import annotations

import asyncio
import json
import logging

from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import Forbidden, BadRequest

from db import Database
from i18n import t
from ratelimit import RateLimiter, is_spam_block_active

log = logging.getLogger("bepors.admin")

# Telegram's global bot send-rate ceiling: 30/sec. Stay under it.
_BROADCAST_RATE = 25  # messages per second


class Admin:
    def __init__(self, admin_ids: set[int], db: Database, limiter: RateLimiter):
        self.admin_ids = admin_ids
        self.db = db
        self.limiter = limiter

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids

    async def _reject(self, update: Update, lang: str) -> None:
        await update.message.reply_text(t("admin_only", lang))

    # ---- /stats -------------------------------------------------------------

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        user_row = await self.db.ensure_user(user.id, "fa")
        lang = user_row["lang"]
        if not self.is_admin(user.id):
            return await self._reject(update, lang)

        users_today = await self.db.count_users_today()
        errors_today = await self.db.count_errors_today()
        global_used, global_cap = await self.limiter.get_global()
        await update.message.reply_text(
            t(
                "admin_stats",
                lang,
                users=users_today,
                questions=global_used,
                errors=errors_today,
                global_used=global_used,
                global_cap=global_cap,
            )
        )

    # ---- /broadcast ---------------------------------------------------------

    async def broadcast(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        user_row = await self.db.ensure_user(user.id, "fa")
        lang = user_row["lang"]
        if not self.is_admin(user.id):
            return await self._reject(update, lang)

        message_text = " ".join(context.args or []).strip()
        if not message_text:
            await update.message.reply_text("Usage: /broadcast <message>")
            return

        await update.message.reply_text(t("admin_broadcast_started", lang))
        ids = await self.db.list_user_ids()
        sent = failed = 0
        interval = 1.0 / _BROADCAST_RATE

        for uid in ids:
            try:
                await context.bot.send_message(chat_id=uid, text=message_text)
                sent += 1
            except Forbidden:
                # User blocked the bot — drop silently
                failed += 1
            except BadRequest:
                failed += 1
            except Exception:
                log.exception(
                    "broadcast delivery failed",
                    extra={"data": {"event": "broadcast_delivery_failed"}},
                )
                failed += 1
            await asyncio.sleep(interval)

        await update.message.reply_text(
            t("admin_broadcast_done", lang, sent=sent, failed=failed)
        )

    # ---- /block <id> --------------------------------------------------------

    async def block(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        user_row = await self.db.ensure_user(user.id, "fa")
        lang = user_row["lang"]
        if not self.is_admin(user.id):
            return await self._reject(update, lang)

        if not context.args:
            await update.message.reply_text("Usage: /block <user_id>")
            return
        try:
            target = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Invalid user id.")
            return
        await self.db.ensure_user(target, "fa")
        await self.db.set_user_field(target, "blocked", 1)
        await update.message.reply_text(t("admin_blocked", lang, user_id=target))

    # ---- /unblock <id> ------------------------------------------------------

    async def unblock(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        user_row = await self.db.ensure_user(user.id, "fa")
        lang = user_row["lang"]
        if not self.is_admin(user.id):
            return await self._reject(update, lang)

        if not context.args:
            await update.message.reply_text("Usage: /unblock <user_id>")
            return
        try:
            target = int(context.args[0])
        except ValueError:
            await update.message.reply_text("Invalid user id.")
            return
        await self.db.set_user_field(target, "blocked", 0)
        await update.message.reply_text(t("admin_unblocked", lang, user_id=target))

    # ---- /setlimit <n> ------------------------------------------------------

    async def setlimit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        user_row = await self.db.ensure_user(user.id, "fa")
        lang = user_row["lang"]
        if not self.is_admin(user.id):
            return await self._reject(update, lang)

        if not context.args:
            await update.message.reply_text("Usage: /setlimit <number>")
            return
        try:
            n = int(context.args[0])
            if n <= 0:
                raise ValueError
        except ValueError:
            await update.message.reply_text("Invalid number.")
            return
        self.limiter.update_config(daily_limit=n)
        await update.message.reply_text(t("admin_limit_set", lang, limit=n))

    # ---- /users [N] --------------------------------------------------------

    async def list_users(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Top-N users by lifetime answered questions."""
        user = update.effective_user
        user_row = await self.db.ensure_user(user.id, "fa")
        lang = user_row["lang"]
        if not self.is_admin(user.id):
            return await self._reject(update, lang)

        limit = 20
        if context.args:
            try:
                limit = max(1, min(100, int(context.args[0])))
            except ValueError:
                pass

        rows = await self.db.top_users(limit=limit)
        total_users = await self.db.count_total_users()

        if not rows:
            await update.message.reply_text(t("admin_users_empty", lang))
            return

        lines = [t("admin_users_header", lang, n=len(rows), total_users=total_users)]
        for i, r in enumerate(rows, 1):
            uid = r["user_id"]
            name = await self._user_display_name(context.bot, uid)
            lines.append(
                t(
                    "admin_user_row",
                    lang,
                    rank=i,
                    name=f"{name} ({uid})" if name else str(uid),
                    total=r["total_answers"],
                    today=r["today_count"],
                    last_seen=_short_ts(r["last_seen"]),
                )
            )
        await update.message.reply_text("\n".join(lines))

    # ---- /user <id> --------------------------------------------------------

    async def user_detail(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        user = update.effective_user
        user_row = await self.db.ensure_user(user.id, "fa")
        lang = user_row["lang"]
        if not self.is_admin(user.id):
            return await self._reject(update, lang)

        if not context.args:
            await update.message.reply_text(t("admin_users_usage", lang))
            return
        try:
            target = int(context.args[0])
        except ValueError:
            await update.message.reply_text(t("admin_users_usage", lang))
            return

        row = await self.db.user_with_today(target)
        if not row:
            await update.message.reply_text(t("admin_user_not_found", lang))
            return

        # Try to enrich with Telegram name/username (one API call, may fail)
        display_name = await self._user_display_name(context.bot, target)

        # Status: blocked / spam / active
        if row.get("blocked"):
            status = t("admin_user_status_blocked", lang)
        elif is_spam_block_active(row.get("spam_until")):
            status = t("admin_user_status_spam", lang)
        else:
            status = t("admin_user_status_active", lang)

        # Filters: pretty-print
        try:
            filters = json.loads(row.get("filters_json") or "{}")
        except json.JSONDecodeError:
            filters = {}
        if filters:
            filters_str = ", ".join(f"--{k}:{v}" for k, v in filters.items())
            filters_line = t("admin_user_detail_filters", lang, filters=filters_str)
        else:
            filters_line = t("admin_user_detail_no_filters", lang)

        lines = [t("admin_user_detail_header", lang, user_id=target)]
        if display_name:
            lines.append(t("admin_user_detail_name", lang, name=display_name))
        lines.append(t("admin_user_detail_lang", lang, lang=row.get("lang", "fa")))
        lines.append(t("admin_user_detail_format", lang, format=row.get("format", "compact")))
        lines.append(
            t(
                "admin_user_detail_search",
                lang,
                state=t("on" if row.get("search_enabled") else "off", lang),
            )
        )
        lines.append(filters_line)
        lines.append(t("admin_user_detail_total", lang, total=row.get("total_answers", 0)))
        lines.append(
            t(
                "admin_user_detail_today",
                lang,
                today=row.get("today_count", 0),
                limit=self.limiter.cfg.daily_limit,
            )
        )
        lines.append(t("admin_user_detail_first_seen", lang, first=_short_ts(row.get("created_at", ""))))
        lines.append(t("admin_user_detail_last_seen", lang, last=_short_ts(row.get("last_seen", ""))))
        lines.append(t("admin_user_detail_status", lang, status=status))

        await update.message.reply_text("\n".join(lines))

    # ---- helpers -----------------------------------------------------------

    @staticmethod
    async def _user_display_name(bot, user_id: int) -> str:
        """
        Best-effort enrichment: try to fetch the user's name/username via the
        Telegram API. Returns "" if the user has never started a chat with the
        bot, has blocked it, or any other API failure.
        """
        try:
            chat = await bot.get_chat(user_id)
        except Exception:
            return ""
        first = getattr(chat, "first_name", None) or ""
        last = getattr(chat, "last_name", None) or ""
        username = getattr(chat, "username", None)
        full = f"{first} {last}".strip()
        if username:
            return f"{full} @{username}".strip() if full else f"@{username}"
        return full


def _short_ts(ts: str) -> str:
    """Trim ISO timestamp to YYYY-MM-DD HH:MM (drop seconds + timezone for compactness)."""
    if not ts:
        return "—"
    try:
        return ts[:16].replace("T", " ")
    except Exception:
        return ts
