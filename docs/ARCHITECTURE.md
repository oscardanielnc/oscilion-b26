# Oscilion — Arquitectura

## 1. Principio de diseño

**Separar el cerebro del brazo.** El motor de señales decide; el ejecutor opera. Así pasamos de monitor → bot → copy-lead sin reescribir nada.

```
        DATOS            CEREBRO (señales)              BRAZO            SALIDA
   ┌───────────┐   ┌──────────────────────────┐   ┌───────────┐   ┌──────────┐
   │  Binance  │──▶│ features → scoring → risk │──▶│ executor  │──▶│ Binance  │
   │  (ccxt)   │   │   → signals (state mach.) │   │ paper/live│   │  órdenes │
   └─────┬─────┘   └────────────┬─────────────┘   └─────┬─────┘   └──────────┘
         │                      │                       │
         ▼                      ▼                       ▼
   ┌──────────────────── PERSISTENCIA (append-only, auditable) ───────────────┐
   │  snapshots · predictions · decisions · trades · params · logs            │
   └──────────────────────────────────┬───────────────────────────────────────┘
                                       ▼
                            ┌────────────────────┐
                            │  API (FastAPI)     │──▶ Frontend (React) + Alertas
                            └────────────────────┘
```

## 2. Estructura de carpetas

```
Oscilion/
├── CLAUDE.md  README.md  requirements.txt  .gitignore
├── config.py                  # configuración central (env, símbolos, umbrales)
├── deploy.sh                  # 1 comando: pull + deps + verify + restart (estilo kepler)
├── setup_vm.sh                # provisión inicial en la VM Oracle
├── oscilion.service           # systemd: orquestador (Restart=always)
├── oscilion-api.service       # systemd: API/dashboard
├── docs/                      # VISION · RISK_MODEL · ARCHITECTURE · ROADMAP
├── oscilion/                  # paquete principal
│   ├── orchestrator.py        # loop principal, scheduling, resiliencia
│   ├── data/
│   │   ├── fetch.py           # OHLCV + funding desde Binance (ccxt)
│   │   ├── store.py           # parquet + DB, sin huecos, sin look-ahead
│   │   └── universe.py        # universo de monedas y su metadata
│   ├── features/
│   │   ├── indicators.py      # ATR, BB, Keltner, VWAP, Donchian, ADX
│   │   ├── ranges.py          # rangos horizontales + canales diagonales
│   │   ├── regime.py          # rango vs tendencia + régimen de volatilidad
│   │   └── reversion.py       # Hurst, half-life OU, variance ratio, ADF
│   ├── scoring/
│   │   ├── conviction.py      # score 0–100% combinando features
│   │   └── calibration.py     # mide si el score se cumple (forward)
│   ├── risk/
│   │   ├── stops.py           # stop anti-barridas (clúster + ATR)
│   │   ├── sizing.py          # L = 2%/stop, tamaño de posición
│   │   └── allocation.py      # pesos cartera: kelly + vol + correlación
│   ├── signals/
│   │   ├── state_machine.py   # estado por moneda (ver §4)
│   │   ├── entry.py           # borde + confirmación de giro
│   │   ├── exit.py            # TP/trailing/stop/ruptura-en-contra
│   │   └── maker_taker.py     # decide maker vs taker
│   ├── execution/
│   │   ├── broker.py          # interfaz común de órdenes
│   │   ├── paper.py           # paper trading (simula fills+costos)
│   │   └── binance.py         # ejecución real perps (Fase 7)
│   ├── backtest/
│   │   ├── engine.py          # walk-forward, sin look-ahead
│   │   ├── costs.py           # fees + funding + slippage
│   │   └── metrics.py         # Sharpe, DD, MAE/MFE, winrate, calibración
│   ├── persistence/
│   │   ├── db.py              # conexión, migraciones, append-only
│   │   └── models.py          # esquema de tablas (ver §5)
│   ├── circuit_breaker.py     # kill-switch de seguridad
│   ├── notify.py              # alertas (Telegram/otros)
│   └── api/
│       ├── app.py             # FastAPI: endpoints de estado/historial
│       ├── dashboard.html     # dashboard mínimo (antes del frontend React)
│       └── __main__.py
├── frontend/                  # React + TS + lightweight-charts (Fase 5)
├── data/                      # parquet + oscilion.db   (gitignored)
├── logs/                      # logs persistentes        (gitignored)
└── research/                  # notebooks y experimentos
```

## 3. Módulos y responsabilidades clave

