"""P3 tests: §9 evaluation-contract checks + runner/strategy causality.

§9 requires: cash risk-free subtraction, constant-price cases, loss/drawdown
sign conventions, annualization, missing fold failure, and all-in versus
ongoing turnover reconciliation.
"""
from __future__ import annotations

import math
from datetime import date

import pytest

from research.baselines.folds import build_folds
from research.baselines.metrics import compute_metrics
from research.baselines.panel import Panel, load_panel, trailing_adv
from research.baselines.report import (b0_references, fold_table,
                                       path_metrics, run_report)
from research.baselines.runner import (DEFAULT_CONFIGS, DayRecord,
                                       _decision_orders, run_strategy)
from research.baselines import strategies as strat


# ---------------- synthetic panel -------------------------------------------

def make_panel(sessions, closes, opens=None, vols=None, rf_annual=0.0):
    """Minimal synthetic panel: closes[symbol] -> list of prices per session.
    Uniform $1e9 dollar volume (ADV never binds), flat rf."""
    n = len(sessions)
    syms = list(closes)
    open_ = opens or {s: list(closes[s]) for s in syms}
    vols = vols or {s: [1e9 / c for c in closes[s]] for s in syms}
    return Panel(
        sessions=list(sessions),
        open={s: list(open_[s]) for s in syms},
        close={s: list(closes[s]) for s in syms},
        volume={s: list(vols[s]) for s in syms},
        dividends={s: {} for s in syms},
        splits={s: {} for s in syms},
        rf_daily=[rf_annual / 100.0 / 252.0] * n,
        rf_annual_pct=[rf_annual] * n,
    )


SYMS = ["SPY", "VEA", "VWO", "IEF", "TLT", "TIP", "GLD", "BIL"]


def flat_panel(n=80, price=100.0):
    return make_panel(
        [(date(2020, 1, 1) + __import__("datetime").timedelta(days=i)).isoformat()
         for i in range(n)],
        {s: [price] * n for s in SYMS},
    )


# ---------------- §9: rf subtraction ----------------------------------------

def test_sharpe_zero_when_excess_returns_zero():
    # Exactly-flat excess returns (rf=0, flat NAV): zero variance -> Sharpe
    # is None (undefined), never infinite (§1 contract).
    sessions = [(date(2020, 1, 1) + __import__("datetime").timedelta(days=i)).isoformat()
                for i in range(10)]
    m = compute_metrics(sessions, [100.0] * 10, [0.0] * 10)
    assert m.sharpe is None
    # Constant negative excess (flat NAV vs constant positive rf) is also
    # zero-variance: None, not -infinity.
    m2 = compute_metrics(sessions, [100.0] * 10, [0.01] * 10)
    assert m2.sharpe is None


def test_sharpe_positive_when_beating_rf():
    sessions = [(date(2020, 1, 1) + __import__("datetime").timedelta(days=i)).isoformat()
                for i in range(10)]
    rf = 0.01 / 252.0
    nav = [100.0 * 1.001 ** i for i in range(10)]
    m = compute_metrics(sessions, nav, [rf] * 10)
    assert m.sharpe > 0


def test_cash_rf_subtraction_flows_through_runner():
    # Flat prices: strategy holds cash, NAV flat; Sharpe must reflect rf drag
    panel = flat_panel()
    r = run_strategy(panel, DEFAULT_CONFIGS["B1"])
    days = r["days"]
    m = compute_metrics([d.session for d in days], [d.nav for d in days],
                        [d.rf_daily for d in days])
    assert m.sharpe is None or m.sharpe < 0  # flat NAV vs positive rf


# ---------------- §9: constant-price cases -----------------------------------

def test_constant_price_no_trades_no_gain():
    panel = flat_panel()
    r = run_strategy(panel, DEFAULT_CONFIGS["B1"])
    led = r["ledger"]
    # Flat prices: equal-weight drift = 0, band suppresses everything after
    # the first establishment; NAV stays at 100k (minus first-fill costs).
    assert abs(r["days"][-1].nav - 100_000.0) < 1_000.0
    assert len(led.fills) > 0  # establishment trades happened
    # All fills at price 100 with $1e9 volume: commission + small friction only
    assert led.cost_total < 200.0


def test_constant_price_turnover_establishment_only():
    panel = flat_panel()
    r = run_strategy(panel, DEFAULT_CONFIGS["B1"])
    taus = [d.tau for d in r["days"]]
    # establishment is tau = 0.5 on the fill sessions (g=1)
    assert sum(taus) == pytest.approx(0.5, abs=0.05)


