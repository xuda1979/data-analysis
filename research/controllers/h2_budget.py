"""P4d — H2 persistent holdings + rolling turnover budget (plan §5 H2).

Three spending rules on IDENTICAL forecasts (frozen module `forecasts.py`)
drawing from the SAME rolling budget container (equal budgets):

  uniform      — no cost gate; admit candidates in descending expected
                 benefit until the per-decision allowance
                 (B * sessions_since_last_decision / 252) is spent.
  fixed-bands  — H1(b) cost-band gate (benefit > worst-case cost), admit in
                 descending benefit until the remaining budget is spent.
  persistence  — cohort holdings with a live forecast hold without orders
                 (no spend); planned reviews at cohort expiry; hypothesis-
                 failure exits (forecast flipped to zero) are risk-mandated
                 and override the budget (turnover still spent, visible);
                 discretionary entries/top-ups ranked by net benefit per
                 unit expected turnover, admitted while budget remains.

Budget mechanics (frozen): ANNUAL_BUDGET = 1.0 half-turn per 252 sessions.
Every fill spends its ACTUAL half-turn (0.5 * shares * ref / pretrade NAV,
via on_fill — H2 spends real turnover, not planned). The rolling window
refills as old spend expires, so consuming early leaves less for the rest
of the window: the early-consumption penalty is structural, not a tuned
discount. Risk-mandated exits can drive the remaining budget negative;
discretionary admissions then wait until it recovers.

Receding horizon (plan §5 H2 "optimize a short horizon ... execute only
the first, and replan"): each monthly decision admits the best affordable
trades now and replans next month with the refilled budget and new
forecasts. No multi-month plan is cached.

Ablation record (plan §5 H2): gross vs net benefit, realized holding time
(FIFO lot matching post-run), avoided orders (budget-suppressed candidates
from the decision log), minimum-fee drag (commissions / traded value), and
opportunity lost by waiting (sum of logged benefits of budget-blocked
candidates — a proxy, disclosed).
"""
from __future__ import annotations

from research.baselines import strategies as strat
from research.baselines.panel import Panel
from research.controllers import forecasts
from research.controllers.base import Controller, drifted_weights

ANNUAL_BUDGET = 1.0        # half-turn per rolling 252 sessions (frozen)
WINDOW = 252               # rolling budget window in sessions (frozen)
REVIEW_HORIZON = forecasts.HORIZON  # cohort review every 63 sessions (frozen)
ARMS = ("uniform", "fixed-bands", "persistence")


