"""Guardas de proceso (FORWARD_REVIEW 06-10): gate, veto símbolo, stale, tp runner,
piso de stop. Puras (sin red ni BD) — protegen que la sangría del primer ciclo
(DOGE/vwap n=1 ×2, doble posición TRX, tp=1e18) no pueda repetirse.
"""
import math

from oscilion.live import guards
from oscilion.strategies.library import tp_barrier


# ------------------------------ gate de validación ------------------------------
def test_gate_observe_only_siempre_sin_capital():
    obs, reason = guards.gate_decision({"n": 999, "exp_r": 1.0}, True, min_n=30, min_exp_r=0.0)
    assert obs and "observe_only" in reason


def test_gate_sin_backtest_local_bloquea():
    obs, reason = guards.gate_decision(None, False, min_n=30, min_exp_r=0.0)
    assert obs and "sin backtest" in reason


def test_gate_n_chico_bloquea():
    """El caso DOGE/vwap del primer ciclo: backtest local n=1 → jamás capital."""
    obs, reason = guards.gate_decision({"n": 1, "exp_r": -3.46}, False, min_n=30, min_exp_r=0.0)
    assert obs and "n=1" in reason


def test_gate_exp_r_negativo_bloquea():
    obs, reason = guards.gate_decision({"n": 100, "exp_r": -0.05}, False, min_n=30, min_exp_r=0.0)
    assert obs and "exp_R" in reason


def test_gate_combo_validado_pasa():
    obs, reason = guards.gate_decision({"n": 135, "exp_r": 0.357}, False, min_n=30, min_exp_r=0.0)
    assert not obs and reason is None


# ------------------------------ señal vencida ------------------------------
def test_senal_fresca_pasa_y_vieja_no():
    now = 1_900_000_000_000
    assert guards.is_fresh(now - 5 * 60_000, now, max_age_min=30)
    assert not guards.is_fresh(now - 31 * 60_000, now, max_age_min=30)


# ------------------------------ piso de stop ------------------------------
def test_stop_pct_piso():
    assert guards.stop_pct_ok(0.01, min_stop_pct=0.002)      # stop 1% ok
    assert not guards.stop_pct_ok(0.0001, min_stop_pct=0.002)  # stop 0.01% → notional 200×


# ------------------------- régimen de mercado (06-29) -------------------------
def test_regimen_bloquea_largo_en_bajista_y_short_en_alcista():
    assert guards.market_regime_block("long", False) is not None    # trampa alcista
    assert guards.market_regime_block("short", True) is not None     # short contra tendencia
    assert guards.market_regime_block("long", True) is None          # largo con mercado alcista ok
    assert guards.market_regime_block("short", False) is None        # short con mercado bajista ok


def test_regimen_exento_y_desconocido_no_bloquean():
    assert guards.market_regime_block("long", False, exempt=True) is None     # oro descorrelacionado
    assert guards.market_regime_block("long", None) is None                   # sin datos = fail-open
    assert guards.market_regime_block("long", False, enabled=False) is None   # filtro apagado


# ------------------------- costo round-trip en R (06-29) -------------------------
def test_costo_toxico_stops_apretados():
    from oscilion.backtest.costs import DEFAULT_COSTS
    assert DEFAULT_COSTS.round_trip_cost_r(0.0038) > 0.12     # XAU oro: ~0.24R → bloqueado
    assert DEFAULT_COSTS.round_trip_cost_r(0.034) < 0.12      # AVAX stop ancho: ~0.03R → pasa
    assert DEFAULT_COSTS.round_trip_cost_r(0.0) == math.inf   # stop 0 = notional infinito


# ------------------------------ veto por símbolo ------------------------------
class _St:
    def __init__(self, position):
        self.position = position


def test_veto_simbolo_capital_bloquea_y_observe_no():
    states = {
        ("TRX", "vwap_anchor"): _St({"side": "long", "observe": False}),
        ("TRX", "break_retest"): _St(None),
        ("BTC", "ema_trend_stack"): _St({"side": "long", "observe": True}),
    }
    assert guards.capital_position_on_symbol(states, "TRX") == "vwap_anchor"
    assert guards.capital_position_on_symbol(states, "BTC") is None   # observe no bloquea
    assert guards.capital_position_on_symbol(states, "DOT") is None


def test_veto_posicion_formato_previo_cuenta_como_capital():
    states = {("TRX", "orb_breakout"): _St({"side": "short"})}  # sin flag observe
    assert guards.capital_position_on_symbol(states, "TRX") == "orb_breakout"


