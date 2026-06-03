export const fmt = (n: number | null | undefined, d = 2): string =>
  n === null || n === undefined || isNaN(n as number) ? "—" : Number(n).toLocaleString("es", { maximumFractionDigits: d });

export const pct = (n: number | null | undefined, d = 2): string =>
  n === null || n === undefined ? "—" : `${n >= 0 ? "+" : ""}${(n as number).toFixed(d)}%`;

export const cls = (n: number | null | undefined): string =>
  n === null || n === undefined ? "zero" : n > 0 ? "pos" : n < 0 ? "neg" : "zero";

export const timeLima = (ms: number): string =>
  new Date(ms).toLocaleString("es-PE", { timeZone: "America/Lima", hour12: false,
    day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
