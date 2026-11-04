"""P3 baseline strategies B0-B4 (plan §8, protocol "baselines").

Each strategy is a pure function of the panel and the current session index i
(decision made after close of session i): it returns target weights for the
non-reserve symbols. Weights are fractions of NAV. The runner turns weights
into orders from marked drifted shares (plan §6.4: buy-and-hold drift causes
no trades), applies investment caps (protocol caps: 35% per non-cash ETF, 60%
aggregate equity SPY+VEA+VWO, 60% aggregate bond ex-reserve IEF+TLT+TIP, 15%
GLD, BIL <= 100%), and fills the residual into the BIL reserve.

Selection rule: the strongest simple control is selected on INNER development
data (plan §8), never on outer intervals. All functions here use only data at
indices <= i (strictly past/current); this is asserted in tests.

B0 zero-interest cash / equity buy-and-hold / 60-40 are bookkeeping references
(runner paths without a strategy), not candidates.
"""
from __future__ import annotations

import math

from research.baselines.panel import Panel

EQUITY = ("SPY", "VEA", "VWO")
BONDS = ("IEF", "TLT", "TIP")
RESERVE = "BIL"
GOLD = "GLD"
NON_RESERVE = EQUITY + BONDS + (GOLD,)

CAPS = {
    "per_non_cash_ETF": 0.35,
    "aggregate_equity": 0.60,
    "aggregate_bond_ex_short_treasury_reserve": 0.60,
    "gold": 0.15,
    "short_treasury_reserve_ETF_max": 1.00,
}


def apply_caps(w: dict) -> dict:
    """Clip raw target weights (non-reserve symbols) to the protocol's
    investment caps: per-ETF 35%, equity group 60% (proportional renorm inside
    the group), bond group 60%, gold 15%, total risky <= 1.0 (residual is the
    reserve's). Weights < 1e-9 are dropped (no dust orders)."""
    w = {s: max(0.0, float(v)) for s, v in w.items() if s in NON_RESERVE}
    w = {s: min(v, CAPS["per_non_cash_ETF"]) for s, v in w.items()}

    def cap_group(d: dict, keys: tuple, cap: float) -> dict:
        grp = {s: v for s, v in d.items() if s in keys}
        tot = sum(grp.values())
        if tot > cap + 1e-12:
            scale = cap / tot
            d = {s: (v * scale if s in grp else v) for s, v in d.items()}
        return d

    w = cap_group(w, EQUITY, CAPS["aggregate_equity"])
    w = cap_group(w, BONDS, CAPS["aggregate_bond_ex_short_treasury_reserve"])
    w = cap_group(w, (GOLD,), CAPS["gold"])
    tot = sum(w.values())
    if tot > 1.0 + 1e-12:
        w = {s: v / tot for s, v in w.items()}
    return {s: v for s, v in w.items() if v >= 1e-9}


# ---------- B1: capped equal weight, monthly banded rebalance ----------------

def b1_equal_weight(panel: Panel, i: int) -> dict:
    """B1: capped equal weight across the 7 non-reserve ETFs, monthly banded
    rebalance (plan §8). The strategy emits raw equal-weight targets; the band
    rule (runner) gates ordering: a symbol trades only when its drifted
    weight is outside target +/- band."""
    return apply_caps({s: 1.0 / 7.0 for s in NON_RESERVE})


# ---------- B2: fixed 126-session trend/RS, long-only, monthly ---------------

def _trailing_returns(panel: Panel, symbol: str, i: int, window: int) -> float:
    """Total return over `window` sessions ending at i (inclusive), dividends
    reinvested at the ex-date close: close[i]/close[i-window] - 1 plus per-share
    dividends over (i-window, i] divided by close[i-window]. Indices <= i only."""
    if i - window < 0:
        return float("nan")
    c = panel.close[symbol]
    r = c[i] / c[i - window] - 1.0
    divs = panel.dividends.get(symbol, {})
    for j in range(i - window + 1, i + 1):
        if j in divs:
            r += divs[j] / c[i - window]
    return r


