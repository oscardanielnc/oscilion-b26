import { Signal } from "../api";
import { fmt, pct } from "../util";

const STRAT_LABEL: Record<string, string> = {
  ema_trend_stack: "Tendencia · EMA stack",
  orb_breakout: "Ruptura de rango · ORB",
  vwap_anchor: "Tendencia · VWAP anchor",
  break_retest: "Continuación · Break+Retest",
};

function DirBadge({ s }: { s: Signal }) {
  // Sin ruptura (neutral): no hay dirección comprometida → mostramos "en rango"
  // con el sesgo del borde más cercano, sin parpadear como señal real.
  if (s.direction === "neutral") {
    const b = s.bias === "long" ? "▲" : "▼";
    return <span className="badge neutral">◇ En rango <small>({b} sesgo)</small></span>;
  }
  return <span className={"badge " + s.direction}>{s.direction === "long" ? "▲ Long" : "▼ Short"}</span>;
}

function StateBadge({ s }: { s: Signal }) {
  const cls = s.in_trade ? "entrade" : s.signal_active ? "activa" : "esperando";
  const label = s.in_trade ? "EN TRADE" : s.signal_active ? "SEÑAL ACTIVA" : "ESPERANDO";
  return <span className={"state " + cls}>{label}</span>;
}

function StrategyBlock({ s }: { s: Signal }) {
  return (
    <div className="strat">
      <div className="strat-head">
        <span className="strat-name">{STRAT_LABEL[s.strategy] || s.strategy}</span>
        <DirBadge s={s} />
        <span className="badge horizon">{s.horizon}</span>
        {s.observe_only && <span className="badge observe" title="Forward-test sin capital — validando edge en vivo">🔬 observación</span>}
        <StateBadge s={s} />
      </div>

      <div className="trade-grid">
        <div><span className="lbl">Entrada</span><span className="num">{fmt(s.entry, 6)}</span></div>
        <div><span className="lbl">Stop</span><span className="num stop">{fmt(s.stop, 6)}<small>{pct(s.stop_pct ? -Math.abs(s.stop_pct) : null)}</small></span></div>
        <div><span className="lbl">Target · RR {s.rr}</span><span className="num tp">{fmt(s.tp, 6)}<small>{pct(s.tp_pct)}</small></span></div>
      </div>

      <div className="lv-row">
        {Object.entries(s.levels).map(([k, v]) => (
          <span className="lv" key={k}><b>{k.replace(/_/g, " ")}</b> {fmt(v as number, 6)}</span>
        ))}
        {s.indicators.RSI !== undefined && (
          <span className="lv"><b>RSI</b> <span style={{ color: s.indicators.RSI_sano ? "var(--green)" : "var(--muted)" }}>{fmt(s.indicators.RSI, 1)}{s.indicators.RSI_sano ? " ✓" : ""}</span></span>
        )}
      </div>

      <div className="checklist">
        <span className="chk-count">{s.checklist_ok}/{s.checklist_total} criterios</span>
        {s.checklist.map((c, i) => (
          <span className={"chk " + (c.ok ? "ok" : "no")} key={i}>{c.ok ? "✓" : "○"} {c.label}</span>
        ))}
      </div>
    </div>
  );
}

export function Senales({ signals }: { signals: Signal[] }) {
  if (!signals.length) return <div className="loading">Sin series configuradas.</div>;

  // agrupar por moneda
  const byCoin = new Map<string, Signal[]>();
  for (const s of signals) {
    if (!byCoin.has(s.base)) byCoin.set(s.base, []);
    byCoin.get(s.base)!.push(s);
  }
  // ordenar monedas: las que tienen trade/señal activa primero
  const coins = [...byCoin.entries()].sort((a, b) => {
    const score = (xs: Signal[]) => Math.max(...xs.map((x) => (x.in_trade ? 2 : x.signal_active ? 1 : 0) + x.checklist_ok / 10));
    return score(b[1]) - score(a[1]);
  });

  return (
    <>
      <div className="section-title">
        Núcleo · una moneda puede tener varias estrategias · "Entrada/Stop/Target" son niveles propuestos si entrara ahora
      </div>
      <div className="coins">
        {coins.map(([base, list]) => (
          <div className="coin-card" key={base}>
            <div className="coin-head">
              <span className="coin-name">{base}</span>
              <span className="coin-price">{fmt(list[0].price, 6)}</span>
              {list.length > 1 && <span className="badge multi">{list.length} estrategias</span>}
            </div>
            {list.map((s) => <StrategyBlock key={s.strategy} s={s} />)}
          </div>
        ))}
      </div>
    </>
  );
}
