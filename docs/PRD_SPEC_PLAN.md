# Bepors Bot, PRD and Spec Plan

**Status:** DRAFT v1
**Project:** Bepors (@Bepors_iraneman_bot)
**Owner:** Maintainer
**Date:** 2026-04-07
**Target deploy:** Hetzner CX23, Helsinki, `<your-server-ip>`
**Branch:** main

---

## 0. Hand-off Rules for the AI Builder (Claude Code)

Attach this entire file to the AI session. The AI MUST follow these rules before writing a single line of code.

### Rule 1: Investigate Before You Code
Before writing any implementation code, the AI must independently audit the project folder and the constraints in this doc. Do not blindly execute. Report findings first.

Required investigation:
- Read every file already in `bepors-bot/` (bot.py, requirements.txt, .env.example, bepors-bot.service, deploy.sh, README.md)
- Verify the `google-genai` SDK version supports `GoogleSearch` grounding tool the way the doc describes
- Check `python-telegram-bot` v21.6 API for any breaking changes vs the patterns used
- Find every place where user input is logged or stored, confirm no PII leakage
- Identify race conditions in the in-memory rate limiter when scaled to thousands of users
- Check that the systemd service runs as a non-root user where possible
- Find missing pieces this PRD does not cover, report them

Report findings BEFORE coding. Include: what you found, risks, questions, and better alternatives if any.

### Rule 2: Spec-Driven Development
This file IS the spec. If implementation reveals gaps, update this file first, get confirmation, then code. Each numbered section below is one task. Each decimal subsection is one atomic unit. Commits must reference subsection numbers (for example `feat(2.3): add /search command toggle`).

### Rule 3: Implementation Standards
- Small logical commits, one concern per commit
- Run `python -m py_compile bot.py` and `ruff check` (if available) after every change
- Bilingual UX, Persian (Farsi) primary and English secondary, all user-facing strings in `locales/fa.json` and `locales/en.json`, auto-detect from message language
- Follow existing patterns in `bot.py`, do not invent new ones unless justified in writing
- If unsure, ask, do not guess
- Never log full user questions or answers in plain text, only hashes or truncated previews
- Never commit `.env`, `.gitignore` must include it

---

## 1. Product Overview

### 1.1 What Bepors Is
Bepors is a Telegram bot that gives Iranian users free, fast, real-time answers to any question. It uses Google Gemini 2.5 Flash with built-in Google Search grounding so answers reflect live data (news, prices, sports, weather, current events) instead of stale model knowledge.

### 1.2 Why It Exists
Iranian users face heavy filtering and cannot reach Google, ChatGPT, Perplexity, or most major AI services without VPN. Telegram is widely accessible inside Iran via MTProto proxies and VPN. A Telegram-native bot removes the friction: open Telegram, type a question, get an answer with sources, in Farsi.

### 1.3 Who It Is For
- Primary: Persian speaking Telegram users inside Iran
- Secondary: Persian diaspora and English-speaking users who prefer chat-style search
- Excluded: anyone needing voice, image generation, or long-form research (v2)

### 1.4 Success Metrics (first 30 days)
- 1,000+ unique users
- Average 5+ questions per active user per day
- p95 response time under 6 seconds
- Crash-free uptime above 99 percent
- Cost per active user under $0.02 per day

### 1.5 Non-Goals (out of scope for v1)
- Image generation
- Voice messages, transcription, or TTS
- File uploads or document Q and A
- Group chat support (DM only in v1)
- Payment, premium tiers (v2)
- Persistent database (v1 uses in-memory state, v2 adds SQLite)

---

## 2. Current State

### 2.1 What Already Exists
A working v0 in `bepors-bot/` with:
- `bot.py`, basic polling bot, Gemini 2.5 Flash with always-on Google Search grounding, in-memory rate limiter, Farsi welcome and help, source citations
- `.env.example`, holds Telegram and Gemini keys, model name, daily limit
- `bepors-bot.service`, systemd unit
- `deploy.sh`, one shot installer for Ubuntu
- `README.md`, deploy instructions

### 2.2 Known Gaps in v0
- Search grounding is always on, the user has no toggle, this wastes the Google Search quota on questions that do not need real-time data
- No language file, all strings hard-coded in Farsi
- No content filters
- No formatting options, replies are plain text
- No `/lang` command
- No abuse protection beyond per-user daily limit
- No metrics or admin commands
- Rate limiter is in-memory and lost on restart
- Logs include the first 80 chars of every question, a privacy risk

---

## 3. Goals for v1

In plain language: turn v0 into a polished, safe, bilingual, configurable bot that respects user privacy, lets users choose when to use real-time search, formats answers nicely, and is ready for thousands of users.

---

## 4. Investigation Findings (to be filled by Claude Code)

