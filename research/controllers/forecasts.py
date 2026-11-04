"""P4 frozen forecast module (plan §4 interface 2, §5 H1/H2 inputs).

One module feeds ALL controller arms (H1 ablation requirement: identical
forecasts across arms; only the hold/trade rule differs). Frozen at P4 start;
no post-hoc tuning against folds.

Inputs to every estimate: panel indices <= i only (decision after close of
session i). Dividends enter the trend signals via per-session total-return
factors (ex-date entitlement, split-adjusted amounts -- P1-verified semantics).

Components (frozen):
- `total_return_factor(panel, symbol, i)`: TR index level at session i
  (close * cumulative dividend factor). Cachable via `tr_index()`.
- `trend_forecast(panel, i)`: per-symbol expected 63-session excess return
  from a 63/126/252-session trend ensemble, scaled to the 63-session horizon,
  minus the 63-session risk-free drift. Long-only scores (negative -> 0
  expected excess; the trend family maps negative views to reduced holdings,
  plan §4). No ranking cut: caps (apply_caps) do the constraint work.
- `cov_shrinkage(panel, i)`: 252-session close-to-close shrinkage covariance
  of the 7 non-reserve symbols (reuses the P3 B3 machinery; dividends
  excluded from the variance proxy, disclosed there).
- `blocked_validation_error(panel, i)`: trailing blocked forecast-error std
  per symbol for the 63-session horizon: 21-session blocks; within each block
  a one-sided-ahead forecast made at the block's start is compared to realized
  TR over the following 63 sessions; trailing 8 blocks. Index <= i only
  (realized legs need j + 63 <= i).
- `mean_variance_targets(panel, i, risk_aversion)`: capped long-only
  mean-variance weights from the frozen mu/cov (used by B4 and every
  H1/H2 arm so targets are identical across arms).

All pre-T0 intervals are development history (data-exposure registry).
"""
from __future__ import annotations

import math

from research.baselines import strategies as strat
from research.baselines.panel import Panel

HORIZON = 63                      # decision horizon (sessions)
TREND_WINDOWS = (63, 126, 252)    # frozen trend ensemble windows
COV_LOOKBACK = 252                # covariance lookback (matches P3 B3)
BLOCK_LEN = 21                    # blocked-validation block length
N_BLOCKS = 8                      # trailing blocks in the error estimate
ERROR_DECAY = 0.94                # per-block EW weight on recent errors


def _tr_factor_step(panel: Panel, sym: str, j: int) -> float:
    """Per-session total-return factor at j: price return plus dividend yield
    on the ex-date (P1 semantics: holder entering the session is entitled)."""
    c = panel.close[sym]
    f = c[j] / c[j - 1]
    div = panel.dividends.get(sym, {}).get(j)
    if div:
        f += div / c[j - 1]
    return f


def tr_index(panel: Panel, sym: str, i: int, start: int | None = None) -> list:
    """Total-return index levels for sessions [start..i] (default from 1),
    base 1.0 at session `start`. Level_{j} = Level_{j-1} * factor_j."""
    lo = 1 if start is None else start
    if i < lo:
        return []
    lvl = [1.0]
    for j in range(lo, i + 1):
        lvl.append(lvl[-1] * _tr_factor_step(panel, sym, j))
    return lvl


def _tr_return(panel: Panel, sym: str, i: int, window: int) -> float:
    """Total return over `window` sessions ending at i (inclusive), dividends
    reinvested at the ex-date close (same per-session factors as `tr_index`).
    NaN if insufficient history."""
    if i - window < 0:
        return float("nan")
    f = 1.0
    for j in range(i - window + 1, i + 1):
        f *= _tr_factor_step(panel, sym, j)
    return f - 1.0


def _window_forecast(panel: Panel, sym: str, i: int, window: int) -> float:
    """Per-session expected excess return from one trend window, linearly
    de-trended against the risk-free drift over the same window."""
    tr = _tr_return(panel, sym, i, window)
    if not (tr == tr):  # NaN guard (insufficient history)
        return float("nan")
    rf = 1.0
    for j in range(i - window + 1, i + 1):
        rf *= 1.0 + panel.rf_daily[j]
    excess_total = (1.0 + tr) / rf - 1.0
    return excess_total / window


def trend_forecast(panel: Panel, i: int) -> dict:
    """Frozen 63/126/252 trend ensemble, per-session expected excess return,
    scaled to the HORIZON-session horizon. Available windows averaged (a
    symbol needs >= 63 sessions of history); fewer than 2 windows -> the
    available one; none -> excluded. Long-only: negative ensemble means 0
    expected excess (reduced holdings/cash, plan §4 trend family)."""
    out = {}
    for sym in strat.NON_RESERVE:
        per = [w for w in (_window_forecast(panel, sym, i, win)
                           for win in TREND_WINDOWS)
               if w == w]
        if not per:
            continue
        mu_daily = sum(per) / len(per)
        out[sym] = max(0.0, mu_daily * HORIZON)
    return out


