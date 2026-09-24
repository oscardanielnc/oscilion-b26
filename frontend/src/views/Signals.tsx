import { Signal } from "../api";
import { fmt, pct } from "../util";

const STRAT_LABEL: Record<string, string> = {
  ema_trend_stack: "Trend - EMA stack",
  orb_breakout: "Range breakout - ORB",
  vwap_anchor: "Trend - VWAP anchor",
  break_retest: "Continuation - Break+Retest",
};

function DirBadge({ s }: { s: Signal }) {
  // No breakout (neutral): no committed direction, so show "in range" with the
  // nearest-edge bias, without looking like a real signal.
  if (s.direction === "neutral") {
    const b = s.bias === "long" ? "▲" : "▼";
    return <span className="badge neutral">In range <small>({b} bias)</small></span>;
  }
  return <span className={"badge " + s.direction}>{s.direction === "long" ? "▲ Long" : "▼ Short"}</span>;
}

function StateBadge({ s }: { s: Signal }) {
  const cls = s.in_trade ? "in-trade" : s.signal_active ? "active" : "waiting";
  const label = s.in_trade ? "IN TRADE" : s.signal_active ? "SIGNAL ACTIVE" : "WAITING";
  return <span className={"state " + cls}>{label}</span>;
}

function StrategyBlock({ s }: { s: Signal }) {
  return (
    <div className="strat">
      <div className="strat-head">
        <span className="strat-name">{STRAT_LABEL[s.strategy] || s.strategy}</span>
        <DirBadge s={s} />
        <span className="badge horizon">{s.horizon}</span>
        {s.observe_only && <span className="badge observe" title="Forward test without capital: validating the edge live">observe</span>}
        <StateBadge s={s} />
      </div>

      <div className="trade-grid">
        <div><span className="lbl">Entry</span><span className="num">{fmt(s.entry, 6)}</span></div>
        <div><span className="lbl">Stop</span><span className="num stop">{fmt(s.stop, 6)}<small>{pct(s.stop_pct ? -Math.abs(s.stop_pct) : null)}</small></span></div>
        <div><span className="lbl">Target | RR {s.rr}</span><span className="num tp">{fmt(s.tp, 6)}<small>{pct(s.tp_pct)}</small></span></div>
      </div>

      <div className="lv-row">
        {Object.entries(s.levels).map(([k, v]) => (
          <span className="lv" key={k}><b>{k.replace(/_/g, " ")}</b> {fmt(v as number, 6)}</span>
        ))}
        {s.indicators.RSI !== undefined && (
          <span className="lv"><b>RSI</b> <span style={{ color: s.indicators.RSI_healthy ? "var(--green)" : "var(--muted)" }}>{fmt(s.indicators.RSI, 1)}{s.indicators.RSI_healthy ? " ✓" : ""}</span></span>
        )}
      </div>

      <div className="checklist">
        <span className="chk-count">{s.checklist_ok}/{s.checklist_total} criteria</span>
        {s.checklist.map((c, i) => (
          <span className={"chk " + (c.ok ? "ok" : "no")} key={i}>{c.ok ? "✓" : "○"} {c.label}</span>
        ))}
      </div>
    </div>
  );
}

export function Signals({ signals }: { signals: Signal[] }) {
  if (!signals.length) return <div className="loading">No series configured.</div>;

  const byCoin = new Map<string, Signal[]>();
  for (const s of signals) {
    if (!byCoin.has(s.base)) byCoin.set(s.base, []);
    byCoin.get(s.base)!.push(s);
  }
  // coins with an open trade or active signal first
  const coins = [...byCoin.entries()].sort((a, b) => {
    const score = (xs: Signal[]) => Math.max(...xs.map((x) => (x.in_trade ? 2 : x.signal_active ? 1 : 0) + x.checklist_ok / 10));
    return score(b[1]) - score(a[1]);
  });

  return (
    <>
      <div className="section-title">
        Core: a coin can run several strategies. "Entry/Stop/Target" are the proposed levels if it entered now.
      </div>
      <div className="coins">
        {coins.map(([base, list]) => (
          <div className="coin-card" key={base}>
            <div className="coin-head">
              <span className="coin-name">{base}</span>
              <span className="coin-price">{fmt(list[0].price, 6)}</span>
              {list.length > 1 && <span className="badge multi">{list.length} strategies</span>}
            </div>
            {list.map((s) => <StrategyBlock key={s.strategy} s={s} />)}
          </div>
        ))}
      </div>
    </>
  );
}
