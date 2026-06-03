#!/usr/bin/env bash
# Oscilion — despliegue de un comando (en la VM). Estilo kepler:
#   git pull -> deps -> (build front si hay node) -> verificación -> restart -> estado.
# Cualquier fallo aborta ANTES de reiniciar (no se despliega algo roto).
set -euo pipefail

APP_DIR=${OSCILION_DIR:-/opt/oscilion}
APP_USER=${OSCILION_USER:-oscilion}
PY="$APP_DIR/.venv/bin/python"
PIP="$APP_DIR/.venv/bin/pip"

cd "$APP_DIR"
echo "==> Oscilion :: deploy ($(date -u +%FT%TZ))"

echo "==> git pull"
sudo -u "$APP_USER" git pull --ff-only

echo "==> pip install -r requirements.txt"
sudo -u "$APP_USER" "$PIP" install -q -r requirements.txt

# Frontend: si hay node se reconstruye; si no, se usa el dist versionado en el repo.
if command -v npm &>/dev/null; then
  echo "==> build frontend (npm)"
  ( cd frontend && sudo -u "$APP_USER" npm install --silent && sudo -u "$APP_USER" npm run build )
else
  echo "==> sin node: se usa frontend/dist versionado"
fi

echo "==> verificación de import"
sudo -u "$APP_USER" "$PY" -c "import config; from oscilion import orchestrator; from oscilion.live import monitor, forward, signals; from oscilion.strategies import all_assignments; from oscilion.api import app; print('import OK')"

echo "==> systemctl restart"
systemctl restart oscilion.service
systemctl restart oscilion-api.service

sleep 2
echo "==> estado:"
systemctl is-active oscilion.service oscilion-api.service || true
systemctl --no-pager --lines=4 status oscilion.service || true
echo "==> deploy OK"
