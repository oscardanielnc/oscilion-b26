"""CLI de datos (Fase 2).

Uso:
    python -m oscilion.data sync   [--days N] [--symbols BTC/USDT:USDT,...]
    python -m oscilion.data report
    python -m oscilion.data universe [--top N]
"""
from __future__ import annotations

import argparse

from config import config
from oscilion.data import pipeline, universe
from oscilion.logging_setup import setup_logging


def main() -> None:
    setup_logging()
    p = argparse.ArgumentParser(prog="oscilion.data")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("sync", help="descargar + auditar histórico")
    s.add_argument("--days", type=int, default=365)
    s.add_argument("--symbols", type=str, default="")

    sub.add_parser("report", help="reporte de calidad")

    u = sub.add_parser("universe", help="descubrir universo por liquidez")
    u.add_argument("--top", type=int, default=15)

    args = p.parse_args()

    if args.cmd == "sync":
        symbols = [x.strip() for x in args.symbols.split(",") if x.strip()] or config.symbols
        results = pipeline.sync_all(symbols, days=args.days)
        for r in results:
            print(f"  {r['sym']:<18} {r['tf']:<5} filas={r['rows']:<6} "
                  f"+{r['added']:<5} huecos={r['gaps']} dups={r['dupes']}")
        print("\n" + pipeline.quality_report_md())

    elif args.cmd == "report":
        print(pipeline.quality_report_md())

    elif args.cmd == "universe":
        df = universe.fetch_universe()
        universe.save_universe(df)
        cols = ["symbol", "last", "quote_volume"]
        print(df.head(args.top)[cols].to_string(index=False))


if __name__ == "__main__":
    main()
