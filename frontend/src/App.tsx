import { useEffect, useState, useCallback } from "react";
import { getJSON, Status, Signal, Forward, Portfolio, Alert, Trade } from "./api";
import { Resumen } from "./views/Resumen";
import { Senales } from "./views/Senales";
import { Validacion } from "./views/Validacion";
import { Operaciones } from "./views/Operaciones";

type Tab = "resumen" | "senales" | "operaciones" | "validacion";

export default function App() {
  const [tab, setTab] = useState<Tab>("resumen");
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
    const id = setInterval(load, 20000); // refresca cada 20s
    return () => clearInterval(id);
  }, [load]);

  const inTrade = signals.filter((s) => s.in_trade).length;
  const active = signals.filter((s) => s.signal_active).length;

  return (
    <div className="app">
      <header>
        <div className="logo">Oscil<span>ion</span></div>
        <span className={"pill " + (status ? "live" : "")}>
          {status ? `modo ${status.mode}` : "conectando…"}
        </span>
        {status && <span className="pill">v{status.version}</span>}
        <div className="spacer" />
        <span className="pill">{inTrade} en trade · {active} señal activa</span>
        <span className="pill">{updated ? "act. " + new Date(updated).toLocaleTimeString("es-PE", { timeZone: "America/Lima", hour12: false }) : ""}</span>
      </header>

      <nav className="tabs">
        <div className={"tab" + (tab === "resumen" ? " active" : "")} onClick={() => setTab("resumen")}>Resumen</div>
        <div className={"tab" + (tab === "senales" ? " active" : "")} onClick={() => setTab("senales")}>Señales en vivo</div>
        <div className={"tab" + (tab === "operaciones" ? " active" : "")} onClick={() => setTab("operaciones")}>Operaciones</div>
        <div className={"tab" + (tab === "validacion" ? " active" : "")} onClick={() => setTab("validacion")}>Validación forward</div>
      </nav>

      {err && <div className="card" style={{ borderColor: "#5a2730", color: "var(--red)" }}>Error: {err} — ¿está corriendo la API?</div>}
      {!status && !err && <div className="loading">Cargando…</div>}

      {status && tab === "resumen" && <Resumen status={status} signals={signals} portfolio={portfolio} alerts={alerts} />}
      {status && tab === "senales" && <Senales signals={signals} />}
      {status && tab === "operaciones" && <Operaciones trades={trades} alerts={alerts} />}
      {status && tab === "validacion" && <Validacion forward={forward} />}

      <div className="disclaimer">
        Modo observador (dry-run): recomienda y registra, no opera. Las cifras de
        retorno son de backtest/forward; el riesgo real a vigilar es el drawdown.
      </div>
    </div>
  );
}
