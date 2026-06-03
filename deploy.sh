#!/usr/bin/env bash
# Oscilion — despliegue de un comando (en la VM). Estilo kepler:
#   git pull -> deps -> verificación de import -> restart -> resumen.
# Cualquier fallo aborta ANTES de reiniciar (no se despliega algo roto).
set -euo pipefail

APP_DIR=${OSCILION_DIR:-/opt/oscilion}
APP_USER=${OSCILION_USER:-oscilion}
PY="$APP_DIR/.venv/bin/python"
PIP="$APP_DIR/.venv/bin/pip"

cd "$APP_DIR"
echo "==> Oscilion :: deploy ($(date -u +%FT%TZ))"

# 1) Código
echo "==> git pull"
sudo -u "$APP_USER" git pull --ff-only

# 2) Dependencias
echo "==> pip install -r requirements.txt"
sudo -u "$APP_USER" "$PIP" install -q -r requirements.txt

# 3) Verificación de import (humo): si no importa, NO reiniciamos.
echo "==> verificación de import"
sudo -u "$APP_USER" "$PY" -c "import config; from oscilion import orchestrator, notify, circuit_breaker; from oscilion.persistence import db; from oscilion.api import app; print('import OK')"

# 4) Reinicio de ambos servicios
echo "==> systemctl restart"
systemctl restart oscilion.service
systemctl restart oscilion-api.service

# 5) Resumen de estado
sleep 2
echo "==> estado:"
systemctl is-active oscilion.service oscilion-api.service || true
systemctl --no-pager --lines=5 status oscilion.service || true

echo "==> deploy OK"
