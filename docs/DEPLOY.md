# Despliegue v1 en la VM Oracle — guía paso a paso

> Objetivo: dejar Oscilion corriendo 24/7 en dry-run, generando señales (ntfy) y
> **logs mínimos** revisables a diario. No opera con dinero. Repo:
> `https://github.com/oscardanielnc/oscilion-b26.git`

## 0. Antes (en tu PC)
El código ya está commiteado. **Súbelo a GitHub** (yo no hago push):
```bash
git push -u origin main      # (o master, según tu rama)
```

## 1. Provisión inicial en la VM (una sola vez)
SSH a la VM y, como root/sudo:
```bash
# descargar el script de provisión y ejecutarlo (clona, venv, deps, siembra datos, systemd)
curl -fsSL https://raw.githubusercontent.com/oscardanielnc/oscilion-b26/main/setup_vm.sh -o /tmp/setup_vm.sh
sudo bash /tmp/setup_vm.sh
```
Esto:
1. crea el usuario de servicio `oscilion` y `/opt/oscilion`,
2. instala python/venv/git, clona el repo, crea el venv e instala dependencias,
3. crea `/etc/oscilion.env` (con `OSCILION_NTFY_TOPIC=oscar-oscilion-b26` y modo `dry-run`)
   y **fija `OSCILION_FORWARD_INCEPTION_MS` a la fecha de despliegue** (de aquí en
   adelante = datos no vistos = forward real),
4. **siembra 3 años de histórico** de las 5 monedas del núcleo (tarda ~5-10 min),
5. instala y arranca los servicios systemd (`oscilion` = monitor, `oscilion-api` = API).

> Si la siembra de datos falla por red, re-correr:
> `sudo -u oscilion /opt/oscilion/.venv/bin/python -m oscilion.data sync --days 1095`

## 2. Verificar que corre
```bash
systemctl status oscilion oscilion-api          # ambos "active (running)"
journalctl -u oscilion -n 30 --no-pager         # arranque + heartbeat (logs mínimos)
sudo -u oscilion /opt/oscilion/.venv/bin/python -m oscilion.live.forward   # tabla validación
```

## 3. Alertas al móvil (ntfy)
Instala la app **ntfy** (iOS/Android) → suscríbete al canal **`oscar-oscilion-b26`**.
Recibirás ENTRA / SAL / TOMA en tiempo real. (Prueba: `curl -d "test" ntfy.sh/oscar-oscilion-b26`.)

## 4. Ver el dashboard (seguro, sin exponer puertos)
La API escucha en `127.0.0.1:8787` (no expuesta a internet). Desde tu PC, túnel SSH:
```bash
ssh -L 8787:127.0.0.1:8787 usuario@IP_VM
# luego abre en tu navegador:  http://localhost:8787
```

## 5. Actualizaciones futuras (UN comando, estilo kepler)
Tras hacer push de cambios desde tu PC, en la VM desde **cualquier** directorio:
```bash
bash /opt/oscilion/deploy.sh
```
Hace todo: `git pull` → dependencias → verificación de import → **backfill de monedas
nuevas** → reinicia `oscilion` y `oscilion-api` → resumen de estado. No requiere `sudo`
(lo usa internamente solo para systemctl). Si el import falla, **aborta sin reiniciar**.

> **Backfill automático e idempotente:** al añadir monedas nuevas al núcleo
> (`assignment.py`), el deploy las siembra solas (`python -m oscilion.data backfill`):
> baja histórico completo SOLO a las que están por debajo de 1500 velas 1h y salta las ya
> sembradas (deploy rápido). Evita que una moneda nueva arranque "oscura" (build_ctx exige
> ≥300 velas 1h). Forzar manual: `… -m oscilion.data backfill`.
>
> **Frontend:** el dashboard se sirve desde `frontend/dist` **commiteado** (la VM no compila).
> Si cambias `frontend/src`, reconstruye y commitea el `dist` ANTES de desplegar:
> `cd frontend && npm run build` (en tu PC) → `git add frontend/dist && git commit`.

## 6. Revisión diaria (logs MÍNIMOS para compartir)
Para que me los pases sin saturar, comparte cualquiera de estos (son concisos):
```bash
# A) validación: backtest vs forward por moneda×estrategia (lo más útil)
sudo -u oscilion /opt/oscilion/.venv/bin/python -m oscilion.live.forward

# B) alertas recientes (señales del día)
curl -s 127.0.0.1:8787/alerts | python3 -m json.tool | head -40

# C) eventos/errores recientes del servicio
journalctl -u oscilion --since "24 hours ago" -p info --no-pager | tail -40
```
El diseño de logs es **append-only y mínimo**: solo se registran alertas, decisiones,
errores y un heartbeat horario. El detalle ruidoso (fetch, ticks) va a DEBUG (no se guarda).

## Notas
- Modo **dry-run**: registra y avisa, **no coloca órdenes**. Para `paper`/`live` (futuro)
  se cambia `OSCILION_MODE` y se añaden credenciales — pero antes el forward debe confirmar el edge.
- Las posiciones virtuales y cursores **sobreviven reinicios** (persistencia en BD) →
  el forward-test no pierde continuidad aunque el servicio se reinicie.
- `forward_inception` quedó fijado al deploy: el forward acumula desde hoy; revísalo a los días/semanas.
