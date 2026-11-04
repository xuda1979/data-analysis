"""P4a forecast-module tests: causality, TR consistency, staleness, caps,
determinism, long-only mapping. All use indices <= i only."""
from __future__ import annotations

import copy
import math
from datetime import date, timedelta

import pytest

from research.baselines import strategies as strat
from research.baselines.panel import load_panel
from research.controllers import forecasts as fc


def _synthetic_panel(n=400, price=100.0, seed=7):
    """Flat-price panel with \$1e9 dollar volume, one dividend on SPY."""
    from research.baselines.panel import Panel
    sessions = [(date(2020, 1, 1) + timedelta(days=i)).isoformat() for i in range(n)]
    syms = ["SPY", "VEA", "VWO", "IEF", "TLT", "TIP", "GLD", "BIL"]
    closes = {s: [price] * n for s in syms}
    dividends = {s: {} for s in syms}
    dividends["SPY"] = {n // 2: 1.0}
    return Panel(
        sessions=sessions,
        open={s: list(closes[s]) for s in syms},
        close=closes,
        volume={s: [1e9 / price] * n for s in syms},
        dividends=dividends,
        splits={s: {} for s in syms},
        rf_daily=[0.0] * n,
        rf_annual_pct=[0.0] * n,
    )


def test_causality_all_forecast_fns():
    panel = load_panel()
    i = panel.idx("2015-06-01")
    base = (fc.trend_forecast(panel, i),
            fc.blocked_validation_error(panel, i),
            fc.mean_variance_targets(panel, i),
            fc.cov_shrinkage(panel, i))
    p2 = copy.deepcopy(panel)
    for s in p2.close:
        for k in range(i + 1, len(p2.sessions)):
            p2.close[s][k] *= 1.5
            p2.open[s][k] *= 1.5
            p2.volume[s][k] *= 0.5
    for s in p2.dividends:
        p2.dividends[s] = {j: v for j, v in p2.dividends[s].items() if j <= i}
    pert = (fc.trend_forecast(p2, i), fc.blocked_validation_error(p2, i),
            fc.mean_variance_targets(p2, i), fc.cov_shrinkage(p2, i))
    assert base[0] == pert[0]
    assert base[1] == pert[1]
    assert base[2] == pert[2]
    assert base[3] == pert[3]


def test_tr_index_matches_tr_return():
    panel = load_panel()
    i = panel.idx("2015-06-01")
    for sym in ("SPY", "TLT"):
        lvl = fc.tr_index(panel, sym, i)
        w = 126
        from_index = lvl[-1] / lvl[len(lvl) - 1 - w] - 1.0
        direct = fc._tr_return(panel, sym, i, w)
        assert from_index == pytest.approx(direct, rel=1e-12)


def test_blocked_validation_error_staleness():
    panel = load_panel()
    early = panel.idx("2007-10-01")
    e = fc.blocked_validation_error(panel, early)
    assert all(v is None for v in e.values())  # not enough realized history
    late = panel.idx("2015-06-01")
    e2 = fc.blocked_validation_error(panel, late)
    assert all(v is not None and v >= 0.0 for v in e2.values())
    # the most recent block forecast is made at i-63 and realized by i:
    # perturbing data after i must not change the error estimate
    p2 = copy.deepcopy(panel)
    for s in p2.close:
        for k in range(late + 1, len(p2.sessions)):
            p2.close[s][k] *= 1.5
    assert fc.blocked_validation_error(p2, late) == e2


def test_long_only_mu_nonnegative():
    panel = load_panel()
    for iso in ("2009-03-02", "2020-03-02", "2022-01-03", "2026-11-03"):
        mu = fc.trend_forecast(panel, panel.idx(iso))
        assert all(v >= 0.0 for v in mu.values())


def test_targets_respect_caps():
    panel = load_panel()
    for iso in ("2013-01-02", "2016-06-01", "2020-07-01"):
        t = fc.mean_variance_targets(panel, panel.idx(iso))
        assert sum(t.values()) <= 1.0 + 1e-9
        for s, v in t.items():
            assert v <= 0.35 + 1e-9
        assert sum(t.get(s, 0.0) for s in strat.EQUITY) <= 0.60 + 1e-9
        assert sum(t.get(s, 0.0) for s in strat.BONDS) <= 0.60 + 1e-9
        assert t.get("GLD", 0.0) <= 0.15 + 1e-9


def test_determinism():
    panel = load_panel()
    i = panel.idx("2020-07-01")
    assert fc.mean_variance_targets(panel, i) == fc.mean_variance_targets(panel, i)
    assert fc.trend_forecast(panel, i) == fc.trend_forecast(panel, i)


def test_dividend_enters_trend_but_flat_prices_give_zero_excess():
    panel = _synthetic_panel()
    n = panel.n()
    i = n - 1  # full history
    mu = fc.trend_forecast(panel, i)
    # flat prices + one dividend: TR positive only via the dividend; rf=0 so
    # ensemble excess is the dividend amortized -- small but positive for SPY
    assert mu["SPY"] > 0.0
    assert mu["VEA"] == 0.0  # no dividend, flat -> exactly zero excess
