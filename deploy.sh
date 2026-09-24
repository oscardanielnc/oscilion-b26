#!/usr/bin/env bash
# deploy.sh: update Oscilion and restart the services. One command.
# Usage (on the VM, from any directory):
#   bash /opt/oscilion/deploy.sh
# Does not need to run under sudo: it uses sudo internally only where required.
set -euo pipefail

APP_DIR="/opt/oscilion"
APP_USER="oscilion"
PY="${APP_DIR}/.venv/bin/python"
PIP="${APP_DIR}/.venv/bin/pip"
ASU=(sudo -u "$APP_USER")          # run as the owner of the repo/venv

cd "$APP_DIR"
sudo git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true
"${ASU[@]}" git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true

echo ""
echo "======================================================="
echo "  OSCILION DEPLOY  -  $(date '+%Y-%m-%d %H:%M') UTC"
echo "======================================================="

echo ""
echo "[1/6] Pulling from GitHub..."
"${ASU[@]}" git pull --ff-only
echo "  OK code updated"

echo ""
echo "[2/6] Python dependencies..."
"${ASU[@]}" "$PIP" install --quiet -r requirements.txt 2>/dev/null || true
echo "  OK dependencies"

echo ""
echo "[3/6] Smoke check (package import)..."
if "${ASU[@]}" "$PY" -c "import config; from oscilion import orchestrator; from oscilion.live import monitor, forward, signals; from oscilion.data import fetch; from oscilion.strategies import all_assignments; from oscilion.api import app" 2>/dev/null; then
    echo "  OK package imports"
else
    echo "  FAIL import error, aborting deploy (nothing restarted)"; exit 1
fi

echo ""
echo "[4/6] Backfill of new symbols (idempotent; skips already seeded ones)..."
if "${ASU[@]}" "$PY" -m oscilion.data backfill; then
    echo "  OK history ready for the whole core"
else
    # Do not restart: starting with symbols that have no history would run blind.
    echo "  FAIL backfill failed, aborting"; exit 1
fi

echo ""
echo "[5/6] Restarting orchestrator (oscilion)..."
sudo systemctl restart oscilion && sleep 2
[ "$(systemctl is-active oscilion 2>/dev/null)" = "active" ] \
    && echo "  OK oscilion active" \
    || { echo "  FAIL oscilion did not start: journalctl -u oscilion -n 30"; }

echo ""
echo "[6/6] Restarting dashboard (oscilion-api)..."
sudo systemctl restart oscilion-api && sleep 2
[ "$(systemctl is-active oscilion-api 2>/dev/null)" = "active" ] \
    && echo "  OK oscilion-api active (dashboard: SSH tunnel to 127.0.0.1:8787)" \
    || { echo "  FAIL oscilion-api did not start: journalctl -u oscilion-api -n 30"; }

echo ""
echo "======================================================="
echo "  oscilion:     $(systemctl is-active oscilion     2>/dev/null || echo '?')"
echo "  oscilion-api: $(systemctl is-active oscilion-api 2>/dev/null || echo '?')"
echo "======================================================="
echo ""
