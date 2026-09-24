import { useEffect, useState, useCallback } from "react";
import { getJSON, Status, Signal, Forward, Portfolio, Alert, Trade } from "./api";
import { fmtClock } from "./util";
import { Overview } from "./views/Overview";
import { Signals } from "./views/Signals";
import { Validation } from "./views/Validation";
import { Trades } from "./views/Trades";

type Tab = "overview" | "signals" | "trades" | "validation";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "signals", label: "Live signals" },
  { id: "trades", label: "Trades" },
  { id: "validation", label: "Forward validation" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("overview");
  const [status, setStatus] = useState<Status | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [forward, setForward] = useState<Forward[]>([]);
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [updated, setUpdated] = useState<number>(0);
  const [err, setErr] = useState<string>("");

  const load = useCallback(async () => {
    try {
      const [st, sg, fw, pf, al, tr] = await Promise.all([
        getJSON<Status>("/status"), getJSON<Signal[]>("/signals"),
        getJSON<Forward[]>("/forward"), getJSON<Portfolio>("/portfolio"),
        getJSON<Alert[]>("/alerts"), getJSON<Trade[]>("/trades"),
      ]);
      setStatus(st); setSignals(sg); setForward(fw); setPortfolio(pf); setAlerts(al); setTrades(tr);
      setUpdated(Date.now()); setErr("");
    } catch (e: any) { setErr(String(e.message || e)); }
  }, []);

  useEffect(() => {
    load();
    const id = setInterval(load, 20000);
    return () => clearInterval(id);
  }, [load]);

  const inTrade = signals.filter((s) => s.in_trade).length;
  const active = signals.filter((s) => s.signal_active).length;

  return (
    <div className="app">
      <header>
        <div className="logo">Oscil<span>ion</span></div>
        <span className={"pill " + (status ? "live" : "")}>
          {status ? `mode ${status.mode}` : "connecting..."}
        </span>
        {status && <span className="pill">v{status.version}</span>}
        <div className="spacer" />
        <span className="pill">{inTrade} in trade | {active} active signal</span>
        <span className="pill">{updated ? "updated " + fmtClock(updated) : ""}</span>
      </header>

      <nav className="tabs">
        {TABS.map((t) => (
          <div key={t.id} className={"tab" + (tab === t.id ? " active" : "")} onClick={() => setTab(t.id)}>{t.label}</div>
        ))}
      </nav>

      {err && <div className="card" style={{ borderColor: "#5a2730", color: "var(--red)" }}>Error: {err}. Is the API running?</div>}
      {!status && !err && <div className="loading">Loading...</div>}

      {status && tab === "overview" && <Overview signals={signals} portfolio={portfolio} alerts={alerts} />}
      {status && tab === "signals" && <Signals signals={signals} />}
      {status && tab === "trades" && <Trades trades={trades} alerts={alerts} />}
      {status && tab === "validation" && <Validation forward={forward} />}

      <div className="disclaimer">
        Observer mode (dry-run): it recommends and records, it never places orders. Return
        figures come from backtest/forward; the real risk to watch is the drawdown.
      </div>
    </div>
  );
}
