# Oscilion — Hallazgos de validación del edge

> Registro honesto de la campaña de validación (2026-06-03). Resume qué se
> probó, qué dijeron los datos, qué considerar y qué probar después.
> Reportes crudos: `data/reports/*.md` (gitignored, regenerables).

---

## 0. TL;DR

- ❌ **La tesis original (reversión en bordes de rango) NO tiene edge.** 12 monedas × 3 años, 1h y 15m, neto de costos: todas las configs pierden (PF 0.72–0.78) y la **calibración está invertida** (más score ⇒ peor). Enterrada con evidencia.
- ✅ **Pivot a momentum/breakout: edge real.** La *ruptura* funciona donde el *rebote* falla — justo el riesgo que VISION.md §45 marcó como decisivo.
- 🔒 **Validado OOS** (umbral elegido solo en train): la relación "ruptura más fuerte ⇒ mejor" se mantiene **monótona en datos no vistos**; walk-forward POOL OOS PF 1.18.
- 🎯 **Estrategia candidata: ruptura de rango fuerte.** `range` + breakout ≥2 ATR + confirmación → PF 1.37, +0.46%/trade, 38% winrate, y **positivo incluso en el período reciente** (el único filtro que repara 2025Q4→).
- ⚠️ **Caveats:** edge **fino y de baja frecuencia** (~323 trades/3 años/12 monedas). Vive o muere en la **ejecución (maker)**. Confianza moderada-positiva, no alta.

**Decisión de proyecto: PIVOT = GO** (desarrollar momentum/breakout). Infra, riesgo y motor en vivo se reutilizan tal cual; solo cambia la señal.

---

## 1. Cronología y evidencia

| Paso | Pregunta | Resultado |
|---|---|---|
| Campaña 1h | ¿Reversión tiene edge en 12 monedas × 3 años? | ❌ PF 0.76; **calibración invertida**; stops 66% vs TP 10% |
| Campaña 15m | ¿Cambia con el timeframe? | ❌ Peor (PF 0.72; más frecuencia ⇒ más costos) |
| Probe momentum | ¿El edge está en la dirección opuesta? | ✅ Momentum: calibración **monótona**; rupturas ≥1 ATR positivas |
| Validación OOS | ¿Es real o data-snooping? | ✅ Monótono en test no visto; walk-forward POOL OOS PF 1.18 |
| Robustez | ¿Estable o concentrado? | ✅ amplio (9/12 monedas), mejor en `range` que `trend`; 🚩 3 últimos trimestres negativos sin filtrar |
| Recencia | ¿`range`+≥2 ATR repara la recencia? | ✅ **Sí**: único filtro con período reciente positivo (PF 1.17) |

### Tablas clave

**Reversión vs momentum (1h, 12 monedas × 3 años, por-trade, neto de costos):**

| Estrategia | N | Winrate | PF | Exp/trade | Calibración |
|---|--:|--:|--:|--:|---|
| Reversión + giro | 5747 | 30.3% | 0.76 | −0.256% | 🔴 invertida |
| Momentum (todas las rupturas) | 7857 | 17.7% | 0.94 | −0.073% | 🟢 monótona |
| Momentum rupturas fuertes ≥1 ATR | 3092 | 28.9% | 1.07 | +0.125% | 🟢 |

**OOS (umbral elegido solo en train):** grilla con relación monótona en TEST (PF 0.92→1.18 al subir el umbral). Split anclado TEST: PF 1.01 (breakeven+). Walk-forward POOL OOS: PF 1.18, +0.308%/trade.

**Estabilidad por umbral (3 años):** PF sube hasta ~2.0–2.5 ATR (PF 1.15–1.20), luego el sample colapsa (2.5 ATR=246 trades; 3.0=65, ruido).

**Recencia — `range` + ≥2 ATR (el candidato):**

| Scope | N | Winrate | PF | Exp/trade |
|---|--:|--:|--:|--:|
| TODO (3 años) | 323 | 38.4% | 1.37 | +0.456% |
| anterior (→2025Q3) | 246 | 38.6% | 1.44 | +0.512% |
| **RECIENTE (2025Q4→)** | 77 | 37.7% | **1.17** | **+0.277%** |

Aflojar cualquiera de los dos filtros (≥1.5 ATR, o todos los regímenes) ⇒ período reciente **negativo**. La combinación es la que repara.

---

## 2. Estrategia candidata (spec actual)

