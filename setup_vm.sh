#!/usr/bin/env bash
# Oscilion — provisión inicial en la VM Oracle (ejecutar UNA vez, como root/sudo).
# Idempotente. Clona el repo, crea venv, siembra histórico, fija inception y
# deja los servicios systemd listos.
set -euo pipefail

APP_DIR=/opt/oscilion
APP_USER=oscilion
ENV_FILE=/etc/oscilion.env
REPO=${OSCILION_REPO:-https://github.com/oscardanielnc/oscilion-b26.git}
PYBIN=${PYTHON:-python3}          # override: PYTHON=python3.12 sudo -E bash setup_vm.sh

echo "==> Oscilion :: setup_vm"

# 1) Usuario de servicio
if ! id "$APP_USER" &>/dev/null; then
  useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
fi

# 2) Dependencias del sistema (multi-distro: apt / dnf / yum)
if command -v apt-get &>/dev/null; then
  apt-get update -y
  apt-get install -y python3 python3-venv python3-pip git
elif command -v dnf &>/dev/null; then
  dnf install -y python3 python3-pip git          # Oracle Linux / RHEL / Fedora
elif command -v yum &>/dev/null; then
  yum install -y python3 python3-pip git
fi
# marcar el repo como seguro para git (evita "dubious ownership")
git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true

# 3) Código
if [ ! -d "$APP_DIR/.git" ]; then
  echo "==> clonando $REPO"
  git clone "$REPO" "$APP_DIR"
fi
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# 4) Virtualenv + deps  (requiere Python ≥ 3.10)
echo "==> Python: $($PYBIN --version)"
sudo -u "$APP_USER" "$PYBIN" -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# 5) Env file (no sobreescribir). Fija inception del forward = AHORA (datos no vistos).
if [ ! -f "$ENV_FILE" ]; then
  echo "==> creando $ENV_FILE"
  cp "$APP_DIR/example.env" "$ENV_FILE"
  NOW_MS=$(($(date +%s) * 1000))
  echo "OSCILION_FORWARD_INCEPTION_MS=$NOW_MS" >> "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "    inception forward fijado a $NOW_MS (ahora)"
fi

# 6) Semilla de histórico (para el baseline de validación forward). ~5-10 min.
echo "==> sembrando histórico (3 años) — esto tarda unos minutos"
sudo -u "$APP_USER" bash -c "cd $APP_DIR && set -a && . $ENV_FILE && set +a && \
  .venv/bin/python -m oscilion.data sync --days 1095" || echo "  (si falla, re-correr: deploy luego data sync)"

# 7) Servicios systemd
echo "==> instalando units systemd"
cp "$APP_DIR/oscilion.service" /etc/systemd/system/oscilion.service
cp "$APP_DIR/oscilion-api.service" /etc/systemd/system/oscilion-api.service
systemctl daemon-reload
systemctl enable oscilion.service oscilion-api.service
systemctl start oscilion.service oscilion-api.service

echo "==> LISTO. Estado:"
systemctl is-active oscilion.service oscilion-api.service || true
echo "    API/dashboard en http://127.0.0.1:8787 (abrir túnel SSH para verlo)"
