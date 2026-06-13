# Estado del proyecto Oscilion — v0.6.0-pilot

**Actualizado:** 2026-06-12 (deploy confirmado en vivo + 2ª revisión forward).
Lee también `FORWARD_REVIEW.md` (bitácora forward + diseños de las guardas),
`STRATEGY_MAP.md` (dirección), `B_PORTFOLIO_PLAN.md`.

> **Resumen en una línea (2026-06-12):** infraestructura y proceso ✅ verificados en
> producción; **el edge sigue SIN veredicto** — la muestra gateada limpia es 1 trade abierto.
> No pivotar: decidir ahora sería con ruido. Acumular ≥50 trades gateados (§6).

---

## 1. Dirección (confirmada por Oscar)

**Oscilion = observador multi-moneda que asigna a CADA moneda la estrategia que se le
validó, deja correr ganadores, y solo opera donde hay edge demostrado.** Convicción > cantidad.

**Portfolio v1 (9 monedas, 12 series):**
| Moneda | Estrategia | Capital | Notas |
|---|---|---|---|
| BTC, BNB, TRX | EMA_TREND_STACK (tp_r=4) | ✅ (si pasa gate) | trenders; full+OOS+WF positivos |
| LINK, DOT, TRX | ORB_BREAKOUT (tp_r=4) | ✅ (si pasa gate) | breakout rescata alts |
| ETH, AVAX | VWAP_ANCHOR (tp_r=2.5) | ✅ (si pasa gate) | R3c; diversifican |
| BTC, TRX, XRP, DOGE | VWAP_ANCHOR | 👁️ observe | WF dudoso (full/test neg) |
| TRX | BREAK_RETEST | 👁️ observe | n=1 local; confirmar |

**"Capital" siempre condicionado al gate dinámico** (ver §3): sin n≥30 y exp_R>0 en el
backtest LOCAL, la serie opera como observe (sin capital) aunque la asignación diga capital.

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
3. **Gate de validación** (`gate_min_n=30`, `gate_min_exp_r=0`): capital solo si el
   backtest LOCAL (forward_results) lo respalda; si no → degrada a **observe**
   (trade virtual sin capital, `trades.observe=1`, fuera del PnL, sigue sumando stats).
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
- **2026-06-12: deploy CONFIRMADO en vivo.** Logs 10–12 jun: `cost_audit` poblado en cierres,
  stops a −1.04R exactos (slippage ya modelado, sin coste oculto), `errors: []`. 2 cierres de
  la ventana son **pre-gate** (DOGE/ETH vwap, entraron 22 min antes de los commits del gate);
  1ª entrada gateada legítima (AVAX, abierta). Acumulado forward 7 cerrados ≈ −6.2R, **todos
  pre-gate** → no refutan edge. Detalle en `FORWARD_REVIEW.md` (revisión 06-12).

## 6. Qué esperar tras el deploy + pendiente

**Tras desplegar, es NORMAL ver:**
- Eventos "degradado a observe" en monedas nuevas con histórico local corto (ETH/AVAX
  posiblemente) — es el gate funcionando; se gradúan solos cuando el backfill crece.
- Export diario con dos tablas: trades CON capital (cuentan) y observe (no cuentan).
- Alertas 👁️ OBSERVA en el móvil además de 🟢 ENTRA.

**Criterio vigente: ≥50 trades forward con capital (gateados) antes de cualquier
veredicto de edge. No tocar parámetros ni añadir estrategias mientras tanto.**
A ritmo post-gate ~0.5 trades/día ⇒ ≈3 meses; si es muy lento, palanca segura =
ampliar universo dentro de combos ya validados (n≥30 local), nunca aflojar el gate.

**A evaluar la próxima revisión (no urgente):**
- ⚠️ `vwap_anchor` va 0/5 en forward y ETH pasa el gate con exp_R **+0.022** (casi-cero).
  Propuesta: subir `OSCILION_GATE_MIN_EXP_R` 0.0 → **+0.05/+0.10** (≈ coste ida+vuelta) para
  exigir margen sobre comisiones. 1 línea / env var, sin tocar código. Decisión de Oscar.

**Backlog priorizado:**
- **B (infra):** retención BD (90d snapshots/events) + VACUUM mensual; StartLimitBurst=5
  en systemd; chequeo de disco; ORDER BY ts en /events.
- **C (deuda):** borrar ~700 LOC research/legacy (features/{ranges,regime,reversion},
  scoring, signals/entry, backtest/{engine,metrics,report}); mover costs.py fuera de
  backtest/; tests de integración (rehidratación, breaker, gate round-trip); CI GitHub.
- **D (validación — decide el target):** semáforo semanal backtest-vs-forward automático
  (ntfy domingos); regla explícita de graduación/demote de observe (p.ej. n_fwd≥20 y
  exp_R>0 gradúa; sum_R<−8R demota); al pasar a fills reales, comparar fill vs cost_audit
  y recalibrar slippage; reabrir maker-entry (R4).

> Docs clave: `FORWARD_REVIEW.md` · `STRATEGY_MAP.md` · `B_PORTFOLIO_PLAN.md` · `DEPLOY.md`.
