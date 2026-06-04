"""Exportación de logs para revisión diaria (Fase A).

Genera un reporte CONCISO (markdown o json) de un rango de días, con todo lo que
sirve para decidir keep/remove/fix/improve: info del sistema, validación forward
(backtest vs vivo), trades del rango (+ resumen por estrategia para validar
targets), alertas y errores. Pensado para compartir sin saturar.

Rango interpretado en hora de Lima (UTC-5, sin DST).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from config import config
from oscilion import __version__
from oscilion.persistence import db
from oscilion.strategies import all_assignments
from oscilion.strategies import portfolio as P

LIMA = timezone(timedelta(hours=-5))


def range_ms(date_from: str, date_to: str) -> tuple[int, int]:
    """'YYYY-MM-DD'..'YYYY-MM-DD' (días Lima, inclusivos) → (from_ms, to_ms)."""
    d0 = datetime.strptime(date_from, "%Y-%m-%d").replace(tzinfo=LIMA)
    d1 = datetime.strptime(date_to, "%Y-%m-%d").replace(tzinfo=LIMA) + timedelta(days=1)
    return int(d0.timestamp() * 1000), int(d1.timestamp() * 1000)


def _lima(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=LIMA).strftime("%Y-%m-%d %H:%M")


def collect(from_ms: int, to_ms: int) -> dict:
    con = db.get_connection()
    with db._lock:
        trades = [dict(r) for r in con.execute(
            "SELECT exit_ts, sym, strategy, side, entry, exit, r_multiple, pnl FROM trades "
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
            s["latest_state"] = latest.get(f"{s['sym']}|{s['strategy']}", "—")
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
    L = [f"# Oscilion — logs {date_from} → {date_to} (hora Lima)",
         f"_Generado {_lima(int(datetime.now(LIMA).timestamp()*1000))} · v{__version__} · modo {config.mode.value}_\n",
         "## Sistema",
         f"- Núcleo: {len(all_assignments())} series · límites maxc {P.MAX_CONCURRENT}/clúster {P.MAX_PER_CLUSTER} · tuned={P._TUNED}",
         f"- DB filas: " + ", ".join(f"{k}={v}" for k, v in d['counts'].items() if k in ('trades', 'predictions', 'decisions', 'events', 'forward_results', 'series_snapshots')),
         ""]

    L.append("## Validación forward (backtest vs vivo) — acumulado")
    L.append("| Moneda | Estrategia | scope | n | winrate | exp_R |")
    L.append("|---|---|---|--:|--:|--:|")
    for r in d["forward"]:
        wr = f"{r['win_rate']*100:.0f}%" if r["win_rate"] is not None else "—"
        er = f"{r['exp_r']:+.3f}" if r["exp_r"] is not None else "—"
        L.append(f"| {r['sym'].split('/')[0]} | {r['strategy']} | {r['scope']} | {r['n']} | {wr} | {er} |")

    L.append(f"\n## Trades cerrados en el rango ({len(d['trades'])})")
    if d["trades"]:
        L.append("| Cierre (Lima) | Moneda | Estrategia | Lado | R | PnL |")
        L.append("|---|---|---|---|--:|--:|")
        for t in d["trades"]:
            L.append(f"| {_lima(t['exit_ts'])} | {t['sym'].split('/')[0]} | {t['strategy']} | "
                     f"{t['side']} | {t['r_multiple']:+.2f} | {t['pnl']:+.2f} |")
        L.append("\n**Resumen por estrategia (para validar targets):**")
        L.append("| Estrategia | n | winrate | R medio |")
        L.append("|---|--:|--:|--:|")
        for s in _trade_summary(d["trades"]):
            L.append(f"| {s['strategy']} | {s['n']} | {s['winrate']*100:.0f}% | {s['avg_R']:+.3f} |")
    else:
        L.append("_Sin trades cerrados en el rango._")

    L.append(f"\n## Actividad del observador (snapshots del rango)")
    if d["snapshots"]:
        L.append("| Moneda | Estrategia | ciclos | últ. estado | mejor checklist | señal activa | en trade |")
        L.append("|---|---|--:|---|--:|--:|--:|")
        for s in d["snapshots"]:
            chk = f"{s['best_ok']}/{s['tot']}" if s["tot"] is not None else "—"
            L.append(f"| {s['sym'].split('/')[0]} | {s['strategy']} | {s['n']} | {s['latest_state']} | "
                     f"{chk} | {s['n_active'] or 0} | {s['n_in_trade'] or 0} |")
    else:
        L.append("_Sin snapshots en el rango (el monitor aún no los ha generado)._")

    L.append(f"\n## Alertas en el rango ({len(d['alerts'])})")
    for a in d["alerts"]:
        L.append(f"- {_lima(a['ts'])} · {a['msg']}")
    if not d["alerts"]:
        L.append("_Sin alertas._")

    L.append(f"\n## Errores/avisos ({len(d['errors'])})")
    for e in d["errors"]:
        L.append(f"- {_lima(e['ts'])} · {e['level']} · {e['module']} · {e['msg']}")
    if not d["errors"]:
        L.append("_Sin errores ni avisos._")

    if d["decisions"]:
        L.append("\n## Decisiones (conteo): " + ", ".join(f"{x['action']}={x['n']}" for x in d["decisions"]))
    return "\n".join(L)


def build_json(date_from: str, date_to: str) -> str:
    from_ms, to_ms = range_ms(date_from, date_to)
    d = collect(from_ms, to_ms)
    d["range"] = {"from": date_from, "to": date_to, "from_ms": from_ms, "to_ms": to_ms}
    d["trade_summary"] = _trade_summary(d["trades"])
    return json.dumps(d, default=str, ensure_ascii=False, indent=2)
