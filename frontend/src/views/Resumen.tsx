import { useState } from "react";
import { Status, Signal, Portfolio, Alert, exportUrl } from "../api";
import { timeLima, todayLima } from "../util";

function Stat({ k, v }: { k: string; v: string }) {
  return <div className="card stat"><div className="k">{k}</div><div className="v">{v}</div></div>;
}

function ExportLogs() {
  const [from, setFrom] = useState(todayLima());
  const [to, setTo] = useState(todayLima());
  const dl = (fmt: "md" | "json") => {
    const a = document.createElement("a");
    a.href = exportUrl(from, to, fmt);
    a.download = `oscilion_logs_${from}_${to}.${fmt}`;
    document.body.appendChild(a); a.click(); a.remove();
  };
  return (
    <div className="card export">
      <div className="section-title">Descargar logs (revisión diaria)</div>
      <div className="export-row">
        <label>Desde<input type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} /></label>
        <label>Hasta<input type="date" value={to} min={from} max={todayLima()} onChange={(e) => setTo(e.target.value)} /></label>
        <button className="btn" onClick={() => dl("md")}>⬇ Descargar .md</button>
        <button className="btn ghost" onClick={() => dl("json")}>.json</button>
      </div>
      <div className="muted small">Incluye: sistema · validación forward · trades · alertas · errores. Rango por defecto: hoy.</div>
    </div>
  );
}

const STRAT: Record<string, string> = { ema_trend_stack: "EMA stack", orb_breakout: "ORB" };

export function Resumen({ status, signals, portfolio, alerts }:
  { status: Status; signals: Signal[]; portfolio: Portfolio | null; alerts: Alert[] }) {
  const inTrade = signals.filter((s) => s.in_trade);
  const active = signals.filter((s) => s.signal_active && !s.in_trade);

  return (
    <>
      <ExportLogs />

      <div className="grid stats">
        <Stat k="Series del núcleo" v={String(signals.length)} />
        <Stat k="En trade" v={String(inTrade.length)} />
        <Stat k="Señal activa" v={String(active.length)} />
        <Stat k="Monedas" v={String(new Set(signals.map((s) => s.base)).size)} />
        <Stat k="Máx concurrentes" v={portfolio ? `${portfolio.max_concurrent} · clúster ${portfolio.max_per_cluster}` : "—"} />
      </div>

      <div className="grid" style={{ gridTemplateColumns: "1.3fr 1fr" }}>
        <div className="card">
          <div className="section-title">Núcleo · moneda → estrategia</div>
          <table>
            <thead><tr><th>Moneda</th><th>Estrategia</th><th>Dirección</th><th>Estado</th><th>Convicción</th></tr></thead>
            <tbody>
              {signals.map((s) => (
                <tr key={s.sym + s.strategy}>
                  <td>{s.base}</td>
                  <td className="muted">{STRAT[s.strategy] || s.strategy}</td>
                  <td className={s.direction === "long" ? "pos" : "neg"}>{s.direction === "long" ? "▲ Long" : "▼ Short"}</td>
                  <td>{s.in_trade ? "EN TRADE" : s.signal_active ? "SEÑAL ACTIVA" : "esperando"}</td>
                  <td className="muted">{s.conviction}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="muted small" style={{ marginTop: 8 }}>
            Clústers de correlación: majors = BTC/BNB/LINK/DOT · TRX diversifica.
          </div>
        </div>

        <div className="card">
          <div className="section-title">Alertas recientes</div>
          <div className="alerts">
            {alerts.length === 0 && <div className="muted small">Sin alertas todavía. Llegarán por ntfy.sh y aquí.</div>}
            {alerts.map((a, i) => (
              <div className="alert" key={i}>
                <span className="t">{timeLima(a.ts)}</span>
                <span>{a.msg}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
