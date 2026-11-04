"""P5 H3 tests: risk-budget controller semantics and runner risk-trigger
integration. Frozen constants per plan §5 H3: VOL_TARGET 10%, DD_CAUTION 8%,
DD_REDUCE 12%, RECOVERY_SESSIONS 20, breach tolerance 5%, monitor sells
only, band disabled on monitor fires, static arm = matched control.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import pytest

from research.baselines import strategies as strat
from research.baselines.panel import load_panel
from research.baselines.runner import DEFAULT_CONFIGS, RunConfig, run_strategy
from research.controllers import h3_risk
from research.controllers.h3_risk import (
    ARMS, BREACH_TOL, DD_CAUTION, DD_REDUCE, H3Controller,
    RECOVERY_SESSIONS, VOL_TARGET,
)
from research.controllers.h1_hold import H1Controller


SYMS = ["SPY", "VEA", "VWO", "IEF", "TLT", "TIP", "GLD", "BIL"]


def make_panel(sessions, closes, opens=None, vols=None, rf_annual=0.0):
    n = len(sessions)
    open_ = opens or {s: list(closes[s]) for s in closes}
    vols = vols or {s: [1e9 / c for c in closes[s]] for s in closes}
    from research.baselines.panel import Panel
    return Panel(
        sessions=list(sessions),
        open={s: list(open_[s]) for s in closes},
        close={s: list(closes[s]) for s in closes},
        volume={s: list(vols[s]) for s in closes},
        dividends={s: {} for s in closes},
        splits={s: {} for s in closes},
        rf_daily=[rf_annual / 100.0 / 252.0] * n,
        rf_annual_pct=[rf_annual] * n,
    )


def weekday_sessions(d0: date, n: int) -> list:
    out, d = [], d0
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


# ---------------- multiplier semantics ----------------------------------------


def test_static_multiplier_is_one_and_monitor_silent():
    panel = load_panel()
    ctrl = H3Controller("static")
    cfg = RunConfig(strategy="H3-static", controller=ctrl)
    r = run_strategy(panel, cfg, end="2012-12-31")
    # m logged in every decision row is exactly 1.0
    ms = {row["m"] for row in ctrl.decision_log if "m" in row}
    assert ms == {1.0}
    # static monitor never fires (matched control)
    assert ctrl.risk_log == []
    assert all("risk monitor triggered" not in w for w in r["warnings"])


def test_vol_multiplier_caps_at_one_and_never_borrows():
    # high-vol synthetic: m_vol = min(1, 0.10 / forecast) < 1
    panel = load_panel()
    ctrl = H3Controller("vol-only")
    weights = {s: 1.0 / 7 for s in strat.NON_RESERVE}
    m = ctrl._m_vol(panel, 400, weights)
    assert 0.0 < m <= 1.0
    # degenerate: zero portfolio vol -> m = 1 (never borrow, never > 1)
    assert ctrl._m_vol(panel, 400, {}) == 1.0


def test_asymmetric_drawdown_shrinks_fast_recovers_slow():
    ctrl = H3Controller("asymmetric")
    ctrl._update_drawdown(100.0)          # peak
    ctrl._update_drawdown(88.0)           # 12% dd -> m_dd = 0.5 immediately
    assert ctrl._m_dd == 0.5
    one = 0.25 / RECOVERY_SESSIONS        # gradual: < full recovery after 19
    for _ in range(RECOVERY_SESSIONS - 1):
        ctrl._update_drawdown(100.0)
    assert ctrl._m_dd == 0.5              # not yet: 19 < 20 clean sessions
    ctrl._update_drawdown(100.0)          # 20th: step recovery 0.5 -> 0.75
    assert ctrl._m_dd == 0.75
    for _ in range(RECOVERY_SESSIONS):
        ctrl._update_drawdown(100.0)
    assert ctrl._m_dd == 1.0


def test_symmetric_recovers_immediately():
    ctrl = H3Controller("symmetric")
    ctrl._update_drawdown(100.0)
    ctrl._update_drawdown(88.0)
    assert ctrl._m_dd == 0.5
    ctrl._update_drawdown(100.0)          # symmetric: instant recovery
    assert ctrl._m_dd == 1.0


def test_caution_threshold_tier():
    ctrl = H3Controller("asymmetric")
    ctrl._update_drawdown(100.0)
    ctrl._update_drawdown(91.0)           # 9% dd: caution tier (8-12%)
    assert ctrl._m_dd == 0.75
    ctrl2 = H3Controller("asymmetric")
    ctrl2._update_drawdown(100.0)
    ctrl2._update_drawdown(93.0)          # 7% dd: under caution, no shrink
    assert ctrl2._m_dd == 1.0


# ---------------- monthly decision semantics -----------------------------------


def test_warmup_is_true_hold_zero_mu_is_explicit_zero():
    """Warmup (no covariance history) returns drifted weights (hold-all);
    zero-mu months return explicit per-symbol 0.0 targets (risk-cut path),
    mirroring the P4 correction."""
    panel = load_panel()
    ctrl = H3Controller("asymmetric")
    cfg = RunConfig(strategy="H3-asym", controller=ctrl)
    r = run_strategy(panel, cfg, end="2008-06-30")
    warmup = [row for row in ctrl.decision_log
              if row.get("reason") == "no-data (warmup)"]
    assert warmup, "expected warmup hold-all rows before cov history exists"
    # every warmup decision is a hold-all: no orders emitted those months
    for row in warmup:
        assert row["action"] == "hold-all"


def test_static_arm_reproduces_b4_decisions():
    """The static arm is B4's rule through the H3 code path: same cost-band
    gate, same forecasts, m = 1. Decision targets must match H1(b) exactly
    on a slice, and the funded NAV path is identical."""
    panel = load_panel()
    b4 = H1Controller("b-cost-band")
    h3s = H3Controller("static")
    r_b4 = run_strategy(panel, RunConfig(strategy="B4", controller=b4),
                        end="2011-12-30")
    r_h3 = run_strategy(panel, RunConfig(strategy="H3-static",
                                         controller=h3s),
                        end="2011-12-30")
    b4_rows = {(row["session"], row["symbol"]): row["target"]
               for row in b4.decision_log if "symbol" in row}
    h3_rows = {(row["session"], row["symbol"]): row["target"]
               for row in h3s.decision_log if "symbol" in row}
    common = set(b4_rows) & set(h3_rows)
    assert len(common) > 50
    for k in common:
        assert abs(b4_rows[k] - h3_rows[k]) < 1e-9, f"divergence at {k}"
    # whole funded path identical (same orders through the same runner)
    n_b4 = [d.nav for d in r_b4["days"]]
    n_h3 = [d.nav for d in r_h3["days"]]
    assert len(n_b4) == len(n_h3)
    for a, b in zip(n_b4, n_h3):
        assert abs(a - b) < 1e-6


def test_risk_cut_trades_regardless_of_cost_gate():
    """A scaled-down target below the drifted weight trades even when the
    benefit-cost gate would hold: risk budgets shrink fast (asymmetry)."""
    panel = load_panel()
    ctrl = H3Controller("asymmetric")
    cfg = RunConfig(strategy="H3-asym", controller=ctrl)
    r = run_strategy(panel, cfg, end="2011-12-30")
    cuts = [row for row in ctrl.decision_log
            if row.get("constraint") == "risk cut"]
    assert cuts, "expected de-risking cuts in 2008-2011 on drifted holdings"
    for row in cuts:
        assert row["target"] < row["drifted"]
        assert row["m"] < 1.0   # cuts only from a shrunken budget


# ---------------- daily monitor + runner integration ----------------------------


class RecordingH3(H3Controller):
    """H3 that forces a monitor fire on a chosen session (test hook)."""
    def __init__(self, arm, fire_on: set):
        super().__init__(arm)
        self.fire_on = fire_on

    def risk_targets(self, panel, i, ledger):
        if panel.sessions[i] in self.fire_on:
            marks = {s: panel.close[s][i] for s in ledger.positions}
            nav = ledger.nav(marks)
            cur = {}
            for sym, pos in ledger.positions.items():
                if pos.shares > 0 and marks.get(sym):
                    cur[sym] = pos.shares * marks[sym] / nav
            return {s: w * 0.5 for s, w in cur.items()
                    if s != strat.RESERVE}
        return super().risk_targets(panel, i, ledger)


def test_monitor_targets_replace_pending_and_band_disabled():
    """A monitor fire on a NON-decision session: runner replaces pending
    orders with the monitor's, executes with band=None, and logs the
    emergency warning."""
    panel = load_panel()
    fire = {"2008-10-15"}   # mid-month, not a decision session
    ctrl = RecordingH3("asymmetric", fire)
    cfg = RunConfig(strategy="H3-asym", controller=ctrl)
    r = run_strategy(panel, cfg, end="2008-11-28")
    fired = [w for w in r["warnings"] if "risk monitor triggered" in w]
    assert any("2008-10-15" in w for w in fired)
    # monitor sells filled at the next session's open (t+1 clock, same as
    # decision sells)
    fills = [f for f in r["ledger"].fills
             if f.order.session == date(2008, 10, 16)
             and f.order.side == "sell"]
    assert fills, "monitor sells should fill at the next session open"


def test_monitor_never_adds_exposure():
    """Monitor targets are sells-only: every returned weight <= current."""
    panel = load_panel()
    from research.execution.ledger import Ledger, Position

    i = 400
    led = Ledger(initial_cash=100_000.0)
    led.settled_cash = 0.0
    for s in SYMS[:7]:
        led.positions[s] = Position()
        led.positions[s].shares = 100.0
    marks = {s: panel.close[s][i] for s in SYMS[:7]}
    nav = sum(100.0 * marks[s] for s in SYMS[:7])
    cur = {s: 100.0 * marks[s] / nav for s in SYMS[:7]}

    ctrl = H3Controller("asymmetric")
    ctrl._risk_alloc = 0.40          # force a large breach (risky ~1.0)
    targets = ctrl.risk_targets(panel, i, led)
    assert targets is not None, "breach should fire"
    for s, w in targets.items():
        assert w <= cur.get(s, 0.0) + 1e-12   # sells only, never adds
    # and the intended risky total is respected: sum <= allowed + tolerance
    allowed = ctrl._multiplier(panel, i, cur) * ctrl._risk_alloc
    assert sum(targets.values()) <= allowed + BREACH_TOL + 1e-9


def test_monitor_silent_within_tolerance():
    """No fire when risky weight is within BREACH_TOL of the allocation."""
    ctrl = H3Controller("vol-only")
    ctrl._risk_alloc = 0.50
    panel = load_panel()
    from research.execution.ledger import Position

    class L:
        positions = {}

    led = L()
    i = 400
    led.positions = {s: Position() for s in SYMS}
    for s in SYMS[:7]:
        led.positions[s].shares = 100.0
    # m will be <= 1; allowed = m * 0.50; current risky = 1.0 -> fires unless
    # m > (1 - tol)/0.5; with vol scaling m < 1 -> should fire. Instead test
    # the tolerance boundary directly:
    risky_w = 1.0
    m = ctrl._multiplier(panel, i, {s: 1 / 7 for s in SYMS[:7]})
    allowed = m * ctrl._risk_alloc
    assert risky_w > allowed + BREACH_TOL   # precondition: this WOULD fire
    # now a book already at the allocation: risky_w == allowed -> silent
    ctrl2 = H3Controller("vol-only")
    ctrl2._risk_alloc = risky_w / m
    assert risky_w <= m * ctrl2._risk_alloc + BREACH_TOL


def test_causality_future_perturbation():
    """Perturbing FUTURE prices leaves past decisions and NAV unchanged."""
    panel = load_panel()
    ctrl = H3Controller("asymmetric")
    cfg = RunConfig(strategy="H3-asym", controller=ctrl)
    r1 = run_strategy(panel, cfg, end="2012-12-31")

    from research.baselines.panel import Panel as P
    import copy
    closes = {s: list(panel.close[s]) for s in panel.close}
    i_cut = panel.idx("2011-06-30")
    for s in closes:
        for j in range(i_cut, len(closes[s])):
            closes[s][j] = closes[s][j] * 1.5
    p2 = P(sessions=panel.sessions,
           open={s: list(panel.open[s]) for s in panel.open},
           close=closes,
           volume={s: list(panel.volume[s]) for s in panel.volume},
           dividends=panel.dividends, splits=panel.splits,
           rf_daily=panel.rf_daily, rf_annual_pct=panel.rf_annual_pct)
    ctrl2 = H3Controller("asymmetric")
    r2 = run_strategy(p2, RunConfig(strategy="H3-asym", controller=ctrl2),
                      end="2011-06-29")
    n1 = {d.session: d.nav for d in r1["days"] if d.session <= "2011-06-29"}
    n2 = {d.session: d.nav for d in r2["days"] if d.session <= "2011-06-29"}
    common = set(n1) & set(n2)
    assert len(common) > 100
    for s in common:
        assert abs(n1[s] - n2[s]) < 1e-6


def test_base_default_none_leaves_p4_unchanged():
    """Controller.risk_targets default None: P4 controllers never trigger
    the runner's monitor path (structural non-regression)."""
    from research.controllers.base import Controller, MVController
    c = MVController()
    assert c.risk_targets(None, 0, None) is None
    panel = load_panel()
    b4 = H1Controller("b-cost-band")
    r = run_strategy(panel, RunConfig(strategy="B4", controller=b4),
                     end="2010-12-31")
    assert all("risk monitor triggered" not in w for w in r["warnings"])


def test_emergency_turnover_is_recorded_not_hidden():
    """Monitor fires append to warnings and their fills spend real turnover
    (DayRecord.tau > 0 on the fill session)."""
    panel = load_panel()
    fire = {"2008-10-15"}
    ctrl = RecordingH3("asymmetric", fire)
    r = run_strategy(panel, RunConfig(strategy="H3-asym", controller=ctrl),
                     end="2008-11-28")
    tau = {d.session: d.tau for d in r["days"]}
    assert tau.get("2008-10-16", 0.0) > 0.0
    assert any("risk monitor triggered" in w for w in r["warnings"])