```
Señal:    ruptura de rango (breakout) en continuación, NO reversión.
Setup:    régimen = range (precio venía oscilando en banda) Y el cierre
          rompe un borde por ≥ 2·ATR.
Lado:     ruptura alcista → long ; ruptura bajista → short.
Confirm:  vela en la dirección + momentum (RSI) acompañando.
Stop:     de vuelta dentro del rango (borde roto ∓ buffer ATR) — anti-fakeout.
TP:       measured move = proyección del ancho del rango.
Riesgo:   2% del equity por trade; L = 2% / stop% (invariante intacta).
Frecuencia: BAJA (~108 trades/año sobre 12 monedas). Calidad sobre cantidad.
```

Implementación: `oscilion/analysis.py::breakout_candidate`, `engine` con
`BTParams(strategy="momentum", min_breakout_atr=2.0, allow_regimes=("range",))`.

---

## 3. Consideraciones (leer antes de seguir)

**Metodológicas**
- **Las métricas pooled de retorno/Sharpe/MaxDD NO son fiables** (juntan 12 backtests independientes, cada uno sizeado al 2% de SU equity → la cuenta ficticia llega a ruina; el −100%/−98% lo delata). Usar SIEMPRE las **por-trade**: winrate, PF, expectancy, y calibración.
- El umbral ≥2 ATR se eligió mirando datos; mitigado con OOS (train/test + walk-forward) pero **conviene re-confirmar** al cambiar cualquier cosa (costos, TF, universo).
- **Sin look-ahead** garantizado: decisión al cierre de la barra i, fill al open de i+1; intrabar conservador (stop antes que TP).

**De riesgo / negocio**
- **Baja frecuencia ⇒ poco sample ⇒ ruido alto** por trimestre. El cuello de botella es el número de trades. Más instrumentos / multi-TF darían más muestra.
- **Edge fino (+0.28 a +0.46%/trade) ⇒ los costos mandan.** El probe usó taker+slippage (peor caso). Entradas **maker** podrían ser la diferencia entre tradeable y no.
- **Recencia:** reparada con el filtro, pero 2026Q1 sigue negativo y los buckets recientes son chicos. Vigilar en forward-test.
- `trend`-regime breakouts pierden (llegan tarde); por eso el filtro `range` importa.

**Infra / reproducibilidad**
- Backtest paralelo en Windows: **fijar `OMP/OPENBLAS/MKL_NUM_THREADS=1` antes de importar numpy** o se cuelga por sobre-suscripción de hilos BLAS (ya está en los scripts de `research/`).
- Reproducir: `python -m oscilion.data sync --days 1095` y luego los scripts de `research/` (ver §5).

---

## 4. Backlog priorizado (qué probar)

1. **Ejecución maker** (mayor impacto). Modelar entradas límite (en el nivel / en el retest, con no-fill) en el engine y re-validar OOS. Un edge fino se gana o se pierde acá.
2. **Confirmar el candidato OOS** con el filtro completo (`range`+≥2 ATR) en walk-forward dedicado (no solo el umbral suelto).
3. **TP/exits para momentum:** measured-move vs trailing (dejar correr ganadores; el momentum tiene colas gordas). Hoy el TP fijo puede dejar dinero en la mesa.
4. **Subir el sample:** multi-TF (4h/1h/15m combinados), más instrumentos líquidos, sin sobre-ajustar el umbral por TF.
5. **Sizing de cartera** con el edge real (Kelly fraccionado sobre expectancy medida + correlación). El edge por-trade es fino: la construcción de cartera importa.
6. **Reconstruir el `score`** para momentum (hoy es solo fuerza de ruptura). Buscar features que mejoren la calibración monótona (volumen en la ruptura, compresión previa de rango, etc.).
7. **Detección de régimen reciente** (filtro adaptativo): si el mercado entra en modo choppy/anti-breakout, reducir o pausar.
8. **Forward-test en vivo** (dry-run) del candidato para acumular track record fuera de muestra real.

---

## 5. Scripts de investigación (`research/`)

| Script | Qué hace | Reporte |
|---|---|---|
| `edge_campaign.py --tf {1h,15m}` | reversión vs variantes, por símbolo/semestre/régimen/calibración | `edge_campaign_{tf}.md` |
| `momentum_probe.py` | reversión vs momentum + filtro de rupturas fuertes | `momentum_probe.md` |
| `breakout_oos.py` | validación OOS (split anclado + walk-forward) | `breakout_oos.md` |
| `breakout_robustness.py` | umbral, recencia trimestral, régimen, vol, símbolo | `breakout_robustness.md` |
| `breakout_recency.py` | ¿el filtro range+≥2ATR repara la recencia? | `breakout_recency.md` |

