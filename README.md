# Bepors Bot

> A privacy-first Telegram search bot with real-time Google grounding, built for users who can't reach Google directly.

[![Tests](https://img.shields.io/badge/tests-81%20passing-brightgreen)](tests/)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Deploy](https://img.shields.io/badge/deploy-systemd-orange)](deploy.sh)

Bepors (`@Bepors_iraneman_bot` on Telegram) answers any question in any language using **Gemini 2.5 Flash** with built-in **Google Search grounding**, returning live data with tappable source citations. Designed for Persian-speaking users who face heavy internet filtering, but works for everyone.

```
سلام 👋 من بپرسم.
هر سوالی داری، جوابش رو زنده از گوگل برات می‌گیرم — به فارسی، انگلیسی یا هر زبانی.

🎁 روزانه ۲۰ سوال رایگان

[💵 قیمت دلار]  [🌤 هوای تهران]  [📰 خبر امروز]
```

---

## 🚀 Quick install (one line)

On a fresh Ubuntu/Debian server, SSH in as root and paste:

```bash
curl -fsSL https://raw.githubusercontent.com/MohammadShamchi/bepors-bot/main/install.sh | bash
```

(If you're not root, prefix with `sudo`: `... | sudo bash`.)

The installer will:

1. Install Python, set up a hardened systemd service running as a locked-down `bepors` user
2. Configure UFW (SSH only inbound), daily SQLite backups (14-day retention), unattended security upgrades
3. Open an interactive **TUI prompt** asking you for:
   - Your **Telegram bot token** — from [@BotFather](https://t.me/BotFather) (validated live via `getMe`)
   - Your **Telegram user ID** for admin access — optional, from [@userinfobot](https://t.me/userinfobot)
   - Your **Gemini API key** — free from [Google AI Studio](https://aistudio.google.com/api-keys)
4. Start the bot and confirm it's reachable

Total time: **~2 minutes** on a fresh Hetzner CX22.

Safe to re-run — pulls latest from `main`, pre-fills credential prompts with your current values. Useful as a "reconfigure" tool too.

---

## ✨ Features

### For users
- **Live Google Search grounding** on every question by default — answers reflect today's news, prices, weather, scores
- **One-shot search override** — prefix any message with `?` (force search ON) or `.` (force OFF)
- **Inline search filters** — `قیمت دلار --site:tgju.org --time:day --news` constrains the search
- **Persistent filter defaults** via `/filters` (interactive inline keyboard with state)
- **Bilingual** Farsi (default) + English, with `/lang` to switch and persist
- **Three reply formats** — compact, detailed (sectioned), or MarkdownV2
- **Tappable numbered source citations** under every answer
- **Per-line emoji enhancement** for price/score/weather KV blocks (font-safe, no parse_mode hacks)
- **Looping typing indicator** that survives long Gemini calls (no dead "is it working?" gap)
- **👍 / 👎 feedback** on every answer
- **Progressive tips** that teach power features after the 2nd / 5th / 10th successful answer
- **`/forget`** with explicit confirmation step (no accidental wipes)

### For operators
- **Privacy-first by design** — question and answer text are **never** logged. User IDs are SHA-256 hashed with a per-install salt for any event records
- **Per-user + burst + global rate limits** + sustained-flood soft-blocking
- **Daily admin error alert** when error rate spikes (10-min window, 30-min cooldown)
- **Admin commands** scoped to admin chats via `BotCommandScopeChat` so regular users never see them in their `/` menu:
  - `/stats` aggregate counts
  - `/users [N]` top users by lifetime activity
  - `/user <id>` full detail card with name + filters + status
  - `/broadcast`, `/block`, `/unblock`, `/setlimit`
- **SQLite persistence** in WAL mode with auto-migration on schema changes
- **Health endpoint** + optional **Prometheus metrics** on `127.0.0.1:8088`
- **Hardened systemd unit** — non-root service user, `ProtectSystem=strict`, `NoNewPrivileges`, `MemoryDenyWriteExecute`, etc.
- **Daily SQLite backups** with 14-day retention (cron-installed by `deploy.sh`)
- **One-shot deploy** — idempotent shell script sets up venv, user, systemd, UFW, unattended-upgrades

---

## 📦 Architecture

```
bepors-bot/
├── bot.py            # entry point + handler pipeline
├── ai.py             # Gemini wrapper (asyncio.to_thread)
├── db.py             # async SQLite layer (WAL mode)
├── ratelimit.py      # daily / burst / global limiters
├── filters.py        # flag parser + content safety + censor
├── formatting.py     # compact/detailed/markdown renderers + KV enhance
├── i18n.py           # locale loader (auto fa-digit conversion)
├── admin.py          # admin command handlers
├── health.py         # aiohttp /health + /metrics
├── locales/
│   ├── fa.json       # 67 Persian strings
│   ├── en.json       # 67 English strings (parity verified)
│   ├── badwords_fa.txt
│   └── badwords_en.txt
├── tests/            # 81 pytest tests, runs in 100ms
├── docs/PRD_SPEC_PLAN.md   # full v1 product spec
├── scripts/
│   ├── backup.sh     # daily SQLite backup (cron)
│   └── update.sh     # one-shot redeploy
├── deploy.sh         # one-shot Hetzner installer
├── bepors-bot.service
└── .env.example
```

The full v1 product spec lives in [`docs/PRD_SPEC_PLAN.md`](docs/PRD_SPEC_PLAN.md). The pipeline ordering rationale and privacy invariants are documented in [`CLAUDE.md`](CLAUDE.md).

---

## 🛠 Local development

```bash
git clone https://github.com/<your-username>/bepors-bot.git
cd bepors-bot

python3 -m venv venv
./venv/bin/pip install -r requirements.txt

cp .env.example .env
# Edit .env: set TELEGRAM_TOKEN (BotFather) and GEMINI_API_KEY
# (https://aistudio.google.com/apikey)

./venv/bin/python bot.py
```

### Running the test suite

```bash
./venv/bin/pip install -r requirements-dev.txt
./venv/bin/python -m pytest -q
```

Expect: **81 passed in ~100ms**.

### Verify health while running

```bash
curl 127.0.0.1:8088/health
```

---

## 🛠 Manual install (without the one-liner)

Tested on Ubuntu 24.04 (Hetzner CX23). Works on any Debian/Ubuntu box with `systemd`. Use this path if you want to audit `deploy.sh` line-by-line, or you've already cloned the repo locally and want to push it via `scp` instead of letting the installer pull from GitHub.

From your **local machine**:

```bash
scp -r bepors-bot root@<your-server-ip>:/opt/
```

Then SSH in and run the deploy script:

```bash
ssh root@<your-server-ip>
cd /opt/bepors-bot
chmod +x deploy.sh
./deploy.sh
```

The `deploy.sh` script is idempotent. It will:

1. Install Python 3, venv, pip, UFW, unattended-upgrades
2. Create a locked-down `bepors` service user (no shell, no home)
3. Set up the virtualenv and install requirements
4. Copy `.env.example` → `.env` (you edit afterwards to set real keys)
5. Install the hardened systemd unit
6. Install a daily SQLite backup cron (`/var/backups/bepors`, 14-day retention)
7. Enable UFW (SSH only inbound)
8. Enable unattended security upgrades
9. Start the service

After the first deploy, edit `/opt/bepors-bot/.env` with your real keys and `systemctl restart bepors-bot`.

### Verify it's running

```bash
systemctl status bepors-bot
journalctl -u bepors-bot -f      # live logs (one JSON object per line)
curl 127.0.0.1:8088/health
```

### Update the bot later

```bash
# from your local machine
rsync -az --exclude venv/ --exclude __pycache__/ --exclude data/bepors.db* \
  --exclude data/.log_salt --exclude .env \
  bepors-bot/ root@<your-server-ip>:/opt/bepors-bot/

ssh root@<your-server-ip> '/opt/bepors-bot/scripts/update.sh'
```

### Change the daily limit

- **Runtime** (resets on service restart): as admin, send `/setlimit 30` in Telegram.
- **Persistent**: edit `/opt/bepors-bot/.env`, set `DAILY_LIMIT=30`, then `systemctl restart bepors-bot`.

---

## 🔒 Privacy

Only the following is ever written to the database or logs:

| What | Where | Why |
|---|---|---|
| Telegram user ID | `users` table | Required for daily quotas + rate limits |
| Language preference | `users.lang` | Localized replies |
| Format / filter / search settings | `users.*`, `users.filters_json` | Personalization persistence |
| Per-day question count | `usage` table | Daily quota enforcement |
| Event type, question length, response time | `events` table (with hashed user_id) | Operational metrics |

**Question and answer text are never logged.** Users can `/forget` at any time to wipe their row + usage history.

The hashing salt is auto-generated on first run and persisted to `data/.log_salt` (mode 600). It is **not** committed to git (see `.gitignore`).

---

## 🛡 Security checklist before going live

1. Revoke any test tokens via @BotFather → `/revoke`, paste the new one into `.env`
2. Revoke test API keys at https://aistudio.google.com/apikey and create a fresh one
3. Confirm `chmod 600 /opt/bepors-bot/.env` (the deploy script does this automatically)
4. `systemctl restart bepors-bot`
5. **Verify the privacy invariant** holds:
   ```bash
   journalctl -u bepors-bot --since "10 min ago" | grep -iE 'question|answer'
   # → expect zero matches
   ```

---

## 📂 Configuration reference

All values configurable via `.env` (defaults shown):

```bash
TELEGRAM_TOKEN=                  # required — from @BotFather
GEMINI_API_KEY=                  # required — from Google AI Studio
GEMINI_MODEL=gemini-2.5-flash    # any Gemini model with grounding support

DAILY_LIMIT=20                   # questions per user per UTC day
BURST_LIMIT=5                    # questions per user per minute
GLOBAL_LIMIT=10000               # cap across all users per day

DB_PATH=data/bepors.db           # SQLite path (parent dir auto-created)

ADMIN_IDS=                       # comma-separated Telegram user IDs
BLOCKED_USER_IDS=                # comma-separated hard-blocked IDs

HEALTH_HOST=127.0.0.1            # health endpoint host
HEALTH_PORT=8088                 # health endpoint port

METRICS_ENABLED=false            # enable Prometheus /admin/metrics
METRICS_SECRET=                  # required if METRICS_ENABLED=true (X-Metrics-Secret header)

LOG_SALT=                        # leave empty to auto-generate
```

---

## 🤝 Contributing

PRs welcome. Before submitting:

1. Run the test suite: `./venv/bin/python -m pytest -q` (must stay 81/81 green)
2. `./venv/bin/python -m py_compile *.py`
3. **Never** introduce question/answer text into logs or DB columns. The privacy invariant is non-negotiable — it's why this project exists.
4. Keep `locales/fa.json` and `locales/en.json` at parity (every key in both languages).
5. New user-facing strings go through `i18n.t(key, lang, **kwargs)` — do not hard-code Farsi or English in handler code.

The `tests/` suite covers i18n digit conversion, filter parsing, content safety, formatting (incl. HTML escape + KV enhancement idempotency), rate limiting (burst/spam/daily/global), and the async DB layer.

---

## 📜 License

[MIT](LICENSE) © Mohammad Shamchi

---

## 🙏 Credits

Built with [python-telegram-bot](https://github.com/python-telegram-bot/python-telegram-bot), [google-genai](https://github.com/googleapis/python-genai), and [aiohttp](https://github.com/aio-libs/aiohttp).