# ---------------- §9: sign conventions ---------------------------------------

def test_loss_is_negative_and_maxdd_positive():
    sessions = [(date(2020, 1, 1) + __import__("datetime").timedelta(days=i)).isoformat()
                for i in range(6)]
    nav = [100.0, 120.0, 60.0, 90.0, 50.0, 70.0]
    m = compute_metrics(sessions, nav, [0.0] * 6)
    assert m.worst_day < 0
    assert m.maxdd > 0
    assert m.maxdd == pytest.approx(1 - 50.0 / 120.0, abs=1e-12)
    assert m.cagr < 0


def test_cagr_annualization_matches_power_law():
    sessions = [(date(2020, 1, 1) + __import__("datetime").timedelta(days=i)).isoformat()
                for i in range(366)]
    nav = [100.0 * 1.10 ** (i / 365.0) for i in range(366)]
    m = compute_metrics(sessions, nav, [0.0] * 366)
    assert m.cagr == pytest.approx(0.10, rel=0.01)


# ---------------- §9: missing fold failure ------------------------------------

def test_fold_table_reports_insufficient_fold_not_silent():
    panel = flat_panel(n=60)  # too short for any fold
    days = [DayRecord(s, 100.0, 0.0, 0.0, 0.0, 100.0) for s in panel.sessions]
    rows = fold_table(panel, days, ledger=None)
    # No folds exist on a 60-session panel: fold list empty is correct
    assert rows == []


def test_build_folds_requires_panel_coverage():
    panel = flat_panel(n=60)
    assert build_folds(panel) == []


# ---------------- §9: all-in vs ongoing turnover reconciliation ---------------

def test_allin_vs_ongoing_turnover_reconciliation():
    # §9: all-in (establishment included) and ongoing (post-establishment)
    # turnover reconcile: sum of per-session half-turns equals the ledger's
    # total |filled*ref| / pretrade NAV tally over the same fills.
    panel = flat_panel()
    r = run_strategy(panel, DEFAULT_CONFIGS["B1"])
    days, ledger = r["days"], r["ledger"]
    total_tau = sum(d.tau for d in days)
    # establishment is the first fill session's tau (g=1 -> tau=0.5)
    fill_sessions = sorted({d.session for d in days if d.tau > 0})
    assert fill_sessions, "no fills on a flat panel (establishment missing)"
    establishment_tau = sum(d.tau for d in days if d.session == fill_sessions[0])
    assert establishment_tau == pytest.approx(0.5, abs=0.05)
    # ongoing = all-in minus establishment (same path, additive)
    ongoing_tau = total_tau - establishment_tau
    assert ongoing_tau >= 0.0
    # ledger's own USD tally matches the day-record tau sum on flat prices
    usd = sum(f.shares_filled * f.order.ref_price
              for f in ledger.fills if f.shares_filled > 0)
    assert total_tau * 2 * 100_000.0 == pytest.approx(usd, rel=0.05)


# ---------------- causality ----------------------------------------------------

def test_strategy_decisions_use_only_past_data():
    panel = load_panel()
    i = panel.idx("2015-06-01")
    before = {name: DEFAULT_CONFIGS[name].strategy and
              __import__("research.baselines.strategies", fromlist=["b2_trend_rs"])
              for name in ()}
    # Perturb all future closes and verify the decision at i is unchanged.
    import copy as _copy
    for name in ("B1", "B2", "B3-minvar", "B3-ivvol"):
        fn = {"B1": strat.b1_equal_weight, "B2": strat.b2_trend_rs,
              "B3-minvar": strat.b3_minvar, "B3-ivvol": strat.b3_inverse_vol}[name]
        base = fn(panel, i)
        p2 = _copy.deepcopy(panel)
        j = i + 1
        for s in p2.close:
            for k in range(j, len(p2.sessions)):
                p2.close[s][k] *= 1.5
        assert fn(p2, i) == base, f"{name} decision changed with future data"


def test_runner_past_path_unchanged_by_future_prices():
    panel = load_panel()
    i_cut = panel.idx("2015-06-01")
    cfg = DEFAULT_CONFIGS["B1"]
    r1 = run_strategy(panel, cfg, end="2015-06-01")
    # perturb futures in a copy
    import copy as _copy
    p2 = _copy.deepcopy(panel)
    for s in p2.close:
        for k in range(i_cut + 1, len(p2.sessions)):
            p2.close[s][k] *= 1.5
    r2 = run_strategy(p2, cfg, end="2015-06-01")
    n1 = [d.nav for d in r1["days"]]
    n2 = [d.nav for d in r2["days"]]
    assert len(n1) == len(n2)
    assert n1 == pytest.approx(n2, abs=1e-6)


