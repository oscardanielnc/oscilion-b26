"""Oscilion central configuration.

Single source of truth for paths, symbols, thresholds and risk constants.
Loaded from environment variables (on the VM: EnvironmentFile=/etc/oscilion.env;
locally: an optional .env). No hardcoded secrets.

The risk constants mirror docs/RISK_MODEL.md and are INVARIANTS:
do not change them without discussion.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path

# Optional .env loading (dev only; production uses systemd's EnvironmentFile).
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv is optional
    pass


# ----------------------------- paths -----------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("OSCILION_DATA_DIR", BASE_DIR / "data"))
LOGS_DIR = Path(os.getenv("OSCILION_LOGS_DIR", BASE_DIR / "logs"))
DB_PATH = Path(os.getenv("OSCILION_DB_PATH", DATA_DIR / "oscilion.db"))

# Created at import time: the rest of the system assumes they exist.
for _d in (DATA_DIR, LOGS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# ----------------------------- modes -----------------------------
class Mode(str, Enum):
    """Always starts in the safest mode (dry-run)."""

    DRY_RUN = "dry-run"   # observes and records, never trades
    PAPER = "paper"       # simulated fills + costs
    LIVE = "live"         # real orders (never implemented)


# ------------------------- env helpers ---------------------------
def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


def _env_int(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, default))
    except (TypeError, ValueError):
        return default


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _env_list(key: str, default: list[str]) -> list[str]:
    raw = os.getenv(key)
    if not raw:
        return default
    return [s.strip() for s in raw.split(",") if s.strip()]


def _default_symbols() -> list[str]:
    """Universe = env override, or the CORE defined in strategies/assignment
    (single source, so config and assignment cannot drift apart)."""
    raw = os.getenv("OSCILION_SYMBOLS")
    if raw:
        return [s.strip() for s in raw.split(",") if s.strip()]
    try:
        from oscilion.strategies.assignment import core_symbols
        return core_symbols()
    except Exception:
        return ["BTC/USDT:USDT", "BNB/USDT:USDT", "TRX/USDT:USDT",
                "LINK/USDT:USDT", "DOT/USDT:USDT"]


# ---------------------------- config -----------------------------
@dataclass(frozen=True)
class Config:
    # parameter-set version (persisted in the `params` table)
    version: str = os.getenv("OSCILION_VERSION", "0.6.0-pilot")
    mode: Mode = Mode(os.getenv("OSCILION_MODE", Mode.DRY_RUN.value))

    # --- universe / timeframes ---
    symbols: list[str] = field(default_factory=_default_symbols)
    base_timeframe: str = os.getenv("OSCILION_BASE_TF", "1h")
    fast_timeframe: str = os.getenv("OSCILION_FAST_TF", "15m")
    exchange: str = os.getenv("OSCILION_EXCHANGE", "binanceusdm")

    # --- loop ---
    tick_seconds: int = _env_int("OSCILION_TICK_SECONDS", 60)
    # Network timeout per ccxt call (ms): bounds how long a fetch can hang a tick
    # (explicit and tunable instead of relying on the library default).
    ccxt_timeout_ms: int = _env_int("OSCILION_CCXT_TIMEOUT_MS", 10_000)

    # --- risk INVARIANTS (RISK_MODEL.md) ---
    risk_per_trade: float = _env_float("OSCILION_RISK_PER_TRADE", 0.02)   # max loss per trade
    min_profit_target: float = _env_float("OSCILION_MIN_PROFIT", 0.05)    # floor target
    min_rr: float = _env_float("OSCILION_MIN_RR", 2.5)                    # entry filter
    taker_fee: float = _env_float("OSCILION_TAKER_FEE", 0.00036)          # 0.036%
    max_concurrent: int = _env_int("OSCILION_MAX_CONCURRENT", 3)
    # Stop-distance floor: below it notional/leverage blows up (fixed risk / stop->0).
    # With stops >= 1x ATR it almost never applies: it is a safety net.
    min_stop_pct: float = _env_float("OSCILION_MIN_STOP_PCT", 0.002)      # 0.2%

    # --- cost filter (audit 06-29): round-trip cost in R = (2*taker + slip)/stop_pct.
    # With a tight stop the notional explodes and fees eat the R (XAU stop 0.38% =>
    # -0.24R per trade; TRX 0.67% => -0.13R). Rejects entries whose estimated cost
    # exceeds this cap (kills cost-toxic combos such as gold).
    max_cost_r: float = _env_float("OSCILION_MAX_COST_R", 0.12)           # 12% of R

    # --- MARKET REGIME gate (audit 06-29): all 17 live vwap_anchor entries were
    # LONG during two weeks of falling alts -> bull traps (-11R). A continuation long
    # must not fire while the base market trends down (nor a short in an uptrend).
    # Benchmark = BTC vs its EMA on a higher TF. Gold is EXEMPT: it is uncorrelated
    # with crypto.
    market_regime_filter: bool = _env_bool("OSCILION_MKT_REGIME", True)
    market_benchmark: str = os.getenv("OSCILION_MKT_BENCH", "BTC/USDT:USDT")
    market_regime_tf_h: int = _env_int("OSCILION_MKT_TF_H", 4)            # regime TF (hours)
    market_regime_ema: int = _env_int("OSCILION_MKT_EMA", 50)             # trend EMA
    # Strategies EXEMPT from the regime filter: the ANTI-BETA ones. break_retest wins
    # by shorting alts that fall INDEPENDENTLY of BTC (alpha, not beta); a beta filter
    # kills its winning shorts (FLOW: -0.48 exp_R, 3 shorts worth +4.42R cut).
    regime_exempt_strategies: list[str] = field(
        default_factory=lambda: _env_list("OSCILION_REGIME_EXEMPT", ["break_retest"]))
    # Symbols EXEMPT because they are uncorrelated with the crypto benchmark (gold).
    # Per SYMBOL, not per cluster: PAXG/ema is observe-only and not in the cluster
    # dict, so a cluster check would let it through and apply BTC's regime (wrong).
    regime_exempt_symbols: list[str] = field(default_factory=lambda: _env_list(
        "OSCILION_REGIME_EXEMPT_SYMS", ["PAXG/USDT:USDT", "XAU/USDT:USDT"]))

    # --- validation gate (FORWARD_REVIEW #1): a symbol x strategy combo only trades
    # with capital if ITS local backtest (honest engine, forward_results) has sample
    # and edge: n >= gate_min_n and exp_r > gate_min_exp_r.
    # Otherwise it is demoted to observe (alerts + stats, no capital).
    gate_min_n: int = _env_int("OSCILION_GATE_MIN_N", 30)
    # +0.05R demands a REAL margin over costs (audit 06-22 showed exp_R~0 combos do
    # not survive: the edge must pay fees with room to spare).
    gate_min_exp_r: float = _env_float("OSCILION_GATE_MIN_EXP_R", 0.05)
    # The gate backtest is measured ONLY from here (OOS), not over the whole history:
    # portfolio params were chosen in-sample, so exp_R over the full history inflates
    # them 2-3x (audit 06-22: TRX break_retest +1.23 full vs +0.39 OOS). Measuring from
    # 2025-01 leaves the selection window out -> an honest number.
    gate_backtest_from_ms: int = _env_int(
        "OSCILION_GATE_BT_FROM_MS", 1735689600000  # 2025-01-01 UTC
    )
    # --- ADAPTIVE gate (audit 06-29): the backtest gate did not close the loop with
    # reality -> live, the 'observe' book (+1.77R) beat the 'capital' book (-16.85R).
    # The gate now also looks at the FORWARD results:
    #   - KILL-SWITCH: a capital combo whose real forward already proved it bleeds
    #     (n >= kill_n and exp_R <= kill_exp_r) is demoted to observe.
    #   - GRADUATION: an observe combo whose forward confirms edge (n >= grad_n and
    #     exp_R >= grad_exp_r) is promoted to capital.
    # High n: acting needs a real forward sample (do not react to noise).
    gate_fw_kill_n: int = _env_int("OSCILION_GATE_FW_KILL_N", 15)
    gate_fw_kill_exp_r: float = _env_float("OSCILION_GATE_FW_KILL_EXP_R", -0.10)
    gate_fw_grad_n: int = _env_int("OSCILION_GATE_FW_GRAD_N", 20)
    gate_fw_grad_exp_r: float = _env_float("OSCILION_GATE_FW_GRAD_EXP_R", 0.10)
    # Audit 07-02: kill/graduation read the REAL book (db.real_forward_stats), not
    # the engine simulation (scope 'forward', which diverged: XAU +1.35 simulated vs
    # -2.47R real). This cutoff limits the evidence to the CURRENT rules era
    # (v0.8, 2026-06-29 23:48 UTC): losses from older eras (e.g. vwap without the
    # regime filter) must not kill a combo that would trade differently today.
    gate_real_fw_from_ms: int = _env_int(
        "OSCILION_GATE_REAL_FW_FROM_MS", 1782776880000  # 2026-06-29 23:48 UTC (v0.8)
    )
    # --- recency-aware ROBUST gate (audit 06-29): the aggregate backtest lets through
    # a combo whose edge already DECAYED (+0.30 old / -0.20 recent: the average lies).
    # Requires the MOST RECENT OOS window (2026-YTD) with enough sample
    # (n >= robust_min_n) to be non-negative. It does NOT require both halves positive:
    # that would kill emerging alpha (break_retest wins when alts fall, a 2026
    # phenomenon). The split divides the OOS [2025, inception) into 2025 vs 2026-YTD.
    gate_robust: bool = _env_bool("OSCILION_GATE_ROBUST", True)
    gate_robust_min_n: int = _env_int("OSCILION_GATE_ROBUST_MIN_N", 20)
    gate_robust_split_ms: int = _env_int(
        "OSCILION_GATE_ROBUST_SPLIT_MS", 1767225600000  # 2026-01-01 UTC
    )

    # --- stale signal (FORWARD_REVIEW): if the signal candle closed longer ago than
    # this, do NOT enter (the reference price is old; happens after downtime or a
    # failed data refresh).
    max_signal_age_min: int = _env_int("OSCILION_MAX_SIGNAL_AGE_MIN", 30)

    # --- circuit breaker (hard limits) ---
    max_daily_loss: float = _env_float("OSCILION_MAX_DAILY_LOSS", 0.06)   # -6% of capital/day
    max_consecutive_errors: int = _env_int("OSCILION_MAX_ERRORS", 10)     # consecutive failed ticks

    # --- notify ---
    ntfy_topic: str = os.getenv("OSCILION_NTFY_TOPIC", "")
    telegram_token: str = os.getenv("OSCILION_TG_TOKEN", "")
    telegram_chat_id: str = os.getenv("OSCILION_TG_CHAT", "")

    # --- API ---
    api_host: str = os.getenv("OSCILION_API_HOST", "127.0.0.1")
    api_port: int = _env_int("OSCILION_API_PORT", 8787)

    # --- forward validation ---
    # Start of the "unseen" period (epoch ms). Before deploying: a recent holdout to
    # self-test the pipeline; on the VM, set it to the deployment date.
    forward_inception_ms: int = _env_int(
        "OSCILION_FORWARD_INCEPTION_MS", 1767225600000  # 2026-01-01 UTC
    )

    log_level: str = os.getenv("OSCILION_LOG_LEVEL", "INFO")

    def as_params(self) -> dict:
        """JSON-safe serialization for the `params` table (audit/reproducibility)."""
        d = asdict(self)
        d["mode"] = self.mode.value
        d["telegram_token"] = bool(self.telegram_token)   # never persist secrets
        return d


config = Config()
