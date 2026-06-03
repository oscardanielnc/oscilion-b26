# Mapa estrategia × moneda — qué funciona, dónde (validación honesta R2+R3)

> 2026-06-03. 4 estrategias portadas del proyecto BTC, validadas en el motor
> honesto de Oscilion (señal 2h/4h/1h, salida 15m pesimista, costos taker
> reales), **por moneda**, 12 monedas × 3 años. Métrica: expectativa por trade en
> R. "Genuino" = positivo en período completo **y** OOS (config insesgada) +
> confirmado en walk-forward. Reportes: `data/reports/r2_*.md`, `r3_*.md`.

---

## 1. Resultado por moneda (mejor estrategia con edge genuino)

| Moneda | Mejor estrategia | full / OOS / WF (exp_R) | Convicción | Notas |
|---|---|---|:--:|---|
| **TRX** | EMA_STACK · ORB · momentum | múltiples positivas (ORB +0.18/+0.29/+0.36) | 🟢🟢 muy alta | trend Y breakout limpios |
| **LINK** | **ORB_BREAKOUT** | +0.20 / +0.31 / +0.23 | 🟢 alta | trend-follow fallaba aquí |
| **DOT** | **ORB_BREAKOUT** | +0.13 / +0.10 / +0.19 | 🟢 alta | trend-follow fallaba aquí |
| **BNB** | **EMA_TREND_STACK** (tp4) | +0.13 / +0.41 / +0.11 | 🟢 alta | trender limpio |
| **BTC** | **EMA_TREND_STACK** (tp4) | +0.34 / +0.13 / +0.16 | 🟢 alta | ORB también marginal+ |
| ADA | ORB_BREAKOUT | +0.25 / +0.04 / +0.02 | 🟡 media-baja | full fuerte, OOS flojo |
| DOGE | ORB_BREAKOUT | +0.02 / +0.05 / +0.03 | 🟡 baja | marginal |
| XRP | ORB / break_retest | marginal (~+0.05 OOS) | 🟡 baja | marginal |
| LTC | ORB_BREAKOUT | mixto (WF +0.05) | 🟡 baja | marginal |
| SOL | — | sin edge limpio | ⚪ | revisar con otras tácticas |
| ETH | — | sin edge limpio | ⚪ | revisar con otras tácticas |
| AVAX | — | sin edge limpio | ⚪ | ORB def_test alto pero n chico = ruido |

## 2. Resultado por estrategia (mediana equiponderada entre monedas)

| Estrategia | mediana exp_R | monedas + / total | genuinos (full+OOS+WF) | lectura |
|---|---:|:--:|---|---|
| **ORB_BREAKOUT** | **+0.029** | 8/11 | TRX, LINK, DOT | ✅ el workhorse multi-moneda (alts) |
| EMA_TREND_STACK (tp4) | ~0 (coin-específico) | 5/12 | BTC, BNB, TRX | ✅ para large-caps de tendencia limpia |
| MOMENTUM_PULLBACK | −0.086 | 3/12 | TRX | ⚠️ solo TRX; baja prioridad |
| BREAK_RETEST | −0.161 | 4/12 | TRX (n chico) | ❌ descartar (salvo TRX, con cautela) |

## 3. Conclusión — la dirección de Oscilion

**Oscilion = observador multi-moneda que asigna a CADA moneda la estrategia que se le
validó, deja correr ganadores, y solo opera donde hay edge demostrado.** Dos motores núcleo:

1. **EMA_TREND_STACK** (tp_r alto / trailing) → large-caps de **tendencia limpia**:
   BTC, BNB, TRX.
2. **ORB_BREAKOUT** (rompe rango estrecho, sesión EU/NY, EMA50 4h, gate de frescura)
   → **alts** (workhorse, mediana positiva): LINK, DOT, TRX + marginales.

Esto **confirma y refina el propio pivot de Oscilion**: ORB es exactamente "ruptura de
rango estrecho fuerte" — el edge de breakout que Oscilion ya había encontrado, ahora
con filtros (rango<1.5%, sesión, EMA50, frescura) que lo mejoran y lo extienden a alts.

**Coins sin edge limpio (SOL, ETH, AVAX):** no se operan hasta encontrarles una táctica
propia (futuras sesiones). Disciplina: si no hay edge, no se opera esa moneda.

## 3b. Exits — TP fijo vs trailing (R5)
Probado TP fijo `tp_r=4` vs trailing ATR (1.5/2/3) con entrada fija, por moneda:
- **EMA_TREND_STACK → TP fijo amplio (tp_r=4) gana**; el trailing lo descose
  (BTC/BNB/TRX mejores con fijo).
- **ORB_BREAKOUT → trailing 2–3·ATR es competitivo o mejor OOS** en DOT, ADA, DOGE;
  comparable en LINK/TRX. Diferencias dentro del ruido.
- Decisión: **`tp_r=4` fijo como base** para ambos; trailing = tweak futuro para ORB.
  Reporte: `data/reports/r5_exit_check.md`.

## 4. Aprendizajes consolidados (R1–R3)
- **Dejar correr ganadores** (tp_r alto / sin TP + timeout) supera al TP en borde opuesto.
- **La estrategia depende del carácter de la moneda:** trend-stack ≠ sirve en choppy;
  ORB sí. No hay una sola estrategia para todas.
- **Maker rescata poco** (+0.015–0.04R) → R4 baja prioridad.
- **Salida 15m ≈ 1m** → motor honesto robusto.
- **BREAK_RETEST y MOMENTUM_PULLBACK** aportan poco fuera de TRX → no son núcleo.
- Los **Sharpe del proyecto BTC eran optimistas**; bajo motor honesto el edge es real
  pero más chico y **coin-específico** — por eso validar por moneda fue clave.

## 5. Decisiones pendientes / próximos pasos
Ver `docs/VALIDATION_R1_R2.md §DECISIONES PENDIENTES`. Próximo:
- **R5 — exits trailing** (podrían superar el tp_r fijo en ambos motores).
- **R3b — VWAP_ANCHOR** (otro trender; ¿aporta sobre EMA_STACK?). Opcional.
- **R6 — cartera** de los genuinos (BTC/BNB/TRX trend + LINK/DOT/TRX breakout),
  correlación, y **forward-test en vivo (dry-run)**.
- Buscar táctica para SOL/ETH/AVAX o excluirlas con honestidad.