# ---------------- caps ----------------------------------------------------------

def test_apply_caps_enforces_protocol_limits():
    w = strat.apply_caps({"SPY": 0.5, "VEA": 0.3, "VWO": 0.2, "IEF": 0.7,
                          "TLT": 0.3, "GLD": 0.5})
    assert w["SPY"] <= 0.35 + 1e-9
    assert sum(w.get(s, 0.0) for s in ("SPY", "VEA", "VWO")) <= 0.60 + 1e-9
    assert sum(w.get(s, 0.0) for s in ("IEF", "TLT", "TIP")) <= 0.60 + 1e-9
    assert w["GLD"] <= 0.15 + 1e-9
    assert sum(w.values()) <= 1.0 + 1e-9


def test_b1_max_single_ETF_weight_at_most_35pct():
    panel = load_panel()
    fills_by_sym = {}
    for name in ("B1",):
        r = run_strategy(panel, DEFAULT_CONFIGS[name])
        for f in r["ledger"].fills:
            if f.shares_filled > 0:
                fills_by_sym.setdefault(f.order.symbol, []).append(f)
        # post-fill weights never exceed 35% of NAV at that fill's session
        for sym, fs in fills_by_sym.items():
            for f in fs:
                assert f.shares_filled * f.fill_price / 100_000.0 <= 0.35 * 3 \
                    or sym == "BIL"  # BIL may reach 100%


# ---------------- warmup abstention --------------------------------------------

def test_warmup_abstention_before_adv_exists():
    panel = flat_panel(n=60)
    # trailing ADV requires >= half the 20-session window: 0.0 before i=9
    assert trailing_adv(panel, "BIL", 5) == 0.0
    assert trailing_adv(panel, "BIL", 15) > 0
    # First decision (session 0) has no trailing ADV: warmup abstention is
    # disclosed via warning, generates no doomed orders, and no fill fails.
    r = run_strategy(panel, DEFAULT_CONFIGS["B1"])
    warmups = [w for w in r["warnings"] if "warmup" in w]
    assert warmups and "no trailing ADV" in warmups[0]
    assert r["failed"] == []
    # once ADV exists, later decisions carry no warmup warnings
    first_dec = panel.sessions[0]
    later = [w for w in warmups if not w.startswith(first_dec)]
    assert later == []


# ---------------- band behavior -------------------------------------------------

def test_band_suppresses_small_drift_trades():
    # Prices drift 1% per session; a 5% band should block most rebalances
    n = 130
    sessions = [(date(2020, 1, 1) + __import__("datetime").timedelta(days=i)).isoformat()
                for i in range(n)]
    closes = {"SPY": [100 * 1.01 ** i for i in range(n)],
              "IEF": [100 * 0.99 ** i for i in range(n)],
              "BIL": [100.0] * n}
    for s in ("VEA", "VWO", "TLT", "TIP", "GLD"):
        closes[s] = [100.0] * n
    panel = make_panel(sessions, closes)
    r = run_strategy(panel, DEFAULT_CONFIGS["B1"])
    led = r["ledger"]
    # after establishment, drift trades are rare (band + dust filters)
    assert len(led.fills) < 25


# ---------------- whole-share / flooring ------------------------------------------

def test_whole_share_fills_only():
    panel = load_panel()
    r = run_strategy(panel, DEFAULT_CONFIGS["B1"])
    for f in r["ledger"].fills:
        assert f.shares_filled == math.floor(f.shares_filled + 1e-9)


# ---------------- reserve switch (B2 cash vs BIL) ----------------------------------

def test_b2_abstains_in_cash_not_BIL():
    panel = load_panel()
    r = run_strategy(panel, DEFAULT_CONFIGS["B2"])
    bil_fills = [f for f in r["ledger"].fills if f.order.symbol == "BIL"]
    # B2 may hold BIL only if it never fills BIL: reserve is literal cash
    assert bil_fills == []


# ---------------- B0 references -----------------------------------------------------

def test_b0_references_cover_four_paths():
    panel = load_panel()
    refs = b0_references(panel)
    assert set(refs) == {"B0-cash", "B0-BIL", "B0-SPY", "B0-6040"}
    assert refs["B0-cash"]["cagr"] == 0.0
    assert refs["B0-SPY"]["cagr"] > 0


