#!/usr/bin/env bash
#
# Bepors Bot — one-line installer
#
# Usage (on a fresh Ubuntu/Debian server, as root):
#
#   curl -fsSL https://raw.githubusercontent.com/MohammadShamchi/bepors-bot/main/install.sh | bash
#
# Or, if not already root:
#
#   curl -fsSL https://raw.githubusercontent.com/MohammadShamchi/bepors-bot/main/install.sh | sudo bash
#
# What it does:
#   1. Installs git + whiptail + curl
#   2. Clones (or pulls) the repo into /opt/bepors-bot
#   3. Runs deploy.sh — sets up venv, bepors service user, systemd unit,
#      UFW, daily backup cron, unattended-upgrades
#   4. Opens whiptail TUI dialogs to ask the user for:
#        - Telegram bot token (validated live via getMe)
#        - Telegram admin user ID (optional)
#        - Google Gemini API key
#   5. Writes them into /opt/bepors-bot/.env, restarts the service, verifies.
#
# Safe to re-run: pulls latest, pre-fills credential prompts with current values.

set -euo pipefail

REPO_URL="https://github.com/MohammadShamchi/bepors-bot.git"
INSTALL_DIR="/opt/bepors-bot"
APP_USER="bepors"
SERVICE="bepors-bot"

# ---- preflight ------------------------------------------------------------

if [[ $EUID -ne 0 ]]; then
    echo "ERROR: this installer must run as root."
    echo
    echo "Try:"
    echo "  curl -fsSL https://raw.githubusercontent.com/MohammadShamchi/bepors-bot/main/install.sh | sudo bash"
    exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
    echo "ERROR: this installer supports Debian/Ubuntu only (needs apt-get)."
    exit 1
fi

echo "==> Installing bootstrap packages (git, curl, whiptail)..."
apt-get update -qq
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    git curl ca-certificates whiptail >/dev/null

# ---- clone or update ------------------------------------------------------
#
# Three cases:
#   1. /opt/bepors-bot does not exist                    → fresh clone
#   2. /opt/bepors-bot exists and IS a git repo          → fetch + reset --hard
#   3. /opt/bepors-bot exists but NOT a git repo (e.g.   → convert in place via
#      pushed via scp/rsync from a previous deploy)        git init + fetch +
#                                                          reset --hard
#
# Case 3 is critical: if we did `rm -rf` first we'd nuke runtime data
# (data/bepors.db, data/.log_salt, .env). Instead we convert the dir to a git
# checkout in place. Untracked files (data/, .env) stay because they're listed
# in .gitignore so `git reset --hard` won't touch them.
#
# In both case 2 and case 3 the directory may be owned by the `bepors` service
# user (set up by a previous deploy.sh run) while we're running as root, which
# triggers git's CVE-2022-24765 "dubious ownership" check. We add a safe.directory
# exception so git will operate on it.

if [[ -d "$INSTALL_DIR" ]]; then
    git config --global --add safe.directory "$INSTALL_DIR"
fi

if [[ -d "$INSTALL_DIR/.git" ]]; then
    echo "==> Existing git install detected — pulling latest from origin/main..."
    git -C "$INSTALL_DIR" fetch --quiet origin main
    git -C "$INSTALL_DIR" reset --hard --quiet origin/main
elif [[ -d "$INSTALL_DIR" ]]; then
    echo "==> Existing non-git install detected — converting to git checkout in place..."
    cd "$INSTALL_DIR"
    git init -q -b main
    git remote remove origin 2>/dev/null || true
    git remote add origin "$REPO_URL"
    git fetch --quiet --depth 1 origin main
    # `reset --hard` overwrites tracked files but leaves untracked (data/, .env, db files) alone.
    git reset --hard --quiet origin/main
    cd - >/dev/null
else
    echo "==> Cloning repo into $INSTALL_DIR..."
    git clone --depth 1 --quiet "$REPO_URL" "$INSTALL_DIR"
fi

# ---- run the technical installer (idempotent) ----------------------------

echo "==> Running deploy.sh (venv, systemd, UFW, cron)..."
chmod +x "$INSTALL_DIR/deploy.sh"
[[ -d "$INSTALL_DIR/scripts" ]] && chmod +x "$INSTALL_DIR/scripts/"*.sh
bash "$INSTALL_DIR/deploy.sh"

# ---- credential prompts via whiptail -------------------------------------

ENV_FILE="$INSTALL_DIR/.env"

# Read current value of a key from the env file. Returns empty string if the
# key holds the .env.example placeholder so we don't pre-fill garbage.
read_env() {
    local key="$1"
    local val=""
    if [[ -f "$ENV_FILE" ]]; then
        val=$(grep -E "^${key}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true)
    fi
    case "$val" in
        put-your-telegram-bot-token-here|put-your-gemini-api-key-here)
            val=""
            ;;
    esac
    printf '%s' "$val"
}

CURRENT_TOKEN=$(read_env TELEGRAM_TOKEN)
CURRENT_API_KEY=$(read_env GEMINI_API_KEY)
CURRENT_ADMIN=$(read_env ADMIN_IDS)

export NEWT_COLORS='root=,blue'

whiptail --backtitle "Bepors Bot Installer" \
    --title "Welcome" --msgbox \
"Welcome to Bepors Bot!

I'll guide you through setting up 3 credentials:

  1. Telegram bot token  (from @BotFather)
  2. Admin user ID       (optional, for /stats /users /broadcast)
  3. Gemini API key      (free from Google AI Studio)

