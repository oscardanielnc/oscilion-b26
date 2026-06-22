# GENERADO/curado tras la auditoría 2026-06-22 (purged-WF + barrido de universo +
# validación 15m anti-beta de alts). Esquema validado en Fase B: equal-weight,
# maxc=3, clúster=2 (tunear pesos por moneda sobreajusta en muestras chicas).
# Solo combos CON capital van aquí (observe nunca recibe capital ni pasa el límite).
#
# Clústeres = control de correlación para "máx N por clúster". Con 17 combos y solo 3
# posiciones concurrentes, separar por familia FUERZA diversificación (no 3 del mismo tipo):
#   trx      → 4 estrategias sobre TRX (el veto por símbolo ya deja 1 viva).
#   altlong  → largos sesgados (orb/vwap mean-rev) en alts mayores correlacionados.
#   altbreak → break_retest bidireccional en alts (gana por el lado SHORT en caídas;
#              anti-correlacionado con los largos → gran diversificador).
#   gold     → oro, descorrelacionado del cripto.

WEIGHTS = {
    'TRX/USDT:USDT|vwap_anchor': 1.0,
    'TRX/USDT:USDT|ema_trend_stack': 1.0,
    'TRX/USDT:USDT|orb_breakout': 1.0,
    'TRX/USDT:USDT|break_retest': 1.0,
    'LINK/USDT:USDT|orb_breakout': 1.0,
    'XRP/USDT:USDT|orb_breakout': 1.0,
    'DOGE/USDT:USDT|orb_breakout': 1.0,
    'BNB/USDT:USDT|vwap_anchor': 1.0,
    'AVAX/USDT:USDT|vwap_anchor': 1.0,
    'TIA/USDT:USDT|vwap_anchor': 1.0,
    'ATOM/USDT:USDT|vwap_anchor': 1.0,
    'RUNE/USDT:USDT|break_retest': 1.0,
    'NEO/USDT:USDT|break_retest': 1.0,
    'FLOW/USDT:USDT|break_retest': 1.0,
    'HBAR/USDT:USDT|break_retest': 1.0,
    'PAXG/USDT:USDT|break_retest': 1.0,
    'XAU/USDT:USDT|momentum_pullback': 1.0,
}

CLUSTERS = {
    'TRX/USDT:USDT|vwap_anchor': 'trx',
    'TRX/USDT:USDT|ema_trend_stack': 'trx',
    'TRX/USDT:USDT|orb_breakout': 'trx',
    'TRX/USDT:USDT|break_retest': 'trx',
    'LINK/USDT:USDT|orb_breakout': 'altlong',
    'XRP/USDT:USDT|orb_breakout': 'altlong',
    'DOGE/USDT:USDT|orb_breakout': 'altlong',
    'BNB/USDT:USDT|vwap_anchor': 'altlong',
    'AVAX/USDT:USDT|vwap_anchor': 'altlong',
    'TIA/USDT:USDT|vwap_anchor': 'altlong',
    'ATOM/USDT:USDT|vwap_anchor': 'altlong',
    'RUNE/USDT:USDT|break_retest': 'altbreak',
    'NEO/USDT:USDT|break_retest': 'altbreak',
    'FLOW/USDT:USDT|break_retest': 'altbreak',
    'HBAR/USDT:USDT|break_retest': 'altbreak',
    'PAXG/USDT:USDT|break_retest': 'gold',
    'XAU/USDT:USDT|momentum_pullback': 'gold',
}

# max_concurrent 3→4 (research/concurrency_sweep.py, 2026-06-22): con 17 combos el tope
# de 3 era el cuello de botella. 4 DOMINA a 3 en OOS — más throughput, mejor Sharpe
# (1.78 vs 1.18) Y menor MaxDD (-61% vs -70%). Más de 4 baja Sharpe y sube DD.
LIMITS = {'max_concurrent': 4, 'max_per_cluster': 2}
