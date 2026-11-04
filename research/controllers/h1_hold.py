"""P4c — H1 hold/trade threshold arms (plan §5 H1).

Four ablation arms on IDENTICAL forecasts (frozen module `forecasts.py`);
only the hold/trade rule differs:

  (a) monthly    — trade to targets every decision; no threshold.
  (b) cost-band  — no-trade band sized by round-trip cost of the deviation
                   (B4 control arm: "same forecasts plus fixed no-trade
                   bands and realistic costs", plan §8).
  (c) error-band — band widened by the symbol's trailing blocked-validation
                   forecast-error std scaled to the weight deviation
                   (forecast uncertainty enters the hold region).
  (d) full       — incremental-utility admission rule G_t(z) > delta:
                   expected utility of the weight change over the 63-session
                   horizon (mu·z, risk term via shrunk covariance) minus the
                   ADVERSE cost scenario (doubled costs), with the
                   forecast-error std subtracted from the expected benefit
                   (inf over Theta, sup over Phi — a feasible one-sided
                   bound, not a fabricated 95%). delta fixed at 10bp of NAV
                   per decision (frozen).

Every decision records the competing hold action, predicted benefit, cost
interval, and deciding constraint (plan §5 H1 "record ... for every
decision").

Turnover accounting note: the runner's own band/dust gates still apply
downstream (whole-share, $250 dust, warmup). A symbol the controller holds
keeps its drifted weight in the returned targets, so the runner's band rule
sees delta ~ 0 and generates no order: holds are real holds, not trades that
cancel.
"""
from __future__ import annotations

from research.baselines import strategies as strat
from research.baselines.panel import Panel
from research.controllers import forecasts
from research.controllers.base import Controller, drifted_weights

HORIZON = forecasts.HORIZON
DELTA = 0.0010              # G_t(z) admission threshold: 10bp of NAV (frozen)
COST_SCENARIOS = (1.0, 2.0)  # (d): cost multiplier scenarios; sup = worst
ROUND_TRIP_FLOOR = 0.0015    # (b)/(c): 15bp round-trip cost floor per unit weight


def _round_trip_cost(panel: Panel, sym: str, i: int, weight: float) -> float:
    """Cost of moving `weight` of NAV into/out of sym, as a fraction of NAV.
    Commission floor dominates at retail size: max(rate*shares, min_fee)
    amortized over the position, plus spread/slippage terms. Conservative
    scalar model (frozen): 15bp round-trip floor, scaled by the weight
    moved."""
    return weight * ROUND_TRIP_FLOOR