Press OK to continue." 16 60

# ---- 1/3: Telegram bot token (validated via getMe) -----------------------

BOT_USERNAME=""
while true; do
    set +e
    TELEGRAM_TOKEN=$(whiptail --backtitle "Bepors Bot Installer" \
        --title "1/3 — Telegram Bot Token" --inputbox \
"Paste your Telegram bot token below.

Don't have one? Open Telegram and message @BotFather:
  1. Send  /newbot
  2. Choose a name and username for your bot
  3. Copy the token (looks like 1234567890:ABCdef...)
  4. Paste it here" \
        17 70 "$CURRENT_TOKEN" 3>&1 1>&2 2>&3)
    rc=$?
    set -e
    [[ $rc -ne 0 ]] && { echo "Cancelled."; exit 1; }

    if [[ -z "$TELEGRAM_TOKEN" ]]; then
        whiptail --msgbox "Token cannot be empty." 8 40
        continue
    fi

    # Validate live by calling Telegram getMe
    response=$(curl -fsS --max-time 10 \
        "https://api.telegram.org/bot${TELEGRAM_TOKEN}/getMe" 2>/dev/null || echo "")
    if echo "$response" | grep -q '"ok":true'; then
        BOT_USERNAME=$(echo "$response" \
            | grep -oE '"username":"[^"]+"' | head -1 | cut -d'"' -f4)
        whiptail --msgbox "Token verified!\n\nBot: @${BOT_USERNAME}" 9 50
        break
    fi

    whiptail --title "Invalid Token" --yesno \
        "Telegram rejected this token.\n\nTry again?" 9 50 || exit 1
done

# ---- 2/3: Admin user ID (optional) ---------------------------------------

set +e
ADMIN_IDS=$(whiptail --backtitle "Bepors Bot Installer" \
    --title "2/3 — Admin User ID (optional)" --inputbox \
"Optionally set your Telegram user ID to unlock admin commands:
  /stats  /users  /user  /broadcast  /block  /setlimit

Get your ID by messaging @userinfobot on Telegram —
it replies with your numeric ID (like 123456789).

Leave blank to skip — you can always add it later by editing
$ENV_FILE and restarting the service." \
    18 70 "$CURRENT_ADMIN" 3>&1 1>&2 2>&3)
rc=$?
set -e
[[ $rc -ne 0 ]] && ADMIN_IDS="$CURRENT_ADMIN"

# ---- 3/3: Gemini API key (syntax-checked) --------------------------------

while true; do
    set +e
    GEMINI_API_KEY=$(whiptail --backtitle "Bepors Bot Installer" \
        --title "3/3 — Gemini API Key" --inputbox \
"Paste your Google Gemini API key below.

Free tier — get one in 30 seconds:

  https://aistudio.google.com/api-keys

  1. Sign in with a Google account
  2. Click 'Create API key'
  3. Copy the key (starts with AIza...)
  4. Paste it here" \
        19 70 "$CURRENT_API_KEY" 3>&1 1>&2 2>&3)
    rc=$?
    set -e
    [[ $rc -ne 0 ]] && { echo "Cancelled."; exit 1; }

    if [[ -z "$GEMINI_API_KEY" ]]; then
        whiptail --msgbox "API key cannot be empty." 8 40
        continue
    fi
    if [[ "$GEMINI_API_KEY" =~ ^AIza[A-Za-z0-9_-]{30,}$ ]]; then
        break
    fi
    whiptail --title "Invalid Format" --yesno \
        "That doesn't look like a Gemini API key.\nIt should start with AIza... and be ~39 chars.\n\nTry again?" \
        11 60 || exit 1
done

# ---- write to .env -------------------------------------------------------

# We use | as the sed delimiter because none of TELEGRAM_TOKEN / GEMINI_API_KEY
# / ADMIN_IDS contain a literal | character (per their respective formats).
sed -i "s|^TELEGRAM_TOKEN=.*|TELEGRAM_TOKEN=${TELEGRAM_TOKEN}|" "$ENV_FILE"
sed -i "s|^GEMINI_API_KEY=.*|GEMINI_API_KEY=${GEMINI_API_KEY}|" "$ENV_FILE"
sed -i "s|^ADMIN_IDS=.*|ADMIN_IDS=${ADMIN_IDS}|" "$ENV_FILE"
chown "${APP_USER}:${APP_USER}" "$ENV_FILE"
chmod 600 "$ENV_FILE"

# ---- restart and verify --------------------------------------------------

systemctl reset-failed "$SERVICE" 2>/dev/null || true
systemctl restart "$SERVICE"
sleep 4

if systemctl is-active --quiet "$SERVICE"; then
    whiptail --backtitle "Bepors Bot Installer" \
        --title "✓ Installation Complete!" --msgbox \
"Bepors Bot is now running!

Bot: @${BOT_USERNAME}
Status: active
Health: http://127.0.0.1:8088/health

Useful commands:
  systemctl status ${SERVICE}
  journalctl -u ${SERVICE} -f
  curl 127.0.0.1:8088/health

Open Telegram and message @${BOT_USERNAME} to test it!

If you set an admin user ID, message your bot from that
account and try /stats or /users." 22 64
else
    whiptail --backtitle "Bepors Bot Installer" \
        --title "⚠ Service did not start" --msgbox \
"The service failed to become active. Check the logs:

  journalctl -u ${SERVICE} -n 50

Your config is saved at:
  $ENV_FILE

Edit it and restart with:
  systemctl restart ${SERVICE}" 15 64
    exit 1
fi