# ------------------------- límites de cartera (Fase B) -------------------------
def _cluster_of(sym, strategy):
    return {"BTC": "majors", "BNB": "majors", "LINK": "majors", "DOT": "majors",
            "TRX": "trx"}.get(sym, sym)


def test_cartera_max_concurrent_bloquea():
    abiertos = [("BTC", "ema"), ("LINK", "orb"), ("TRX", "orb")]
    r = guards.cluster_cap_reason(abiertos, "DOT", "orb", _cluster_of, 3, 2)
    assert r is not None and "max_concurrent" in r


def test_cartera_max_por_cluster_bloquea():
    abiertos = [("BTC", "ema"), ("LINK", "orb")]          # 2 en 'majors'
    r = guards.cluster_cap_reason(abiertos, "DOT", "orb", _cluster_of, 3, 2)
    assert r is not None and "majors" in r
    # pero TRX (otro clúster) sí cabe
    assert guards.cluster_cap_reason(abiertos, "TRX", "orb", _cluster_of, 3, 2) is None


def test_cartera_con_hueco_pasa():
    assert guards.cluster_cap_reason([("BTC", "ema")], "TRX", "orb", _cluster_of, 3, 2) is None
    assert guards.cluster_cap_reason([], "BTC", "ema", _cluster_of, 3, 2) is None


# ------------------------------ freno diario ------------------------------
def test_freno_diario_limite():
    cap = 10_000.0
    assert not guards.daily_loss_hit(-599.0, cap, max_daily_loss=0.06)
    assert guards.daily_loss_hit(-600.0, cap, max_daily_loss=0.06)   # justo −6%
    assert guards.daily_loss_hit(-814.0, cap, max_daily_loss=0.06)   # el primer ciclo
    assert not guards.daily_loss_hit(+100.0, cap, max_daily_loss=0.06)


def test_utc_midnight():
    d = 86_400_000
    assert guards.utc_midnight_ms(5 * d + 123_456) == 5 * d
    assert guards.utc_midnight_ms(5 * d) == 5 * d


# ------------------------------ tp runner (sin TP) ------------------------------
def test_tp_barrier_runner_nunca_dispara():
    assert tp_barrier(None, "long") == math.inf
    assert tp_barrier(None, "short") == -math.inf
    assert tp_barrier(105.0, "long") == 105.0
    # ninguna vela real supera ±inf → hit_tp imposible
    assert not (1e17 >= tp_barrier(None, "long"))
    assert not (-1e17 <= tp_barrier(None, "short"))


def test_estrategias_runner_devuelven_tp_none():
    """tp_r=0 → tp None (nada de 1e18 contaminando sizing/logs)."""
    import numpy as np
    from oscilion.strategies import library as S
    n = 120
    a = lambda v: np.full(n, v, dtype=float)  # noqa: E731
    # contexto que dispara orb_breakout short: rango estrecho previo y cierre debajo
    close = a(100.0); close[-1] = 97.0
    low = a(99.5); high = a(100.5); high[-1] = 100.5; low[-1] = 96.5
    ema9 = a(100.0); ema21 = a(99.0)          # short: 9>21 NO alineado a la baja → fresh ok
    tf = S.TFArrays(ts=np.arange(n) * 3_600_000 + 8 * 3_600_000, open=a(100), high=high,
                    low=low, close=close, volume=a(1), ema9=ema9, ema21=ema21,
                    ema50=a(100), atr=a(1.0), rsi=a(50), vwap=a(100))
    ctx = S.Ctx(sig=tf, sig_tf_h=1, aux={4: S.TFArrays(
        ts=np.arange(n) * 4 * 3_600_000, open=a(100), high=high, low=low, close=close,
        volume=a(1), ema9=a(100), ema21=a(100), ema50=a(200), atr=a(1), rsi=a(50), vwap=a(100))})
    out = S.orb_breakout(ctx, n - 1, {"tp_r": 0.0, "session_filter": False,
                                      "range_max_pct": 0.05, "fresh_gate": False})
    if out is not None:                        # si dispara, el runner va sin TP
        assert out["tp"] is None
    # vwap_anchor con tp_r=0 — camino directo
    out2 = S.vwap_anchor(ctx, n - 1, {"tp_r": 0.0, "fresh_gate": False})
    if out2 is not None:
        assert out2["tp"] is None