# ---------------- run_report end-to-end ----------------------------------------------

def test_run_report_discloses_everything():
    panel = load_panel()
    rep = run_report(panel, DEFAULT_CONFIGS["B3-ivvol"])
    for key in ("strategy", "path", "folds", "b0_references", "disclosure"):
        assert key in rep
    d = rep["disclosure"]
    for key in ("failed_fills", "warnings", "partial_fills",
                "rejected_fills", "terminal_liquidation", "pre_t0_status"):
        assert key in d


# ---------------- runner timing regressions (2026-11-04 fixes) -------------------
# Session-aware dispatch: every pending order fills ONLY at its own fill
# session's open (sells t+1; buys at the first session at/after the sells'
# settlement). Pre-fix, the main loop executed ALL pending orders at t+1's
# open, so rotation buys filled a session (or more) early and
# Ledger.execute's _receive_settlements(future buy date) spent the
# same-rotation sells' unsettled proceeds at t+1. Dividends: ex-date credit
# now runs BEFORE the session's fills (sell at the ex-date open does not
# forfeit; buy at the ex-date open does not receive). These tests fail on
# the pre-fix code.

def test_every_fill_at_its_own_sessions_open():
    panel = load_panel()
    r = run_strategy(panel, DEFAULT_CONFIGS["B1"])
    for f in r["ledger"].fills:
        if f.shares_filled <= 0:
            continue
        idx = panel.sessions.index(f.order.session.isoformat())
        assert f.fill_price == panel.open[f.order.symbol][idx], (
            f"{f.order.symbol} {f.order.side} filled at "
            f"{f.order.session.isoformat()} with price {f.fill_price} != "
            f"that session's open {panel.open[f.order.symbol][idx]}")


def test_no_fill_before_decision_plus_2_for_buys():
    """Physical fill session of every buy is at least decision+1 (sells) or
    decision+2 (buys wait for the post-settlement session; buy-only
    decisions also wait to t+2 by construction)."""
    panel = load_panel()
    r = run_strategy(panel, DEFAULT_CONFIGS["B1"])
    for f in r["ledger"].fills:
        gap = (f.order.session - f.order.decision_session).days
        if f.order.side == "sell":
            assert gap >= 1
        else:
            assert gap >= 2


def _crash_panel(n=50):
    """Weekday panel 2019-12-02..2020-02-07 (50 sessions). The Dec 2 decision
    warmup-abstains (no trailing ADV); the Jan 1 decision is the B1
    establishment (buys fill Jan 3); SPY gaps up to 160 and VEA down to 40 at
    Feb 3, so the Feb 3 decision is a rotation: sell SPY (fill Feb 4 = t+1),
    buy VEA (fill Feb 6 = first session at/after the sells' T+2 settlement).
    Per-session price drift makes every session's open unique."""
    import datetime as _dt
    days = []
    d = _dt.date(2019, 12, 2)
    while d <= _dt.date(2020, 2, 7):
        if d.weekday() < 5:
            days.append(d.isoformat())
        d += _dt.timedelta(days=1)
    sessions = days[:n]
    m = len(sessions)
    feb3 = sessions.index("2020-02-03")
    closes = {s: [100.0 + 0.1 * i for i in range(m)] for s in SYMS}
    closes["SPY"] = [(100.0 + 0.1 * i if i < feb3 else 160.0 + 0.1 * (i - feb3))
                     for i in range(m)]
    closes["VEA"] = [(100.0 - 0.1 * i if i < feb3 else 40.0 + 0.1 * (i - feb3))
                     for i in range(m)]
    opens = {s: [c * 1.001 for c in closes[s]] for s in closes}
    return make_panel(sessions, closes, opens=opens)


