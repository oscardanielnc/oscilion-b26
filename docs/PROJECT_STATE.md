# Estado del proyecto Oscilion — v0.7 (cartera v2)

**Actualizado:** 2026-06-22 (auditoría fuerte + reconstrucción de cartera por edge OOS +
anti-beta + ampliación de universo). Lee también `AUDIT_2026-06-22.md` (la auditoría
completa y el método), `FORWARD_REVIEW.md`, `STRATEGY_MAP.md`.

> **Resumen en una línea (2026-06-22):** la auditoría refutó el miedo a "overfit" (purged-WF
> deja los combos positivos) y reveló que el problema era el **gate** (leía un backtest
> in-sample inflado 2-3× y elegía perdedores). Corregido: gate OOS + regla de capital por
> **doble régimen OOS + anti-beta**. Cartera reconstruida a **17 combos con capital + 6
> observe** (incluye oro y alts con alpha real por el lado short). **Desplegado y verificado
> en vivo el 2026-06-22.** Riesgo abierto #1: el sizing 2%/trade da MaxDD backtest ~-60% →
> bajar R antes de capital real (ver §7).

---

## 1. Dirección (confirmada por Oscar)

**Oscilion = observador multi-moneda que asigna a CADA moneda la estrategia que se le
validó, deja correr ganadores, y solo opera donde hay edge demostrado.** Convicción > cantidad.

**Cartera v2 (2026-06-22) — 17 con capital + 6 observe, 17 monedas.**
Regla de capital: exp_R ≥ +0.10 en DOS regímenes OOS (holdout >2025 **Y** 2026) con n≥30,
salida 15m, costes reales, **y** pasar el chequeo anti-beta (rinde por el lado short o con
el activo plano, no montando una subida). Config FIJA por estrategia.

| Clúster | Combos con capital | Edge (OOS/2026) |
|---|---|---|
| `trx` | TRX × {vwap, ema, orb, break_retest} | +0.13..+0.34 / +0.45..+0.99 |
| `altlong` | LINK orb, XRP orb, DOGE orb, BNB vwap, AVAX vwap, TIA vwap, ATOM vwap | +0.10..+0.37 |
| `altbreak` | RUNE, NEO, FLOW, HBAR — break_retest (alpha por el SHORT en alts en caída) | +0.13..+0.34 / +0.15..+1.07 |
| `gold` | PAXG break_retest, XAU momentum (descorrelacionados del cripto) | +0.15..+0.47 |

**Observe (sin capital):** BTC ema, BTC orb, BNB ema, ETH vwap, DOT orb, **PAXG ema**
(degradado: era beta del oro +41%). Podados: BTC/DOGE/XRP vwap (negativos ambos regímenes).

**"Capital" siempre condicionado al gate dinámico** (ver §3), ahora medido en ventana OOS
`[2025-01, inception)` (no in-sample) con `exp_R > +0.05`. Límites de cartera:
**máx 4 concurrentes (subido de 3 con `concurrency_sweep.py`), máx 2 por clúster.**

## 2. Arquitectura (estado actual)

```
oscilion/
├── strategies/          ★ fuente única de señal
│   ├── library.py       5 estrategias puras + tp_barrier (runner = tp None)
│   ├── context.py       build_ctx multi-TF (backtest Y live) — sin look-ahead
│   ├── assignment.py    PORTFOLIO: moneda→estrategia(s)+params+observe_only
│   ├── portfolio.py     weights/clusters/límites (tuned.py de Fase B)
│   └── tuned.py         GENERADO fase B: equal-weight, maxc=3, clúster=2
├── live/                ★ FASE A (validación con datos reales)
│   ├── monitor.py       dry-run: señales→trades virtuales; TODAS las guardas (§3)
│   ├── guards.py        ★ guardas PURAS: gate, vetos, freno diario, stale, stop-floor
│   ├── forward.py       backtest vs forward por serie → forward_results (BD)
│   ├── signals.py       vista curada para frontend
│   └── export.py        reporte diario md/json (capital vs observe separados)
├── backtest/            engine_strat (motor honesto) · costs (compartido con live) · resample
├── data/                fetch (ccxt + timeout explícito) · store · universe · pipeline
├── persistence/         db · models — **schema v6** (trades: observe, exit_reason, cost_audit)
├── api/app.py           /signals /trades /forward /alerts /export /portfolio /events ...
├── orchestrator.py      loop 24/7 resiliente + warn de tick lento + backup BD diario
└── circuit_breaker · notify · logging_setup
```

**Tests: 23 (pytest)** — smoke (imports, riesgo, resampleo causal, separación
producción/research, universo único) + guardas (gate, vetos, freno, stale, tp runner, piso stop).

## 3. Guardas de proceso (orden de evaluación al abrir) — TODAS enforced en monitor

Nacen del primer ciclo forward (−4.07R, del cual −3.2R fue de combos sin validar; ver
`FORWARD_REVIEW.md`). Cada bloqueo deja evento en BD (visible en /alerts y export).

1. **Señal vencida** (`max_signal_age_min=30`): vela de señal vieja (downtime/refresh
   fallido) → no entrar a precio vencido.
