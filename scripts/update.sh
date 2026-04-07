#!/usr/bin/env bash
# Pull new code from your local machine, restart the service.
# Usage: run from /opt/bepors-bot on the server after scp'ing new files.
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

cd "${APP_DIR}"
chown -R "${APP_USER}:${APP_USER}" "${APP_DIR}"
run_as_app_user "${APP_DIR}/venv/bin/pip" install -r "${APP_DIR}/requirements.txt"
systemctl restart bepors-bot
systemctl status bepors-bot --no-pager
