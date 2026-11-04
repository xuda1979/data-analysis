"""P3 fold calendar: walk-forward layout on the common verified window.

Plan §7: expanding train (36m) -> 12m inner -> 12m outer, annual rolls, carry
holdings through boundaries (the runner does that; this module only draws the
calendar). Anchored at the common window start 2007-07-26: fold 0 inner
2010-07-26..2011-07-26, outer 2011-07-26..2012-07-26; ... fold 15 outer
2026-07-26..2027-07-26 truncated at panel end 2026-11-03 (partial outer fold,
disclosed, not skipped, per §7.4 "never skip a bad or failed fold").

All pre-T0 outer intervals are retrospective development diagnostics (data
exposure registry); nothing here is confirmation evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from research.baselines.panel import Panel


@dataclass
class Fold:
    k: int                 # fold number
    train_end: str         # ISO date: last session of the expanding train
    inner: tuple           # (start_iso, end_iso_inclusive_of_train) inner window
    outer: tuple           # (start_iso, end_iso) outer evaluation window
    outer_sessions: int    # number of common sessions in the outer window
    partial: bool          # True when the outer window is truncated by panel end


def _to_iso(d: date) -> str:
    return d.isoformat()


def build_folds(panel: Panel) -> list:
    """Folds anchored at the panel's first session, annual rolls by calendar
    year (12 months), 36m initial train, 12m inner, 12m outer."""
    sessions = panel.sessions
    anchor = date.fromisoformat(sessions[0])
    last_session = date.fromisoformat(sessions[-1])

    def add_months(d: date, months: int) -> date:
        y, m = divmod((d.year * 12 + d.month - 1) + months, 12)
        y, m = int(y), int(m) + 1
        day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28,
                          31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
        return date(y, m, day)

    def first_session_on_or_after(d: date) -> str:
        iso = _to_iso(d)
        for s in sessions:
            if s >= iso:
                return s
        return None

    folds = []
    k = 0
    while True:
        train_end = add_months(anchor, 36 + 12 * k)          # expanding: anchor + 36m + k*12m
        inner_start = train_end                              # inner follows train
        inner_end = add_months(inner_start, 12)
        outer_start = inner_end
        outer_end = add_months(outer_start, 12)
        if date.fromisoformat(first_session_on_or_after(outer_start) or "9999-12-31") > last_session:
            break
        osess = first_session_on_or_after(outer_start)
        oend = _to_iso(min(outer_end, last_session))
        n_outer = sum(1 for s in sessions if osess <= s <= oend)
        folds.append(Fold(
            k=k,
            train_end=first_session_on_or_after(train_end) or sessions[-1],
            inner=(_to_iso(inner_start), _to_iso(inner_end)),
            outer=(osess, oend),
            outer_sessions=n_outer,
            partial=outer_end > last_session,
        ))
        k += 1
    return folds
