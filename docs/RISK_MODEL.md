# Oscilion — Modelo de Riesgo

El corazón del sistema. Todo trade respeta esta matemática.

## 1. La ecuación maestra

```
Apalancamiento (L) = Riesgo_máx(%) ÷ Distancia_stop(%)
                   = 2% ÷ stop%
```

Consecuencias automáticas (sin elegir números a mano):

| Propiedad | Resultado | Por qué |
|---|---|---|
| Pérdida si salta el stop | **= 2% del margen** siempre | L · stop% = 2% |
| Ganancia si llega a meta | **= 2% · RR** | L · move% = 2% · (move/stop) |
| Distancia a liquidación | **~50× la del stop** | stop está al 2% del camino a la liquidación |
| Apalancamiento por moneda | alto en baja-vol, bajo en alta-vol | stop fino ⇒ L grande |

> 📌 **Regla de oro:** el usuario piensa en "pierdo máx 2% / gano mín 5%". El sistema elige el apalancamiento para que eso se cumpla, sea cual sea la distancia del stop.

## 2. El filtro RR ≥ 2.5

Como `ganancia = 2% · RR`, para una meta de **+5%** se necesita **RR ≥ 2.5** (la meta a ≥ 2.5× la distancia del stop).

```
profit% = 2% × RR
RR 2.5 → +5%   |   RR 3 → +6%   |   RR 4 → +8%
```

➡️ **Una moneda cuyo setup no ofrece RR ≥ 2.5 NO se opera ese día.** Es un filtro, no una preferencia.

## 3. Ejemplo por moneda (capital $10k)

| Moneda | Vol/día | Stop seguro | L = 2%/stop | Meta (RR≥2.5) | Pérdida máx |
|---|---|---|---|---|---|
| BTC | ~1.5% | 0.5% | ~4× | +5% (move ~1.25%) | −2% |
| ETH | ~3% | 1.2% | ~1.7× | +5% (move ~3%) | −2% |
| Alt volátil | ~10% | 4% | ~0.5× | +5% (move ~10%) | −2% |

## 4. Stop anti-barridas 🩸

El nivel obvio (p.ej. 100) es donde cazan stops. El stop NO va ahí.

```
   rango: [100 ────────────── 120]
                │
   clúster de stops obvios →  99-98  ← zona de barrida institucional
                │
   STOP SEGURO  →  97.9   (más allá del clúster + buffer ATR)
```

Inputs para calcularlo: mechas históricas que perforaron y revirtieron, mapa de liquidaciones/stops, ruido típico (ATR) de la moneda. Si el stop seguro queda más lejos → **L baja solo**, pérdida sigue en 2%. Sin costo de riesgo extra.

## 5. Sizing de cartera (multi-moneda)

El usuario elige hasta ~3 monedas del top. Cada una mantiene su −2%/+5% **sobre su propio margen**. Peso del capital por:

```
peso_i ∝ f( conviccion_i , 1/volatilidad_i , correlación_entre_elegidas )
```

- **Convicción** (score) → más capital al más probable.
- **Volatilidad** → menos a la más errática.
- **Correlación** ⚠️ → BTC/ETH/SOL van casi juntos. 3 longs correlacionados = **1 sola apuesta triplicada**, no diversificación. El sistema lo avisa y ajusta.
- Método: **Kelly fraccionado** (acota el tamaño solo) con la versión proporcional como referencia visible.

Peor caso (todos los trades saltan el stop el mismo día) ≈ **−2% del capital total** si está desplegado al 100%.

## 6. TP dinámico

`+5%` es el **piso para entrar**, no el techo. En el trade:
- Si el momentum tiene convicción de seguir → la meta se extiende con **trailing**.
- Si el momentum se agota a mitad de camino → **avisar / tomar ganancia parcial**.
- Trailing sube el stop a break-even apenas el trade va a favor.

## 7. Maker vs Taker (decisión de ejecución)

| Acción | ¿Urgencia? | Orden | Costo (USDC) | Regla |
|---|---|---|---|---|
| Entrada en borde | No | Límite **post-only** (maker) | 0% | Si no llena, no se opera. Sin daño. |
| Take-profit en meta | No | Límite maker | 0% | Paciente, espera el precio. |
| **Stop / ruptura en contra** | **SÍ** | Mercado / taker | ~0.036% | **Salir ya.** Nunca arriesgar el fill por ahorrar fee. |

Costo real medido = **fee + medio spread** por moneda (no asumir USDC siempre; usarlo donde rinde).

> ⚠️ **Nunca sacrificar la certeza de ejecución de un stop por ahorrar comisión.** 0.036% es seguro barato contra una pérdida de 2%+.
