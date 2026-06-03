import { Forward } from "../api";
import { fmt, cls } from "../util";

const STRAT: Record<string, string> = { ema_trend_stack: "EMA stack", orb_breakout: "ORB" };

// agrupa por sym+strategy con sus dos scopes
function rows(forward: Forward[]) {
  const m = new Map<string, { sym: string; strategy: string; bt?: Forward; fw?: Forward }>();
  for (const f of forward) {
    const k = f.sym + "|" + f.strategy;
    const e = m.get(k) || { sym: f.sym, strategy: f.strategy };
    if (f.scope === "backtest") e.bt = f; else e.fw = f;
    m.set(k, e);
  }
  return [...m.values()];
}

function verdict(bt?: Forward, fw?: Forward) {
  if (!fw || fw.n < 10 || fw.exp_r === null) return { t: "⏳ poca muestra", c: "zero" };
  if (fw.exp_r > 0) return { t: "✅ aguanta", c: "pos" };
  return { t: "⚠️ revisar", c: "neg" };
}

export function Validacion({ forward }: { forward: Forward[] }) {
  const data = rows(forward);
  if (!data.length) return <div className="loading">Sin datos de validación todavía.</div>;
  return (
    <>
      <div className="section-title">
        Backtest vs forward (datos no vistos) por moneda×estrategia · expectativa por trade en R · revisión diaria
      </div>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Moneda</th><th>Estrategia</th>
              <th>BT n</th><th>BT exp.R</th>
              <th>FWD n</th><th>FWD exp.R</th><th>FWD winrate</th>
              <th>Veredicto</th>
            </tr>
          </thead>
          <tbody>
            {data.map((d) => {
              const v = verdict(d.bt, d.fw);
              return (
                <tr key={d.sym + d.strategy}>
                  <td>{d.sym.split("/")[0]}</td>
                  <td className="muted">{STRAT[d.strategy] || d.strategy}</td>
                  <td>{d.bt?.n ?? "—"}</td>
                  <td className={cls(d.bt?.exp_r)}>{d.bt?.exp_r != null ? fmt(d.bt.exp_r, 3) : "—"}</td>
                  <td>{d.fw?.n ?? 0}</td>
                  <td className={cls(d.fw?.exp_r)}>{d.fw?.exp_r != null ? fmt(d.fw.exp_r, 3) : "—"}</td>
                  <td className="muted">{d.fw?.win_rate != null ? (d.fw.win_rate * 100).toFixed(0) + "%" : "—"}</td>
                  <td className={"verdict " + v.c}>{v.t}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="muted small" style={{ marginTop: 10 }}>
        BT = backtest (histórico). FWD = forward (datos posteriores a la inception, no vistos).
        Si FWD aguanta el signo y nivel del BT → el edge es real. Pre-deploy es un holdout de auto-test;
        en la VM, FWD pasa a ser datos en vivo reales.
      </div>
    </>
  );
}
