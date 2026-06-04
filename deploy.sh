#!/usr/bin/env bash
# deploy.sh — Actualiza Oscilion y reinicia los servicios. Un solo comando.
# Uso (desde la VM, desde cualquier directorio):
#   bash /opt/oscilion/deploy.sh
# No requiere ejecutarse con sudo: usa sudo internamente solo donde hace falta.
set -euo pipefail

APP_DIR="/opt/oscilion"
APP_USER="oscilion"
PY="${APP_DIR}/.venv/bin/python"
PIP="${APP_DIR}/.venv/bin/pip"
ASU=(sudo -u "$APP_USER")          # correr como el dueño del repo/venv

cd "$APP_DIR"
sudo git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true
"${ASU[@]}" git config --global --add safe.directory "$APP_DIR" 2>/dev/null || true

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  OSCILION DEPLOY  —  $(date '+%Y-%m-%d %H:%M') UTC"
echo "═══════════════════════════════════════════════════════"

echo ""
echo "[1/5] Sincronizando con GitHub..."
"${ASU[@]}" git pull --ff-only
echo "  ✓ Código actualizado"

echo ""
echo "[2/5] Dependencias Python..."
"${ASU[@]}" "$PIP" install --quiet -r requirements.txt 2>/dev/null || true
echo "  ✓ Dependencias OK"

echo ""
echo "[3/6] Verificación rápida (import del paquete)..."
if "${ASU[@]}" "$PY" -c "import config; from oscilion import orchestrator; from oscilion.live import monitor, forward, signals; from oscilion.data import fetch; from oscilion.strategies import all_assignments; from oscilion.api import app" 2>/dev/null; then
    echo "  ✓ Paquete importa correctamente"
else
    echo "  ✗ Error de import — abortando deploy (no se reinicia nada)"; exit 1
fi

echo ""
echo "[4/6] Backfill de monedas nuevas (idempotente; salta las ya sembradas)..."
if "${ASU[@]}" "$PY" -m oscilion.data backfill; then
    echo "  ✓ Histórico listo para todo el núcleo"
else
    echo "  ✗ Backfill falló — abortando (no se reinicia: evita arrancar con monedas oscuras)"; exit 1
fi

echo ""
echo "[5/6] Reiniciando orquestador (oscilion)..."
sudo systemctl restart oscilion && sleep 2
[ "$(systemctl is-active oscilion 2>/dev/null)" = "active" ] \
    && echo "  ✓ oscilion activo" \
    || { echo "  ✗ oscilion no arrancó — journalctl -u oscilion -n 30"; }

echo ""
echo "[6/6] Reiniciando dashboard (oscilion-api)..."
sudo systemctl restart oscilion-api && sleep 2
[ "$(systemctl is-active oscilion-api 2>/dev/null)" = "active" ] \
    && echo "  ✓ oscilion-api activo  →  Dashboard: túnel SSH a 127.0.0.1:8787" \
    || { echo "  ✗ oscilion-api no arrancó — journalctl -u oscilion-api -n 30"; }

echo ""
echo "═══════════════════════════════════════════════════════"
echo "  oscilion:     $(systemctl is-active oscilion     2>/dev/null || echo '?')"
echo "  oscilion-api: $(systemctl is-active oscilion-api 2>/dev/null || echo '?')"
echo "═══════════════════════════════════════════════════════"
echo ""