Todos paralelizan por símbolo (12 cores) con el pin de hilos BLAS.

---

## R6 — Horizonte de los trades EMA-trend (2026-06-04)

> ¿Acortar el hold (timeout 240h ≈ 10d) reduce riesgo sin matar el edge?
> Motor honesto, entrada fija validada, solo cambia el exit. OOS=2025→.
> Reporte crudo: `data/reports/r6_exit_horizon.md` (regenerable: `research/exit_horizon.py`).

**Marco:** el hold **mediano real es ~2 días**, no 10; el timeout de 10d solo muerde al 6-18% (la cola). Cripto cotiza 24/7 → **sin gaps de finde**; el funding ya está costeado.

**Evidencia OOS (exp_R):**

| Moneda | baseline 240h | 120h | 96h | 72h | Lectura |
|---|---:|---:|---:|---:|---|
| BTC | **+0.131** | +0.021 | −0.007 | −0.105 | acortar **destruye** el edge (monótono) |
| BNB | **+0.407** | +0.348 | +0.222 | +0.065 | 120h casi gratis; <96h colapsa |
| TRX | +0.137 | +0.123 | −0.074 | +0.141 | tolera 72-120h, ~neutral |

Trailing (1.5/2/3 ATR) y time-stops ≤72h salieron negativos o peores → **confirma aprendizaje #9 (recortar ganadores hace daño)**. El edge de tendencia vive en los runners.

**Decisión:** BTC mantiene 240h (no tocar). **BNB y TRX → cap 120h** (`max_hold` 30 barras 4h): ~gratis en OOS y elimina el 100% de zombies de 10d (timeout 6-8% → 0%).

**Bug colateral corregido:** el monitor en vivo NO aplicaba timeout (`_manage` solo cerraba por stop/tp → posición eterna). Ahora cierra a mercado al vencer el horizonte (reason `timeout`, alerta ⏱️ CIERRE_TIEMPO), consistente con el motor honesto.

---

## R3b — Campaña momentum_pullback + break_retest (2026-06-04)

> Validar las 2 estrategias codificadas-sin-desplegar en las 12 monedas, motor honesto,
> full + sweep(train→test) + walk-forward (veredicto primario). `research/strat_validation.py`.

**`momentum_pullback` → ❌ RECHAZAR.** 12 monedas, solo 3 positivas WF y marginales (SOL +0.056,
XRP +0.064, LTC +0.201); mediana −0.081; default full negativo en las 12. Edge ≈ ruido. No desplegar.

**`break_retest` → ❌ general, ✅ TRX (candidato).** Mediana −0.161 (11/12 neg). **TRX robusto en
TODOS los cortes:** full +0.608 · test +0.190 · sweep +0.391 · **WF +1.451 (n=67, WR 30%)**.
Cfg: long_only · retest_half_atr=0.3 · tp_r=0 (sin TP) · trend_filter=False · vol_max_ratio=1.0.

**Asterisco:** TRX = 1 de 24 combos → riesgo de comparaciones múltiples; además TRX ya carga ema+orb
(concentración). Decisión: NO desplegar con capital aún → **forward-test** TRX break_retest antes de darle peso.

---

## R3c — Validación vwap_anchor (2026-06-04)

> Portado fiel de sentinel (VWAP Anchor v2, LONG-only). Gate de entrada = C1 (price>VWAP 1h)
> ∧ C2 (price>VWAP 4h) ∧ O1 (frescura EMA9<EMA21 1h). C3 (EMA50 4h) opcional. SL=k·ATR1h, TP=tp_r·R.
> signal_tf=1h, aux=4h, max_hold=120 (5d). `research/strat_validation.py vwap_anchor`.

**Veredicto: ✅ EDGE GENERALIZABLE (el mejor de los 3 portados).** 12 monedas, **6 positivas WF OOS**,
mediana equiponderada **+0.069** (positiva, vs −0.08/−0.16 de momentum/break_retest).

