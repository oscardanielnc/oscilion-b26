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
