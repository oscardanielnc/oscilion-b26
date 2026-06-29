"""¿El gate de régimen de mercado mejora el edge? — backtest comparativo (06-29).

Corre el motor honesto para cada combo del portfolio DOS veces — sin filtro de
régimen (OFF) y con filtro (ON, benchmark=BTC vs EMA50 4h) — y compara exp_R /
sum_R / winrate por ventana OOS independiente:

  W1 holdout  : [2025-01-01, 2026-01-01)   ← fuera de la selección de params
  W2 2026-YTD : [2026-01-01, ahora)

El oro (clúster 'gold') está EXENTO (descorrelacionado del cripto) → se reporta
como tal, sin filtro. Solo lectura: no toca BD ni despliegue.

Uso:  python -m research.regime_backtest
"""
from __future__ import annotations

import numpy as np

from config import config
from oscilion.backtest.engine_strat import StratParams, load_bundle, run
from oscilion.data import store
from oscilion.features import market_regime
from oscilion.strategies import all_assignments, portfolio as P

W1 = (1735689600000, 1767225600000)   # 2025
W2 = (1767225600000, 10_000_000_000_000)  # 2026-YTD (tope abierto)


def _stats(trades, lo, hi):
    R = np.array([t["R"] for t in trades if lo <= t["entry_ts"] < hi])
    if R.size == 0:
        return {"n": 0, "exp": None, "sum": 0.0, "win": None}
    return {"n": int(R.size), "exp": float(R.mean()), "sum": float(R.sum()),
            "win": float((R > 0).mean())}


def _fmt(s):
    if s["n"] == 0:
        return f"{'0':>3} {'—':>7} {'—':>7}"
    return f"{s['n']:>3} {s['exp']:>+7.3f} {s['sum']:>+7.2f}"


def main():
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    reg_ts, reg_bull = market_regime.regime_series(
        store.load_bars(config.market_benchmark, config.base_timeframe),
        config.market_regime_tf_h, config.market_regime_ema)
    print(f"Régimen: {config.market_benchmark} close>EMA{config.market_regime_ema} "
          f"@ {config.market_regime_tf_h}h | {reg_ts.size} barras | "
          f"alcista {100*reg_bull.mean():.0f}% del tiempo\n")

    hdr = f"{'COMBO':<26}{'VENT':<5}│ {'OFF  n   expR   sumR':<22}│ {'ON   n   expR   sumR':<22}│ Δexp"
    print(hdr); print("─" * len(hdr))

    agg = {}  # (window, on/off) -> [sumR, n]
    for sym, a in all_assignments():
        exempt = P.regime_exempt(sym, a.strategy)
        bundle = load_bundle(sym, a.strategy)
        if bundle is None:
            continue
        base = dict(strategy=a.strategy, params=a.params,
                    max_hold_signal_bars=a.max_hold_signal_bars)
        t_off = run(bundle, StratParams(**base))
        t_on = t_off if exempt else run(bundle, StratParams(
            **base, regime_close_ts=reg_ts, regime_bull=reg_bull))

        label = f"{sym.split('/')[0]}|{a.strategy}"
        for wname, (lo, hi) in (("W1", W1), ("W2", W2)):
            off, on = _stats(t_off, lo, hi), _stats(t_on, lo, hi)
            dexp = (on["exp"] - off["exp"]) if (on["exp"] is not None and off["exp"] is not None) else None
            dtxt = f"{dexp:+.3f}" if dexp is not None else "—"
            tag = " (anti-beta=exento)" if exempt else ""
            print(f"{label:<26}{wname:<5}│ {_fmt(off):<22}│ {_fmt(on):<22}│ {dtxt}{tag}")
            for key, st in ((("off", wname), off), (("on", wname), on)):
                agg.setdefault(key, [0.0, 0])
                if st["n"]:
                    agg[key][0] += st["sum"]; agg[key][1] += st["n"]
        print()

    print("═" * len(hdr))
    print("AGREGADO (suma de R sobre todos los combos):")
    for w in ("W1", "W2"):
        o, n_o = agg.get(("off", w), [0, 0])
        c, n_c = agg.get(("on", w), [0, 0])
        eo = o / n_o if n_o else 0.0
        ec = c / n_c if n_c else 0.0
        print(f"  {w}: OFF sumR {o:>+7.2f} (n={n_o}, exp {eo:+.3f})  →  "
              f"ON sumR {c:>+7.2f} (n={n_c}, exp {ec:+.3f})  | Δexp {ec-eo:+.3f}")


if __name__ == "__main__":
    main()
