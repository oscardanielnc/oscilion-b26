import { Signal } from "../api";
import { fmt, pct } from "../util";

const STRAT_LABEL: Record<string, string> = {
  ema_trend_stack: "Tendencia (EMA stack)",
  orb_breakout: "Ruptura de rango (ORB)",
};

function SignalCard({ s }: { s: Signal }) {
  const stClass = s.in_trade ? "entrade" : s.signal_active ? "activa" : "ESPERANDO";
  const stLabel = s.in_trade ? "EN TRADE" : s.signal_active ? "SEÑAL ACTIVA" : "ESPERANDO";
  return (
    <div className="card">
      <div className="sig-head">
        <span className="sig-base">{s.base}</span>
        <span className={"badge " + s.direction}>{s.direction === "long" ? "▲ Long" : "▼ Short"}</span>
        <span className="badge">{STRAT_LABEL[s.strategy] || s.strategy} · {s.signal_tf}</span>
        <span className={"state " + stClass}>{stLabel}</span>
      </div>

      <div className="trade-row">
        <div className="item"><div className="lbl">Precio</div><div className="num">{fmt(s.price, 6)}</div></div>
        <div className="item"><div className="lbl">Entrada</div><div className="num">{fmt(s.entry, 6)}</div></div>
        <div className="item"><div className="lbl">Stop</div><div className="num stop">{fmt(s.stop, 6)} <span className="small muted">{pct(s.stop_pct ? -Math.abs(s.stop_pct) : null)}</span></div></div>
        <div className="item"><div className="lbl">Target (RR {s.rr})</div><div className="num tp">{fmt(s.tp, 6)} <span className="small muted">{pct(s.tp_pct)}</span></div></div>
      </div>

      <div className="levels">
        {Object.entries(s.levels).map(([k, v]) => (
          <div className="lv" key={k}><span className="k">{k.replace(/_/g, " ")}</span><span className="v">{fmt(v as number, 6)}</span></div>
        ))}
        {s.indicators.RSI !== undefined && (
          <div className="lv"><span className="k">RSI</span>
            <span className="v" style={{ color: s.indicators.RSI_sano ? "var(--green)" : "var(--muted)" }}>
              {fmt(s.indicators.RSI, 1)} {s.indicators.RSI_sano ? "✓" : ""}</span></div>
        )}
      </div>

      <div className="checklist">
        {s.checklist.map((c, i) => (
          <div className={"chk " + (c.ok ? "ok" : "no")} key={i}>
            <span className="dot">{c.ok ? "✓" : "·"}</span>{c.label}
          </div>
        ))}
      </div>
    </div>
  );
}

export function Senales({ signals }: { signals: Signal[] }) {
  if (!signals.length) return <div className="loading">Sin series configuradas.</div>;
  // ordenar: en trade → señal activa → más condiciones cumplidas
  const sorted = [...signals].sort((a, b) =>
    Number(b.in_trade) - Number(a.in_trade) ||
    Number(b.signal_active) - Number(a.signal_active) ||
    b.checklist_ok - a.checklist_ok);
  return (
    <>
      <div className="section-title">Núcleo · {signals.length} series · dirección y niveles según la estrategia de cada moneda</div>
      <div className="grid cards">
        {sorted.map((s) => <SignalCard key={s.sym + s.strategy} s={s} />)}
      </div>
    </>
  );
}
