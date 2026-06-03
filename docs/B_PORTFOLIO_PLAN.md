# Fase B — Cartera y afinamiento (plan de pruebas)

> Objetivo: **máximo beneficio con el mínimo riesgo** sobre el núcleo validado
> (BTC/BNB/TRX con EMA_STACK; LINK/DOT/TRX con ORB). Todo se valida con el motor
> honesto + forward; nada se fija sin evidencia. Métrica primaria: expectativa en R
> y, a nivel cartera, Sharpe/MaxDD reales de una cuenta única.

---

## Preguntas a responder (TODAS, nada al aire)

### B1 — Mejores parámetros por moneda
Cada moneda puede tener su óptimo. Barrer por moneda (train→OOS→walk-forward) los params de su
estrategia y fijar los mejores **robustos** (no el pico de train).
- EMA_STACK: `atr_mult_sl`, `tp_r`, `fresh_gate`, `session_filter`, `rsi_filter`.
- ORB: `range_max_pct`, `tp_r`, `fresh_gate`, `long_only`, `session_filter`, `sl_atr_buf`.
- Harness: `research/strat_validation.py` (ya hace default+sweep OOS+walk-forward por moneda).
- Criterio de "queda": positivo full+OOS+WF, calibración/forward coherente.

### B2 — Capital por moneda (weights)
Cuánto del capital a cada serie. Propuesta a validar: `weight ∝ edge_medido(exp_R) × (1/vol) ×
haircut_correlación`, con **Kelly fraccionado** como tope.
- Entregable: tabla de weights por serie, justificada por backtest de cartera.

### B3 — Multiplicador de apalancamiento por moneda
Sobre el capital asignado, el `L = 2% / stop%` (invariante) ya fija el riesgo; B decide si hay
un multiplicador extra por convicción/régimen y su tope. Validar que no rompe el −2%/trade.

### B4 — Mapa de correlaciones (✅ v1 hecho — `data/reports/correlation_map.md`)
**Hallazgo:** **TRX es diversificador** (corr ~0.4 full, ~0.1 reciente con todo). BTC/BNB/LINK/DOT
son un **clúster correlacionado** (~0.68–0.78; LINK-DOT 0.78). 
- Regla para sizing: **tratar el clúster correlacionado como ~una sola apuesta**; TRX cuenta
  aparte. No abrir full-size en BTC+BNB+LINK+DOT a la vez.
- Pendiente: re-correr periódicamente (la correlación cambia con el régimen).

### B5 — Límites duros
`MAX_CONCURRENT` (¿3?), `MAX_TOTAL_EXPOSURE` (¿100%?), máx por clúster correlacionado.
Validar el peor caso (todas las del clúster saltan stop el mismo día ≈ −2%·n_efectivo).

### B6 — Simulación de CARTERA (cuenta única)
Combinar todas las series en UNA cuenta (capital finito, límites, correlación) y medir el
**Sharpe/MaxDD/retorno REALES** — el riesgo que de verdad se vive. Hoy los backtests son por
serie independiente; falta la vista conjunta.

---

## Orden sugerido
B1 (mejores params) → B4/B5 (correlación + límites) → B2/B3 (weights + leverage) → B6 (cartera) →
forward de la cartera completa. Iterar hasta el equilibrio beneficio/riesgo.

## Estado del scaffold
`oscilion/strategies/portfolio.py` tiene `equal_weights()` provisional + límites + TODOs.
`assignment.py` tiene `weight=None` por serie (B lo rellena). El motor (`engine_strat`) y el
harness (`strat_validation`) ya sirven para todas estas pruebas.
