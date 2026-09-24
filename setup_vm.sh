#!/usr/bin/env bash
# Oscilion initial provisioning on the VM (run ONCE, as root/sudo).
# Idempotent. Clones the repo, creates the venv, seeds history, sets the forward
# inception and installs the systemd services.
set -euo pipefail

APP_DIR=/opt/oscilion
APP_USER=oscilion
ENV_FILE=/etc/oscilion.env
REPO=${OSCILION_REPO:-https://github.com/oscardanielnc/oscilion-b26.git}
PYBIN=${PYTHON:-python3}          # override: PYTHON=python3.12 sudo -E bash setup_vm.sh

echo "==> Oscilion :: setup_vm"

# 1) Service user
if ! id "$APP_USER" &>/dev/null; then
  useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
fi

# 2) System dependencies (apt / dnf / yum)
if command -v apt-get &>/dev/null; then
  apt-get update -y
  apt-get install -y python3 python3-venv python3-pip git
elif command -v dnf &>/dev/null; then
  dnf install -y python3.11 python3.11-pip git    # Oracle Linux / RHEL (leaves the system python3 alone)
elif command -v yum &>/dev/null; then
  yum install -y python3.11 python3.11-pip git
fi
# avoid git's "dubious ownership" error
git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true

# Pick an interpreter >= 3.10. Do not use the system python3 if it is older
# (e.g. 3.9 on Oracle Linux): other services on the VM depend on it.
if [ -z "${PYTHON:-}" ]; then
  for c in python3.12 python3.11 python3.10 python3; do
    if command -v "$c" &>/dev/null && "$c" -c 'import sys; exit(0 if sys.version_info>=(3,10) else 1)' 2>/dev/null; then
      PYBIN="$c"; break
    fi
  done
fi
if ! "$PYBIN" -c 'import sys; exit(0 if sys.version_info>=(3,10) else 1)' 2>/dev/null; then
  echo "ERROR: Python >= 3.10 is required. Install python3.11 (dnf install -y python3.11)."; exit 1
fi

# 3) Code
if [ ! -d "$APP_DIR/.git" ]; then
  echo "==> cloning $REPO"
  git clone "$REPO" "$APP_DIR"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# 4) Virtualenv + deps
echo "==> Python: $($PYBIN --version)"
sudo -u "$APP_USER" "$PYBIN" -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# 5) Env file (never overwritten). Forward inception = NOW, so the forward test
#    only ever sees unseen data.
if [ ! -f "$ENV_FILE" ]; then
  echo "==> creating $ENV_FILE"
  cp "$APP_DIR/example.env" "$ENV_FILE"
  NOW_MS=$(($(date +%s) * 1000))
  echo "OSCILION_FORWARD_INCEPTION_MS=$NOW_MS" >> "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "    forward inception set to $NOW_MS (now)"
fi

# 6) Seed history (baseline for forward validation). ~5-10 min.
# The env file is not sourced (core symbols are config.py's default), which avoids
# permission issues. cwd=APP_DIR so the oscilion package resolves.
echo "==> seeding history (3 years), this takes a few minutes"
( cd "$APP_DIR" && sudo -u "$APP_USER" .venv/bin/python -m oscilion.data sync --days 1095 ) \
  || echo "  (on failure, re-run: cd $APP_DIR && sudo -u $APP_USER .venv/bin/python -m oscilion.data sync --days 1095)"

# 7) systemd services
echo "==> installing systemd units"
cp "$APP_DIR/oscilion.service" /etc/systemd/system/oscilion.service
cp "$APP_DIR/oscilion-api.service" /etc/systemd/system/oscilion-api.service
systemctl daemon-reload
systemctl enable oscilion.service oscilion-api.service
systemctl start oscilion.service oscilion-api.service

echo "==> DONE. Status:"
systemctl is-active oscilion.service oscilion-api.service || true
echo "    API/dashboard on http://127.0.0.1:8787 (open an SSH tunnel to view it)"
