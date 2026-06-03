"""Persistencia de datos limpios: parquet (detalle) + DB (resumen auditable).

Layout en disco:
    data/ohlcv/<exchange>/<SYM>/<tf>.parquet
    data/funding/<exchange>/<SYM>.parquet

Garantías:
  • `clean_bars` valida sanidad OHLC y elimina duplicados/NaN.
  • `save_bars` hace MERGE idempotente con lo existente (sin perder histórico),
    escritura atómica (tmp + replace).
  • `gaps_report` detecta velas faltantes según el timeframe.
  • cada guardado actualiza `ohlcv_status` en la DB (auditoría).
"""
from __future__ import annotations

import logging
import os

import pandas as pd

from config import DATA_DIR, config
from oscilion.data.fetch import OHLCV_COLS, timeframe_to_ms
from oscilion.persistence import db

log = logging.getLogger(__name__)

OHLCV_DIR = DATA_DIR / "ohlcv"
FUNDING_DIR = DATA_DIR / "funding"


def _sanitize(sym: str) -> str:
    return sym.replace("/", "_").replace(":", "_")


def _ohlcv_path(sym: str, tf: str):
    p = OHLCV_DIR / config.exchange / _sanitize(sym)
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{tf}.parquet"


def _funding_path(sym: str):
    p = FUNDING_DIR / config.exchange
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{_sanitize(sym)}.parquet"


def _atomic_write(df: pd.DataFrame, path) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


# ------------------------------- limpieza -------------------------------
def clean_bars(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Devuelve (df_limpio, n_duplicados_removidos). Valida sanidad OHLC."""
    if df.empty:
        return df.reindex(columns=OHLCV_COLS), 0
    df = df.copy()
    for c in OHLCV_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=OHLCV_COLS)
    # sanidad: high es el máximo y low el mínimo del rango
    hi = df[["open", "close", "high"]].max(axis=1)
    lo = df[["open", "close", "low"]].min(axis=1)
    sane = (df["high"] >= df["low"]) & (df["high"] >= hi) & (df["low"] <= lo) & (df["volume"] >= 0)
    df = df[sane]
    before = len(df)
    df = df.drop_duplicates(subset="ts", keep="last").sort_values("ts").reset_index(drop=True)
    dupes = before - len(df)
    df["ts"] = df["ts"].astype("int64")
    return df, dupes


def gaps_report(df: pd.DataFrame, tf: str) -> list[dict]:
    """Lista de huecos: cada uno {from_ts, to_ts, missing} según el timeframe."""
    if len(df) < 2:
        return []
    tf_ms = timeframe_to_ms(tf)
    ts = df["ts"].to_numpy()
    diffs = ts[1:] - ts[:-1]
    gaps = []
    for i, d in enumerate(diffs):
        if d > tf_ms:
            missing = int(d // tf_ms) - 1
            gaps.append({"from_ts": int(ts[i]), "to_ts": int(ts[i + 1]), "missing": missing})
    return gaps


# ------------------------------- OHLCV ----------------------------------
def load_bars(sym: str, tf: str, *, since: int | None = None, until: int | None = None) -> pd.DataFrame:
    path = _ohlcv_path(sym, tf)
    if not path.exists():
        return pd.DataFrame(columns=OHLCV_COLS)
    df = pd.read_parquet(path)
    if since is not None:
        df = df[df["ts"] >= since]
    if until is not None:
        df = df[df["ts"] <= until]
    return df.reset_index(drop=True)


def save_bars(sym: str, tf: str, df_new: pd.DataFrame) -> dict:
    """Merge idempotente con lo existente. Devuelve resumen de calidad.

    `dupes` cuenta solo duplicados ANÓMALOS dentro del lote descargado
    (exchange devolviendo velas repetidas). El solapamiento normal con el
    histórico ya guardado se deduplica en silencio (es esperado al re-sync).
    """
    new_clean, dupes = clean_bars(df_new)  # anomalías reales del fetch
    existing = load_bars(sym, tf)
    merged = pd.concat([existing, new_clean], ignore_index=True) if not existing.empty else new_clean
    clean, _overlap = clean_bars(merged)   # overlap esperado, no es anomalía
    _atomic_write(clean, _ohlcv_path(sym, tf))

    gaps = gaps_report(clean, tf)
    first_ts = int(clean["ts"].iloc[0]) if not clean.empty else None
    last_ts = int(clean["ts"].iloc[-1]) if not clean.empty else None
    db.upsert_ohlcv_status(
        config.exchange, sym, tf, "ohlcv",
        first_ts=first_ts, last_ts=last_ts, rows=len(clean),
        gaps=len(gaps), dupes=dupes,
    )
    return {"sym": sym, "tf": tf, "rows": len(clean), "added": len(clean) - len(existing),
            "dupes": dupes, "gaps": len(gaps), "missing": sum(g["missing"] for g in gaps),
            "first_ts": first_ts, "last_ts": last_ts}


# ------------------------------- funding --------------------------------
def load_funding(sym: str) -> pd.DataFrame:
    path = _funding_path(sym)
    if not path.exists():
        return pd.DataFrame(columns=["ts", "funding_rate"])
    return pd.read_parquet(path)


def save_funding(sym: str, df_new: pd.DataFrame) -> dict:
    existing = load_funding(sym)
    merged = pd.concat([existing, df_new], ignore_index=True) if not existing.empty else df_new
    if not merged.empty:
        merged["funding_rate"] = pd.to_numeric(merged["funding_rate"], errors="coerce")
        merged = (merged.dropna(subset=["ts"]).drop_duplicates(subset="ts", keep="last")
                  .sort_values("ts").reset_index(drop=True))
        merged["ts"] = merged["ts"].astype("int64")
    _atomic_write(merged, _funding_path(sym))

    first_ts = int(merged["ts"].iloc[0]) if not merged.empty else None
    last_ts = int(merged["ts"].iloc[-1]) if not merged.empty else None
    db.upsert_ohlcv_status(
        config.exchange, sym, "funding", "funding",
        first_ts=first_ts, last_ts=last_ts, rows=len(merged),
    )
    return {"sym": sym, "rows": len(merged), "added": len(merged) - len(existing),
            "first_ts": first_ts, "last_ts": last_ts}
