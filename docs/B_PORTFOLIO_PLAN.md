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

## ✅ Resultados B v1 (2026-06-03) — `data/reports/phase_b.md`

Ejecutada honestamente (selección en train, OOS=2025→ genuino):

- **B1 — params por moneda:** ⚠️ **tunear por moneda SOBREAJUSTA** en muestras chicas
  (BTC·ema train +0.80 → OOS −0.00; TRX·ema +0.77 → +0.05). **Decisión: NO tunear —
  usar el baseline fijo `tp_r=4`**, que aguanta OOS en las 6 (BTC +0.13, BNB +0.41,
  TRX +0.14/+0.34, LINK +0.37, DOT +0.11). Disciplina anti-overfit.
- **B2 — weights:** equal-weight gana a edge-weight in-sample (que sobreajusta).
  **v1 = equal-weight.**
- **B3 — leverage:** se mantiene `L = 2%/stop` (invariante); **sin multiplicador extra**
  v1 (la convicción no demostró edge → no añadir riesgo).
- **B4 — correlación:** TRX diversifica (~0.1 reciente); {BTC,BNB,LINK,DOT} clúster (~0.7).
- **B5 — límites:** **máx 3 concurrentes, máx 2 por clúster** (control de concentración).
- **B6 — cartera (cuenta única, OOS):** mejor esquema robusto = **equal + maxc3 + clu2** →
  **OOS Sharpe 1.89, retorno +207%, MaxDD −26%** (533 trades). "Sin límites" daba Sharpe
  1.98 pero con concentración no controlada → descartado por riesgo.

⚠️ **Honestidad:** los retornos son de backtest compuesto y deben **confirmarse en FORWARD
(Fase A) en la VM** antes de creerlos; el número sobrio es el **MaxDD ~26%** (el riesgo real
del pilot). Config elegida persistida en `oscilion/strategies/tuned.py` (generada, en uso).

**Pendiente B (futuro, con más datos forward):** re-tunear params cuando haya más muestra,
weights dinámicos validados, re-correr correlación periódicamente, simular con fees maker.

## Estado del scaffold
`oscilion/strategies/portfolio.py` tiene `equal_weights()` provisional + límites + TODOs.
`assignment.py` tiene `weight=None` por serie (B lo rellena). El motor (`engine_strat`) y el
harness (`strat_validation`) ya sirven para todas estas pruebas.
