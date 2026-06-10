# Forward Review — primer ciclo real (paper)

> Bitácora de revisiones del forward en vivo (dry-run) y puntos abiertos a resolver.
> Última revisión: **2026-06-10** (datos 08–10 jun).

## 📌 Estado al 2026-06-10

- **Infraestructura:** sana. `errors: []`, reinicios OK, logging de cierre de trades **ya funciona** (`trades` + `trade_summary` poblados; antes faltaba).
- **Primer ciclo cerrado:** 5 trades.

| # | Símbolo | Estrategia | Lado | R | PnL | Cierre |
|---|---|---|---|---|---|---|
| 1 | TRX | orb_breakout | short | +0.25 | +$50 | timeout |
| 2 | TRX | vwap_anchor | long | −1.13 | −$226 | stop |
| 3 | TRX | break_retest | long | −1.10 | −$220 | stop |
| 4 | DOGE | vwap_anchor | long | −1.04 | −$208 | stop |
| 5 | DOGE | vwap_anchor | long | −1.04 | −$209 | stop |

**Neto: −4.07R · −$814 · win-rate 20% (1/5).** Paper, no capital real. n diminuto → no concluyente, pero la señal va en dirección incómoda.

## 🔴 Hallazgos

1. **Cero TPs alcanzados.** 4/5 a stop completo; el único verde fue timeout (+0.25R), no objetivo. La tesis *let winners run* no se materializó ni una vez. Patrón peligroso: cortar verde chico, perder full en rojo.
2. **Stops realizan peor que −1R** (−1.04 a −1.13R). Buffer anti-barridas + ejecución taker cuesta 4–13% extra sobre el 1R planeado. Sospecha: el backtest honesto puede NO modelar este slippage de salida → edge teórico inflado.
3. **`vwap_anchor` es el sangrador** (3 trades, 0% WR, −1.07R). Y **DOGE/vwap_anchor entró 2× en vivo con backtest n=1** (exp_R −3.46, sin validación). Re-entró el mismo setup perdedor. Fuga de proceso.
4. **Concentración correlacionada:** TRX tomó vwap LONG + break_retest LONG a la vez, misma dirección → 2× tamaño en la misma apuesta; ambas stopearon casi simultáneas. (La vez anterior, 06–08 jun, fue al revés: SHORT + LONG simultáneos en TRX casi al mismo precio → exposición neta ≈ 0 pagando doble coste.)

### Backtest vs forward (señal temprana = roja, n minúsculo)
| Combo | Backtest exp_R | Forward exp_R |
|---|---|---|
| TRX break_retest | +1.23 | −1.10 (n=1) |
| TRX vwap_anchor | +0.22 | −1.13 (n=1) |
| TRX orb_breakout | +0.18 | +0.22 (n=1) ✅ |
| DOGE vwap_anchor | −3.46 (n=1) | −0.82 (n=2) |

## 🎯 Puntos abiertos a resolver (próxima sesión)

> El usuario quiere buscar la **forma correcta** de resolver cada uno, no parchear. Discutir diseño antes de implementar.

1. **Gate de universo por validación.** Prohibir en vivo cualquier combo símbolo×estrategia con backtest `n < N` (N a definir, ~30). Mataría DOGE/vwap (n=1) y similares.
   - A discutir: ¿umbral por n? ¿además exigir exp_R>0 en backtest? ¿walk-forward en vez de un solo backtest?
2. **Veto cruzado por símbolo.** No abrir 2ª posición misma dirección/símbolo (evita doblar apuesta); bloquear también dirección opuesta (evita pagar doble coste para quedar flat).
   - A discutir: ¿netting real a nivel cartera vs veto a nivel señal? ¿límite de exposición por símbolo en lugar de veto binario?
3. **Auditar slippage de salida del backtest.** Confirmar si el motor honesto modela el −1.07R real en stops; si no, corregir para no sobrestimar el edge.
4. **Revisar `tp = 1e+18` (runner sin TP).** Aún pendiente de la revisión 06–08: loggear como `runner`/`null` y confirmar que ninguna fórmula de sizing/RR lo toma literal.

## 🗂️ Histórico de revisiones
- **2026-06-08** (datos 06–08 jun): 2 entradas TRX abiertas, sin cierres. Detectado: posiciones opuestas mismo símbolo, `tp=1e+18`, mono-TRX (resto ESPERANDO), faltaba logging de cierre.
- **2026-06-10** (datos 08–10 jun): primer ciclo de 5 trades cerrados (este doc).
