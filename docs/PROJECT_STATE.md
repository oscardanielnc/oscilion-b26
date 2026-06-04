# Estado del proyecto Oscilion — v0.6.0-pilot

**Actualizado:** 2026-06-03. Lee también `STRATEGY_MAP.md` (dirección), `VALIDATION_R1_R2.md`,
`BTC_SALVAGE.md` (rescate), `B_PORTFOLIO_PLAN.md` (lo que falta afinar).

---

## 1. Dirección (confirmada por Oscar)

**Oscilion = observador multi-moneda que asigna a CADA moneda la estrategia que se le
validó, deja correr ganadores, y solo opera donde hay edge demostrado.** Convicción > cantidad.

**Núcleo v1 (pilot):**
| Moneda | Estrategia | Por qué |
|---|---|---|
| BTC, BNB, TRX | **EMA_TREND_STACK** (tp_r=4) | trenders limpios; positivos full+OOS+WF |
| LINK, DOT, TRX | **ORB_BREAKOUT** (tp_r=4) | breakout rescata alts; positivos full+OOS+WF |

Fuera por ahora (sin edge limpio): SOL, ETH, AVAX. Marginales en observación: ADA, DOGE, XRP, LTC.

---

## 2. Arquitectura (estado actual)

```
oscilion/
├── strategies/          ★ NÚCLEO de primera clase (fuente única de señal)
│   ├── library.py       4 estrategias puras (EMA_STACK, ORB, momentum, break_retest)
│   ├── context.py       build_ctx multi-TF (backtest Y live) — sin look-ahead
│   ├── assignment.py    PORTFOLIO: moneda→estrategia(s)+params (la DIRECCIÓN)
│   └── portfolio.py     capa de cartera (scaffold B: weights/leverage/límites)
├── live/                ★ FASE A (validación con datos reales)
│   ├── forward.py       backtest vs forward por moneda×estrategia → BD (log conciso)
│   └── monitor.py       dry-run: alertas ENTRA/SAL + trades virtuales + estado
├── backtest/
│   ├── engine_strat.py  motor honesto (señal coarse, salida 15m pesimista, costos, R)
│   ├── resample.py      1h→2h/4h causal
│   ├── engine.py·costs·metrics·report   (research/validación previa)
├── data/                fetch·store·universe·pipeline (ccxt, parquet+DB, sin look-ahead)
├── features/            indicators (ATR/EMA/RSI/BB/VWAP/ADX...) · ranges·regime·reversion (research)
├── risk/                sizing (L=2%/stop)·stops·allocation
├── persistence/         db (SQLite WAL, append-only, migraciones) · models (schema v3)
├── api/app.py           /health /status /state /forward /trades /candidates /calibration /data /events
├── orchestrator.py      loop resiliente 24/7 → LiveMonitor + publica state.json
├── circuit_breaker · notify · logging_setup
research/                campañas de validación (edge_campaign, *_validation, correlation_map...)
docs/                    VISION · STRATEGY_MAP · VALIDATION_R1_R2 · BTC_SALVAGE · B_PORTFOLIO_PLAN · este
```

**Calidad/robustez:** SQLite WAL + lock + **busy_timeout** (concurrencia API↔orquestador),
escrituras atómicas (parquet, state.json), cada tick en try/except (no muere), migraciones
idempotentes, estrategia = fuente única, **backup diario de la BD** (VACUUM INTO, data/backups/),
**ejecución compartida engine↔monitor** (`costs.realized` → los trades del monitor coinciden con
la validación forward), **tests** (`pytest`, 7 smoke) incl. guardián que impide que producción
importe research.

### Producción vs Research (separación, enforced por test)
- **Producción (path vivo):** `config`, `persistence/{db,models}`, `data/{fetch,store,pipeline,universe}`,
  `features/indicators`, `strategies/{library,context,assignment,portfolio,tuned}`,
  `backtest/{engine_strat,resample,costs,portfolio_sim}`, `live/{monitor,forward,signals,export}`,
  `signals/maker_taker`, `orchestrator`, `circuit_breaker`, `notify`, `logging_setup`, `api/app`.
- **Research/legacy (NO en producción):** `analysis` (reversión), `backtest/{engine,metrics,report}`,
  `scoring/conviction`, `features/{ranges,regime,reversion}`, `risk/{sizing,allocation,stops}`,
  `signals/entry`. Los usan los scripts de `research/`. `test_production_no_importa_research` lo verifica.

---

## 3. Fase A — validación forward (ACTIVA)

Cada implementación que necesite validación deja **logs concisos en BD consultables desde el
frontend** (directiva permanente). Hoy:
- `forward_results` (tabla): por moneda×estrategia, `backtest` vs `forward` (n, winrate, exp_R).
- `trades` (status=closed): trades virtuales con `strategy` y `r_multiple`.
- API: `/forward`, `/trades`, `/state`. CLI diario: `python -m oscilion.live.forward`.
- `inception` = 2026-01-01 (holdout pre-deploy de auto-test); **al desplegar en la VM se fija a
  la fecha de despliegue** y el forward pasa a ser datos reales no vistos.

**Auto-test del holdout 2026 (pre-deploy):** BTC/TRX/LINK aguantan fuerte; BNB y DOT flaquean
(n chico) — se vigilará en vivo.

---

## 4. Cómo correr

```powershell
python -m oscilion                  # orquestador 24/7 (monitor dry-run + alertas + forward)
python -m oscilion.api              # API para el frontend
python -m oscilion.live.forward     # revisión diaria backtest vs forward
python -m oscilion.data sync --days 1095   # refrescar histórico
```

---

## 5. Pendiente (en orden)
1. **Fase B — cartera** (ver `B_PORTFOLIO_PLAN.md`): mejores params por moneda, capital por
   moneda, multiplicadores de apalancamiento, mapa de correlación (ya hay v1), límites. Muchas
   pruebas hasta máx. beneficio / mín. riesgo.
2. **Frontend** (React + lightweight-charts) leyendo la API.
3. **Deploy v1 en VM Oracle** (systemd, fijar inception) y vigilancia diaria por logs.
4. **Expansión futura** (anotado): más estrategias por moneda, monedas nuevas, recuperar
   SOL/ETH/AVAX, VWAP_ANCHOR, ejecución maker (R4, lift chico), exits trailing para ORB.
```