| Superviviente | V | full | TEST | WF OOS (n) |
|---|:--:|---:|---:|---:|
| TRX | ✅ | +0.220 | +0.318 | **+0.877** (72) |
| ETH | ✅ | +0.023 | +0.111 | **+0.173** (90) |
| AVAX | ✅ | +0.171 | +0.104 | **+0.154** (68) |
| BTC | 🟡 | +0.035 | −0.014 | +0.608 (43) |
| XRP | 🟡 | −0.106 | −0.249 | +0.200 (110) |
| DOGE | 🟡 | −0.068 | −0.234 | +0.697 (36) |

**Más confiables = ✅ trío (ETH, AVAX, TRX):** positivos en full+test+WF a la vez. Los 🟡 (BTC/XRP/DOGE)
tienen full o test negativo → WF positivo huele a suerte de fold; tratar como observación.

**Caveats:** WR bajo (12-37%) → cola gorda, depende de pocos ganadores grandes; los WF eligen casi siempre
**tp_r=0** (sin TP, deja correr) — coherente con #9. n OOS modesto (36-110). Confianza moderada-positiva.

---

## R7 — Patrones de vela como filtro (2026-06-04)

> Estudio de poder discriminante (independiente de estrategia), 12 monedas, 3 años, 1h.
> 6 patrones de sentinel; métrica = P(dirección correcta) con barreras ±1·ATR, H=24h.
> `research/candle_patterns.py`. (~6500 eventos/moneda; SE≈0.6pp.)

**Parte 1 — Patrón SOLO = SIN edge.** P(correcta) entre 49.0% y 50.8% en las 12 monedas →
indistinguible de 50% (azar). Confirma sentinel y la tesis "un patrón no garantiza nada".

**Hipótesis 'volátiles respetan más' → NO apoyada (en 1h).** Spearman respeto↔volatilidad
ρ=**−0.48** (p=0.12): si acaso, las MENOS volátiles (BNB 0.71%, TRX 0.44%) respetaron algo más;
las más volátiles (SOL/AVAX/DOT/LINK ~1.2%) quedaron en medio/abajo. (Sentinel lo vio en 15m →
puede ser dependiente del TF; pendiente verificar en 15m.)

**Parte 2 — Confirmadores (lift en P, equiponderado, consistencia entre monedas):**

| Indicador | lift | consistencia | lectura |
|---|--:|--:|---|
| vwap_lado (precio del lado correcto de VWAP) | +1.5pp | 10/12 | mejor, pero pequeño |
| trend (precio vs EMA50 alineado) | +1.1pp | 10/12 | consistente |
| vol_spike / vol_alta | +0.5–0.8pp | 6–8/12 | ruidoso |
| **rsi_extremo** (reversión en sobreventa/compra) | **−3.7pp** | 1/12 | **DAÑA** |
| en_extremo (en soporte/resistencia) | −0.8pp | 6/12 | no ayuda |

**Síntesis:** el patrón vale algo SOLO con la TENDENCIA (alineado a VWAP/EMA50 = continuación),
nunca como reversión (RSI extremo y "en soporte" restan). El lift es marginal (~1-1.5pp) → sirve
como **filtro/boost de confluencia sobre una estrategia trend existente, jamás como señal primaria**.

### R7b — Verificación 15m + SUI (2026-06-04)

> Repetido en 15m (TF nativo de sentinel) y añadida SUI (caso fuerte en sentinel).
> `research/candle_patterns.py 15m`. n enorme (25k+ eventos/moneda → SE≈0.3pp).

**Patrón solo = cero edge, confirmado en 15m.** P(correcta) 49.2-50.2% (ruido con ese n).

**Hipótesis 'volátiles respetan más' → ENTERRADA (2 TFs).** 1h ρ=−0.21 (p=0.48), 15m ρ=+0.08 (p=0.79).
SUI fue alta en 1h (50.7%, y la más volátil 1.56%) pero **media en 15m** (49.9%) → el caso de sentinel
no reproduce en datos honestos. Sin correlación respeto↔volatilidad en ninguno.

**Confirmadores (15m, consistente con 1h):** trend +1.2pp (11/13), vwap_lado +0.9pp (11/13),
stack +0.8pp (11/13), vol_spike +0.7pp (12/13). Reversión vuelve a restar (rsi_extremo −1.0, en_extremo −0.9).

**VEREDICTO FINAL:** patrones de vela NO se despliegan. Solos = ruido; la única confluencia útil
(alineación con tendencia) ya la capturan las estrategias trend (ema/vwap/orb). Lift ~1pp no justifica
la complejidad. Documentado y aparcado.