The AI builder must complete this section before writing code. Template:

```
### Finding 1: [title]
What I found:
Risk level: low | medium | high
Recommended fix:
Affects spec section:
```

---

## 5. Feature Spec, Numbered Tasks

### 5.1 Bilingual i18n (Farsi default, English fallback)

5.1.1 Create `locales/fa.json` and `locales/en.json` with every user-facing string keyed by name (`welcome`, `help`, `quota_exceeded`, `error_generic`, `sources_label`, etc.)

5.1.2 Add `i18n.py` helper with `t(key, lang, **kwargs)` that loads JSON once and supports `{var}` interpolation

5.1.3 Detect user language from Telegram `update.effective_user.language_code`, fallback to Farsi if Iranian or unknown, English otherwise

5.1.4 Add `/lang` command that lets the user pick `fa` or `en`, persist choice in user state

5.1.5 Acceptance: starting bot with English Telegram client shows English welcome, with Persian client shows Farsi, `/lang en` then `/start` shows English

5.1.6 Risk: language code may be missing for some users, default safely

### 5.2 User-Toggleable Web Search

5.2.1 Add per-user state field `search_enabled` (default `true`)

5.2.2 Add `/search on` and `/search off` commands, replies confirm new state in user's language

5.2.3 In `ask` handler, only attach the `GoogleSearch` tool when `search_enabled` is true

5.2.4 Add a quick inline shortcut: any message starting with `?` forces search ON for that one query, any message starting with `.` forces search OFF for that one query, both prefixes are stripped before sending to Gemini

5.2.5 Show a small footer in the reply: `🌐 با جستجوی زنده` or `💭 بدون جستجو` so the user knows which mode produced the answer

5.2.6 Acceptance: with search off, a question like "آخرین قیمت دلار" returns a model-only answer with a clear note that live data is disabled, with search on it returns sourced live data

5.2.7 Risk: Gemini grounding is metered, this feature directly reduces cost

### 5.3 Search Filters

When search is enabled the user can constrain the search via flags inside the message or persistent settings.

5.3.1 Inline flags parsed from the message, stripped before sending to Gemini:
- `--site:domain.com` restrict to a domain
- `--lang:fa|en|ar` restrict result language
- `--time:day|week|month|year` restrict freshness
- `--region:ir|us|gb|...` restrict region
- `--news` shortcut for `--time:day` plus news intent
- `--academic` prefer scholarly sources

5.3.2 These flags are translated into the Gemini system instruction as constraints, not into the Google Search tool config (the SDK does not yet expose all of these directly), so the model is told to prefer matching sources and to skip non-matching ones

5.3.3 Persistent defaults via `/filters` command: shows current defaults, lets user toggle each via inline keyboard

5.3.4 Acceptance: `قیمت طلا --site:tgju.org --time:day` returns answer that cites tgju.org from the last 24 hours

5.3.5 Risk: model may ignore constraints, mitigation is strict prompt wording plus post-filter on cited URLs

### 5.4 Output Formatting and "Drawing"

The user said "best drawing ways". For a text-only Telegram bot, "drawing" means rich, scannable formatting.

5.4.1 Support three reply formats, user-selectable via `/format` command:
- `compact`, one short paragraph, no headings, default
- `detailed`, structured with bullet sections (Summary, Details, Sources)
- `markdown`, full Telegram MarkdownV2 with bold key terms, bullet lists, and inline links

5.4.2 For `markdown` format use Telegram's MarkdownV2 parse mode, escape all reserved chars (`_*[]()~\`>#+-=|{}.!`) via a helper, never trust raw model output

5.4.3 For numerical answers (prices, scores, weather) the bot detects the pattern and renders a small ASCII or unicode-box "card":

```
┌─ قیمت دلار ─────────┐
│ خرید:   ۸۲٬۳۰۰ تومان │
│ فروش:   ۸۲٬۸۰۰ تومان │
│ تغییر:  ▲ ۰٫۴٪       │
└─ منبع: tgju.org ─────┘
```

5.4.4 Long answers (over 3500 chars) are split on paragraph boundaries, never mid-sentence, with `(۱/۳)` style page indicators

5.4.5 Source list at the bottom uses numbered footnote style `[1] title, url`, max 5 sources, deduplicated by domain

5.4.6 Emoji is allowed in headers but never required, off by default for English

5.4.7 Acceptance: `/format detailed` then asking a question returns a multi-section reply, `/format markdown` returns bolded headings with no escape errors

### 5.5 Privacy and Safety

5.5.1 Log only: timestamp, user_id (hashed with a random salt loaded from env), message length, search_enabled flag, response time, success or error code. NEVER log question or answer text.

5.5.2 Add a `/privacy` command that shows the user, in their language, exactly what is stored

