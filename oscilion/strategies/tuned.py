# GENERADO por research/phase_b.py — no editar a mano.
# 2026-06-03 20:41 UTC · mejor esquema: equal maxc3 clu2
# params = baseline (tunear por moneda sobreajusta en muestras chicas).

WEIGHTS = {
    'BTC/USDT:USDT|ema_trend_stack': 1.0,
    'BNB/USDT:USDT|ema_trend_stack': 1.0,
    'TRX/USDT:USDT|ema_trend_stack': 1.0,
    'TRX/USDT:USDT|orb_breakout': 1.0,
    'LINK/USDT:USDT|orb_breakout': 1.0,
    'DOT/USDT:USDT|orb_breakout': 1.0,
}

CLUSTERS = {
    'BTC/USDT:USDT|ema_trend_stack': 'majors',
    'BNB/USDT:USDT|ema_trend_stack': 'majors',
    'TRX/USDT:USDT|ema_trend_stack': 'trx',
    'TRX/USDT:USDT|orb_breakout': 'trx',
    'LINK/USDT:USDT|orb_breakout': 'majors',
    'DOT/USDT:USDT|orb_breakout': 'majors',
}

LIMITS = {'max_concurrent': 3, 'max_per_cluster': 2}