def b2_trend_rs(panel: Panel, i: int) -> dict:
    """B2: fixed 126-session trend/relative-strength rule, long-only, monthly;
    reserve when ineligible (plan §8). Frozen mechanical rule: hold a symbol
    when its 126-session total return (dividends included) is positive; equal
    weight among held symbols. No ranking cut beyond the trend filter (keeps
    B2 a transparent slow-signal competitor; hyperparameter-free relative to
    the trial budget). NaN (insufficient history) -> not held."""
    held = [s for s in NON_RESERVE if _trailing_returns(panel, s, i, 126) > 0.0]
    if not held:
        return {}          # all-reserve month (strategy abstention)
    return apply_caps({s: 1.0 / len(held) for s in held})


# ---------- B3: shrinkage min-variance + capped inverse-vol ------------------

def _daily_returns_matrix(panel: Panel, i: int, lookback: int) -> tuple:
    """(rows, syms): close-to-close simple returns over `lookback` sessions
    ending at i for the 7 non-reserve symbols; dividends excluded (proxy
    variance input; disclosed). None if insufficient history. Indices <= i."""
    syms = list(NON_RESERVE)
    if i - lookback < 0:
        return None, syms
    rows = []
    for j in range(i - lookback + 1, i + 1):
        rows.append([panel.close[s][j] / panel.close[s][j - 1] - 1.0 for s in syms])
    return rows, syms


def _cov_shrinkage(rows: list, syms: list, shrink: float = 0.25) -> "np.ndarray":
    """Sample covariance shrunk toward the diagonal average variance with a
    frozen constant intensity (disclosed simplification, not tuned)."""
    import numpy as np
    X = np.asarray(rows)
    cov = np.cov(X, rowvar=False, ddof=1)
    diag = float(np.mean(np.diag(cov)))
    return (1.0 - shrink) * cov + shrink * np.eye(cov.shape[0]) * diag


def b3_minvar(panel: Panel, i: int, lookback: int = 252) -> dict:
    """B3: shrinkage minimum-variance allocation, no borrowing (plan §8).
    Closed-form w = C^-1 1 / (1' C^-1 1) on the shrunk 252-session covariance;
    negative weights floored at 0 and renormalized once (frozen rule, no
    iterative optimization; disclosed). Residual to reserve. Indices <= i."""
    import numpy as np
    rows, syms = _daily_returns_matrix(panel, i, lookback)
    if rows is None:
        return {}
    C = _cov_shrinkage(rows, syms)
    try:
        Cinv1 = np.linalg.solve(C, np.ones(len(syms)))
    except np.linalg.LinAlgError:
        return {}
    denom = float(np.sum(Cinv1))
    if denom <= 0:
        return {}
    w = np.maximum(Cinv1 / denom, 0.0)
    if w.sum() <= 0:
        return {}
    w = w / w.sum()
    return apply_caps({s: float(v) for s, v in zip(syms, w) if v > 1e-9})


def b3_inverse_vol(panel: Panel, i: int, lookback: int = 252) -> dict:
    """B3 variant: capped inverse-volatility allocation over the 7 non-reserve
    ETFs from trailing `lookback`-session close-to-close volatility (dividends
    excluded; proxy, disclosed). No borrowing: residual to reserve."""
    rows, syms = _daily_returns_matrix(panel, i, lookback)
    if rows is None:
        return {}
    inv = []
    for t, s in enumerate(syms):
        col = [r[t] for r in rows]
        mean = sum(col) / len(col)
        var = sum((x - mean) ** 2 for x in col) / (len(col) - 1)
        vol = math.sqrt(var)
        inv.append((s, 1.0 / vol if vol > 0 else 0.0))
    tot = sum(v for _, v in inv)
    if tot <= 0:
        return {}
    return apply_caps({s: v / tot for s, v in inv})