def _daily_returns_matrix(panel: Panel, i: int, lookback: int) -> tuple:
    """(rows, syms): close-to-close simple returns ending at i for the 7
    non-reserve symbols; dividends excluded (P3 B3 proxy, disclosed).
    None if insufficient history."""
    syms = list(strat.NON_RESERVE)
    if i - lookback < 0:
        return None, syms
    rows = []
    for j in range(i - lookback + 1, i + 1):
        rows.append([panel.close[s][j] / panel.close[s][j - 1] - 1.0 for s in syms])
    return rows, syms


def cov_shrinkage(panel: Panel, i: int, lookback: int = COV_LOOKBACK):
    """252-session shrinkage covariance (P3 B3 machinery, shrink=0.25) as a
    {(s1, s2): cov} dict over the 7 non-reserve symbols. None if insufficient
    history."""
    rows, syms = _daily_returns_matrix(panel, i, lookback)
    if rows is None:
        return None
    C = strat._cov_shrinkage(rows, syms)
    return {(a, b): float(C[k1][k2])
            for k1, a in enumerate(syms) for k2, b in enumerate(syms)}


def _block_forecast_error(panel: Panel, sym: str, block_start: int) -> float | None:
    """One blocked-validation error: forecast made after close of
    `block_start` (trend ensemble), realized TR excess over the following
    HORIZON sessions vs the risk-free path. None if the realized leg is not
    fully inside [.., i] (caller enforces) or history is short."""
    i = block_start
    per = [w for w in (_window_forecast(panel, sym, i, win)
                       for win in TREND_WINDOWS)
           if w == w]
    if not per:
        return None
    pred = max(0.0, sum(per) / len(per) * HORIZON)
    tr = _tr_return(panel, sym, i + HORIZON, HORIZON)
    if not (tr == tr):
        return None
    rf = 1.0
    for j in range(i + 1, i + HORIZON + 1):
        rf *= 1.0 + panel.rf_daily[j]
    realized = (1.0 + tr) / rf - 1.0
    return realized - pred


def blocked_validation_error(panel: Panel, i: int) -> dict:
    """Trailing blocked forecast-error std per symbol (63-session horizon):
    21-session blocks, trailing 8, EW-weighted (decay 0.94, recent-heavy),
    sample std of the weighted mean-zero deviations. None for symbols whose
    most recent block error cannot be computed with data <= i (staleness
    surfaces explicitly)."""
    out = {}
    for sym in strat.NON_RESERVE:
        errs = []
        for b in range(N_BLOCKS):
            start = i - HORIZON - b * BLOCK_LEN
            if start < 0:
                break
            e = _block_forecast_error(panel, sym, start)
            if e is None:
                break
            errs.append(e)
        if len(errs) < 2:
            out[sym] = None
            continue
        wts = [ERROR_DECAY ** k for k in range(len(errs))]
        tot = sum(wts)
        mean = sum(w * e for w, e in zip(wts, errs)) / tot
        var = sum(w * (e - mean) ** 2 for w, e in zip(wts, errs)) / tot
        out[sym] = math.sqrt(max(var, 0.0))
    return out


def mean_variance_targets(panel: Panel, i: int,
                          risk_aversion: float = 4.0) -> dict:
    """Capped long-only mean-variance weights from the frozen mu/cov:
    maximize mu'w - (ra/2) w'Cw over w >= 0 with protocol caps. Closed-form
    per-scheme projection is not reliable under caps, so use a small
    projected-gradient ascent (deterministic, fixed 200 iterations,
    step 1/(ra*max_diag), projection = apply_caps + renormalize to <= 1).
    Residual is the reserve's (runner). None-history -> {} (abstain month).

    mu comes from `trend_forecast` (63-session horizon); C from
    `cov_shrinkage` (daily). mu is horizon-total, C is daily: scale mu to
    per-session (mu/HORIZON) so the ra units are per-session variance."""
    mu = trend_forecast(panel, i)
    C = cov_shrinkage(panel, i)
    if not mu or C is None:
        return {}
    syms = [s for s in strat.NON_RESERVE if s in mu]
    if not syms:
        return {}
    import numpy as np
    mu_vec = np.array([mu[s] / HORIZON for s in syms])
    Cm = np.array([[C[(a, b)] for b in syms] for a in syms])
    dmax = float(np.max(np.diag(Cm)))
    if dmax <= 0:
        return {}
    step = 1.0 / (risk_aversion * dmax)
    w = np.full(len(syms), 1.0 / len(syms))
    for _ in range(200):
        grad = mu_vec - risk_aversion * (Cm @ w)
        w = np.maximum(w + step * grad, 0.0)
        d = {s: float(v) for s, v in zip(syms, w)}
        d = strat.apply_caps(d)
        w = np.array([d.get(s, 0.0) for s in syms])
    return {s: float(v) for s, v in zip(syms, w) if v >= 1e-9}
