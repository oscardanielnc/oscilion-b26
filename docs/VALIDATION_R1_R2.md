# Validación R1+R2 — estrategias rescatadas de BTC (motor honesto, por moneda)

> 2026-06-03. Portamos 2 estrategias del proyecto BTC (EMA_TREND_STACK,
> MOMENTUM_PULLBACK) al **motor honesto de Oscilion** (señal 2h/4h, salida 15m
> pesimista, costos taker reales) y las validamos **por moneda** (12 monedas, 3
> años) con default + barrido OOS + walk-forward. Reportes:
> `data/reports/r2_strat_validation.md`, `r2b_exec_check.md`.

---

## ⏳ DECISIONES PENDIENTES (para Oscar — responder al despertar)

La ejecución NO se detiene por estas; las dejo con mi recomendación.

> **ACTUALIZACIÓN R3 (hecho):** porté ORB_BREAKOUT y BREAK_RETEST. **ORB es el
> workhorse multi-moneda** (mediana +0.029, 8/11 positivas) y RESCATA a LINK y DOT
> (donde trend-follow fallaba). El **mapa estrategia×moneda y la dirección propuesta
> están en `docs/STRATEGY_MAP.md`** (léelo primero). Decisión grande nueva (#6 abajo).

1. **Incorporar los supervivientes de alta convicción**: EMA_TREND_STACK (con
   `tp_r=4`, gate de frescura, filtro de sesión) en **BTC, BNB, TRX**.
   → *Recomiendo SÍ.* Son positivos en período completo **y** OOS, con config fija
   (sin sesgo de selección). [SÍ / ajustar cuáles]
2. **MOMENTUM_PULLBACK** solo sobrevive en **TRX** (y BNB marginal). ¿Lo
   incorporamos como secundario en TRX o lo dejamos en banca?
   → *Recomiendo banca* (un solo coin, menor convicción). [banca / incorporar TRX]
3. **9 monedas (SOL, ETH, XRP, ADA, DOGE, AVAX, LINK, LTC, DOT)**: trend-follow
   y pullback **no** funcionan ahí. ¿Las probamos con OTRAS estrategias en R3
   (ORB/VWAP/BREAK_RETEST) antes de descartarlas del universo?
   → *Recomiendo SÍ* (estoy corriendo R3). [SÍ / descartar]
4. **Cambio de filosofía de salida**: el edge aparece con **"dejar correr
   ganadores" (`tp_r` alto / trailing)**, no con TP en el borde opuesto. ¿OK
   adoptar esto para las estrategias de tendencia? → *Recomiendo SÍ.* [SÍ / discutir]
5. **Ejecución maker (R4)**: el lift medido es chico (+0.015 a +0.04R) → no es el
   salvador que esperábamos. ¿Lo bajamos de prioridad? → *Recomiendo SÍ, baja prioridad.*
6. **(NUEVA) Adoptar la dirección de dos motores por-moneda** (ver STRATEGY_MAP.md):
   EMA_TREND_STACK para large-caps de tendencia limpia (BTC/BNB/TRX) + ORB_BREAKOUT
   para alts (LINK/DOT/TRX + marginales). Núcleo de alta convicción:
   **BTC, BNB, TRX, LINK, DOT**. → *Recomiendo adoptar esto como dirección de Oscilion.*
   [adoptar / discutir]
7. **SOL/ETH/AVAX**: sin edge limpio en ninguna de las 4 estrategias. ¿Las dejamos
   fuera del universo operable por ahora (disciplina) y buscamos táctica propia después?
   → *Recomiendo dejarlas fuera hasta tener edge demostrado.*

---

## 1. Veredicto honesto

**La mayoría de las estrategias del proyecto BTC NO sobreviven el motor honesto.**
Sus Sharpe 1.41/1.01 eran optimistas (la auditoría ya lo advertía). Con costos
reales y salidas pesimistas, la mediana de expectativa **entre monedas es negativa**.

**PERO hay un edge real, coin-específico, en tendencia:**

| Estrategia | Edge GENUINO (full + OOS positivos, config fija taker) | Convicción |
|---|---|---|
| **EMA_TREND_STACK** (`tp_r=4`) | **BTC** (OOS +0.13 / full +0.34), **BNB** (+0.41 / +0.13), **TRX** (+0.14 / +0.34) | **Alta** |
| MOMENTUM_PULLBACK (`tp_r=4`) | **TRX** (+0.28 / +0.21); BNB marginal | Media |
| (ambas) FALLAN en | SOL, ETH, XRP, ADA, DOGE, AVAX, LINK, LTC, DOT | — |

Lectura: **trend-follow rinde en large-caps de tendencia limpia (BTC/BNB/TRX), no en
alts choppy.** Esto valida tu visión: **cada moneda con su estrategia**, no una para todas.

## 2. Aprendizajes cuantificados

- **"Dejar correr ganadores" es la palanca real.** Subir `tp_r` de 2 a 4 da vuelta a
  BTC de negativo a positivo. El walk-forward elige `tp_r=4` casi siempre. ⇒ el TP en
  borde opuesto (estilo reversión) era el error; tendencia quiere TP amplio / trailing.
- **Maker no rescata** (lift +0.015 a +0.04R/trade). Útil pero menor; R4 baja de prioridad.
- **Resolución de salida 15m ≈ 1m** (BTC: +0.344 vs +0.346 full; +0.131 vs +0.142 OOS).
  El motor honesto es robusto; no hace falta 1m para las alts.
- **El default (params del YAML) casi nunca sobrevive OOS**; el edge requiere el ajuste
  `tp_r` alto. Confirma que los números originales venían de un harness optimista.
- **Winrate bajo (~25-35%) con TP amplio** → muchas pérdidas chicas, pocas ganancias
  grandes. Coherente con trend-follow; exige disciplina (no es "máquina de acertar").

## 3. Qué se construyó (R1)

- `backtest/resample.py` — 1h→2h/4h causal (sin look-ahead).
- `backtest/strategies_lib.py` — EMA_TREND_STACK y MOMENTUM_PULLBACK portadas, puras,
  parametrizadas (fieles a los YAML del proyecto BTC + gate de frescura).
- `backtest/engine_strat.py` — **motor honesto**: señal coarse, **salida en TF fino
  (15m) pesimista** (stop antes que TP), entrada al open siguiente, costos+funding,
  métrica primaria en **R**; `load_bundle`/`run` separan carga (cara) de corrida (barata).
- BTC 1m ingerido al store (`backtest/data/.../BTCUSDT_1m.parquet` → Oscilion) para el
  chequeo de resolución.

## 4. Implicación para la DIRECCIÓN de Oscilion

Evidencia (Oscilion + proyecto BTC, dos veces) apunta a:

> **Observador multi-moneda de TENDENCIA/CONTINUACIÓN, por-moneda, que deja correr
> ganadores.** No reversión. No una estrategia única. Cada moneda recibe la estrategia
> y params que se le validaron. Arrancamos con EMA_TREND_STACK en BTC/BNB/TRX.

Esto pronostica dirección (las de tendencia limpia son LONG-sesgadas) y dice cuándo
entrar (stack + pullback fresco), con salida que corta pérdidas chico y deja correr.

## 5. Siguiente (en curso / planificado)
- **R3 (corriendo):** portar ORB_BREAKOUT, VWAP_ANCHOR, BREAK_RETEST y validar por
  moneda — ¿rescatan a las 9 monedas donde trend-follow falla?
- R5: **exits trailing** (podrían superar a `tp_r=4` fijo).
- R6: cartera de supervivientes + forward-test en vivo (dry-run).
