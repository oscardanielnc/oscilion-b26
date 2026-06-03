#!/usr/bin/env bash
# Oscilion — provisión inicial en la VM Oracle (ejecutar UNA vez, como root/sudo).
# Idempotente: se puede re-correr sin romper nada.
set -euo pipefail

APP_DIR=/opt/oscilion
APP_USER=oscilion
ENV_FILE=/etc/oscilion.env

echo "==> Oscilion :: setup_vm"

# 1) Usuario de servicio (sin login)
if ! id "$APP_USER" &>/dev/null; then
  echo "==> Creando usuario $APP_USER"
  useradd --system --create-home --shell /usr/sbin/nologin "$APP_USER"
fi

# 2) Directorio de la app
mkdir -p "$APP_DIR"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# 3) Dependencias del sistema
if command -v apt-get &>/dev/null; then
  apt-get update -y
  apt-get install -y python3 python3-venv python3-pip git
fi

# 4) Código (clonar si está vacío)
if [ ! -d "$APP_DIR/.git" ]; then
  echo "==> Clona el repo en $APP_DIR antes de continuar, o ya está colocado."
fi

# 5) Virtualenv + deps
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/.venv"
sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install --upgrade pip
if [ -f "$APP_DIR/requirements.txt" ]; then
  sudo -u "$APP_USER" "$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"
fi

# 6) Archivo de entorno (no sobreescribir si existe)
if [ ! -f "$ENV_FILE" ]; then
  echo "==> Creando $ENV_FILE desde example.env (EDITAR luego)"
  cp "$APP_DIR/example.env" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
fi

# 7) Servicios systemd
echo "==> Instalando units systemd"
cp "$APP_DIR/oscilion.service" /etc/systemd/system/oscilion.service
cp "$APP_DIR/oscilion-api.service" /etc/systemd/system/oscilion-api.service
systemctl daemon-reload
systemctl enable oscilion.service oscilion-api.service

echo "==> Listo. Edita $ENV_FILE y luego: ./deploy.sh"