| Módulo | Responsabilidad | Funciones núcleo (firma orientativa) |
|---|---|---|
| `data/fetch.py` | Bajar datos sin huecos | `fetch_ohlcv(sym, tf, since)` · `fetch_funding(sym)` |
| `data/store.py` | Persistir/leer datos limpios | `save_bars()` · `load_bars()` · `gaps_report()` |
| `features/ranges.py` | Rango horizontal y diagonal | `horizontal_range(bars)` · `diagonal_channel(bars)` |
| `features/regime.py` | Clasificar régimen | `classify_regime(bars) -> {range|trend|chaos}` |
| `features/reversion.py` | Calidad de reversión | `hurst()` · `ou_half_life()` · `variance_ratio()` · `adf()` |
| `scoring/conviction.py` | Score 0–100 | `conviction(sym, snapshot) -> {score, components}` |
| `scoring/calibration.py` | ¿El score se cumple? | `update_calibration()` · `reliability_curve()` |
| `risk/stops.py` | Stop seguro | `safe_stop(sym, side, entry, bars)` |
| `risk/sizing.py` | L y tamaño | `leverage(stop_pct)` · `position_size(capital, stop_pct)` |
| `risk/allocation.py` | Pesos de cartera | `allocate(candidates, capital) -> weights` |
| `signals/state_machine.py` | Estado por moneda | `step(sym, snapshot) -> state` |
| `signals/entry.py` | Señal de entrada | `entry_signal(sym) -> {enter?, price, conf}` |
| `signals/exit.py` | Gestión de salida | `exit_signal(trade) -> {hold|tp|stop|break}` |
| `execution/broker.py` | Órdenes (paper/live) | `place()` · `cancel()` · `position()` |
| `backtest/engine.py` | Validación histórica | `walk_forward(strategy, period)` |
| `persistence/db.py` | Auditoría | `log_snapshot()` · `log_prediction()` · `log_decision()` · `log_trade()` |
| `orchestrator.py` | Pegamento + loop | `run_loop()` · `tick()` |
| `circuit_breaker.py` | Seguridad | `check()` (pausa todo si algo se descontrola) |

## 4. Máquina de estados por moneda 🔁

```
   ┌──────────┐  precio lejos del borde
   │ ESPERANDO│◀───────────────────────────────────┐
   └────┬─────┘                                     │
        │ precio se acerca a un borde               │ no confirma / se aleja
        ▼                                           │
   ┌──────────────┐    confirma giro    ┌───────────┴────┐
   │ ACERCÁNDOSE  │────────────────────▶│  CONFIRMANDO   │
   └──────────────┘                     └───────┬────────┘
                                                │ giro confirmado + RR≥2.5
                                                ▼
                                        ┌────────────────┐
                                        │ ENTRADA IDEAL ✅│ → alerta "ENTRA"
                                        └───────┬────────┘
                                                ▼
                                        ┌────────────────┐
                                        │   EN TRADE     │  (monitoreo continuo)
                                        └───────┬────────┘
              ┌──────────────┬──────────────────┼───────────────────┐
              ▼              ▼                   ▼                   ▼
          TP alcanzado   momentum cae       stop tocado        ruptura en contra
          (o trailing)   → toma parcial     → salida taker     → salida taker urgente
```

## 5. Modelo de datos (append-only, auditable) 🗄️

| Tabla | Para qué | Campos clave |
|---|---|---|
| `market_snapshots` | Estado del mercado en cada tick | ts, sym, price, ohlcv_ref, indicadores |
| `predictions` | Lo que el sistema "creía" | ts, sym, score, rango(lo,hi), regimen, stop, tp, RR |
| `decisions` | Qué se decidió y por qué | ts, sym, accion(entrar/esperar/no-operar), motivo |
| `trades` | Operaciones reales/paper | id, sym, side, entry, stop, tp, exit, pnl, fees, funding, L |
| `params` | Configuración usada | ts, version, json_params (para reproducir) |
| `calibration` | Score predicho vs resultado | bucket_score, n, aciertos, ratio_real |
| `events/logs` | Errores, reinicios, alertas | ts, nivel, modulo, msg |

> Regla: nunca se sobreescribe ni se borra. Esto da: historial para el frontend, materia para mejorar, medición de calibración y **forward-test honesto** = track record para copy-lead.

## 6. Operación y resiliencia (estilo kepler) 🛡️

- **systemd**: `oscilion.service` (orquestador) + `oscilion-api.service` (dashboard). `Restart=always`, `RestartSec=30`. Logs a journal **y** a `logs/`.
- **Nunca morir**: cada `tick()` envuelto en try/except → loguea y continúa. Un error en una moneda no tumba el sistema.
- **Circuit breaker**: si algo se descontrola (datos raros, pérdidas en cadena, desconexión) → pausa segura y alerta.
- **`deploy.sh` de un comando** (en la VM): `git pull` → `pip install` → verificación de import → `systemctl restart` de ambos servicios → resumen de estado. Idéntico patrón a kepler.
- **`setup_vm.sh`**: provisión inicial (venv, env file, servicios) la primera vez.
- **Config por entorno**: `EnvironmentFile=/etc/oscilion.env` (claves API, modo dry-run/demo). Nada de secretos en git.
- **Modos**: `dry-run` (no opera), `paper` (simula), `live` (real). Arranca siempre en el modo más seguro.

## 7. Frontend (Fase 5)

React + TS + **lightweight-charts**. Vistas: ranking de candidatos con score, rango+stop+TP dinámicos por moneda, estado de la máquina, posiciones abiertas, historial auditable, curva de equity y calibración. Lee de la API; la API lee de la DB. Alertas push para los 3 momentos: **ENTRA / TOMA GANANCIA / SAL**.
