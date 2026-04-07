# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project

Bepors (@Bepors_iraneman_bot) is a Telegram bot that answers questions using Gemini 2.5 Flash with Google Search grounding for real-time data. Primary audience is Persian-speaking Telegram users inside Iran; Farsi is the primary UX language, English is secondary.

## Source of Truth: docs/PRD_SPEC_PLAN.md

`docs/PRD_SPEC_PLAN.md` is the spec for v1 and overrides any ad-hoc direction. Before coding, re-read it. Key rules from it that apply to every change:

- **Spec-driven**: Each numbered subsection (e.g. `5.2.3`) is one atomic unit of work. Commit messages reference them, e.g. `feat(5.2): add /search toggle`. If implementation reveals a gap, update the spec first and confirm before coding.
- **Investigate before coding**: Audit the affected files and verify SDK behavior (especially `google-genai` grounding and `python-telegram-bot` v21.6 APIs) before writing code. Report findings before making changes.
- **Do not invent patterns**: Follow what's already in `bot.py`. New patterns need written justification.

## Privacy Invariants (non-negotiable)

These come from `PRD_SPEC_PLAN.md §5.5` and apply even when editing unrelated code:

- **Never log full question or answer text.** Only log: timestamp, hashed user_id, message length, flags, response time, status. `bot.py:108` currently logs the first 80 chars of the question — this is a known v0 privacy gap that must not be replicated or made worse.
- `.env` is never committed. Use `.env.example` as the template.
- No third-party analytics (no GA, no Sentry) without explicit opt-in.

## Architecture

v1 is a modular Python bot. Each module has a single responsibility and is called from `bot.py`'s handlers.

- `bot.py` — entry point. Loads env, configures JSON logging, instantiates `Database`/`RateLimiter`/`GeminiClient`/`Admin`/`HealthServer`, registers Telegram handlers, wires the `ask_handler` pipeline (block check → burst → spam → prefix/flag parse → jailbreak check → global cap → daily limit → Gemini call → unsafe-output filter → badwords censor → render → send).
- `ai.py` — `GeminiClient.ask()` offloads the (sync) `google-genai` call via `asyncio.to_thread`. The `GoogleSearch` tool is attached only when `search_enabled=True`. `_build_system_prompt` injects filter constraints from `filters.flags_to_constraints()`.
- `db.py` — `Database` is a thin async wrapper over one sqlite3 connection (WAL mode), serialized via `asyncio.Lock`. Tables: `users`, `usage`, `global_usage`, `events`.
- `ratelimit.py` — `RateLimiter` holds `LimitConfig` + in-memory deques for burst/spam windows. Daily and global counters are persisted via `db`. `check_and_consume_daily` / `check_and_consume_global` are atomic.
- `filters.py` — `detect_prefix` (`?`/`.`), `parse_flags` (`--site`/`--time`/`--lang`/`--region`/`--news`/`--academic`), `flags_to_constraints` (turns flags into a NL constraint block for the system prompt), `is_jailbreak`, `is_unsafe_output`, `censor_badwords`.
- `formatting.py` — `render()` dispatches to compact/detailed/markdown renderers, builds an optional numeric card via `try_build_card`, escapes MarkdownV2 via `escape_markdown_v2`, splits long replies on paragraph boundaries with `(۱/۳)` page indicators.
- `i18n.py` — `t(key, lang, **kwargs)` with JSON locale caching and fallback to the other language then the key itself. `detect_lang()` reads Telegram `language_code`.
- `admin.py` — `Admin` class gates on `ADMIN_IDS`. `broadcast` is throttled at 25 msg/s to stay under Telegram's global bot limit.
- `health.py` — aiohttp server on `127.0.0.1:8088`. `/health` is always on; `/admin/metrics` returns Prometheus text if `METRICS_ENABLED=true` and the `X-Metrics-Secret` header matches.

### Handler pipeline ordering (non-obvious)
In `ask_handler`, the order is: **block → burst → spam → parse → jailbreak → global cap → daily limit → Gemini → post-filter → render**. The global cap is consumed BEFORE the per-user daily counter so a runaway user can't drain quota past the global ceiling. Both consumptions happen BEFORE the Gemini call so a failed call still "costs" the user a slot (intentional — prevents abuse via repeated failed calls).

### Log format invariant
`bot.py` installs a `JsonFormatter` — every log line is one JSON object. `_event()` is the only way to emit an app event; it always hashes the user_id and never takes question/answer text. If you need to add new logging, use `_event(uid, "name", **meta)` and never put raw user text in `meta`.

### Deployment model
systemd service `bepors-bot.service` runs `/opt/bepors-bot/venv/bin/python /opt/bepors-bot/bot.py` on a Hetzner box. `deploy.sh` is a one-shot installer (apt deps → venv → copy `.env` from example → install + enable + restart the service). v1 hardening (§5.10) moves the service to a dedicated `bepors` user with systemd sandboxing directives — not yet applied.

## Commands

### Local development

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
# Create .env from .env.example with TELEGRAM_TOKEN and GEMINI_API_KEY
./venv/bin/python bot.py
```

Required env: `TELEGRAM_TOKEN`, `GEMINI_API_KEY`. Optional: `DAILY_LIMIT` (default 20), `GEMINI_MODEL` (default `gemini-2.5-flash`).

### Syntax check (run after every edit, per PRD §0 Rule 3)

```bash
python -m py_compile bot.py
ruff check .    # if available
```

### Production (on the Hetzner box)

```bash
systemctl restart bepors-bot
systemctl status bepors-bot
journalctl -u bepors-bot -f        # live logs
```

Deploy flow: edit locally → `scp -r bepors-bot root@<host>:/opt/` → `ssh` in → `systemctl restart bepors-bot`. First-time setup uses `./deploy.sh`.

## Conventions

- Python 3.11+, stdlib-first. No ORM, no Redis, no Docker in v1. The only approved new dep for v1 is `aiohttp` (for the health endpoint, §5.9).
- Telegram message limit is 4096 — long replies are chunked at 4000-char boundaries (`bot.py:145`). For v1 formatting work, split on paragraph boundaries, not mid-sentence, with `(۱/۳)` page indicators.
- All user-facing strings in v1 go through `i18n.t(key, lang, **kwargs)` — do not add new hard-coded Farsi or English strings to handler code.
- For MarkdownV2 output, always escape reserved chars (`_*[]()~\`>#+-=|{}.!`) via a helper. Never pass raw model output to Telegram with `parse_mode=MarkdownV2`.