5.5.3 Add a `/forget` command that wipes the user's in-memory state immediately

5.5.4 Add a content filter, both pre and post:
- Pre: block prompts that look like jailbreaks or attempts to extract the system prompt
- Post: block answers that contain instructions for weapons, self-harm, or content sexualizing minors

5.5.5 Add a swear and slur filter for outgoing text in both languages, configurable via `locales/badwords_fa.txt` and `locales/badwords_en.txt`, replace with `***`

5.5.6 No analytics third party, no Google Analytics, no Sentry without explicit opt-in

5.5.7 Acceptance: `journalctl -u bepors-bot` shows no question text, `/privacy` returns the policy in correct language

### 5.6 Rate Limiting and Abuse Protection

5.6.1 Tiers, all configurable via env:
- `DAILY_LIMIT=20` per user per UTC day
- `BURST_LIMIT=5` per user per minute
- `GLOBAL_LIMIT=10000` total per day across all users (safety cap)

5.6.2 When a global cap is hit, bot replies with a polite "service is at capacity, try again later" and logs an admin alert

5.6.3 Anti-spam: if a user sends more than 30 messages in 5 minutes, soft-block them for 1 hour, send one notice

5.6.4 Block list, env var `BLOCKED_USER_IDS=123,456`, instantly drop messages from those IDs

5.6.5 Acceptance: scripted test that fires 25 questions in 1 minute hits BURST_LIMIT and gets the polite throttle message

### 5.7 Admin Commands

Available only to user IDs in env `ADMIN_IDS=`.

5.7.1 `/stats`, total users today, total questions today, errors today, current global usage vs cap

5.7.2 `/broadcast <message>`, queued, throttled to 25 messages per second to respect Telegram limits, supports Farsi or English

5.7.3 `/block <user_id>` and `/unblock <user_id>`, runtime additions to the block list

5.7.4 `/setlimit <number>`, change DAILY_LIMIT at runtime without restart

5.7.5 Acceptance: non-admin users get "command not found" for these

### 5.8 Persistence Layer (light SQLite)

Replace the in-memory dict with SQLite so restarts do not lose state.

5.8.1 File: `data/bepors.db`, schema:
```sql
CREATE TABLE users (
    user_id INTEGER PRIMARY KEY,
    lang TEXT DEFAULT 'fa',
    search_enabled INTEGER DEFAULT 1,
    format TEXT DEFAULT 'compact',
    filters_json TEXT DEFAULT '{}',
    blocked INTEGER DEFAULT 0,
    created_at TEXT,
    last_seen TEXT
);
CREATE TABLE usage (
    user_id INTEGER,
    day TEXT,
    count INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, day)
);
CREATE TABLE events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT,
    user_hash TEXT,
    event TEXT,
    meta TEXT
);
```

5.8.2 Use stdlib `sqlite3` with WAL mode, no extra dependency

5.8.3 All writes go through a single `db.py` module with typed helpers

5.8.4 Daily backup script `backup.sh` that zips `data/bepors.db` to `/var/backups/bepors/`, called by a cron entry installed by `deploy.sh`

5.8.5 Acceptance: stop and start the service, user state and usage persist

### 5.9 Observability

5.9.1 Structured JSON logs via stdlib `logging` with a JSON formatter, one event per line

5.9.2 Health endpoint: spawn a tiny `aiohttp` server on `127.0.0.1:8088/health` that returns `{"ok": true, "uptime": ..., "users_today": ...}`

5.9.3 Optional: a simple `/admin/metrics` route on the same port behind a shared secret in env, returns Prometheus text format if `METRICS_ENABLED=true`

5.9.4 Acceptance: `curl 127.0.0.1:8088/health` on the server returns 200

### 5.10 Deployment Hardening

5.10.1 Run the bot under a dedicated non-root user `bepors`, `deploy.sh` creates it with `useradd -r -s /usr/sbin/nologin bepors`

5.10.2 Move install path to `/opt/bepors-bot`, owned by `bepors:bepors`, mode 750

5.10.3 systemd hardening directives:
```
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=/opt/bepors-bot/data
RestrictAddressFamilies=AF_INET AF_INET6
```

5.10.4 UFW firewall: allow 22 only from your IPs, deny everything else, the bot uses outbound only

5.10.5 Auto-update via unattended-upgrades for security patches

5.10.6 Acceptance: `systemctl status bepors-bot` shows green, `ps -u bepors` shows the python process, `id bepors` shows no shell

---

## 6. Tech Stack and Dependencies

- Python 3.11 or newer
- `python-telegram-bot==21.6`
- `google-genai>=0.3.0`
- `python-dotenv>=1.0.1`
- `aiohttp>=3.9` (for health endpoint)
- stdlib only for: sqlite3, logging, json, hashlib, asyncio
- No ORM, no Redis, no Docker in v1

