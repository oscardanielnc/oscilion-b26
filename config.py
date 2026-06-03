"""Oscilion — configuración central.

Fuente única de verdad para rutas, símbolos, umbrales y constantes de riesgo.
Se carga desde variables de entorno (en la VM: EnvironmentFile=/etc/oscilion.env;
en local: un .env opcional). Nada de secretos hardcodeados.

Las constantes de riesgo replican docs/RISK_MODEL.md y son INVARIANTES:
no cambiar sin discutir (ver CLAUDE.md).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path

# --- carga opcional de .env (solo dev; en prod usa EnvironmentFile de systemd) ---
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # dotenv es opcional
    pass


# ----------------------------- rutas -----------------------------
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.getenv("OSCILION_DATA_DIR", BASE_DIR / "data"))
LOGS_DIR = Path(os.getenv("OSCILION_LOGS_DIR", BASE_DIR / "logs"))
DB_PATH = Path(os.getenv("OSCILION_DB_PATH", DATA_DIR / "oscilion.db"))

# Se crean al importar: el resto del sistema asume que existen.
for _d in (DATA_DIR, LOGS_DIR):
    _d.mkdir(parents=True, exist_ok=True)


# ----------------------------- modos -----------------------------
class Mode(str, Enum):
    """Arranca siempre en el modo más seguro (dry-run)."""

    DRY_RUN = "dry-run"   # observa y registra, NO opera
    PAPER = "paper"       # simula fills + costos
    LIVE = "live"         # órdenes reales (Fase 8)


# --------------------- helpers de entorno ------------------------
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


def _env_list(key: str, default: list[str]) -> list[str]:
    raw = os.getenv(key)
    if not raw:
        return default
    return [s.strip() for s in raw.split(",") if s.strip()]


# --------------------------- config -----------------------------
@dataclass(frozen=True)
class Config:
    # versión del set de parámetros (se persiste en tabla `params`)
    version: str = os.getenv("OSCILION_VERSION", "0.6.0-pilot")
    mode: Mode = Mode(os.getenv("OSCILION_MODE", Mode.DRY_RUN.value))

    # --- universo / timeframes ---
    symbols: list[str] = field(
        default_factory=lambda: _env_list(
            "OSCILION_SYMBOLS",
            # núcleo v1 (ver oscilion/strategies/assignment.py)
            ["BTC/USDT:USDT", "BNB/USDT:USDT", "TRX/USDT:USDT",
             "LINK/USDT:USDT", "DOT/USDT:USDT"],
        )
    )
    base_timeframe: str = os.getenv("OSCILION_BASE_TF", "1h")
    fast_timeframe: str = os.getenv("OSCILION_FAST_TF", "15m")
    exchange: str = os.getenv("OSCILION_EXCHANGE", "binanceusdm")

    # --- loop ---
    tick_seconds: int = _env_int("OSCILION_TICK_SECONDS", 60)

    # --- INVARIANTES de riesgo (RISK_MODEL.md) ---
    risk_per_trade: float = _env_float("OSCILION_RISK_PER_TRADE", 0.02)   # pérdida máx por trade
    min_profit_target: float = _env_float("OSCILION_MIN_PROFIT", 0.05)    # meta piso
    min_rr: float = _env_float("OSCILION_MIN_RR", 2.5)                    # filtro de entrada
    taker_fee: float = _env_float("OSCILION_TAKER_FEE", 0.00036)          # 0.036%
    max_concurrent: int = _env_int("OSCILION_MAX_CONCURRENT", 3)          # ~3 monedas

    # --- circuit breaker (límites duros) ---
    max_daily_loss: float = _env_float("OSCILION_MAX_DAILY_LOSS", 0.06)   # -6% del capital/día
    max_consecutive_errors: int = _env_int("OSCILION_MAX_ERRORS", 10)     # ticks fallidos seguidos

    # --- notify ---
    ntfy_topic: str = os.getenv("OSCILION_NTFY_TOPIC", "oscar-oscilion-b26")  # push al móvil
    telegram_token: str = os.getenv("OSCILION_TG_TOKEN", "")
    telegram_chat_id: str = os.getenv("OSCILION_TG_CHAT", "")

    # --- API ---
    api_host: str = os.getenv("OSCILION_API_HOST", "127.0.0.1")
    api_port: int = _env_int("OSCILION_API_PORT", 8787)

    # --- validación forward (Fase A) ---
    # Inicio del período "no visto" (epoch ms). Pre-deploy: holdout reciente para
    # auto-test del pipeline; al desplegar en la VM, fijar a la fecha de despliegue.
    forward_inception_ms: int = _env_int(
        "OSCILION_FORWARD_INCEPTION_MS", 1767225600000  # 2026-01-01 UTC
    )

    log_level: str = os.getenv("OSCILION_LOG_LEVEL", "INFO")

    def as_params(self) -> dict:
        """Serialización JSON-safe para la tabla `params` (auditoría/reproducibilidad)."""
        d = asdict(self)
        d["mode"] = self.mode.value
        # nunca persistir secretos
        d["telegram_token"] = bool(self.telegram_token)
        return d


# instancia única
config = Config()
