import { useState } from "react";
import { Signal, Portfolio, Alert, exportUrl } from "../api";
import { fmtTime, today } from "../util";

function Stat({ k, v }: { k: string; v: string }) {
  return <div className="card stat"><div className="k">{k}</div><div className="v">{v}</div></div>;
}

function ExportLogs() {
  const [from, setFrom] = useState(today());
  const [to, setTo] = useState(today());
  const dl = (fmt: "md" | "json") => {
    const a = document.createElement("a");
    a.href = exportUrl(from, to, fmt);
    a.download = `oscilion_logs_${from}_${to}.${fmt}`;
    document.body.appendChild(a); a.click(); a.remove();
  };
  return (
    <div className="card export">
      <div className="section-title">Download logs (daily review)</div>
      <div className="export-row">
        <label>From<input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} /></label>
        <label>To<input type="date" value={to} min={from} max={today()} onChange={(e) => setTo(e.target.value)} /></label>
        <button className="btn" onClick={() => dl("md")}>Download .md</button>
        <button className="btn ghost" onClick={() => dl("json")}>.json</button>
      </div>
      <div className="muted small">Includes: system, forward validation, trades, alerts, errors. Default range: today.</div>
    </div>
  );
}

const STRAT: Record<string, string> = { ema_trend_stack: "EMA stack", orb_breakout: "ORB", vwap_anchor: "VWAP anchor", break_retest: "Break+Retest" };

export function Overview({ signals, portfolio, alerts }:
  { signals: Signal[]; portfolio: Portfolio | null; alerts: Alert[] }) {
  const inTrade = signals.filter((s) => s.in_trade);
  const active = signals.filter((s) => s.signal_active && !s.in_trade);

  return (
    <>
      <ExportLogs />

      <div className="grid stats">
        <Stat k="Core series" v={String(signals.length)} />
        <Stat k="In trade" v={String(inTrade.length)} />
        <Stat k="Active signal" v={String(active.length)} />
        <Stat k="Coins" v={String(new Set(signals.map((s) => s.base)).size)} />
        <Stat k="Max concurrent" v={portfolio ? `${portfolio.max_concurrent} | cluster ${portfolio.max_per_cluster}` : "-"} />
      </div>

      <div className="grid" style={{ gridTemplateColumns: "1.3fr 1fr" }}>
        <div className="card">
          <div className="section-title">Core: coin to strategy</div>
          <table>
            <thead><tr><th>Coin</th><th>Strategy</th><th>Direction</th><th>State</th><th>Conviction</th></tr></thead>
            <tbody>
              {signals.map((s) => (
                <tr key={s.sym + s.strategy}>
                  <td>{s.base}</td>
                  <td className="muted">{STRAT[s.strategy] || s.strategy}</td>
                  <td className={s.direction === "long" ? "pos" : s.direction === "short" ? "neg" : "muted"}>{s.direction === "long" ? "▲ Long" : s.direction === "short" ? "▼ Short" : "In range"}</td>
                  <td>{s.in_trade ? "IN TRADE" : s.signal_active ? "SIGNAL ACTIVE" : "waiting"}</td>
                  <td className="muted">{s.observe_only ? "forward test" : s.conviction}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="muted small" style={{ marginTop: 8 }}>
            Correlation clusters come from the portfolio config (oscilion/strategies/tuned.py).
          </div>
        </div>

        <div className="card">
          <div className="section-title">Recent alerts</div>
          <div className="alerts">
            {alerts.length === 0 && <div className="muted small">No alerts yet. They arrive here and via ntfy.sh when configured.</div>}
            {alerts.map((a, i) => (
              <div className="alert" key={i}>
                <span className="t">{fmtTime(a.ts)}</span>
                <span>{a.msg}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
