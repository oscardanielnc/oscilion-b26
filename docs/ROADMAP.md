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

### 🚦 Veredicto go/no-go (2026-06-03)

Campaña honesta: 12 monedas × 3 años, 1h, neto de costos (`research/edge_campaign.py`).
**Resultado: la estrategia v1 (reversión en bordes de rango) NO tiene edge → PIVOTAR.**
- Todas las configs pierden (PF 0.72–0.78); los 12 símbolos negativos.
- Calibración **invertida** (mayor score ⇒ peor winrate) ⇒ score mal especificado.
- Salidas: stop 66% vs TP 10% ⇒ la tesis "entrar en borde / salir en el opuesto" no se cumple.
- El Sharpe 1.89 previo (BTC, 120d) era suerte de muestra (única ventana favorable).
- **15m confirma:** misma campaña en 15m = aún peor (PF 0.71–0.76; más frecuencia ⇒ más
  costos). El timeframe NO es el problema; es la SEÑAL.
- La INFRA (datos, backtest, riesgo, motor en vivo) es sólida y reutilizable; el problema es la SEÑAL.
- **Pivot identificado (probe momentum/breakout):** la reversión pierde (PF 0.76) pero el
  MOMENTUM tiene la estructura correcta — calibración monótona (a más fuerza de ruptura,
  más winrate) y el subconjunto de **rupturas fuertes (≥1 ATR) es POSITIVO** neto de costos
  (PF 1.07, +0.125%/trade, 3092 trades). Veredicto: **PIVOTAR a momentum/breakout**, no descartar.
- **Validación OOS (breakout_oos.py): ✅ edge CONFIRMADO fuera de muestra pero FINO.**
  La relación "más fuerza de ruptura → mejor" se mantiene monótona en test no visto
  (PF test 0.92→1.18). Split anclado TEST: PF 1.01 (breakeven+). Walk-forward POOL OOS:
  PF 1.18, +0.308%/trade, 1505 trades (3/4 folds positivos). Edge real y marginal: vive
  o muere en la EJECUCIÓN (entradas maker). Decisión del proyecto: **PIVOT = GO**.
- **Robustez + recencia:** el edge es amplio (9/12 monedas) y mejor en régimen `range`;
  el filtro **`range` + ruptura ≥2 ATR repara el período reciente** (único con 2025Q4→ positivo:
  PF 1.17). Estrategia candidata definida. Caveat: baja frecuencia (~323 trades/3a) ⇒ ruido.
- **Documentación completa del pivot en `docs/FINDINGS.md`** (hallazgos, consideraciones, backlog).
- Backlog priorizado: ejecución maker (mayor impacto), confirmar candidato OOS, TP/trailing,
  subir sample (multi-TF/instrumentos), sizing de cartera, forward-test en vivo.
- Reportes: `data/reports/{edge_campaign_1h,edge_campaign_15m,momentum_probe,breakout_oos,breakout_robustness,breakout_recency}.md`.

---

## 🗺️ Fase de pruebas — rescate del proyecto BTC/Sentinel (multi-sesión)

Contexto: la revisión de `C:\Users\LENOVO\btc` (ver `docs/BTC_SALVAGE.md`) confirma —de
forma independiente— el pivot de Oscilion: la reversión pierde, momentum/tendencia/breakout
ganan OOS. Aporta datos (5 años 1m BTC + 14 alts), 5 estrategias direccionales y aprendizajes.
**Pero sus backtests salieron de un harness optimista** ⇒ todo se re-valida con el motor
honesto de Oscilion. Plan por sesiones (cada una entrega evidencia o mata una hipótesis):

