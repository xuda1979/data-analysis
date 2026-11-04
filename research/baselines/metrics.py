"""P3 metrics: the plan §1 metric contract on a daily marked NAV path.

- r_t = N_t / N_(t-1) - 1 (no external flows)
- CAGR = (N_end/N_start)^(365.25/elapsed_calendar_days) - 1
- MaxDD = max_t(1 - N_t / max_{s<=t} N_s)
- Sharpe = sqrt(252) * mean(r_t - rf_t) / sample_std(r_t - rf_t)
- Annualized half-turn = 252/n_sessions * sum(tau_t), tau = g/2 (§6.4)
- Rolling 252-session half-turn = max over FULL 252-session windows of the
  window sum of tau (no partial-window annualization; None if < 252 sessions)

Zero-variance Sharpe is undefined (None), never infinite. Drawdown is a
positive magnitude; losses are negative returns. sessions[0] carries the
pre-interval mark (nav[0]); returns accrue from index 1.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date


@dataclass
class Metrics:
    n_sessions: int
    start: str
    end: str
    elapsed_years: float
    nav_start: float
    nav_end: float
    cagr: float
    vol: float                      # annualized daily return volatility
    sharpe: float | None
    maxdd: float                    # positive magnitude
    worst_day: float
    turnover_annual_half_turn: float
    rolling_252_half_turn_max: float | None
    cost_total: float
    commission_total: float
    gross_exposure_max: float       # max over marks of risky/NAV
    trades: int
    annual_returns: dict = field(default_factory=dict)   # year -> simple return

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        for k in ("cagr", "vol", "maxdd", "worst_day", "sharpe",
                  "turnover_annual_half_turn", "rolling_252_half_turn_max",
                  "cost_total", "commission_total", "gross_exposure_max"):
            if d.get(k) is not None:
                d[k] = round(d[k], 6)
        return d


def compute_metrics(sessions: list, nav: list, rf_daily: list,
                    tau: list | None = None,
                    gross_exposure: list | None = None,
                    cost_total: float = 0.0, commission_total: float = 0.0,
                    trades: int = 0) -> Metrics:
    """sessions/nav/rf_daily aligned, length n >= 2. tau[i] is session i's
    half-turn (g/2); tau[0] should be 0 (pre-interval mark)."""
    n = len(sessions)
    if n < 2 or len(nav) != n or len(rf_daily) != n:
        raise ValueError("need >= 2 sessions with aligned nav and rf")
    if tau is None:
        tau = [0.0] * n
    if gross_exposure is None:
        gross_exposure = [0.0] * n
    rets = [nav[i] / nav[i - 1] - 1.0 for i in range(1, n)]
    ex = [rets[i - 1] - rf_daily[i] for i in range(1, n)]

    elapsed_days = (date.fromisoformat(sessions[-1])
                    - date.fromisoformat(sessions[0])).days
    elapsed_years = elapsed_days / 365.25
    cagr = (nav[-1] / nav[0]) ** (1.0 / elapsed_years) - 1.0 if nav[-1] > 0 else -1.0

    mean_ex = sum(ex) / len(ex)
    var = sum((x - mean_ex) ** 2 for x in ex) / (len(ex) - 1)
    sd = math.sqrt(var) if var > 0 else 0.0
    sharpe = math.sqrt(252.0) * mean_ex / sd if sd > 0 else None

    mean_r = sum(rets) / len(rets)
    var_r = sum((x - mean_r) ** 2 for x in rets) / (len(rets) - 1)
    vol = math.sqrt(var_r) * math.sqrt(252.0) if var_r > 0 else 0.0

    peak, maxdd = nav[0], 0.0
    for v in nav:
        peak = max(peak, v)
        maxdd = max(maxdd, 1.0 - v / peak)
    worst = min(rets)

    # annualized half-turn: 252/n_sessions * sum(tau) (plan §6.4)
    annual_half = 252.0 / n * sum(tau)

    # rolling 252-session half-turn: full windows only, window sum, no scaling
    roll_max = None
    if n >= 252:
        roll_max = 0.0
        csum = 0.0
        for i in range(n):
            csum += tau[i]
            if i >= 252:
                csum -= tau[i - 252]
            if i >= 251:
                roll_max = max(roll_max, csum)

    annual_returns = {}
    for i in range(1, n):
        y = sessions[i][:4]
        if y not in annual_returns:
            annual_returns[y] = [nav[i - 1], nav[i]]
        annual_returns[y][1] = nav[i]
    annual_returns = {y: v[1] / v[0] - 1.0 for y, v in sorted(annual_returns.items())}

    return Metrics(
        n_sessions=n, start=sessions[0], end=sessions[-1],
        elapsed_years=elapsed_years, nav_start=nav[0], nav_end=nav[-1],
        cagr=cagr, vol=vol, sharpe=sharpe, maxdd=maxdd, worst_day=worst,
        turnover_annual_half_turn=annual_half,
        rolling_252_half_turn_max=roll_max,
        cost_total=cost_total, commission_total=commission_total,
        gross_exposure_max=max(gross_exposure), trades=trades,
        annual_returns=annual_returns,
    )
