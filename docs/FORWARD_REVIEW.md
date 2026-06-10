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

## ✅ Puntos resueltos (2026-06-10, diseño + implementación)

1. **Gate de universo por validación** → `live/guards.gate_decision` + `db.get_forward_backtest`.
   Diseño elegido: el gate lee el **backtest LOCAL** (`forward_results` scope=backtest, motor
   honesto sobre los datos de ESTA máquina), no números de research: el caso DOGE/vwap fue
   exactamente "research dice n=36, la VM solo tiene n=1". Umbrales: `n ≥ 30` **y** `exp_R > 0`
   (`OSCILION_GATE_MIN_N` / `OSCILION_GATE_MIN_EXP_R`). Si no pasa → el trade se **degrada a
   observe** (virtual sin capital, `trades.observe=1`, excluido del PnL): sigue acumulando
   stats para poder graduarse, pero no sangra. Auto-corrige al crecer el histórico.
2. **Veto cruzado por símbolo** → `guards.capital_position_on_symbol`: máx **1 posición CON
   capital por símbolo** (cualquier estrategia y dirección). Observe no bloquea ni es bloqueado
   (no lleva capital). Netting de cartera descartado por sobreingeniería con 9 monedas.
3. **Auditoría de slippage de salida** → hallazgo: monitor y backtest usan el MISMO
   `CostModel.realized` ⇒ el −1.04/−1.13R **sí está modelado** (es slippage 2bps + fees +
   funding, no un coste oculto). Para verificarlo con datos cada cierre persiste
   `trades.cost_audit` (JSON): R descompuesto en `r_gross` (precio puro), `r_slip_exit`,
   `r_fee_entry/exit`, `r_funding` — visible en `/trades` y en el export diario. Si el día
   que haya fills reales el slippage observado supera el modelado, se recalibra `costs.py`.
4. **`tp = 1e+18`** → eliminado. Runner = `tp None` en estrategias/posición/BD/alertas
   ("tp runner"); internamente `tp_barrier()` usa ±inf que jamás dispara ni contamina sizing.

   Extras del mismo cambio: **piso de stop** `min_stop_pct` 0.2% (riesgo fijo / stop→0
   disparaba el notional; aplicado idéntico en monitor y engine) y **guard de señal vencida**
   `max_signal_age_min` 30m (tras downtime/refresh fallido no se entra a precio viejo — causa
   probable del ORB fuera de sesión: el filtro evalúa la hora de la VELA, no la actual).

## 🎯 Puntos abiertos

- Acumular ≥50 trades forward del núcleo gateado antes de cualquier veredicto de edge.
- Si llega ejecución real (paper→live): comparar fill real vs `cost_audit` modelado y
  recalibrar slippage de stop si el real es peor.

## 🗂️ Histórico de revisiones
- **2026-06-08** (datos 06–08 jun): 2 entradas TRX abiertas, sin cierres. Detectado: posiciones opuestas mismo símbolo, `tp=1e+18`, mono-TRX (resto ESPERANDO), faltaba logging de cierre.
- **2026-06-10** (datos 08–10 jun): primer ciclo de 5 trades cerrados (este doc).
