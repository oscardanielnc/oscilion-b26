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
  dnf install -y python3.11 python3.11-pip git    # Oracle Linux / RHEL (NO toca el python3 del sistema)
elif command -v yum &>/dev/null; then
  yum install -y python3.11 python3.11-pip git
fi
# marcar el repo como seguro para git (evita "dubious ownership")
git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true

# elegir intérprete >= 3.10 (NO usar el python3 del sistema si es viejo, p.ej. 3.9
# en Oracle Linux — kepler/opportunity_alert dependen de ese 3.9, no se toca)
if [ -z "${PYTHON:-}" ]; then
  for c in python3.12 python3.11 python3.10 python3; do
    if command -v "$c" &>/dev/null && "$c" -c 'import sys; exit(0 if sys.version_info>=(3,10) else 1)' 2>/dev/null; then
      PYBIN="$c"; break
    fi
  done
fi
if ! "$PYBIN" -c 'import sys; exit(0 if sys.version_info>=(3,10) else 1)' 2>/dev/null; then
  echo "ERROR: se requiere Python >= 3.10. Instala python3.11 (dnf install -y python3.11)."; exit 1
fi

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
# No se sourcea el env (los símbolos del núcleo son el default de config.py) → sin
# problemas de permisos. cwd=APP_DIR para que el paquete oscilion resuelva.
echo "==> sembrando histórico (3 años) — esto tarda unos minutos"
( cd "$APP_DIR" && sudo -u "$APP_USER" .venv/bin/python -m oscilion.data sync --days 1095 ) \
  || echo "  (si falla, re-correr: cd $APP_DIR && sudo -u $APP_USER .venv/bin/python -m oscilion.data sync --days 1095)"

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
