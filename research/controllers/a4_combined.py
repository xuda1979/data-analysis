"""P5 — A4 combined controller (plan §5, trial rows 9-10).

Registered combination: B4's monthly cost-band gate + H3's asymmetric risk
budgets and daily monitor (H1 threshold arms and H2 budget spending were
REFUTED in P4; the one carry-forward candidate on risk-adjusted grounds —
H2 persistence's exit rule — is tested here as A4-loo-persistence).

A4 (row 9): H3Controller("asymmetric") — the combination IS B4's gate plus
H3's risk layer, because H3's monthly decide already runs B4's cost-band
gate on the scaled targets. Implemented directly by H3Controller; this
module registers the mapping and the leave-one-out family:

  A4            = H3-asymmetric           (B4 gate + vol target + dd monitor)
  A4-loo-vol    = H3 with vol term off    (dd monitor only, m = m_dd)
  A4-loo-dd     = H3 with dd term off     (= H3-vol-only, m = m_vol)
  A4-loo-monitor = H3-asymmetric with the daily monitor disabled
                   (monthly risk cuts only)

Leave-one-out semantics (row 10, registered family): each variant removes
exactly one component; the daily monitor disable is a flag, not a new arm
class. All variants share the frozen forecasts and the frozen H3 constants.
"""
from __future__ import annotations

from research.controllers.h3_risk import H3Controller


class A4NoVol(H3Controller):
    """A4-loo-vol: m = m_dd only (drawdown monitor, no volatility target)."""

    def _multiplier(self, panel, i, weights):
        if self.arm == "static":
            return 1.0
        return self._m_dd


class A4NoMonitor(H3Controller):
    """A4-loo-monitor: asymmetric budgets retained, daily monitor disabled
    (risk cuts happen only at monthly decisions)."""

    def risk_targets(self, panel, i, ledger):
        return None


def build(variant: str):
    """Factory for the registered A4 family."""
    if variant == "A4":
        return H3Controller("asymmetric")
    if variant == "A4-loo-vol":
        return A4NoVol("asymmetric")
    if variant == "A4-loo-dd":
        return H3Controller("vol-only")
    if variant == "A4-loo-monitor":
        return A4NoMonitor("asymmetric")
    raise ValueError(f"unknown A4 variant: {variant}")
