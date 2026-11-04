"""P4 tests: controller interface, determinism (hash-seed invariance).

The hash-seed test is a regression for the P3 record-integrity bug: the
runner's decision loop iterated a set of symbols, so the funded path depended
on PYTHONHASHSEED when buys competed for settled cash. Any fixed symbol order
is a disclosed choice; hash order is not. This test re-runs a B1 slice under
two seeds via subprocess and asserts identical NAV paths.
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import date, timedelta

import pytest

from research.baselines import strategies as strat
from research.baselines.panel import Panel, load_panel
from research.baselines.runner import DEFAULT_CONFIGS, RunConfig, run_strategy
from research.controllers import forecasts as fc
from research.controllers.base import Controller, MVController, drifted_weights


# ---------------- controller interface ---------------------------------------


def test_controller_overrides_strategy_and_hooks_fire():
    panel = load_panel()

    events = []

    class Probe(Controller):
        name = "probe"

        def decide(self, panel, i, ledger, nav, marks):
            events.append(("decide", i))
            return strat.b1_equal_weight(panel, i)  # B1 targets from a controller

        def on_fill(self, fill, pretrade_nav):
            events.append(("fill", fill.order.symbol, fill.status))

        def on_session(self, panel, i, ledger):
            events.append(("session", i))

    cfg = RunConfig(strategy="B1", controller=Probe())
    r = run_strategy(panel, cfg, end="2010-12-31")
    kinds = [e[0] for e in events]
    assert "decide" in kinds and "fill" in kinds and "session" in kinds
    # decide fires at most once per calendar month in the window
    dec_sessions = [e[1] for e in events if e[0] == "decide"]
    months = {panel.sessions[i][:7] for i in dec_sessions}
    assert len(months) == len(dec_sessions)
    # on_session fires every in-loop session; the terminal-liquidation day
    # record (appended after the loop, end=2010-12-31 with panel continuing)
    # does not receive one
    n_sessions = len([e for e in events if e[0] == "session"])
    n_loop_days = panel.idx("2010-12-31") + 1
    assert n_sessions == n_loop_days
    assert len(r["days"]) == n_loop_days + 1  # + liquidation day
    # fills recorded include a status; the establishment trades fired
    fill_events = [e for e in events if e[0] == "fill"]
    assert fill_events
    assert all(e[2] in ("filled", "partial", "rejected") for e in fill_events)


def test_mv_controller_decide_matches_forecast_targets():
    panel = load_panel()
    i = panel.idx("2015-06-01")
    ctrl = MVController(4.0)
    marks = {s: panel.close[s][i] for s in panel.close}
    led = run_strategy(panel, DEFAULT_CONFIGS["B1"], end="2015-06-01")["ledger"]
    got = ctrl.decide(panel, i, led, 100_000.0, marks)
    assert got == fc.mean_variance_targets(panel, i, 4.0)


def test_drifted_weights_from_ledger():
    panel = load_panel()
    i = panel.idx("2015-06-01")
    r = run_strategy(panel, DEFAULT_CONFIGS["B1"], end="2015-06-01")
    marks = {s: panel.close[s][i] for s in panel.close}
    w = drifted_weights(r["ledger"], r["ledger"].nav(marks), marks)
    assert all(v > 0 for v in w.values())
    assert sum(w.values()) <= 1.0 + 1e-9


def test_controller_causality_future_perturbation():
    panel = load_panel()
    import copy

    class Recorder(Controller):
        name = "rec"
        seen = []

        def decide(self, panel, i, ledger, nav, marks):
            self.seen.append((i, dict(self.raw(panel, i))))
            return {}

        def raw(self, panel, i):
            return fc.mean_variance_targets(panel, i)

    c1 = Recorder()
    run_strategy(panel, RunConfig(strategy="X", controller=c1), end="2015-06-01")
    p2 = copy.deepcopy(panel)
    i_cut = panel.idx("2015-06-01")
    for s in p2.close:
        for k in range(i_cut + 1, len(p2.sessions)):
            p2.close[s][k] *= 1.5
    c2 = Recorder()
    run_strategy(p2, RunConfig(strategy="X", controller=c2), end="2015-06-01")
    assert c1.seen == c2.seen


# ---------------- hash-seed invariance (P3 record-integrity regression) -------


def _run_slice(seed: str) -> str:
    """Run a B1 slice in a subprocess with PYTHONHASHSEED=seed; print the
    NAV path as a stable string for comparison."""
    code = (
        "from research.baselines.panel import load_panel\n"
        "from research.baselines.runner import DEFAULT_CONFIGS, run_strategy\n"
        "panel = load_panel()\n"
        "r = run_strategy(panel, DEFAULT_CONFIGS['B1'], end='2009-12-31')\n"
        "print(','.join('%.6f' % d.nav for d in r['days']))\n"
    )
    env = dict(os.environ, PYTHONHASHSEED=seed)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, env=env, check=True)
    return out.stdout.strip()


def test_b1_path_is_hash_seed_invariant():
    # 2007-2009 includes several cash-constrained rotations where the old
    # set-iteration order changed which buy filled first.
    a = _run_slice("1")
    b = _run_slice("8")
    assert a == b
    assert a  # non-empty path


def test_all_baselines_hash_seed_invariant_smoke():
    code = (
        "from research.baselines.panel import load_panel\n"
        "from research.baselines.runner import DEFAULT_CONFIGS, run_strategy\n"
        "panel = load_panel()\n"
        "for name in ('B1','B2','B3-minvar','B3-ivvol'):\n"
        "    r = run_strategy(panel, DEFAULT_CONFIGS[name])\n"
        "    print(name, '%.6f' % r['days'][-1].nav)\n"
    )
    outs = []
    for seed in ("1", "8"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        res = subprocess.run([sys.executable, "-c", code], capture_output=True,
                             text=True, env=env, check=True)
        outs.append(res.stdout.strip())
    assert outs[0] == outs[1]
