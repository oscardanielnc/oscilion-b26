# Oscilion — Visión

> ⚠️ **ACTUALIZACIÓN 2026-06-03 — PIVOT.** La validación honesta (12 monedas × 3
> años, neto de costos) **descartó la tesis de reversión** de este documento: no
> tiene edge y su calibración está invertida. El edge está en la **RUPTURA**
> (momentum/breakout de rango), no en el rebote — exactamente el riesgo que el §
> "veredicto honesto" marcó como decisivo. Ver **`docs/FINDINGS.md`** para la
> tesis vigente y los resultados. El resto de este documento queda como registro
> histórico de la hipótesis v1; los principios y el modelo de riesgo siguen vigentes.

## 🎯 Qué es

Sistema que analiza BTC, ETH, SOL y otras criptos para descubrir **rangos de oscilación** (horizontales y diagonales) y operar **reversión intradía** con alta convicción: entrar cerca de un borde del rango *con confirmación de giro*, salir en el borde opuesto, y proteger con un stop calculado contra barridas.

**Frecuencia:** baja (1–2 trades/día, o ninguno si no hay claridad). Calidad sobre cantidad.

## 🌟 Norte (hacia dónde vamos)

```
Calculadora  →  Monitor en vivo + alertas  →  Bot semi-auto  →  Bot 100% auto  →  Copy-lead Binance
   (Fase 2-3)        (Fase 4-5)                 (Fase 6)           (Fase 7)          (Fase 8)
```

El valor final: un bot que opera solo, con bajo drawdown, del que otros copian y pagamos/cobramos comisión (10–12%). Por eso desde el día 1: arquitectura bot-ready, riesgo controlado y **track record auditable**.

## 🧭 Principios (no negociables)

1. **Honestidad antes que esperanza.** El sistema debe poder decir *"hoy no operes"* y *"esta estrategia no tiene edge"*. Eso es éxito, no fracaso.
2. **Auditabilidad total.** Todo se guarda (snapshots, predicciones, decisiones, trades, parámetros). Sin datos no hay aprendizaje. El registro forward es el antídoto real contra el autoengaño del overfitting.
3. **Riesgo primero.** Nunca arriesgar > 2% por trade. La supervivencia importa más que el retorno.
4. **Solo lo predecible.** Operamos régimen de rango / canal limpio. El caos se observa, no se opera.
5. **Adaptado por moneda.** Nada se trata igual: apalancamiento, stops y tamaño se calibran por la volatilidad de cada moneda.
6. **Iterar con evidencia.** Si la v1 no rinde, diagnosticar con datos y mejorar dirigido; no abandonar a ciegas ni insistir a ciegas.

## 💡 Las ideas centrales

| Concepto | Traducción técnica |
|---|---|
| Rango horizontal | Bollinger / Keltner / VWAP bands / Donchian sobre S/R |
| Rango diagonal (tendencia) | Canal de regresión lineal |
| "¿Qué moneda respeta su rango?" | Hurst (<0.5), half-life OU, variance ratio, ADF → **score de reversión** |
| Régimen | Clasificador rango vs tendencia (ADX, ancho/estabilidad de bandas) + régimen de volatilidad |
| Convicción | Score 0–100% **calibrado** (80% ⇒ histórico ~80% de acierto) |
| Stop seguro | Borde + más allá del clúster de barridas + buffer ATR |
| Apalancamiento | = 2% ÷ distancia_stop → riesgo fijo, liquidación lejísimos |
| "Mejor entrada" | Borde + **confirmación de giro** (no a mitad de rango) |
| Salir a tiempo | Detección de agotamiento de momentum + ruptura en contra |

## ⚖️ El veredicto honesto (estado: hipótesis a validar)

- **Construirlo: viable.** La estrategia es legítima y la gestión de riesgo es superior a la media retail.
- **Que sea rentable: no garantizado.** Depende de un edge predictivo que **solo el backtest honesto + forward-test** pueden confirmar. Es posible que no exista tras costos.
- **Riesgo clave:** distinguir en vivo *rebote* de *ruptura*. Ahí se gana o se pierde.
- **Expectativa realista:** un Sharpe neto ~1–1.5 en un subconjunto de monedas/regímenes sería un buen resultado operable. No es una máquina de imprimir dinero.

## 🚦 Go / No-Go (puerta de decisión)

Antes de arriesgar dinero real, el sistema debe pasar:

- [ ] Backtest walk-forward **con costos reales** (fees + funding + slippage) → expectativa positiva.
- [ ] Score **calibrado** (probabilidades que se cumplen).
- [ ] Drawdown máximo tolerable y estable.
- [ ] **Paper trading** en vivo coherente con el backtest.

Si pasa → capital pequeño → escalar. Si no → diagnosticar, iterar, o pivotar/parar honestamente.

## 🛑 Lo que NO haremos

- Estrategias **sin stop-loss** ("esperar a que el precio vuelva"). Curva bonita hasta que un cisne negro liquida todo. Es riesgo escondido, no edge.
- Apalancamiento extremo (margen mínimo) por "eficiencia". La liquidación se acerca peligrosamente.
- Confiar en rangos pasados fijos. Todo se recalcula en ventana móvil, en tiempo real.
