"""Log export for the daily review.

Builds a CONCISE report (markdown or json) for a range of days with everything
needed to decide keep/remove/fix/improve: system info, forward validation
(backtest vs live), trades in the range (+ a per-strategy summary to check
targets), alerts and errors. Meant to be shared without overwhelming.

Dates are interpreted in the report timezone (UTC-5, no DST).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from config import config
from oscilion import __version__
from oscilion.persistence import db
from oscilion.strategies import all_assignments
from oscilion.strategies import portfolio as P

REPORT_TZ = timezone(timedelta(hours=-5))


def range_ms(date_from: str, date_to: str) -> tuple[int, int]:
    """'YYYY-MM-DD'..'YYYY-MM-DD' (report-TZ days, inclusive) -> (from_ms, to_ms)."""
    d0 = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=REPORT_TZ)
    d1 = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=REPORT_TZ) + timedelta(days=1)
    return int(d0.timestamp() * 1000), int(d1.timestamp() * 1000)


def _local(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=REPORT_TZ).strftime("%Y-%m-%d %H:%M")


def collect(from_ms: int, to_ms: int) -> dict:
    con = db.get_connection()
    with db._lock:
        trades = [dict(r) for r in con.execute(
            "SELECT exit_ts, sym, strategy, side, entry, exit, r_multiple, pnl,"
            " COALESCE(observe,0) observe, exit_reason, cost_audit FROM trades "
            "WHERE status='closed' AND exit_ts>=? AND exit_ts<? ORDER BY exit_ts", (from_ms, to_ms))]
        alerts = [dict(r) for r in con.execute(
            "SELECT ts, msg FROM events WHERE module='live.monitor' AND ts>=? AND ts<? ORDER BY ts",
            (from_ms, to_ms))]
        errors = [dict(r) for r in con.execute(
            "SELECT ts, level, module, msg FROM events WHERE level IN ('WARN','ERROR','CRITICAL') "
            "AND ts>=? AND ts<? ORDER BY ts", (from_ms, to_ms))]
        decisions = [dict(r) for r in con.execute(
            "SELECT action, COUNT(*) n FROM decisions WHERE ts>=? AND ts<? GROUP BY action",
            (from_ms, to_ms))]
        fwd = [dict(r) for r in con.execute(
            "SELECT sym, strategy, scope, n, win_rate, exp_r FROM forward_results ORDER BY sym, strategy, scope")]
        snaps = [dict(r) for r in con.execute(
            "SELECT sym, strategy, COUNT(*) n, SUM(signal_active) n_active, SUM(in_trade) n_in_trade,"
            " MAX(checklist_ok) best_ok, MAX(checklist_total) tot"
            " FROM series_snapshots WHERE ts>=? AND ts<? GROUP BY sym, strategy ORDER BY sym, strategy",
            (from_ms, to_ms))]
        latest = {f"{r['sym']}|{r['strategy']}": r["state"] for r in con.execute(
            "SELECT sym, strategy, state FROM series_snapshots WHERE id IN"
            " (SELECT MAX(id) FROM series_snapshots WHERE ts>=? AND ts<? GROUP BY sym, strategy)",
            (from_ms, to_ms))}
        for s in snaps:
            s["latest_state"] = latest.get(f"{s['sym']}|{s['strategy']}", "-")
        counts = db.counts()
    return {"trades": trades, "alerts": alerts, "errors": errors,
            "decisions": decisions, "forward": fwd, "snapshots": snaps, "counts": counts}


def _trade_summary(trades: list[dict]) -> list[dict]:
    by: dict[str, list[dict]] = {}
    for t in trades:
        by.setdefault(t["strategy"] or "?", []).append(t)
    out = []
    for strat, ts in by.items():
        rs = [t["r_multiple"] for t in ts if t["r_multiple"] is not None]
        wins = sum(1 for t in ts if (t["pnl"] or 0) > 0)
        out.append({"strategy": strat, "n": len(ts),
                    "winrate": wins / len(ts) if ts else 0,
                    "avg_R": sum(rs) / len(rs) if rs else 0})
    return out


def build_markdown(date_from: str, date_to: str) -> str:
    from_ms, to_ms = range_ms(date_from, date_to)
    d = collect(from_ms, to_ms)
    L = [f"# Oscilion - logs {date_from} -> {date_to} (UTC-5)",
         f"_Generated {_local(int(datetime.now(REPORT_TZ).timestamp()*1000))} | v{__version__} | mode {config.mode.value}_\n",
         "## System",
         f"- Core: {len(all_assignments())} series | limits maxc {P.MAX_CONCURRENT}/cluster {P.MAX_PER_CLUSTER} | tuned={P._TUNED}",
         "- DB rows: " + ", ".join(f"{k}={v}" for k, v in d['counts'].items() if k in ('trades', 'predictions', 'decisions', 'events', 'forward_results', 'series_snapshots')),
         ""]

    L.append("## Forward validation (backtest vs live), cumulative")
    L.append("| Coin | Strategy | scope | n | winrate | exp_R |")
    L.append("|---|---|---|--:|--:|--:|")
    for r in d["forward"]:
        wr = f"{r['win_rate']*100:.0f}%" if r["win_rate"] is not None else "-"
        er = f"{r['exp_r']:+.3f}" if r["exp_r"] is not None else "-"
        L.append(f"| {r['sym'].split('/')[0]} | {r['strategy']} | {r['scope']} | {r['n']} | {wr} | {er} |")

    capital = [t for t in d["trades"] if not t.get("observe")]
    observe = [t for t in d["trades"] if t.get("observe")]

    def _audit_txt(t: dict) -> str:
        try:
            a = json.loads(t["cost_audit"]) if t.get("cost_audit") else None
        except Exception:
            a = None
        if not a:
            return "-"
        return (f"px {a['r_gross']:+.2f} | slip {a['r_slip_exit']:+.3f} | "
                f"fees {a['r_fee_entry'] + a['r_fee_exit']:+.3f} | fund {a['r_funding']:+.3f}")

    def _table(rows: list[dict]) -> None:
        L.append("| Close (UTC-5) | Coin | Strategy | Side | R | PnL | Exit | Cost (R: px/slip/fees/fund) |")
        L.append("|---|---|---|---|--:|--:|---|---|")
        for t in rows:
            L.append(f"| {_local(t['exit_ts'])} | {t['sym'].split('/')[0]} | {t['strategy']} | "
                     f"{t['side']} | {t['r_multiple']:+.2f} | {t['pnl']:+.2f} | "
                     f"{t.get('exit_reason') or '-'} | {_audit_txt(t)} |")

    L.append(f"\n## Closed trades WITH capital ({len(capital)})")
    if capital:
        _table(capital)
        L.append("\n**Per-strategy summary (to check targets):**")
        L.append("| Strategy | n | winrate | mean R |")
        L.append("|---|--:|--:|--:|")
        for s in _trade_summary(capital):
            L.append(f"| {s['strategy']} | {s['n']} | {s['winrate']*100:.0f}% | {s['avg_R']:+.3f} |")
    else:
        L.append("_No capital trades in the range._")

    L.append(f"\n## Forward test WITHOUT capital, observe ({len(observe)})")
    L.append("_Excluded from PnL: combos without enough local validation (gate) or under observation._")
    if observe:
        _table(observe)
    else:
        L.append("_No observe trades in the range._")

    L.append("\n## Observer activity (snapshots in the range)")
    if d["snapshots"]:
        L.append("| Coin | Strategy | cycles | last state | best checklist | signal active | in trade |")
        L.append("|---|---|--:|---|--:|--:|--:|")
        for s in d["snapshots"]:
            chk = f"{s['best_ok']}/{s['tot']}" if s["tot"] is not None else "-"
            L.append(f"| {s['sym'].split('/')[0]} | {s['strategy']} | {s['n']} | {s['latest_state']} | "
                     f"{chk} | {s['n_active'] or 0} | {s['n_in_trade'] or 0} |")
    else:
        L.append("_No snapshots in the range (the monitor has not produced any yet)._")

    L.append(f"\n## Alerts in the range ({len(d['alerts'])})")
    for a in d["alerts"]:
        L.append(f"- {_local(a['ts'])} | {a['msg']}")
    if not d["alerts"]:
        L.append("_No alerts._")

    L.append(f"\n## Errors/warnings ({len(d['errors'])})")
    for e in d["errors"]:
        L.append(f"- {_local(e['ts'])} | {e['level']} | {e['module']} | {e['msg']}")
    if not d["errors"]:
        L.append("_No errors or warnings._")

    if d["decisions"]:
        L.append("\n## Decisions (count): " + ", ".join(f"{x['action']}={x['n']}" for x in d["decisions"]))
    return "\n".join(L)


def build_json(date_from: str, date_to: str) -> str:
    from_ms, to_ms = range_ms(date_from, date_to)
    d = collect(from_ms, to_ms)
    d["range"] = {"from": date_from, "to": date_to, "from_ms": from_ms, "to_ms": to_ms}
    d["trade_summary"] = _trade_summary([t for t in d["trades"] if not t.get("observe")])
    d["trade_summary_observe"] = _trade_summary([t for t in d["trades"] if t.get("observe")])
    return json.dumps(d, default=str, ensure_ascii=False, indent=2)