Pin everything in `requirements.txt` with exact versions before deploy.

---

## 7. File Layout (target)

```
bepors-bot/
├── bot.py                 # entry point, handlers, app wiring
├── ai.py                  # Gemini call, grounding, prompt building
├── db.py                  # SQLite helpers
├── i18n.py                # locale loader and t() helper
├── filters.py             # inline flag parser, content filter, badwords
├── formatting.py          # compact/detailed/markdown renderers, card builder
├── ratelimit.py           # daily, burst, global limiters
├── admin.py               # admin commands, broadcast queue
├── health.py              # aiohttp health and metrics server
├── locales/
│   ├── fa.json
│   ├── en.json
│   ├── badwords_fa.txt
│   └── badwords_en.txt
├── data/
│   └── bepors.db          # created at first run
├── scripts/
│   ├── deploy.sh
│   ├── backup.sh
│   └── update.sh
├── bepors-bot.service
├── .env.example
├── .gitignore
├── requirements.txt
├── README.md
└── docs/
    └── PRD_SPEC_PLAN.md   # this file
```

---

## 8. SQL Changes

See section 5.8.1 for the full schema. All `CREATE TABLE` statements are wrapped in `IF NOT EXISTS`. There are no destructive migrations in v1.

---

## 9. Verification Checklist

Manual smoke test, run after deploy:

1. `/start` in Persian Telegram client, see Farsi welcome
2. `/start` in English client, see English welcome
3. `/lang en`, then `/help`, see English help
4. Ask "weather in Tehran today", get a sourced answer with the search-on footer
5. `/search off`, ask same question, see model-only answer with the warning
6. `/search on`, ask "قیمت دلار --site:tgju.org --time:day", verify cited URL is from tgju.org
7. `/format detailed`, ask any question, see structured sections
8. `/format markdown`, ask a question with special chars like `*` and `_`, verify no parse error
9. Send 25 questions in 1 minute, hit burst limit
10. Send 21 questions in a day, hit daily limit
11. `/usage`, see correct counters
12. `/privacy`, see privacy text in current language
13. `/forget`, see confirmation, then `/usage` shows reset
14. As admin, `/stats`, see numbers
15. Restart service, repeat `/usage`, verify persistence
16. `curl 127.0.0.1:8088/health` from the server, get 200
17. `journalctl -u bepors-bot --since "10 minutes ago" | grep -i question`, must return zero lines
18. Stop the service, edit `.env` to change `DAILY_LIMIT`, start, verify new limit applies

---

## 10. Files Changed Summary (to be filled during implementation)

| File | Change | Spec section |
|------|--------|--------------|
| bot.py | refactor into modules | 5.1, 5.2, 5.4, 5.5 |
| ai.py | new, Gemini wrapper | 5.2, 5.3 |
| db.py | new, SQLite layer | 5.8 |
| i18n.py | new | 5.1 |
| ... | ... | ... |

---

## 11. Risks and Rollback

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Gemini API quota exhausted | medium | high | Global cap (5.6.1), search toggle (5.2) |
| Telegram bans bot for spam | low | high | Burst limit (5.6.1), broadcast throttle (5.7.2) |
| Iranian gov blocks Hetzner IP for users | medium | medium | Telegram MTProto absorbs this, server is the one calling Google |
| Token leak | medium | high | `.gitignore`, `.env` mode 600, doc the rotation steps |
| Cost runaway from viral spike | medium | high | GLOBAL_LIMIT, alert via admin /stats |
| SQLite lock under high concurrency | low | medium | WAL mode, single-writer pattern via asyncio lock |

Rollback: keep v0 `bot.py` as `bot_v0.py`, systemd ExecStart can be flipped back in 30 seconds if v1 fails on prod.

---

## 12. Open Questions for the Maintainer

1. Do you want a "donate" command (crypto address) in v1 or v2?
2. Should the bot work in groups too, or DM only? (PRD assumes DM only.)
3. Do you want me to also build a simple admin dashboard (HTML page on the health endpoint) or are journalctl + /stats enough?
4. What is your target launch date? This affects whether 5.8 (SQLite) and 5.10 (hardening) ship in v1 or get pushed to v1.1.
5. Do you want the bot to refuse politically sensitive Iranian topics, answer them carefully, or answer freely with sources? Has legal and safety implications.

---

## 13. Definition of Done for v1

- All sections 5.1 through 5.10 implemented and ticked in section 9
- Zero question or answer text in any log
- README updated with new commands and architecture diagram
- Deploy script tested end to end on a fresh Hetzner box
- Two test users (one Farsi, one English) used the bot for one full day without crashes
- Cost per active user under $0.02 confirmed from a small sample