2. **Piso de stop** (`min_stop_pct=0.2%`): stop→0 dispara el notional. Idéntico en engine.
3. **Gate de validación** (`gate_min_n=30`, `gate_min_exp_r=+0.05`): capital solo si el
   backtest LOCAL lo respalda; si no → degrada a **observe** (sin capital, `observe=1`,
   fuera del PnL, sigue sumando stats). **2026-06-22:** el backtest del gate se mide en
   ventana **OOS `[2025-01, inception)`** (`gate_backtest_from_ms`), no in-sample full-history
   (que inflaba el exp_R 2-3× y elegía perdedores — ver `AUDIT_2026-06-22.md`).
4. **Veto por símbolo**: máx 1 posición CON capital por símbolo (cualquier dirección).
5. **Límites de cartera (Fase B)**: máx 3 posiciones con capital, máx 2 por clúster —
   el esquema con el que se validó el portfolio (antes NO se aplicaba en vivo).
6. **Freno diario** (`max_daily_loss=6%`): PnL cerrado del día (UTC) ≤ −6% del capital →
   sin nuevas entradas con capital hasta 00:00 UTC + ntfy CRITICAL (1 aviso/día).

**Auditoría de costes**: cada cierre persiste `cost_audit` (R = r_gross + r_slip_exit +
r_fee_entry + r_fee_exit + r_funding) → responde con datos si los stops realizan peor que
−1R por modelo o por otra cosa. Hallazgo: monitor y backtest comparten `costs.realized`,
el −1.04/−1.13R observado YA está modelado.

## 4. Cómo correr / desplegar

```powershell
python -m oscilion                  # orquestador 24/7
python -m oscilion.api              # API + frontend
python -m oscilion.live.forward     # revisión backtest vs forward
python -m pytest tests/ -q          # 23 tests
```
Deploy: Oscar hace `git push` → en la VM `bash /opt/oscilion/deploy.sh`. La BD migra a
schema v6 sola (migraciones idempotentes al arrancar). Dashboard http://213.35.121.9:8787.

## 5. Hecho ✅
- Pilot v1 + frontend + VM Oracle (dry-run) + ntfy + export diario.
- 2026-06-08/10: primer ciclo forward cerrado y revisado (FORWARD_REVIEW.md).
- 2026-06-10 (`2980f85`): gate de validación + observe enforced + veto símbolo + señal
  vencida + tp runner None + piso de stop + cost_audit (schema v6).
- 2026-06-10 (`119792b`): límites de cartera Fase B en vivo + freno diario −6% +
  timeout ccxt explícito + warn tick lento + estado solo se persiste tras step exitoso.
- **2026-06-12: deploy CONFIRMADO en vivo** (cost_audit poblado, stops −1.04R exactos, errors:[]).
- **2026-06-22: AUDITORÍA FUERTE + CARTERA v2 (desplegado y verificado).** Ver `AUDIT_2026-06-22.md`.
  - Forward acumulado 26 trades / −10.6R analizado: NO era overfit (purged-WF `research/purged_wf.py`
    deja los combos positivos; 2026-YTD sano) — era muestra diminuta + quincena hostil + un **gate
    inflado** (in-sample full-history, +1.23 vs +0.39 OOS real) que elegía perdedores.
  - **Gate corregido** a ventana OOS + `exp_R>+0.05` (commit `236cb55`).
  - **Cartera reconstruida** por doble-régimen OOS + **anti-beta** (`validate_alts.py`; lección de
    `tvindicators`: oro long-only = beta). 17 capital + 6 observe; ampliado a alts (RUNE/NEO/FLOW/HBAR
    break_retest — alpha por el SHORT) y oro (commits `1cfbb8b`, +concurrency). Histórico 15m de 8
    monedas nuevas sembrado en la VM.
  - **`max_concurrent` 3→4** por evidencia (`research/concurrency_sweep.py`: domina a 3 en return,
    Sharpe y MaxDD).

## 6. Estado en vivo + qué esperar

**Desplegado 2026-06-22:** servicios `active`, `forward refresh: 23 series, 0 oscuras`, sin errores.
El gate lee OOS (PAXG bret +0.51, TRX vwap +0.32...). Es NORMAL ver alertas 👁️ OBSERVA además de
🟢 ENTRA, y algún "degradado a observe"/"señal vencida" (guardas funcionando).

**Criterio vigente:** acumular forward gateado de la cartera v2 (ahora con 17 combos y 4
concurrentes ⇒ mucho más rápido que los ~0.5 trades/día previos) y vigilar que el forward
confirme el OOS. NO aflojar el gate ni el anti-beta. Ampliar solo con combos que pasen
`universe_scan.py --tf 15m` + `validate_alts.py` (15m + doble-OOS + anti-beta).

## 7. ⚠️ Riesgo abierto #1 — SIZING antes de capital real

`concurrency_sweep.py` mostró **MaxDD backtest ~-60% a `risk_per_trade=2%`** (el freno diario
−6% no está en esa sim y ayudaría, pero la cola es alta). En dry-run no afecta el track record
(todo se mide en R). **Antes de pasar a paper/live hay que bajar R por trade** (medio-Kelly,
estilo `tvindicators` R=0.5% → MaxDD p95 ~-14%) y/o pesos por edge-ajustado-a-riesgo. Decisión
de Oscar; es el invariante de riesgo, no tocar a ciegas. Calibrar con una sim de cartera dedicada.

**Backlog:** retención BD + VACUUM; regla explícita de graduación/demote de observe; al pasar a
fills reales comparar fill vs `cost_audit`; borrar research/legacy; CI GitHub.

> Docs clave: `AUDIT_2026-06-22.md` · `FORWARD_REVIEW.md` · `STRATEGY_MAP.md` · `DEPLOY.md`.
