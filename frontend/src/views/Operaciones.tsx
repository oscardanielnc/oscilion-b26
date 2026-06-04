import { Trade, Alert } from "../api";
import { fmt, cls, timeLima } from "../util";

const STRAT: Record<string, string> = { ema_trend_stack: "EMA stack", orb_breakout: "ORB" };

function summary(trades: Trade[]) {
  const by: Record<string, Trade[]> = {};
  for (const t of trades) (by[t.strategy] ||= []).push(t);
  return Object.entries(by).map(([s, ts]) => {
    const rs = ts.map((t) => t.r_multiple ?? 0);
    const wins = ts.filter((t) => (t.pnl ?? 0) > 0).length;
    return { strategy: s, n: ts.length, winrate: wins / ts.length,
             avgR: rs.reduce((a, b) => a + b, 0) / ts.length };
  });
}

export function Operaciones({ trades, alerts }: { trades: Trade[]; alerts: Alert[] }) {
  return (
    <>
      <div className="section-title">Operaciones (dry-run · virtuales) · horas en Lima</div>

      {trades.length === 0 ? (
        <div className="card muted">Aún no hay operaciones cerradas. Aparecerán aquí cuando una estrategia dispare y cierre.</div>
      ) : (
        <>
          <div className="card" style={{ marginBottom: 12 }}>
            <table>
              <thead><tr><th>Estrategia</th><th>N</th><th>Winrate</th><th>R medio</th></tr></thead>
              <tbody>
                {summary(trades).map((s) => (
                  <tr key={s.strategy}>
                    <td>{STRAT[s.strategy] || s.strategy}</td>
                    <td>{s.n}</td><td className="muted">{(s.winrate * 100).toFixed(0)}%</td>
                    <td className={cls(s.avgR)}>{fmt(s.avgR, 3)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="card">
            <table>
              <thead>
                <tr><th>Cierre (Lima)</th><th>Moneda</th><th>Estrategia</th><th>Lado</th>
                  <th>Entrada</th><th>Salida</th><th>R</th><th>PnL</th></tr>
              </thead>
              <tbody>
                {trades.map((t, i) => (
                  <tr key={i}>
                    <td>{timeLima(t.exit_ts ?? t.ts)}</td>
                    <td>{t.sym.split("/")[0]}</td>
                    <td className="muted">{STRAT[t.strategy] || t.strategy}</td>
                    <td className={t.side === "long" ? "pos" : "neg"}>{t.side === "long" ? "▲" : "▼"} {t.side}</td>
                    <td>{fmt(t.entry, 6)}</td>
                    <td>{fmt(t.exit, 6)}</td>
                    <td className={cls(t.r_multiple)}>{t.r_multiple != null ? fmt(t.r_multiple, 2) : "—"}</td>
                    <td className={cls(t.pnl)}>{t.pnl != null ? fmt(t.pnl, 2) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <div className="card" style={{ marginTop: 12 }}>
        <div className="section-title">Alertas recientes</div>
        <div className="alerts">
          {alerts.length === 0 && <div className="muted small">Sin alertas todavía.</div>}
          {alerts.map((a, i) => (
            <div className="alert" key={i}><span className="t">{timeLima(a.ts)}</span><span>{a.msg}</span></div>
          ))}
        </div>
      </div>
    </>
  );
}
