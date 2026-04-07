# 📣 Bepors Bot — launch & community posts

Ready-to-paste copy for X (Twitter), LinkedIn, Reddit, Hacker News, and Persian-speaking channels. Pick the variant that fits the platform.

---

## 🐦 X / Twitter

### Variant A — short, English (260 chars)

> I built **Bepors**, an open-source Telegram search bot for people who can't reach Google directly.
>
> ✅ Live answers from Google Search
> ✅ Bilingual (Persian + English)
> ✅ Never logs your questions
> ✅ One-line install on any Ubuntu server
>
> github.com/MohammadShamchi/bepors-bot

### Variant B — short, Persian (240 chars)

> یه ربات تلگرامی متن‌باز ساختم به اسم **بپرس** — برای کسایی که توی ایران نمی‌تونن مستقیم به گوگل وصل بشن.
>
> ✅ جواب زنده از گوگل
> ✅ فارسی + انگلیسی
> ✅ هیچ سوالی ذخیره نمی‌شه
> ✅ با یه دستور روی سرور خودت نصب می‌شه
>
> github.com/MohammadShamchi/bepors-bot

### Variant C — story-style thread (English, 5 tweets)

**Tweet 1/5**
> Iranian users can't reach Google, ChatGPT, Perplexity, or Claude without VPN. VPNs are slow, expensive, and unreliable.
>
> Telegram still works via MTProto proxies.
>
> So I built a Telegram bot that bridges the two. 🧵

**Tweet 2/5**
> Meet **Bepors** — an open-source Telegram search bot powered by Gemini 2.5 Flash with live Google Search grounding.
>
> Send any question (in any language), get an answer with sources. No VPN, no subscription, no logging.

**Tweet 3/5**
> What makes it different:
>
> 🔓 Open-source — every line on GitHub
> 🔒 Privacy-first — question/answer text NEVER logged
> 🌐 Self-hostable — run your own copy with one command
> 🇮🇷 Bilingual Farsi + English by default
> ⚡ 81-test suite, hardened systemd unit

**Tweet 4/5**
> Self-hosting is the killer feature. On any Ubuntu server, paste:
>
> `curl -fsSL https://raw.githubusercontent.com/MohammadShamchi/bepors-bot/main/install.sh | bash`
>
> An interactive prompt asks for your bot token + Gemini key. Done in ~2 minutes.

**Tweet 5/5**
> If you're someone who builds tools for people in censored regions, fork it. If you're someone who needs it, run it.
>
> Either way, please share. Every self-hosted instance is one more independent path to information.
>
> ⭐ github.com/MohammadShamchi/bepors-bot

---

## 💼 LinkedIn

### Long-form post (English)

> **I built an open-source Telegram bot to help Iranians (and anyone behind a firewall) reach the modern internet.**
>
> The problem: in Iran, accessing Google Search, ChatGPT, Claude, Perplexity, or any major AI tool requires a VPN. VPNs are expensive, unreliable, and constantly blocked. For most people, that means losing access to the basic act of asking a question and getting a sourced answer.
>
> Telegram, however, still works via MTProto proxies. So I built **Bepors** — a bot that bridges the two.
>
> 𝗛𝗼𝘄 𝗶𝘁 𝘄𝗼𝗿𝗸𝘀
> You message the bot in Telegram. It calls Gemini 2.5 Flash with Google Search grounding. You get a sourced, live answer back — in Persian, English, or any language. No VPN required.
>
> 𝗪𝗵𝗮𝘁'𝘀 𝘀𝗽𝗲𝗰𝗶𝗮𝗹
> • 🔓 𝗙𝘂𝗹𝗹𝘆 𝗼𝗽𝗲𝗻-𝘀𝗼𝘂𝗿𝗰𝗲 — every line on GitHub, MIT licensed
> • 🔒 𝗣𝗿𝗶𝘃𝗮𝗰𝘆-𝗳𝗶𝗿𝘀𝘁 — question and answer text are *never* logged. User IDs are SHA-256 hashed with a per-install salt
> • 🌐 𝗦𝗲𝗹𝗳-𝗵𝗼𝘀𝘁𝗮𝗯𝗹𝗲 — one command on a $4/month Ubuntu server gets you your own private instance
> • 🇮🇷 𝗕𝗶𝗹𝗶𝗻𝗴𝘂𝗮𝗹 — Persian default, English opt-in via /lang
> • ⚡ 𝗛𝗮𝗿𝗱𝗲𝗻𝗲𝗱 — non-root systemd service, ProtectSystem=strict, daily SQLite backups, UFW, unattended security upgrades, 81-test suite
> • 🎛️ 𝗥𝗶𝗰𝗵 𝗳𝗲𝗮𝘁𝘂𝗿𝗲𝘀 — search filters (--site, --time, --news, --academic), interactive /filters keyboard, three reply formats, progressive teaching tips, /filters /broadcast /stats admin tools
>
> 𝗧𝗵𝗲 𝗶𝗻𝘀𝘁𝗮𝗹𝗹 𝗲𝘅𝗽𝗲𝗿𝗶𝗲𝗻𝗰𝗲
> ```
> curl -fsSL https://raw.githubusercontent.com/MohammadShamchi/bepors-bot/main/install.sh | bash
> ```
> Two minutes, three TUI prompts (Telegram token, optional admin ID, Gemini API key with a clickable link to Google AI Studio), done. No editing config files, no manual restart, the installer validates your token live and tells you the bot username before exiting.
>
> 𝗪𝗵𝘆 𝗜'𝗺 𝘀𝗵𝗮𝗿𝗶𝗻𝗴 𝘁𝗵𝗶𝘀
> Tools that help people circumvent censorship don't scale through me. They scale through you. If you have an Ubuntu server, please consider running a copy and sharing the bot link with your network. Every independent instance is one more path to information that doesn't depend on any single point of failure.
>
> If you're a developer, the code is welcoming for contributors. The whole codebase is 1,900 lines of Python with an 81-test suite that runs in 100ms. Persian/English locale parity is enforced. Adding a new language is one PR.
>
> 𝗥𝗲𝗽𝗼: github.com/MohammadShamchi/bepors-bot
>
> Star it if it's useful. Fork it if you want to. Run it if you can. ❤️
>
> #OpenSource #Privacy #Iran #DigitalRights #Telegram #Python #AI

