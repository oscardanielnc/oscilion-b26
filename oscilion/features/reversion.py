"""Medidas de calidad de reversión a la media (Fase 3).

Sobre una serie de precios (se usa log-precio internamente donde aplica):
  • hurst        — exponente de Hurst. H<0.5 ⇒ anti-persistente (revierte).
  • ou_half_life — vida media de un proceso Ornstein-Uhlenbeck (AR1). Barras
                   hasta cerrar la mitad de una desviación. Útil = ni muy
                   corta (ruido) ni muy larga (deriva).
  • variance_ratio (Lo-MacKinlay) — VR<1 ⇒ reversión, VR>1 ⇒ momentum.
  • adf          — Dickey-Fuller aumentado. Estadístico muy negativo ⇒
                   estacionaria (revierte). p-valor exacto si hay statsmodels.

Todo es defensivo: con datos insuficientes devuelve NaN, nunca explota.
Sin dependencias duras de statsmodels (se usa si está disponible).
"""
from __future__ import annotations

import numpy as np

# valores críticos ADF (constante, sin tendencia) — MacKinnon aprox.
_ADF_CRIT = {"1%": -3.43, "5%": -2.86, "10%": -2.57}


def _as_array(series) -> np.ndarray:
    a = np.asarray(series, dtype="float64")
    return a[~np.isnan(a)]


def _ols(y: np.ndarray, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """OLS por mínimos cuadrados. Devuelve (coef, se) con se robusto a singular."""
    beta, _res, _rank, _sv = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = max(len(y) - X.shape[1], 1)
    sigma2 = (resid @ resid) / dof
    try:
        cov = sigma2 * np.linalg.inv(X.T @ X)
        se = np.sqrt(np.diag(cov))
    except np.linalg.LinAlgError:
        se = np.full(X.shape[1], np.nan)
    return beta, se


def hurst(series, min_lag: int = 2, max_lag: int = 40) -> float:
    """Exponente de Hurst por dispersión de diferencias retardadas."""
    p = _as_array(series)
    p = np.log(p) if (p > 0).all() else p
    if len(p) < max_lag * 2:
        max_lag = max(min_lag + 2, len(p) // 2)
    if len(p) < min_lag + 3 or max_lag <= min_lag:
        return np.nan
    lags = np.arange(min_lag, max_lag)
    tau = []
    for lag in lags:
        d = p[lag:] - p[:-lag]
        tau.append(np.sqrt(np.std(d)) if d.size else np.nan)
    tau = np.asarray(tau)
    ok = tau > 0
    if ok.sum() < 3:
        return np.nan
    slope = np.polyfit(np.log(lags[ok]), np.log(tau[ok]), 1)[0]
    return float(slope * 2.0)


def ou_half_life(series) -> float:
    """Vida media OU vía AR(1): Δp_t = a + b·p_{t-1}. half_life = -ln2/b."""
    p = _as_array(series)
    if len(p) < 10:
        return np.nan
    y = np.diff(p)
    x = p[:-1]
    X = np.column_stack([np.ones_like(x), x])
    beta, _ = _ols(y, X)
    b = beta[1]
    if b >= 0 or not np.isfinite(b):
        return np.nan  # no hay reversión (deriva o explosivo)
    return float(-np.log(2) / b)


def variance_ratio(series, k: int = 4) -> float:
    """Variance ratio Lo-MacKinlay (insesgado). VR<1 ⇒ reversión."""
    p = _as_array(series)
    p = np.log(p) if (p > 0).all() else p
    r = np.diff(p)
    n = len(r)
    if n < k + 2 or k < 2:
        return np.nan
    mu = r.mean()
    var1 = np.sum((r - mu) ** 2) / (n - 1)
    if var1 == 0:
        return np.nan
    rk = np.convolve(r, np.ones(k), mode="valid")  # sumas de k retornos
    m = k * (n - k + 1) * (1 - k / n)
    vark = np.sum((rk - k * mu) ** 2) / m if m > 0 else np.nan
    return float(vark / var1)


def adf(series, max_lag: int = 1) -> dict:
    """Dickey-Fuller aumentado (const, sin tendencia).

    Devuelve {stat, pvalue, is_stationary, crit}. p-valor exacto si hay
    statsmodels; si no, se decide por valor crítico al 5%.
    """
    p = _as_array(series)
    if len(p) < 3 * (max_lag + 2):
        return {"stat": np.nan, "pvalue": np.nan, "is_stationary": False, "crit": _ADF_CRIT}

    # intento preciso con statsmodels
    try:
        from statsmodels.tsa.stattools import adfuller

        stat, pval, *_ = adfuller(p, maxlag=max_lag, regression="c", autolag=None)
        return {"stat": float(stat), "pvalue": float(pval),
                "is_stationary": pval < 0.05, "crit": _ADF_CRIT}
    except Exception:
        pass

    # fallback numpy: Δy = a + b·y_{t-1} + Σ γ_i Δy_{t-i}
    dy = np.diff(p)
    y_lag = p[:-1]
    cols = [np.ones_like(y_lag), y_lag]
    for i in range(1, max_lag + 1):
        lagged = np.concatenate([np.full(i, np.nan), dy[:-i]])
        cols.append(lagged)
    X = np.column_stack(cols)
    mask = ~np.isnan(X).any(axis=1)
    X, yv = X[mask], dy[mask]
    if len(yv) < X.shape[1] + 2:
        return {"stat": np.nan, "pvalue": np.nan, "is_stationary": False, "crit": _ADF_CRIT}
    beta, se = _ols(yv, X)
    stat = beta[1] / se[1] if se[1] and np.isfinite(se[1]) else np.nan
    is_stat = np.isfinite(stat) and stat < _ADF_CRIT["5%"]
    return {"stat": float(stat) if np.isfinite(stat) else np.nan,
            "pvalue": np.nan, "is_stationary": bool(is_stat), "crit": _ADF_CRIT}


def reversion_summary(series) -> dict:
    """Resumen + score 0..1 de aptitud para reversión (mayor = mejor)."""
    h = hurst(series)
    hl = ou_half_life(series)
    vr = variance_ratio(series, 4)
    adf_r = adf(series, max_lag=1)

    # señales normalizadas a [0,1] (cada una premia reversión)
    s_h = _clamp01((0.5 - h) / 0.3) if np.isfinite(h) else 0.0          # H<0.5 bueno
    s_vr = _clamp01((1.0 - vr) / 0.4) if np.isfinite(vr) else 0.0        # VR<1 bueno
    s_adf = 1.0 if adf_r["is_stationary"] else 0.0
    s_hl = _half_life_score(hl)

    score = float(np.mean([s_h, s_vr, s_adf, s_hl]))
    return {"hurst": h, "half_life": hl, "variance_ratio": vr,
            "adf_stat": adf_r["stat"], "adf_pvalue": adf_r["pvalue"],
            "is_stationary": adf_r["is_stationary"], "reversion_score": score}


def _clamp01(x: float) -> float:
    return float(min(1.0, max(0.0, x)))


def _half_life_score(hl: float, lo: float = 4, hi: float = 96) -> float:
    """Premia vidas medias en banda útil [lo,hi] barras; castiga extremos."""
    if not np.isfinite(hl) or hl <= 0:
        return 0.0
    if lo <= hl <= hi:
        return 1.0
    if hl < lo:
        return _clamp01(hl / lo)
    return _clamp01(hi / hl)  # demasiado lenta ⇒ deriva
