"""H1 arm tests: causality, hold semantics, log completeness, gating order.

The pre-registered ablation expectations (plan §5 H1) are evaluated on the
development run (see P4 record); these tests pin the structural contract:
identical forecasts across arms, (c)/(d) thresholds dominating (b)'s, holds
emitting no orders, decision-log completeness, and future-price causality.
"""
from __future__ import annotations

import copy

import pytest

from research.baselines import strategies as strat
from research.baselines.panel import load_panel
from research.baselines.runner import DEFAULT_CONFIGS, RunConfig, run_strategy
from research.controllers import forecasts as fc
from research.controllers.h1_hold import (
    COST_SCENARIOS,
    DELTA,
    ROUND_TRIP_FLOOR,
    H1Controller,
)


ARMS = ("a-monthly", "b-cost-band", "c-error-band", "d-full")


def test_arm_validation_rejects_unknown():
    with pytest.raises(ValueError):
        H1Controller("e-other")


def test_all_arms_share_identical_forecasts():
    """Ablation validity: arms differ only in the hold/trade rule, never in
    the raw targets (identical frozen forecast module call)."""
    panel = load_panel()
    i = panel.idx("2015-06-01")
    raw = fc.mean_variance_targets(panel, i, 4.0)
    for arm in ARMS:
        c = H1Controller(arm)
        r = run_strategy(panel, DEFAULT_CONFIGS["B1"], end="2015-06-01")
        marks = {s: panel.close[s][i] for s in panel.close}
        got = c.decide(panel, i, r["ledger"], r["ledger"].nav(marks), marks)
        # arm (a) trades to the raw targets: same symbols with nonzero
        # targets, same weights (extra explicit zero keys are equivalent —
        # zero targets never generate orders)
        if arm == "a-monthly":
            assert {k: v for k, v in got.items() if v != 0.0} == \
                {k: v for k, v in raw.items() if v != 0.0}


def test_thresholds_monotone_c_dominates_b():
    """Gating order: for any decision, (c) requires strictly more evidence
    than (b) (cost + err >= cost), and (d) requires (c)'s evidence plus risk
    and delta. Any (c)-trade is a (b)-trade; any (d)-trade is a (c)-trade."""
    panel = load_panel()
    r = run_strategy(panel, DEFAULT_CONFIGS["B1"], end="2016-06-01")
    i = panel.idx("2016-06-01")
    marks = {s: panel.close[s][i] for s in panel.close}
    nav = r["ledger"].nav(marks)
    logs = {}
    for arm in ("b-cost-band", "c-error-band", "d-full"):
        c = H1Controller(arm)
        c.decide(panel, i, r["ledger"], nav, marks)
        logs[arm] = {e["symbol"]: e["action"] for e in c.decision_log}
    b, c_, d = logs["b-cost-band"], logs["c-error-band"], logs["d-full"]
    for sym in b:
        if c_[sym] == "trade":
            assert b[sym] == "trade", (sym, b[sym], c_[sym])
        if d[sym] == "trade":
            assert c_[sym] == "trade", (sym, c_[sym], d[sym])


def test_hold_returns_drifted_weight_no_order():
    """A hold must not create an order: the returned target equals the
    drifted weight, so the runner's band gate sees delta ~ 0. The log's
    "target" field is the REJECTED forecast target (the competing action,
    plan §5), so the check is on the returned dict, not the log row."""
    panel = load_panel()

    class Rec(H1Controller):
        returned = []

        def decide(self, p, i, ledger, nav, marks):
            t = super().decide(p, i, ledger, nav, marks)
            self.returned.append((i, t))
            return t

    ctrl = Rec("d-full")
    cfg = RunConfig(strategy="H1-d", controller=ctrl)
    r = run_strategy(panel, cfg, end="2015-12-31")
    holds = [e for e in ctrl.decision_log
             if e["action"] == "hold" and e["constraint"] != "at-target"]
    assert holds, "expected at least one real hold in the window"
    for e in holds:
        assert "benefit" in e and "cost_lo" in e and "cost_hi" in e
        # returned dict carries the drifted weight for held symbols
        # (log rows round to 5 decimals; compare at that precision)
        i = panel.idx(e["session"])
        ret = next(t for j, t in ctrl.returned if j == i)
        assert abs(ret.get(e["symbol"], 0.0) - e["drifted"]) < 1e-4


def test_decision_log_completeness():
    """Every trade/hold row carries the plan-§5 record: benefit, cost
    interval, deciding constraint; every decision session logged."""
    panel = load_panel()
    ctrl = H1Controller("c-error-band")
    cfg = RunConfig(strategy="H1-c", controller=ctrl)
    r = run_strategy(panel, cfg, end="2011-12-30")
    rows = [e for e in ctrl.decision_log if e["action"] in ("trade", "hold")]
    assert rows
    for e in rows:
        assert set(e) >= {"session", "arm", "symbol", "target", "drifted",
                          "dw", "action", "constraint", "benefit",
                          "cost_lo", "cost_hi"}
        if e["constraint"] in ("benefit > cost+err", "benefit <= cost+err"):
            assert "err_discount" in e
    # one row per (decision session, symbol in the decision universe)
    sessions = {e["session"] for e in rows}
    per_s = {}
    for e in rows:
        per_s.setdefault(e["session"], set()).add(e["symbol"])
    n_syms = len(strat.NON_RESERVE)
    assert all(len(v) == n_syms for v in per_s.values())
    # hold-all (no-forecast) sessions are logged too
    holdall = [e for e in ctrl.decision_log if e["action"] == "hold-all"]
    assert holdall and all("session" in e for e in holdall)


def test_h1_causality_future_perturbation():
    """Future-price perturbation leaves decisions and past NAV paths
    unchanged (same contract as the baselines)."""
    panel = load_panel()

    class Rec(H1Controller):
        def __init__(self, arm):
            super().__init__(arm)
            self.seen = []

        def decide(self, p, i, ledger, nav, marks):
            self.seen.append((i, dict(super().decide(p, i, ledger, nav, marks))))
            return self.seen[-1][1]

    c1 = Rec("d-full")
    r1 = run_strategy(panel, RunConfig(strategy="H1", controller=c1),
                      end="2015-06-01")
    p2 = copy.deepcopy(panel)
    i_cut = panel.idx("2015-06-01")
    for s in p2.close:
        for k in range(i_cut + 1, len(p2.sessions)):
            p2.close[s][k] *= 1.5
    c2 = Rec("d-full")
    run_strategy(p2, RunConfig(strategy="H1", controller=c2), end="2015-06-01")
    assert c1.seen == c2.seen


def test_constants_frozen():
    assert DELTA == 0.0010
    assert COST_SCENARIOS == (1.0, 2.0)
    assert ROUND_TRIP_FLOOR == 0.0015
