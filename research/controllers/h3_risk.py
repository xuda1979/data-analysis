"""P5 — H3 slow risk budgets with asymmetric changes (plan §5 H3).

Four arms on IDENTICAL frozen forecasts (`forecasts.py`), the same B4
cost-band monthly gate, and the same daily risk monitor container; only the
risk-multiplier rule differs:

  static      — m = 1 always (matched-control: same structure, no risk
                scaling; reproduces B4's decisions through this code path)
  vol-only    — m_vol = min(1, target_vol / forecast_vol) from a 20-session
                realized portfolio-vol forecast; no drawdown term
  symmetric   — vol term x drawdown term with symmetric shrink/recover
                (same threshold both directions)
  asymmetric  — the frozen design: m = m_vol * m_dd; drawdown can shrink m
                fast (8% caution / 12% reduction thresholds) and recover
                only gradually (20-session recovery rule), never above 1;
                low volatility must never cause borrowing (m <= 1)

Frozen constants (plan §5 H3): VOL_TARGET = 10% annual; DD_CAUTION = 8%,
DD_REDUCE = 12% (research thresholds); RECOVERY_SESSIONS = 20; monitor
breach tolerance 5% (risky weight above m*R_alloc by more than 5% of NAV
triggers a cut); exposure multiplier min(1, target/forecast).

Monthly decide(): B4's cost-band gate applied to targets scaled by m
(raw targets x m, drifted weights otherwise) — so a shrunken budget holds
the drifted weight unless a trade to the scaled target beats the gate.

Daily risk monitor (`risk_targets`, runner band disabled, sells only):
cuts the risky sleeve to m * R_alloc when the current risky weight exceeds
it by more than 5% of NAV. Returns targets for non-reserve symbols only
(sells); residual routes to the reserve through the runner's standard
reserve routing. Stale data blocks new discretionary orders but never
triggers a blind liquidation (plan §5 H3).

All state is development-history diagnostics until T0.
"""
from __future__ import annotations

import math

from research.baselines import strategies as strat
from research.baselines.panel import Panel
from research.controllers import forecasts
from research.controllers.base import Controller, drifted_weights
from research.controllers.h1_hold import ROUND_TRIP_FLOOR

VOL_TARGET = 0.10          # 10% annual volatility budget (frozen)
DD_CAUTION = 0.08          # 8% drawdown: caution threshold (frozen)
DD_REDUCE = 0.12           # 12% drawdown: reduction threshold (frozen)
RECOVERY_SESSIONS = 20     # gradual recovery horizon (frozen)
BREACH_TOL = 0.05          # monitor fires when risky > m*R_alloc + 5% NAV
VOL_WINDOW = 20            # realized portfolio-vol forecast window
ARMS = ("static", "vol-only", "symmetric", "asymmetric")


def _portfolio_vol_forecast(panel: Panel, i: int, weights: dict,
                            lookback: int = VOL_WINDOW) -> float | None:
    """Annualized portfolio-vol forecast: current risky weights against the
    trailing `lookback`-session daily covariance (shrinkage machinery).
    None when history is insufficient (stale — never zero-filled)."""
    C = forecasts.cov_shrinkage(panel, i, lookback)
    if C is None:
        return None
    syms = [s for s in strat.NON_RESERVE if weights.get(s, 0.0) > 0]
    if not syms:
        return 0.0
    var = sum(weights[a] * weights[b] * C[(a, b)]
              for a in syms for b in syms)
    return math.sqrt(max(var, 0.0)) * math.sqrt(252.0)