class H2Controller(Controller):
    def __init__(self, arm: str, risk_aversion: float = 4.0):
        if arm not in ARMS:
            raise ValueError(f"unknown H2 arm: {arm}")
        self.arm = arm
        self.risk_aversion = risk_aversion
        self.decision_log: list[dict] = []
        self._pending_spend = 0.0        # fills at the current open, flushed by on_session
        self._spends: list[tuple[int, float]] = []  # (session_idx, actual half-turn)
        self._last_decision_i: int | None = None
        self._cohort_entry: dict[str, int] = {}     # sym -> session idx of entry/review
        self._session_i = 0

    # ---- budget ----------------------------------------------------------
    def _spent_window(self, i: int) -> float:
        return sum(t for j, t in self._spends if i - WINDOW < j <= i)

    def remaining(self, i: int) -> float:
        return ANNUAL_BUDGET - self._spent_window(i)

    # ---- controller hooks --------------------------------------------------
    def on_fill(self, fill, pretrade_nav: float) -> None:
        if pretrade_nav <= 0 or fill.shares_filled <= 0:
            return
        self._pending_spend += 0.5 * fill.shares_filled * fill.order.ref_price / pretrade_nav

    def on_session(self, panel: Panel, i: int, ledger) -> None:
        if self._pending_spend > 0.0:
            self._spends.append((i, self._pending_spend))
            self._pending_spend = 0.0
        self._session_i = i

    # ---- helpers -----------------------------------------------------------
    def _expected_benefit(self, panel: Panel, i: int, sym: str, dw: float) -> float:
        mu = forecasts.trend_forecast(panel, i).get(sym, 0.0)
        return mu * dw

    def _cost(self, dw: float) -> float:
        # same frozen scalar cost model as H1 (b): 15bp round-trip floor on
        # the moved weight; worst-case doubled scenario for admission
        return abs(dw) * 0.0015 * 2.0

    # ---- decide --------------------------------------------------------------
    def decide(self, panel: Panel, i: int, ledger, nav: float, marks: dict) -> dict:
        cur = drifted_weights(ledger, nav, marks)
        if forecasts.cov_shrinkage(panel, i) is None:
            # no covariance history (warmup/data gap): true hold
            self.decision_log.append({
                "session": panel.sessions[i], "arm": self.arm,
                "action": "hold-all", "reason": "no-data (warmup)"})
            return dict(cur)
        raw = forecasts.mean_variance_targets(panel, i, self.risk_aversion)
        if not raw:
            # valid data, all-zero mu: MV optimum is the reserve; per-symbol
            # zero targets so each arm applies its own spending rule (see
            # the same correction in h1_hold.py — previously the early {}
            # return made every arm liquidate identically on de-risk months)
            raw = {s: 0.0 for s in strat.NON_RESERVE}
        out: dict = {}
        candidates = []   # discretionary (sym, dw, benefit, cost, tau)
        for sym in strat.NON_RESERVE:
            tgt = raw.get(sym, 0.0)
            cw = cur.get(sym, 0.0)
            dw = tgt - cw
            if abs(dw) < 1e-9:
                out[sym] = tgt
                self._log(i, sym, tgt, cw, "hold", "at-target", 0.0)
                continue
            mu_pos = forecasts.trend_forecast(panel, i).get(sym, 0.0) > 0.0
            held = cw > 1e-9
            if self.arm == "persistence" and held and not mu_pos:
                # hypothesis failure: risk-mandated exit, overrides budget;
                # its turnover is still spent and visible
                out[sym] = tgt
                self._log(i, sym, tgt, cw, "trade", "risk-exit (hypothesis failed)",
                          self.remaining(i))
                self._cohort_entry.pop(sym, None)
                continue
            benefit = self._expected_benefit(panel, i, sym, dw)
            cost = self._cost(dw)
            tau = 0.5 * abs(dw)
            candidates.append((sym, tgt, cw, dw, benefit, cost, tau))
        if not candidates:
            self._last_decision_i = i
            return out
        # arm-specific ordering and gating
        if self.arm == "uniform":
            gap = (i - self._last_decision_i
                   if self._last_decision_i is not None else 21)
            allowance = ANNUAL_BUDGET * gap / WINDOW
            # uniform spenders draw from the same rolling container: the
            # monthly allowance can never exceed what the container holds
            budget = min(allowance, self.remaining(i))
            candidates.sort(key=lambda c: -c[4])       # descending expected benefit
        elif self.arm == "fixed-bands":
            # H1(b) cost gate; gate-FAILED symbols must still get an explicit
            # hold key — a missing key would mean target 0 to the runner and
            # an unintended liquidation (found in the first smoke run)
            gated = []
            for c in candidates:
                if c[4] > c[5]:
                    gated.append(c)
                else:
                    out[c[0]] = c[2]
                    self._log(i, c[0], c[1], c[2], "hold",
                              "gate-failed (benefit <= cost)",
                              self.remaining(i), c[4], c[5])
            candidates = gated
            candidates.sort(key=lambda c: -c[4])
            budget = self.remaining(i)
        else:  # persistence
            # discretionary entries/top-ups ranked by net benefit per turnover;
            # existing live holdings hold (no order) unless at a review month
            ranked = []
            for sym, tgt, cw, dw, benefit, cost, tau in candidates:
                entry_i = self._cohort_entry.get(sym)
                if cw > 1e-9 and forecasts.trend_forecast(panel, i).get(sym, 0.0) > 0.0:
                    if entry_i is not None and i - entry_i < REVIEW_HORIZON:
                        out[sym] = cw
                        self._log(i, sym, tgt, cw, "hold", "cohort live (review pending)",
                                  self.remaining(i))
                        continue
                ranked.append((sym, tgt, cw, dw, benefit, cost, tau,
                               (benefit - cost) / tau if tau > 0 else 0.0))
            ranked.sort(key=lambda c: -c[7])
            candidates = [(s, t, w, d, b, c, tau) for s, t, w, d, b, c, tau, _ in ranked]
            budget = self.remaining(i)
        # admit in ranked order while budget remains
        spent_plan = 0.0
        for sym, tgt, cw, dw, benefit, cost, tau in candidates:
            if spent_plan + tau <= budget + 1e-12:
                out[sym] = tgt
                spent_plan += tau
                self._log(i, sym, tgt, cw, "trade",
                          f"admitted (rank spend {spent_plan:.3f}/{budget:.3f})",
                          self.remaining(i), benefit, cost)
                if self.arm == "persistence" and cw <= 1e-9:
                    self._cohort_entry[sym] = i
            else:
                out[sym] = cw
                self._log(i, sym, tgt, cw, "hold",
                          f"budget-blocked (need {tau:.3f}, left {budget - spent_plan:.3f})",
                          self.remaining(i), benefit, cost)
        self._last_decision_i = i
        return out

    def _log(self, i: int, sym: str, tgt: float, cw: float, action: str,
             why: str, remaining: float, benefit: float | None = None,
             cost: float | None = None):
        row = {"session": self._sessions_str(i), "arm": self.arm, "symbol": sym,
               "target": round(tgt, 5), "drifted": round(cw, 5),
               "action": action, "constraint": why,
               "budget_remaining": round(remaining, 5)}
        if benefit is not None:
            row["benefit"] = round(benefit, 6)
        if cost is not None:
            row["cost_worst"] = round(cost, 6)
        self.decision_log.append(row)

    def _sessions_str(self, i: int) -> str:
        # panel reference kept via on_session for log timestamps
        return self._panel.sessions[i] if getattr(self, "_panel", None) else str(i)

    def bind_panel(self, panel: Panel) -> None:
        """Record the panel for log timestamps (called once before running)."""
        self._panel = panel


def fifo_holding_times(ledger) -> dict:
    """Realized holding time per symbol: FIFO-match buy fills against sell
    fills, return {sym: [sessions_held, ...]} using decision-date ordinals.
    Post-run ablation metric (plan §5 H2 'realized holding time')."""
    out: dict = {}
    for sym in {f.order.symbol for f in ledger.fills}:
        lots = []   # (ordinal, shares)
        holds = []
        for f in ledger.fills:
            if f.order.symbol != sym or f.shares_filled <= 0:
                continue
            o = f.order.session.toordinal()
            if f.order.side == "buy":
                lots.append([o, f.shares_filled])
            else:
                rem = f.shares_filled
                while rem > 0 and lots:
                    take = min(rem, lots[0][1])
                    holds.append(o - lots[0][0])
                    lots[0][1] -= take
                    rem -= take
                    if lots[0][1] <= 0:
                        lots.pop(0)
        if holds:
            out[sym] = holds
    return out