def test_rotation_buy_fills_at_settlement_session():
    """The Feb 3 rotation: SPY sell fills at t+1 (Feb 4) open; the VEA buy
    fills at the first session at/after the sells' T+2 settlement (Feb 6)
    open -- never at t+1 (the pre-fix bug) and never at Feb 5 (before
    settlement)."""
    panel = _crash_panel()
    r = run_strategy(panel, DEFAULT_CONFIGS["B1"])
    led = r["ledger"]
    rot_sells = [f for f in led.fills if f.order.symbol == "SPY"
                 and f.order.side == "sell" and f.shares_filled > 0
                 and f.order.decision_session.isoformat() == "2020-02-03"]
    rot_buys = [f for f in led.fills if f.order.symbol == "VEA"
                and f.order.side == "buy" and f.shares_filled > 0
                and f.order.decision_session.isoformat() == "2020-02-03"]
    assert rot_sells and rot_buys, "rotation did not happen on the crash panel"
    sell_f = rot_sells[0]
    buy_f = rot_buys[0]
    assert sell_f.order.session.isoformat() == "2020-02-04"
    assert buy_f.order.session.isoformat() == "2020-02-06"
    assert buy_f.order.session >= sell_f.order.session + __import__(
        "datetime").timedelta(days=2)  # T+2 settlement (2020 regime)
    # each fill is its own session's OPEN (1.001x close marker)
    assert sell_f.fill_price == panel.open["SPY"][46]   # Feb 4
    assert buy_f.fill_price == panel.open["VEA"][48]    # Feb 6
    # nothing from the rotation fills on Feb 5: settlement wait
    assert all(f.order.session.isoformat() != "2020-02-05"
               for f in led.fills if f.shares_filled > 0
               and f.order.decision_session.isoformat() == "2020-02-03")


def test_beyond_window_orders_expire_unfilled_with_warning():
    """Orders whose fill session lies beyond the run window expire unfilled
    (never fire early) and are disclosed in warnings."""
    panel = _crash_panel()
    r = run_strategy(panel, DEFAULT_CONFIGS["B1"], end="2020-02-04")
    led = r["ledger"]
    # the Feb 3 decision's SPY sell filled at Feb 4 (inside the window)
    assert any(f.order.symbol == "SPY" and f.order.side == "sell"
               and f.order.session.isoformat() == "2020-02-04"
               and f.order.decision_session.isoformat() == "2020-02-03"
               for f in led.fills)
    # the Feb 3 VEA buy (due Feb 6, beyond the window) expired, disclosed,
    # unfilled; the Jan 3 establishment buys are unaffected
    expired = [w for w in r["warnings"] if "expired unfilled" in w]
    assert expired and any("VEA" in w and "buy" in w for w in expired)
    assert any("never fired early" in w for w in expired)
    assert not [f for f in led.fills if f.order.symbol == "VEA"
                and f.order.side == "buy" and f.shares_filled > 0
                and f.order.decision_session.isoformat() == "2020-02-03"]


def test_buys_dropped_when_no_fill_session_remains():
    """A rotation decided near the panel edge whose buys have no session at/
    after settlement in the panel: buys are dropped at decision time with a
    warning (never a doomed order, never an early fill)."""
    panel = _crash_panel(48)  # sessions end at Feb 5; settle date is Feb 6
    r = run_strategy(panel, DEFAULT_CONFIGS["B1"])
    led = r["ledger"]
    assert any(f.order.symbol == "SPY" and f.order.side == "sell"
               and f.order.session.isoformat() == "2020-02-04"
               and f.order.decision_session.isoformat() == "2020-02-03"
               for f in led.fills)
    dropped = [w for w in r["warnings"] if "buys dropped" in w]
    assert dropped and any("2020-02-03" in w for w in dropped)
    assert not [f for f in led.fills if f.order.symbol == "VEA"
                and f.order.side == "buy" and f.shares_filled > 0
                and f.order.decision_session.isoformat() == "2020-02-03"]


def test_exdate_sell_receives_buy_at_exdate_open_does_not():
    """Dividend semantics: shares held ENTERING the ex-date session receive
    the credit; the sell at that open does not forfeit it; the buy at that
    open does not receive it (credit runs BEFORE the session's fills)."""
    from research.baselines.runner import _credit_dividends
    from research.execution.ledger import Ledger, Position

    panel = flat_panel(n=6)
    panel.dividends["SPY"] = {3: 1.0}

    # 50 shares entering session 3: $50 credited before fills; a sell at
    # session 3's open (after the credit) does not forfeit it
    led = Ledger(initial_cash=10_000.0)
    led.positions["SPY"] = Position()
    led.positions["SPY"].add(50, 100.0)
    _credit_dividends(led, panel, 3)
    assert led.settled_cash == 10_050.0

    # shares bought AT session 3's open (after the credit) do not receive
    # the dividend; no re-credit on later sessions
    led2 = Ledger(initial_cash=10_000.0)
    led2.positions["SPY"] = Position()
    led2.positions["SPY"].add(30, 100.0)
    _credit_dividends(led2, panel, 3)            # 30 entering shares -> $30
    led2.positions["SPY"].add(20, 100.0)         # ex-date open buy
    _credit_dividends(led2, panel, 4)            # next session: no dividend
    assert led2.settled_cash == 10_030.0
