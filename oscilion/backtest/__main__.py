"""CLI de backtest (Fase 4).

Uso:
    python -m oscilion.backtest [--tf 1h] [--capital 10000] [--symbols ...]
                                [--min-score 0] [--regimes range,trend]
                                [--max-hold 72] [--save report.md]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config import config, DATA_DIR
from oscilion.backtest import report
from oscilion.backtest.engine import BTParams, run
from oscilion.logging_setup import setup_logging


def main() -> None:
    setup_logging()
    try:  # consolas Windows (cp1252) no manejan emojis del informe
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser(prog="oscilion.backtest")
    ap.add_argument("--tf", default=config.base_timeframe)
    ap.add_argument("--capital", type=float, default=10_000.0)
    ap.add_argument("--symbols", default="")
    ap.add_argument("--min-score", type=float, default=0.0)
    ap.add_argument("--regimes", default="range,trend")
    ap.add_argument("--max-hold", type=int, default=72)
    ap.add_argument("--save", default="")
    args = ap.parse_args()

    syms = [s.strip() for s in args.symbols.split(",") if s.strip()] or config.symbols
    p = BTParams(capital=args.capital, min_score=args.min_score,
                 max_hold_bars=args.max_hold,
                 allow_regimes=tuple(r.strip() for r in args.regimes.split(",") if r.strip()))

    result = run(syms, tf=args.tf, p=p)
    md = report.build(result)

    out = Path(args.save) if args.save else (DATA_DIR / "reports" / f"backtest_{args.tf}.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")

    print("\n" + md)
    print(f"\n[guardado en {out}]")


if __name__ == "__main__":
    main()