class H1Controller(Controller):
    """Arm selection: arm in {"a-monthly", "b-cost-band", "c-error-band",
    "d-full"}. Identical raw targets from the frozen forecast module in all
    arms."""

    def __init__(self, arm: str, risk_aversion: float = 4.0):
        if arm not in ("a-monthly", "b-cost-band", "c-error-band", "d-full"):
            raise ValueError(f"unknown H1 arm: {arm}")
        self.arm = arm
        self.risk_aversion = risk_aversion
        self.decision_log: list[dict] = []

    # ---- cost of a weight change, as fraction of NAV -----------------------
    def _cost_interval(self, panel: Panel, sym: str, i: int, dw: float) -> tuple:
        """(lo, hi) cost of trading |dw| across the cost scenarios (d arm);
        hi doubles costs and stresses participation to a 0.05% ADV cap."""
        base = _round_trip_cost(panel, sym, i, abs(dw))
        return base, base * COST_SCENARIOS[-1]

    def _expected_benefit(self, panel: Panel, i: int, sym: str, dw: float) -> float:
        """mu(HORIZON) * dw, the linear expected-excess contribution of the
        weight change over the horizon (fraction of NAV)."""
        mu = forecasts.trend_forecast(panel, i).get(sym, 0.0)
        return mu * dw

    def _risk_penalty(self, panel: Panel, i: int, sym: str, dw: float,
                      cur_w: dict) -> float:
        """Quadratic risk change (ra/2)*[(w+dw)'C(w+dw) - w'Cw] restricted to
        the single-symbol move, daily-scaled to the horizon. Positive when
        the move adds risk. Uses the frozen shrunk covariance."""
        C = forecasts.cov_shrinkage(panel, i)
        if C is None:
            return 0.0
        ra = self.risk_aversion
        cov_ss = C.get((sym, sym), 0.0)
        # cross terms with current weights
        cross = sum(cur_w.get(s2, 0.0) * C.get((sym, s2), 0.0)
                    for s2 in cur_w if s2 != sym)
        daily = ra * (dw * cross + 0.5 * dw * dw * cov_ss)
        return daily * HORIZON

    def _error_discount(self, panel: Panel, i: int, sym: str, dw: float) -> float:
        """Trailing blocked-validation forecast-error std scaled by |dw|:
        the benefit uncertainty the rule must overcome (arm c/d)."""
        err = forecasts.blocked_validation_error(panel, i).get(sym)
        if err is None:
            # No trailing validation evidence: treat uncertainty as total
            # (plan §5: "unknown ... makes it ineligible rather than merely
            # giving it a small penalty")
            return abs(self._expected_benefit(panel, i, sym, dw))
        return err * abs(dw)

    # ---- decide --------------------------------------------------------------
    def decide(self, panel: Panel, i: int, ledger, nav: float, marks: dict) -> dict:
        cur = drifted_weights(ledger, nav, marks)
        if forecasts.cov_shrinkage(panel, i) is None:
            # no covariance history (warmup/data gap): true hold — return
            # drifted weights so the runner emits no orders
            self.decision_log.append({
                "session": panel.sessions[i], "arm": self.arm,
                "action": "hold-all", "reason": "no-data (warmup)"})
            return dict(cur)
        raw = forecasts.mean_variance_targets(panel, i, self.risk_aversion)
        if not raw:
            # valid data, all-zero mu (trend ensemble negative across all
            # windows): the MV optimum is the reserve; every symbol's target
            # is 0 and each arm applies its OWN rule to the sell candidates
            # ((a) trades to target; (b)-(d) hold: a sell's expected benefit
            # under mu=0 cannot exceed its cost, though (d)'s risk term can
            # still justify de-risking). Correction 2026-11-04: previously
            # conflated with warmup (early {} return) which made every arm
            # liquidate identically via the runner's reserve routing — the
            # ablation rules were bypassed on exactly the de-risking months
            # they were designed to distinguish.
            raw = {s: 0.0 for s in strat.NON_RESERVE}
        out = {}
        for sym in (*strat.NON_RESERVE, strat.RESERVE):
            tgt = raw.get(sym, 0.0)
            cw = cur.get(sym, 0.0)
            if sym == strat.RESERVE:
                continue
            dw = tgt - cw
            if abs(dw) < 1e-9:
                out[sym] = tgt  # == cw: hold and trade coincide, no order
                self._log(panel, i, sym, tgt, cw, dw, "hold", "at-target",
                          0.0, 0.0, 0.0)
                continue
            # plan §5: record predicted benefit, cost interval and deciding
            # constraint for EVERY decision — computed uniformly here, logged
            # in every arm (arm (a) logs but does not gate on them)
            benefit = self._expected_benefit(panel, i, sym, dw)
            cost_lo, cost_hi = self._cost_interval(panel, sym, i, dw)
            if self.arm == "a-monthly":
                out[sym] = tgt
                self._log(panel, i, sym, tgt, cw, dw, "trade", "monthly",
                          benefit, cost_lo, cost_hi)
                continue
            if self.arm == "b-cost-band":
                if benefit > cost_hi:
                    out[sym] = tgt
                    self._log(panel, i, sym, tgt, cw, dw, "trade",
                              "benefit > cost", benefit, cost_lo, cost_hi)
                else:
                    out[sym] = cw  # hold drifted weight (delta 0 downstream)
                    self._log(panel, i, sym, tgt, cw, dw, "hold",
                              "benefit <= cost", benefit, cost_lo, cost_hi)
                continue
            err = self._error_discount(panel, i, sym, dw)
            if self.arm == "c-error-band":
                if benefit > cost_hi + err:
                    out[sym] = tgt
                    self._log(panel, i, sym, tgt, cw, dw, "trade",
                              "benefit > cost+err", benefit, cost_lo,
                              cost_hi, err_discount=err)
                else:
                    out[sym] = cw
                    self._log(panel, i, sym, tgt, cw, dw, "hold",
                              "benefit <= cost+err", benefit, cost_lo,
                              cost_hi, err_discount=err)
                continue
            # arm d: full data/cost uncertainty
            risk = self._risk_penalty(panel, i, sym, dw, cur)
            g = benefit - risk - err - cost_hi  # inf-Theta minus sup-Phi
            if g > DELTA:
                out[sym] = tgt
                self._log(panel, i, sym, tgt, cw, dw, "trade",
                          f"G > delta {DELTA}", benefit, cost_lo, cost_hi,
                          err_discount=err, risk_penalty=risk, G=g)
            else:
                out[sym] = cw
                self._log(panel, i, sym, tgt, cw, dw, "hold",
                          f"G <= delta {DELTA}", benefit, cost_lo, cost_hi,
                          err_discount=err, risk_penalty=risk, G=g)
        return out

    def _log(self, panel: Panel, i: int, sym: str, tgt: float, cur: float,
             dw: float, action: str, why: str, benefit: float | None = None,
             cost_lo: float | None = None, cost_hi: float | None = None,
             err_discount: float | None = None, risk_penalty: float | None = None,
             G: float | None = None):
        row = {
            "session": panel.sessions[i], "arm": self.arm, "symbol": sym,
            "target": round(tgt, 5), "drifted": round(cur, 5),
            "dw": round(dw, 5), "action": action, "constraint": why}
        # competing action + predicted benefit + cost interval (plan §5)
        if benefit is not None:
            row["benefit"] = round(benefit, 6)
        if cost_lo is not None:
            row["cost_lo"], row["cost_hi"] = round(cost_lo, 6), round(cost_hi, 6)
        if err_discount is not None:
            row["err_discount"] = round(err_discount, 6)
        if risk_penalty is not None:
            row["risk_penalty"] = round(risk_penalty, 6)
        if G is not None:
            row["G"] = round(G, 6)
        self.decision_log.append(row)