class H3Controller(Controller):
    """H3 risk-budget controller. `arm` in ARMS; the monitor is active in
    all arms (static = matched control whose m is always 1)."""

    def __init__(self, arm: str, risk_aversion: float = 4.0):
        if arm not in ARMS:
            raise ValueError(f"unknown H3 arm: {arm}")
        self.arm = arm
        self.risk_aversion = risk_aversion
        self.decision_log: list[dict] = []
        self.risk_log: list[dict] = []
        # drawdown state (asymmetric/symmetric arms)
        self._nav_peak: float | None = None
        self._m_dd: float = 1.0
        self._dd_sessions: int = 0      # sessions spent in drawdown state
        self._risk_alloc: float | None = None   # intended risky weight (monitor base)

    # ---- risk multipliers ---------------------------------------------------
    def _m_vol(self, panel: Panel, i: int, weights: dict) -> float:
        pv = _portfolio_vol_forecast(panel, i, weights)
        if pv is None:
            return 1.0   # stale: blocks nothing (monthly gate still applies)
        if pv <= 0:
            return 1.0
        return min(1.0, VOL_TARGET / pv)

    def _update_drawdown(self, nav: float) -> None:
        """Track the account drawdown and evolve m_dd per the arm's rule.
        Asymmetric: shrink immediately past thresholds, recover gradually
        (a full 0->1 recovery takes RECOVERY_SESSIONS clean sessions);
        symmetric: same thresholds both directions (one session to shrink,
        one to recover)."""
        if self._nav_peak is None or nav > self._nav_peak:
            self._nav_peak = nav
        dd = 1.0 - nav / self._nav_peak if self._nav_peak > 0 else 0.0
        if self.arm == "vol-only" or self.arm == "static":
            return
        if self.arm in ("symmetric", "asymmetric"):
            if dd >= DD_REDUCE:
                self._m_dd = 0.5
                self._dd_sessions = 0
            elif dd >= DD_CAUTION:
                self._m_dd = 0.75
                self._dd_sessions = 0
            elif self._m_dd < 1.0:
                if self.arm == "symmetric":
                    self._m_dd = 1.0   # symmetric: instant recovery
                else:
                    self._dd_sessions += 1
                    if self._dd_sessions >= RECOVERY_SESSIONS:
                        self._m_dd = min(1.0, self._m_dd + 0.25)
                        self._dd_sessions = 0

    def _multiplier(self, panel: Panel, i: int, weights: dict) -> float:
        if self.arm == "static":
            return 1.0
        m_vol = self._m_vol(panel, i, weights)
        if self.arm == "vol-only":
            return m_vol
        return m_vol * self._m_dd   # symmetric/asymmetric (m_dd=1 in symmetric
        # only via instant recovery; shrink still applies)

    # ---- monthly decision ----------------------------------------------------
    def decide(self, panel: Panel, i: int, ledger, nav: float,
               marks: dict) -> dict:
        cur = drifted_weights(ledger, nav, marks)
        self._update_drawdown(nav)
        if forecasts.cov_shrinkage(panel, i) is None:
            # warmup / data gap: true hold (no blind liquidation, plan §5 H3)
            self.decision_log.append({
                "session": panel.sessions[i], "arm": self.arm,
                "action": "hold-all", "reason": "no-data (warmup)"})
            return dict(cur)
        raw = forecasts.mean_variance_targets(panel, i, self.risk_aversion)
        if not raw:
            raw = {s: 0.0 for s in strat.NON_RESERVE}
        m = self._multiplier(panel, i, cur)
        # B4's cost-band gate on the SCALED targets
        out = {}
        for sym in strat.NON_RESERVE:
            tgt = raw.get(sym, 0.0) * m
            cw = cur.get(sym, 0.0)
            dw = tgt - cw
            if abs(dw) < 1e-9:
                out[sym] = tgt
                self.decision_log.append({
                    "session": panel.sessions[i], "arm": self.arm,
                    "symbol": sym, "target": round(tgt, 5),
                    "drifted": round(cw, 5), "dw": round(dw, 5),
                    "action": "hold", "constraint": "at-target", "m": round(m, 4)})
                continue
            mu = forecasts.trend_forecast(panel, i).get(sym, 0.0)
            benefit = mu * dw
            cost = abs(dw) * ROUND_TRIP_FLOOR * 2.0   # doubled-cost scenario
            # de-risking exception (drawdown arms only, m < 1): when the
            # risk budget SHRANK the target below the drifted weight, the
            # cut trades regardless of the benefit-cost gate — risk budgets
            # shrink fast (plan §5 H3 asymmetry). At m == 1 (static arm /
            # unshrunken months) B4's gate applies verbatim, so the static
            # arm reproduces B4 exactly.
            derisk = (self.arm in ("symmetric", "asymmetric")
                      and m < 1.0 and tgt < cw)
            if derisk or benefit > cost:
                out[sym] = tgt
                why = "risk cut" if derisk else "benefit > cost"
            else:
                out[sym] = cw
                why = "benefit <= cost"
            self.decision_log.append({
                "session": panel.sessions[i], "arm": self.arm,
                "symbol": sym, "target": round(tgt, 5),
                "drifted": round(cw, 5), "dw": round(dw, 5),
                "action": "trade" if out[sym] == tgt else "hold",
                "constraint": why, "m": round(m, 4)})
        self._risk_alloc = sum(out.values())   # intended risky weight
        return out

    # ---- daily risk monitor ---------------------------------------------------
    def risk_targets(self, panel: Panel, i: int, ledger) -> dict | None:
        """Called by the runner at every non-decision close (base protocol).
        Fires when the risky weight exceeds m * R_alloc by more than
        BREACH_TOL of NAV; returns scaled-down sells-only targets. R_alloc
        is the risky weight the monthly decision intended: risky drift
        between decisions moves only through prices, so the intended risky
        weight is the LAST decision's risky total; the monitor cuts back to
        m times that, never adds."""
        if self.arm == "static":
            return None
        marks = {sym: panel.close[sym][i] for sym in ledger.positions}
        nav = ledger.nav(marks)
        if nav <= 0 or self._risk_alloc is None:
            return None   # no monthly decision yet: monitor has no base
        cur = drifted_weights(ledger, nav, marks)
        self._update_drawdown(nav)
        risky_w = sum(cur.get(s, 0.0) for s in strat.NON_RESERVE)
        m = self._multiplier(panel, i, cur)
        allowed = m * self._risk_alloc
        if risky_w <= 0:
            return None
        if risky_w <= allowed + BREACH_TOL:
            return None
        scale = allowed / risky_w if risky_w > 0 else 0.0
        targets = {}
        for s in strat.NON_RESERVE:
            cw = cur.get(s, 0.0)
            targets[s] = cw * scale
        self.risk_log.append({
            "session": panel.sessions[i], "arm": self.arm,
            "risky_w": round(risky_w, 5), "allowed": round(allowed, 5),
            "m": round(m, 4), "scale": round(scale, 5)})
        return targets
