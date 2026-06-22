# GENERADO/curado tras la auditoría 2026-06-22 (purged-WF + barrido de universo).
# Esquema validado en Fase B: equal-weight, maxc=3, clúster=2 (tunear pesos por
# moneda sobreajusta en muestras chicas). Solo combos CON capital necesitan entrada
# aquí (observe nunca recibe capital ni pasa por el límite de clúster).
#
# Clústeres = control de correlación para el límite "máx N por clúster":
#   trx    → las 4 estrategias sobre TRX (el veto por símbolo ya deja 1 viva; aquí
#            refuerza que TRX no monopolice las 3 ranuras de capital).
#   crypto → alts mayores correlacionadas entre sí (LINK/XRP/DOGE/BNB/AVAX).
#   gold   → oro, descorrelacionado del cripto (PAXG/XAU) — fuerza diversificación.

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
    'PAXG/USDT:USDT|break_retest': 1.0,
    'PAXG/USDT:USDT|ema_trend_stack': 1.0,
    'XAU/USDT:USDT|momentum_pullback': 1.0,
}

CLUSTERS = {
    'TRX/USDT:USDT|vwap_anchor': 'trx',
    'TRX/USDT:USDT|ema_trend_stack': 'trx',
    'TRX/USDT:USDT|orb_breakout': 'trx',
    'TRX/USDT:USDT|break_retest': 'trx',
    'LINK/USDT:USDT|orb_breakout': 'crypto',
    'XRP/USDT:USDT|orb_breakout': 'crypto',
    'DOGE/USDT:USDT|orb_breakout': 'crypto',
    'BNB/USDT:USDT|vwap_anchor': 'crypto',
    'AVAX/USDT:USDT|vwap_anchor': 'crypto',
    'PAXG/USDT:USDT|break_retest': 'gold',
    'PAXG/USDT:USDT|ema_trend_stack': 'gold',
    'XAU/USDT:USDT|momentum_pullback': 'gold',
}

LIMITS = {'max_concurrent': 3, 'max_per_cluster': 2}