| Sesión | Objetivo | Entregable | Hipótesis |
|---|---|---|---|
| **R0** ✅ | Revisión a fondo + plan | `BTC_SALVAGE.md` + esta hoja de ruta | — |
| **R1** ✅ | Resample causal 1h→2h/4h; **motor honesto con salida 15m pesimista** (`engine_strat.py`); BTC 1m ingerido; 15m≈1m verificado | engine + datos | — |
| **R2** ✅ | Portadas MOMENTUM_PULLBACK y EMA_TREND_STACK; validación honesta **por moneda** (default+sweep OOS+walk-forward) + chequeo taker/maker | `VALIDATION_R1_R2.md` | H1✅, H3 (maker chico), H4✅ |
| **R3** ✅ | Portadas **ORB_BREAKOUT** y **BREAK_RETEST** (gate de frescura incluido); validadas por moneda. **ORB rescata alts** (mediana +0.029; genuinos LINK/DOT/TRX). break_retest falla salvo TRX. VWAP_ANCHOR pendiente (opcional). | `STRATEGY_MAP.md` | H1✅, H2 (gate incluido) |
| **R4** | **Ejecución maker**: modelar fills límite (no-fill / adverse selection) y re-validar las supervivientes | comparación taker vs maker | H3 |
| **R5** | **Exits**: grid por estrategia (TP fijo vs trailing vs hold-a-T2); **régimen** y **sesión** como filtros | exit óptimo por táctica | H5, H7, H8 |
| **R6** | **Cartera**: combinar supervivientes poco correlacionados; calibración forward; **forward-test en vivo (dry-run)** acumulando track record | señal multi-moneda + monitor | H6 |

Gate de cada estrategia para "sobrevivir": OOS ≥ 0.70 vs baseline · expectativa positiva
neta de costos · calibración monótona · estable en walk-forward. Lo que no pasa, se archiva
con evidencia (no se fuerza). Hipótesis H1–H8 detalladas en `docs/BTC_SALVAGE.md §6`.

### Estado actual
- ✅ Fase 0 — Visión y arquitectura definidas (este conjunto de docs).
- ✅ Fase 1 — Base del sistema: paquete `oscilion/`, config, persistencia
  append-only (SQLite WAL), orquestador resiliente, circuit breaker, notify,
  API mínima y despliegue (systemd + `deploy.sh`/`setup_vm.sh`). Verificado.
- ✅ Fase 2 — Datos: `data/{fetch,store,universe,pipeline}.py`, OHLCV multi-TF
  + funding (ccxt/Binance), **sin look-ahead** (descarta vela en curso),
  parquet + DB (`ohlcv_status`), detección de huecos/dups, reporte de calidad,
  CLI `python -m oscilion.data` y endpoint `/data`. Verificado contra Binance.
- ✅ Fase 3 — Motor de análisis: `features/{indicators,reversion,ranges,regime}.py`
  (ATR/BB/Keltner/VWAP/Donchian/ADX/RSI, Hurst/OU/VR/ADF, rango horizontal+canal
  diagonal, clasificador rango|tendencia|caos), `scoring/conviction.py` (0-100),
  `risk/{stops,sizing,allocation}.py` (anti-barridas, L=2%/stop, Kelly+corr) y
  `analysis.py` (ranking + CLI `python -m oscilion.analysis`). Verificado:
  invariante de riesgo exacta y clasificador valida OU sintético como `range`.
- ✅ Fase 4 — Backtest honesto: `backtest/{costs,metrics,engine,report}.py`,
  walk-forward event-driven SIN look-ahead (decide al cierre i, llena al open
  i+1; intrabar conservador stop-primero), costos reales (fees maker/taker,
  slippage, funding 8h), métricas (Sharpe, MaxDD, winrate, PF, MAE/MFE,
  calibración) e informe go/no-go. CLI `python -m oscilion.backtest`.
  Reusa la MISMA señal del live (`candidate_from_df`). 🚦 Veredicto inicial
  (lógica naïve, ~120d 1h): **NO-GO** (sin confirmación de giro aún; mercado
  en tendencia). Falta validar con histórico multi-año + giro de Fase 5.
- ✅ Fase 5 — Motor en vivo: `signals/{entry,exit,maker_taker,state_machine,live}.py`
  + `scoring/calibration.py`. Máquina de estados por moneda (ESPERANDO→
  ACERCÁNDOSE→EN_TRADE) con **confirmación de giro**, gestión de salida
  (stop/tp/break/trailing/parcial), maker vs taker, calibración forward y
  alertas ENTRA/TOMA-GANANCIA/SAL. Integrado al orquestador (monitor en vivo,
  sin operar); API `/state` y `/calibration`. La confirmación de giro también
  es opcional en el backtest (`--confirm`).
  🚦 **Hallazgo F5 (1h, ~120d):** la confirmación de giro da vuelta el edge —
  SIN: winrate 28% PF 0.87 Sharpe −0.47 ret −41% · CON: winrate 40% PF 1.22
  Sharpe 1.89 ret +47%. Veredicto formal aún NO-GO (PF 1.22 < 1.3) y muestra
  corta: **prometedor, no confirmado**. Falta validación multi-año.
- ⬜ Fase 6 — Frontend — siguiente sesión.