### Short-form LinkedIn (200 words)

> I built **Bepors**, an open-source Telegram search bot for people behind firewalls.
>
> Iranian users can't reach Google or ChatGPT without a VPN. Telegram still works. Bepors bridges them.
>
> Send a question → get a live answer from Google Search via Gemini 2.5 Flash → with sources, in any language. No VPN, no subscription, no logging.
>
> What sets it apart:
> - Fully open source, MIT licensed
> - Question and answer text are NEVER logged (privacy invariant in code)
> - One-command self-host on any $4/month Ubuntu server
> - Hardened systemd, 81-test suite, daily backups
> - Persian default, English opt-in
>
> 𝗜𝗻𝘀𝘁𝗮𝗹𝗹:
> `curl -fsSL https://raw.githubusercontent.com/MohammadShamchi/bepors-bot/main/install.sh | bash`
>
> Three TUI prompts (Telegram token, admin ID, Gemini key), 2 minutes, done.
>
> If you have a server, please run a copy and share with people who need it. Tools against censorship scale through community, not through one operator.
>
> ⭐ github.com/MohammadShamchi/bepors-bot
>
> #OpenSource #Privacy #DigitalRights #Iran

---

## 🤖 Reddit

### r/selfhosted, r/opensource, r/Iran (English)

**Title**: I built a privacy-first, self-hostable Telegram search bot for people behind firewalls — one-line install, never logs your questions

**Body**:
> Hey folks 👋
>
> I've been working on **Bepors**, an open-source Telegram bot that gives users live Google Search results via Gemini 2.5 Flash — designed primarily for Iranian users who can't reach Google or ChatGPT directly, but works for anyone.
>
> The killer feature is the **one-line installer**. On a fresh Ubuntu server:
>
> ```
> curl -fsSL https://raw.githubusercontent.com/MohammadShamchi/bepors-bot/main/install.sh | bash
> ```
>
> ...sets up the whole stack in ~2 minutes: hardened systemd service running as a locked-down user, UFW configured, daily SQLite backups, unattended security upgrades, and a TUI wizard at the end that prompts you for the three credentials (Telegram bot token, optional admin ID, Gemini API key).
>
> **What's in it**:
> - 🔒 Privacy invariant in code: question and answer text are **never** logged. User IDs are SHA-256 hashed with a per-install salt.
> - 🌐 Bilingual Persian + English with auto digit conversion (`۲۰` not `20` for Farsi)
> - 🎛️ Search filters (`--site:`, `--time:`, `--news`, `--academic`)
> - 📊 Admin commands scoped per-chat so regular users never see them in their `/` menu (`/stats`, `/users`, `/user <id>`, `/broadcast`, `/setlimit`, `/block`)
> - 💬 Interactive `/filters` keyboard, progressive teaching tips after 2nd / 5th / 10th answer, 👍/👎 feedback on every reply
> - 🛡️ Hardened systemd: non-root user, `ProtectSystem=strict`, `NoNewPrivileges`, `MemoryDenyWriteExecute`
> - 🧪 81 pytest tests, runs in 100ms
> - 🤖 GitHub Actions CI on Python 3.11 + 3.12
>
> Self-hosting cost: ~$4/month for the server, free Gemini API tier covers most usage.
>
> If you run it on your own server and share the bot link with your network, you're literally giving people access to information they otherwise can't reach. That's the goal.
>
> Repo: github.com/MohammadShamchi/bepors-bot
>
> Happy to answer questions in the comments. Code review welcome — especially around the privacy invariant.

---

## 🟠 Hacker News

### Show HN title

