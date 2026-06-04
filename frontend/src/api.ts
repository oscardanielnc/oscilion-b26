// Capa de acceso a la API. En dev apunta al servidor FastAPI; en prod (servido
// por la propia API) usa mismo origen.
export const API_BASE = import.meta.env.DEV ? "http://127.0.0.1:8787" : "";

export async function getJSON<T>(path: string): Promise<T> {
  const r = await fetch(API_BASE + path);
  if (!r.ok) throw new Error(`${path} → ${r.status}`);
  return r.json();
}

export function exportUrl(from: string, to: string, fmt: "md" | "json"): string {
  return `${API_BASE}/export?date_from=${from}&date_to=${to}&fmt=${fmt}`;
}

// ---- tipos ----
export interface Status {
  version: string; mode: string; symbols: string[];
  risk: { risk_per_trade: number; min_profit_target: number; min_rr: number };
  db_counts: Record<string, number>;
}
export interface Check { label: string; ok: boolean; }
export interface Signal {
  sym: string; base: string; strategy: string; conviction: string; signal_tf: string;
  observe_only?: boolean;
  price: number; state: string; signal_active: boolean; in_trade: boolean;
  horizon: string; horizon_h: number;
  direction: string; bias?: string; entry: number; stop: number; tp: number;
  stop_pct: number | null; tp_pct: number | null; rr: number | string;
  levels: Record<string, number | null>;
  indicators: { RSI?: number; RSI_sano?: boolean };
  checklist: Check[]; checklist_ok: number; checklist_total: number;
  position: any | null;
}
export interface Forward {
  sym: string; strategy: string; scope: string; n: number;
  win_rate: number | null; exp_r: number | null; sum_r: number | null;
}
export interface Portfolio {
  series: { sym: string; base: string; strategy: string; conviction: string; weight: number; cluster: string }[];
  max_concurrent: number; max_per_cluster: number; tuned: boolean;
}
export interface Alert { ts: number; level: string; msg: string; }
export interface Trade {
  ts: number; exit_ts: number | null; sym: string; side: string; strategy: string;
  entry: number; exit: number; stop: number; tp: number;
  r_multiple: number | null; pnl: number | null; status: string;
}
