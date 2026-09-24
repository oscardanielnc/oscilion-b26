// Display timezone for the dashboard (the operator's local time, UTC-5).
const TZ = "America/Lima";

export const fmt = (n: number | null | undefined, d = 2): string =>
  n === null || n === undefined || isNaN(n as number) ? "-" : Number(n).toLocaleString("en-US", { maximumFractionDigits: d });

export const pct = (n: number | null | undefined, d = 2): string =>
  n === null || n === undefined ? "-" : `${n >= 0 ? "+" : ""}${(n as number).toFixed(d)}%`;

export const cls = (n: number | null | undefined): string =>
  n === null || n === undefined ? "zero" : n > 0 ? "pos" : n < 0 ? "neg" : "zero";

export const fmtTime = (ms: number): string =>
  new Date(ms).toLocaleString("en-GB", { timeZone: TZ, hour12: false,
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

export const fmtClock = (ms: number): string =>
  new Date(ms).toLocaleTimeString("en-GB", { timeZone: TZ, hour12: false });

// today's date in the display timezone as YYYY-MM-DD (for date inputs; en-CA formats it that way)
export const today = (): string =>
  new Intl.DateTimeFormat("en-CA", { timeZone: TZ,
    year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