> Show HN: Bepors – Self-hostable Telegram search bot for people behind firewalls

### Show HN body

> Hi HN — I built Bepors, a Telegram search bot that's specifically designed for people who can't reach Google or major AI services directly. Iran is the primary target audience but it works anywhere.
>
> The technical interesting bits:
>
> 1. **Privacy invariant enforced in code**: question and answer text NEVER touch the database or logs. The only event-level data stored is hashed user IDs (SHA-256 + per-install salt), event type, message length, and response time. There's no admin command — anywhere — that would reveal a user's question text, because the text simply isn't kept.
>
> 2. **One-line installer with TUI prompts**: `curl ... | bash` does the whole stack on a fresh Ubuntu box (apt deps, bepors service user, venv, hardened systemd unit, UFW, daily backups, unattended-upgrades), then runs whiptail dialogs for the three credentials. Idempotent — re-running upgrades in place and pre-fills credential prompts from existing .env. Handles three install states cleanly: fresh server, existing git checkout, and (the tricky one) existing rsync/scp install which it converts to a git checkout in place without losing runtime data.
>
> 3. **Stack is intentionally boring**: Python 3.11+, python-telegram-bot, google-genai, aiohttp, stdlib sqlite3 (WAL mode). No ORM, no Redis, no Docker. ~1,900 lines of Python total. 81 pytest tests in 100ms.
>
> 4. **Search grounding is first-class**: by default every question goes through Google Search via Gemini's grounding tool, with tappable HTML source citations under every answer. The user can override per-message with `?` (force search on) / `.` (force off) prefixes, or set persistent filters via an interactive `/filters` keyboard.
>
> Why I built it: the existing landscape for Iranians is "use a VPN" which means slow, expensive, and constantly broken. Telegram is one of the few things that still works reliably via MTProto proxies. Bridging Telegram to a real search backend gives people their basic access to information back without asking them to fight the network.
>
> Repo: https://github.com/MohammadShamchi/bepors-bot
>
> If you have a $4/month VPS lying around, please consider running a copy and sharing the bot link with people who need it. Decentralization is the whole point.
>
> Code review and PR welcome — especially the parts that touch the privacy invariant.

---

## 📨 Telegram channel / Persian community announcement

### کانال‌های فارسی تلگرام

> 📣 **یه ربات جدید آماده شد: بپرس**
>
> یه ربات تلگرامی open-source که هر سوالی داری، با اطلاعات زنده از گوگل برات جواب می‌ده. به فارسی، انگلیسی یا هر زبانی.
>
> 🔓 کاملاً رایگان و متن‌باز
> 🔒 هیچ سوالی ذخیره نمی‌شه — حتی توی لاگ‌ها
> 🌐 بدون فیلترشکن کار می‌کنه
> ⚡ روزانه ۲۰ سوال رایگان (محدودیت قابل تغییر)
>
> اگه ادمین یه کانال یا گروه هستی و سرور داری، می‌تونی **با یه دستور** یه نسخه‌ی شخصی از این ربات رو روی سرور خودت اجرا کنی و با کامیونیتی‌ت به اشتراک بذاری:
>
> ```
> curl -fsSL https://raw.githubusercontent.com/MohammadShamchi/bepors-bot/main/install.sh | bash
> ```
>
> ⭐ مخزن: github.com/MohammadShamchi/bepors-bot
> 📖 راهنمای فارسی: github.com/MohammadShamchi/bepors-bot/blob/main/docs/HELP_FA.md
>
> هر چه بیشتر کاربر و میزبان داشته باشیم، دسترسی به اطلاعات آزادتر می‌شه. لطفاً با دوست‌هایی که نیاز دارن به اشتراک بذارین.

---

## 🎯 Tips for posting

1. **Always star your own repo first** so anyone who clicks gets the social proof of `1+ stars` instead of `0`
2. **Pin the repo on your GitHub profile** so visitors find it
3. **Add topics to the repo**: `telegram-bot`, `gemini`, `persian`, `iran`, `chatbot`, `privacy`, `self-hosted`, `python` — these surface the project in GitHub search
4. **Post timing**: weekday mornings (9-11am Tehran time, 8-10am CET) for maximum Iranian engagement
5. **Engage with replies** — the first 24 hours are when the algorithm decides whether to push it
6. **Follow up in 2-3 days** with usage stats or a feature update — keeps momentum
7. **Cross-post to /r/selfhosted** for the self-hosting angle and /r/opensource for the OSS angle

---

## ⚠ Before you post

Run through this checklist:

- [ ] Tokens in your prod server's `.env` are **rotated** (the original tokens were pasted in chat history during setup)
- [ ] You've **personally tested** the one-liner on a fresh server (or trust the e2e test we ran on prod)
- [ ] The repo has at least one star (yours)
- [ ] The repo `About` section has a description and the relevant topics
- [ ] You can answer "what's your bot username?" — link people to it
- [ ] You're ready to handle inbound issues / questions for the next 24-48 hours
