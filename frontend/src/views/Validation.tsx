import { Forward } from "../api";
import { fmt, cls } from "../util";

const STRAT: Record<string, string> = { ema_trend_stack: "EMA stack", orb_breakout: "ORB", vwap_anchor: "VWAP anchor", break_retest: "Break+Retest" };

// Group by sym+strategy. Only the 'backtest' and 'forward' scopes are shown; the
// oos_a/oos_b sub-windows exist for the robust gate and must not overwrite forward.
function rows(forward: Forward[]) {
  const m = new Map<string, { sym: string; strategy: string; bt?: Forward; fw?: Forward }>();
  for (const f of forward) {
    const k = f.sym + "|" + f.strategy;
    const e = m.get(k) || { sym: f.sym, strategy: f.strategy };
    if (f.scope === "backtest") e.bt = f;
    else if (f.scope === "forward") e.fw = f;
    m.set(k, e);
  }
  return [...m.values()];
}

function verdict(fw?: Forward) {
  if (!fw || fw.n < 10 || fw.exp_r === null) return { t: "small sample", c: "zero" };
  if (fw.exp_r > 0) return { t: "holds", c: "pos" };
  return { t: "review", c: "neg" };
}

export function Validation({ forward }: { forward: Forward[] }) {
  const data = rows(forward);
  if (!data.length) return <div className="loading">No validation data yet.</div>;
  return (
    <>
      <div className="section-title">
        Backtest vs forward (unseen data) per coin x strategy | expectancy per trade in R | daily review
      </div>
      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Coin</th><th>Strategy</th>
              <th>BT n</th><th>BT exp.R</th>
              <th>FWD n</th><th>FWD exp.R</th><th>FWD winrate</th>
              <th>Verdict</th>
            </tr>
          </thead>
          <tbody>
            {data.map((d) => {
              const v = verdict(d.fw);
              return (
                <tr key={d.sym + d.strategy}>
                  <td>{d.sym.split("/")[0]}</td>
                  <td className="muted">{STRAT[d.strategy] || d.strategy}</td>
                  <td>{d.bt?.n ?? "-"}</td>
                  <td className={cls(d.bt?.exp_r)}>{d.bt?.exp_r != null ? fmt(d.bt.exp_r, 3) : "-"}</td>
                  <td>{d.fw?.n ?? 0}</td>
                  <td className={cls(d.fw?.exp_r)}>{d.fw?.exp_r != null ? fmt(d.fw.exp_r, 3) : "-"}</td>
                  <td className="muted">{d.fw?.win_rate != null ? (d.fw.win_rate * 100).toFixed(0) + "%" : "-"}</td>
                  <td className={"verdict " + v.c}>{v.t}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="muted small" style={{ marginTop: 10 }}>
        BT = backtest (history). FWD = forward (data after the inception, never seen).
        If FWD keeps the sign and level of BT, the edge is real. Before deployment it is a
        self-test holdout; on the VM, FWD becomes real live data.
      </div>
    </>
  );
}
