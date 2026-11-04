"""P4 controller protocol (plan §4 interfaces 3-5, §5 H1/H2).

A controller is a stateful object the runner consults at monthly decision
checkpoints. Baselines keep the pure strategy-function path: when
`RunConfig.controller is None` the runner is byte-identical to P3.

Protocol:
  decide(panel, i, ledger, nav, marks) -> dict   (required)
      Monthly checkpoint, called after close of session i (same clock as
      baselines, plan §6.1). `marks` = close marks for all panel symbols at
      i, `nav` = ledger NAV at those marks (settled + unsettled + market
      value). Returns target weights for non-reserve symbols (fractions of
      NAV) AFTER the controller's own hold/trade logic: a symbol the
      controller holds stays at its drifted weight (delta ~ 0 -> no order).
      The runner then applies liquidity qualification, caps via the band/
      dust gates, settlement-aware sell/buy splitting and the ledger exactly
      as for baselines.
  on_fill(fill, pretrade_nav)                     (optional)
      Called after EVERY fill attempt (including rejected/partial) with the
      session's pretrade NAV. H2 budgets spend actual turnover:
      tau contribution = fill.shares_filled * fill.order.ref_price
      / pretrade_nav / 2.
  on_session(panel, i, ledger)                    (optional)
      Called at each session close (after marking, before the monthly
      decision on decision days). H3's daily risk monitor uses it (P5).
  risk_targets(panel, i, ledger) -> dict | None   (optional, P5)
      Daily risk monitor. Called after on_session at each session close
      EXCEPT sessions where a monthly decide() ran (decide() embeds the
      monitor state there). Return None (no action) or target weights for
      non-reserve symbols: a monitor-mandated rebalance the runner executes
      through the SAME order/ledger path with the no-trade band DISABLED
      (predeclared reduction rule, plan §5 H3 — emergency turnover is
      recorded, never hidden). Returned targets REPLACE any pending orders
      (newest decision wins; a de-risking cut cancels stale buys). Base
      default: None (P4 controllers structurally unchanged).

All controller state is development-history diagnostics until T0
(data-exposure registry).
"""
from __future__ import annotations

from research.baselines import strategies as strat
from research.controllers import forecasts


def drifted_weights(ledger, nav: float, marks: dict) -> dict:
    """Current portfolio weights from marked positions: {sym: shares*mark/nav}
    for positive-share positions. Controller helper for hold decisions."""
    if nav <= 0:
        return {}
    out = {}
    for sym, pos in ledger.positions.items():
        if pos.shares > 0 and marks.get(sym):
            out[sym] = pos.shares * marks[sym] / nav
    return out


class Controller:
    """Base controller: no-op hooks, decide() required."""
    name = "controller"

    def decide(self, panel, i, ledger, nav: float, marks: dict) -> dict:
        raise NotImplementedError

    def on_fill(self, fill, pretrade_nav: float) -> None:
        pass

    def on_session(self, panel, i, ledger) -> None:
        pass

    def risk_targets(self, panel, i, ledger) -> dict | None:
        return None


class MVController(Controller):
    """Shared forecast-targets base for B4 and every H1/H2 arm (plan §5 H1
    ablation requirement: IDENTICAL forecasts across arms; only the hold/
    trade rule differs). `decide()` returns the raw mean-variance targets;
    arms override `decide()` and apply their hold logic to
    `self.raw_targets(panel, i)`."""

    def __init__(self, risk_aversion: float = 4.0):
        self.risk_aversion = risk_aversion

    def raw_targets(self, panel, i: int) -> dict:
        return forecasts.mean_variance_targets(panel, i, self.risk_aversion)

    def decide(self, panel, i, ledger, nav: float, marks: dict) -> dict:
        return self.raw_targets(panel, i)
