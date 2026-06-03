# Rescate del proyecto BTC/Sentinel — qué nos sirve

> Revisión a fondo de `C:\Users\LENOVO\btc` (sistema `sentinel`, descartado tras
> auditoría 2026-05-29). Objetivo: extraer datos, estrategias, aprendizajes y
> tácticas reutilizables para Oscilion (observador multi-moneda que pronostica
> dirección y dice cuándo entrar). Fecha de revisión: 2026-06-03.

---

## 0. Conclusión de la revisión

El proyecto BTC llegó **independientemente a las mismas conclusiones que Oscilion** —
con otro código, otras estrategias y otra metodología. Eso eleva mucho la confianza:

| Hallazgo | Oscilion | BTC/Sentinel |
|---|---|---|
| Reversión a la media | ❌ sin edge (PF 0.76, calibración invertida) | ❌ BB_REVERSION Sharpe −0.62/−0.73 |
| Momentum / breakout / continuación | ✅ edge OOS (regime-condicional) | ✅ EMA_STACK, MOMENTUM_PULL, ORB, VWAP, BREAK_RETEST positivos OOS |
| Edge bruto ~breakeven, **los costos deciden** | ✅ | ✅ (auditoría: #1 lever = ejecución maker) |
| La **convicción/score NO predice** edge | ✅ (calibración invertida) | ✅ ("sizing-por-convicción es ruido") |
| Gestión que recorta ganadores hace daño | (pendiente) | ✅ (hold-a-T2 > parcial+breakeven+trail) |

**Hay mucho que rescatar**: 5+ años de datos, una biblioteca de estrategias con
resultados, y decenas de aprendizajes ya pagados con trabajo. **El gran asterisco:**
los backtests positivos de las estrategias salieron del harness propio de sentinel,
que la auditoría encontró **optimista** en otras tácticas (vpoc/mttc/srb dieron
−0.127R al medirlos con motor honesto). ⇒ **hay que re-validar esas estrategias con
el motor honesto de Oscilion** antes de creerles.

---

## 1. Datos reutilizables (alto valor, listos)

`C:\Users\LENOVO\btc\backtest\data\`

| Dataset | Cobertura | Uso |
|---|---|---|
| `futures_um/BTCUSDT_1m.parquet` (120 MB) | 2021–2026, 1 minuto | **Oro**: salidas intrabar honestas (SL antes que TP) |
| `futures_um/BTCUSDT_{5m,15m,1h,4h}.parquet` | 2021–2026 | señales multi-TF |
| `futures_um/BTCUSDT_funding.parquet` | histórico | costo de funding real |
| `{14 alts}_1h_730.csv` + `_15m.csv` | 730 días | aave, ada, apt, avax, bnb, doge, dot, eth, inj, link, sol, sui, xrp |

→ Oscilion ya descarga su propio histórico vía ccxt; estos datos sirven como
**fuente cruzada / verificación** y para el motor de salida 1m (que Oscilion aún no tiene).

---

## 2. Estrategias documentadas (la joya) — TRAIN/TEST 2023–2026

Resultados del harness de sentinel (a re-validar honesto). Ordenadas por interés:

| Estrategia | Tipo | TEST Sharpe | TEST avg R / WR | Dirección | Nota |
|---|---|---:|---|---|---|
| **EMA_TREND_STACK** | tendencia | **1.41** | +0.68R / 60% | LONG-only | stack 9>21>50 4H + pullback a EMA21 |
| **MOMENTUM_PULLBACK** | continuación | **1.01** | +0.14R / 54% | LONG-only | impulso 2H + pullback 10–80%, TP=2R |
| **VWAP_ANCHOR** | tendencia | 0.92 | +0.22R / 40% | LONG-only | precio>VWAP 1H y 4H, TP=2.5R |
| **BREAK_RETEST** | continuación | 0.85 | +0.85R / 50% | long+short | ruptura **silenciosa** (bajo vol) + retest, n pequeño |
| **ORB_BREAKOUT** | breakout | 0.83 | +0.26R / 47% | long+short | rompe rango 6H estrecho, sesión EU/NY |
| BB_REVERSION | reversión | −0.62 | / 34% | — | ❌ pierde salvo régimen lateral raro |

**Lectura:** las 5 primeras son **momentum/tendencia/continuación** → alinean con el
pivot de Oscilion. La única **contraria** (BB_REVERSION) pierde, igual que la reversión
de Oscilion. Código fuente en `btc/sentinel/strategies/*.py`.

---

## 3. Aprendizajes transferibles (tácticas pagadas con trabajo)

1. **Entrar FRESCO, antes de que la multitud confirme.** Gate repetido y validado en
   varias estrategias: si EMA9/21 1H **ya** está alineado → entrada tardía, R:R peor.
   (`O1_gate` / `C3 invertido`). Es un edge real de *timing*. ⇒ probar en Oscilion.
2. **Muchos indicadores estándar son "null filters"** (RSI, MACD): ~igual activación en
   ganadores y perdedores. No confiar sin medir poder discriminante.
3. **Costos deciden.** Edge bruto ~breakeven; ejecución **maker** es la palanca #1 (igual
   que Oscilion). El diseño de entrada límite/retest baja el drag.
4. **Convicción ≠ edge.** Dimensionar por "convicción" fue ruido. (= calibración invertida).
5. **Régimen-dependencia:** breakout/momentum brillan en volátil/rango-luego-ruptura;
   se aplanan en tendencia suave. Reversión solo sirve en lateral. (= Oscilion).
6. **Exits por estrategia:** MOMENTUM_PULL mejora mucho con TP=2R; ORB empeora con TP
   (deja correr ganadores). No hay exit único — depende de la táctica.
7. **Sesgo direccional:** BTC LONG-only (sesgo alcista estructural; SHORT destruyó capital
   en estrategias de tendencia). ORB sí usa SHORT (ruptura de rango en volátil).
   ⇒ la dirección óptima es **condicional al activo/régimen** (clave para "pronosticar dirección").
8. **Sesión:** Europa/NY rinden; Asia genera whipsaws. Ventanas tóxicas: 22–23 UTC,
   cierre CME viernes, ±1h de news macro (CPI/FOMC/NFP).
9. **Gestión:** recortar ganadores (parcial@T1 + breakeven + trail) restó; hold-a-T2 sumó.
10. **Patrones (señales contextuales)** con condiciones documentadas (índice + skip_when):
    FUND_EXT (primer spike, RSI neutro), LIQ_SWEEP (requiere 4H alineado), SESSION_BREAK
    (ruptura Asia contra-tendencia 75%), ROUND_MAG, CME_GAP. Edge débil/contextual — útiles
    como **filtros/boost**, no como señal primaria.

### Ya rechazado con evidencia (NO re-investigar a ciegas)
GARCH/ATR sizing (OOS 0.025) · OU/VA-return (sin edge) · Kelly (N insuficiente) ·
OB-imbalance standalone (sin edge) · liq-stream CVD proxy (OOS 0.21) · sizing-por-convicción.
HMM 5-estados: sofisticado pero **no creó edge** por sí solo (sistema siguió negativo).

---

## 4. Metodología que vale la pena heredar
- **Métrica primaria = expectativa por trade (R)**, no % compuesto.
- **Pipeline:** aislar → backtest OOS ≥0.70 → backtest conjunto → producción.
- **Motor de salida 1m pesimista** (SL antes que TP en el mismo minuto) + costos reales.
  Oscilion hoy resuelve intrabar con la vela base; el 1m de BTC permitiría subir el realismo.

---

## 5. Qué rescatar vs. descartar

| Rescatar ✅ | Descartar / archivar 🗄️ |
|---|---|
| Datos 1m/funding BTC + 14 alts | El stack de producción de sentinel (HMM, torneo, OI, Kalman) — complejo y sin edge neto |
| Lógica de las 5 estrategias momentum/tendencia | BB_REVERSION (contraria, pierde) |
| Aprendizajes 1–10 (esp. gate de frescura, costos, exits) | Patrones de edge débil como señal primaria |
| Metodología (R, OOS≥0.7, motor 1m pesimista) | Conclusiones del harness optimista sin re-validar |

---

## 6. Hipótesis a validar (honestamente, en Oscilion)

| # | Hipótesis | Test |
|---|---|---|
| H1 | Las estrategias momentum/tendencia mantienen expectativa **positiva con motor honesto** (costos reales, salida 1m pesimista) en 12 monedas | portar a `breakout_candidate`-style + engine honesto, OOS |
| H2 | El **gate de frescura** (entrar antes de que EMA 1H confirme) añade edge **genérico** (no solo BTC) | A/B con y sin gate, por moneda |
| H3 | **Ejecución maker** convierte edges finos en sólidos | modelar fills límite (no-fill / adverse selection) |
| H4 | La **dirección óptima** es condicional (LONG-only por sesgo, o regime-dependiente) | medir long vs short por moneda/régimen |
| H5 | El **exit óptimo** depende de la táctica (TP 2R vs trailing vs hold) | grid de exits por estrategia |
| H6 | Combinar **supervivientes poco correlacionados** sube el Sharpe de cartera | portfolio multi-moneda |
| H7 | **Filtro de régimen** (range/trend de Oscilion) mejora cada estrategia | condicionar por régimen |
| H8 | **Filtro de sesión** (EU/NY) generaliza más allá de BTC | A/B por sesión |

---

## 7. Foco (no perderlo)

Oscilion = **observador constante multi-moneda** que pronostica dirección (↑/↓) y dice
**exactamente cuándo entrar**, con la mayor convicción posible y **sabiendo salir a tiempo**
(aunque no llegue al +5%; lo importante es acertar la dirección y gestionar el riesgo).
El rescate del proyecto BTC sirve a ese foco: aporta **estrategias direccionales validadas
en una dirección** (momentum/continuación) y aprendizajes de ejecución/timing — justo lo
que convierte "tenemos un edge fino" en "sabemos cuándo y cómo entrar".

> El plan de pruebas multi-sesión está en `docs/ROADMAP.md` (sección "Fase de pruebas — rescate BTC").
