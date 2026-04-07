#!/usr/bin/env bash
# Run this ONCE (or on every update) on the Hetzner server as root,
# from inside /opt/bepors-bot. Idempotent.
set -euo pipefail

APP_DIR=/opt/bepors-bot
APP_USER=bepors

run_as_app_user() {
  if command -v runuser >/dev/null 2>&1; then
    runuser -u "${APP_USER}" -- "$@"
  else
    su -s /bin/bash "${APP_USER}" -c "$(printf '%q ' "$@")"
  fi
}

echo "==> Installing system packages..."
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  python3 python3-venv python3-pip sqlite3 ufw unattended-upgrades

echo "==> Creating service user '${APP_USER}' (if missing)..."
if ! id "${APP_USER}" >/dev/null 2>&1; then
  useradd -r -s /usr/sbin/nologin -d "${APP_DIR}" "${APP_USER}"
fi

echo "==> Setting up directory ownership..."
mkdir -p "${APP_DIR}/data" /var/backups/bepors
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
chmod 750 "${APP_DIR}"

echo "==> Creating virtualenv..."
if [ ! -d "${APP_DIR}/venv" ]; then
  run_as_app_user python3 -m venv "${APP_DIR}/venv"
fi
run_as_app_user "${APP_DIR}/venv/bin/pip" install --upgrade pip
run_as_app_user "${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"

echo "==> Setting up .env (edit it if you need to change keys)..."
if [ ! -f "${APP_DIR}/.env" ]; then
  cp "${APP_DIR}/.env.example" "${APP_DIR}/.env"
fi
chown "${APP_USER}:${APP_USER}" "${APP_DIR}/.env"
chmod 600 "${APP_DIR}/.env"

echo "==> Installing systemd service..."
cp "${APP_DIR}/bepors-bot.service" /etc/systemd/system/bepors-bot.service
systemctl daemon-reload
systemctl enable bepors-bot

echo "==> Installing daily backup cron..."
chmod +x "${APP_DIR}/scripts/backup.sh"
cat > /etc/cron.d/bepors-backup <<EOF
0 3 * * * root ${APP_DIR}/scripts/backup.sh
EOF

echo "==> Enabling UFW (SSH only inbound)..."
if ! ufw status | grep -q "Status: active"; then
  ufw default deny incoming
  ufw default allow outgoing
  ufw allow 22/tcp
  yes | ufw enable || true
fi

echo "==> Enabling unattended-upgrades..."
dpkg-reconfigure -f noninteractive unattended-upgrades || true

echo "==> Starting service..."
systemctl restart bepors-bot

echo ""
echo "==> Done. Check status with:"
echo "    systemctl status bepors-bot"
echo "    journalctl -u bepors-bot -f"
echo "    curl 127.0.0.1:8088/health"
