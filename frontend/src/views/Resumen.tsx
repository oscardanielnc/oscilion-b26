import { Status, Signal, Portfolio, Alert } from "../api";
import { timeLima } from "../util";

function Stat({ k, v }: { k: string; v: string }) {
  return <div className="card stat"><div className="k">{k}</div><div className="v">{v}</div></div>;
}

const STRAT: Record<string, string> = { ema_trend_stack: "EMA stack", orb_breakout: "ORB" };

export function Resumen({ status, signals, portfolio, alerts }:
  { status: Status; signals: Signal[]; portfolio: Portfolio | null; alerts: Alert[] }) {
  const inTrade = signals.filter((s) => s.in_trade);
  const active = signals.filter((s) => s.signal_active && !s.in_trade);

  return (
    <>
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
