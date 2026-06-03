# Oscilion — Roadmap por fases

Cada fase es autónoma y se construye en una sesión dedicada. Orden pensado para que **el sistema diga la verdad lo antes posible** (datos → backtest) antes de invertir en lo bonito (frontend) o lo arriesgado (dinero real).

```
F1 ─ Base/infra ──▶ F2 ─ Datos ──▶ F3 ─ Motor análisis ──▶ F4 ─ Backtest ──▶ 🚦 GO/NO-GO
                                                                                  │
   F5 ─ Motor en vivo ──▶ F6 ─ Frontend ──▶ F7 ─ Paper ──▶ F8 ─ Auto ──▶ F9 ─ Copy-lead
```

---

## Fase 1 — Base del sistema 🧱
**Objetivo:** esqueleto sólido, resiliente y desplegable.
- Estructura de carpetas y paquete `oscilion/`.
- `config.py`, `requirements.txt`, `.gitignore`, venv.
- `persistence/db.py` + `models.py`: esquema completo (§5 de ARCHITECTURE), append-only.
- `orchestrator.py` con loop resiliente (try/except por tick, logging).
- `circuit_breaker.py` esqueleto, `notify.py` esqueleto.
- `deploy.sh`, `setup_vm.sh`, `oscilion.service`, `oscilion-api.service`.
- **Entregable:** servicio que arranca, loguea, persiste y se reinicia solo (aún sin lógica de trading).

## Fase 2 — Datos 📥
**Objetivo:** datos perfectos, sin look-ahead.
- `data/fetch.py`: OHLCV multi-TF (1h base, 15m) + funding histórico (ccxt/Binance).
- `data/store.py`: parquet + DB, detección de huecos, limpieza.
- `data/universe.py`: universo de monedas + metadata (vol, liquidez).
- **Entregable:** histórico descargado y auditado de BTC/ETH/SOL+otras; reporte de calidad.

## Fase 3 — Motor de análisis 🧠
**Objetivo:** convertir precio en señales medibles (tiempo real, ventana móvil).
- `features/`: indicadores, rangos (horizontal+diagonal), régimen, reversión (Hurst/OU/VR/ADF).
- `scoring/conviction.py`: score 0–100 por moneda.
- `risk/`: `stops.py` (anti-barridas), `sizing.py` (L=2%/stop), `allocation.py` (cartera).
- **Entregable:** dado un instante, ranking de candidatos con rango, stop, TP, L y % capital.

## Fase 4 — Backtest honesto 🔬
**Objetivo:** ¿hay edge tras costos? La puerta de la verdad.
- `backtest/engine.py`: walk-forward, sin look-ahead.
- `backtest/costs.py`: fees + funding + slippage reales.
- `backtest/metrics.py`: Sharpe, max DD, winrate, MAE/MFE, **calibración**.
- **Entregable:** informe go/no-go con métricas netas por moneda/régimen. 🚦

## Fase 5 — Motor en vivo ⚡
**Objetivo:** el cerebro corriendo 24/7.
- `signals/state_machine.py`, `entry.py`, `exit.py`, `maker_taker.py`.
- `scoring/calibration.py`: forward-test real (predicción vs resultado).
- Alertas: ENTRA / TOMA GANANCIA / SAL.
- **Entregable:** monitor en vivo que recomienda y registra todo (sin operar).

## Fase 6 — Frontend 🖥️
**Objetivo:** ver los rangos y stops dinámicamente (el valor para el usuario).
- API FastAPI + React/TS + lightweight-charts.
- Ranking, rango/stop/TP por moneda, estado, posiciones, historial, equity, calibración.
- **Entregable:** dashboard en vivo consultable.

## Fase 7 — Paper trading 📝
**Objetivo:** validar en vivo sin dinero.
- `execution/paper.py`: simula fills + costos en tiempo real.
- Comparar paper vs backtest (¿coherentes?).
- **Entregable:** track record paper auditable.

## Fase 8 — Auto-ejecución 🤖
**Objetivo:** operar solo, con capital pequeño.
- `execution/binance.py`: órdenes reales perps, post-only/maker-taker, gestión de stops.
- Circuit breaker en serio, límites duros.
- **Entregable:** bot operando real, supervisado, escalando gradual.

## Fase 9 — Copy-lead 👥
**Objetivo:** monetizar vía comisiones de copiadores.
- Track record verificable, foco en bajo drawdown, ecosistema para retener copiadores.
- **Entregable:** cuenta lead activa.

---

### Estado actual
- ✅ Fase 0 — Visión y arquitectura definidas (este conjunto de docs).
- ⬜ Fase 1 — siguiente sesión.
