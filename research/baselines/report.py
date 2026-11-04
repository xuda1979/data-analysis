"""P3 reporting: fold-sliced and whole-path §1 metrics + B0 references.

Folds slice one continuous funded path for reporting only (plan §7.4: holdings
carry through every boundary; no per-fold reset). B0 references are bookkeeping
paths that need no strategy runner: zero-interest cash, the Treasury reserve
(BIL) buy-and-hold, equity (SPY) buy-and-hold, and a conventional 60/40
(60% SPY / 40% IEF, monthly re-weighted at close with no costs — a reference
index, not a tradable strategy; disclosed).

Every failed fold and every partial/rejected fill is disclosed, never skipped.
Pre-T0 outer intervals are retrospective development diagnostics.
"""
from __future__ import annotations

from research.baselines.folds import build_folds
from research.baselines.metrics import compute_metrics
from research.baselines.panel import Panel
from research.baselines.runner import DayRecord, run_strategy


def path_metrics(panel: Panel, days: list, ledger=None, cost_total: float = None,
                 commission_total: float = None) -> dict:
    """§1 metrics on a runner day path (whole window or a fold slice)."""
    sessions = [d.session for d in days]
    nav = [d.nav for d in days]
    rf = [panel.rf_daily[panel.idx(s)] for s in sessions]
    tau = [d.tau for d in days]
    ge = [d.gross_exposure for d in days]
    return compute_metrics(
        sessions, nav, rf, tau=tau, gross_exposure=ge,
        cost_total=(ledger.cost_total if ledger is not None and cost_total is None
                    else (cost_total or 0.0)),
        commission_total=(ledger.commission_total if ledger is not None and commission_total is None
                          else (commission_total or 0.0)),
        trades=(sum(1 for f in ledger.fills if f.shares_filled > 0)
                if ledger is not None else 0),
    ).to_dict()


def slice_days(days: list, start_iso: str, end_iso: str) -> list:
    """DayRecords with start_iso <= session <= end_iso. The pre-interval mark
    convention (metrics.py) needs the session BEFORE the window to carry the
    entering NAV, so the slice includes the last session before start_iso when
    present (folds report the same continuous path, not a reset account)."""
    out = [d for d in days if start_iso <= d.session <= end_iso]
    if out:
        i0 = next(j for j, d in enumerate(days) if d is out[0])
        if i0 > 0:
            prev = days[i0 - 1]
            if prev.session < start_iso:
                out = [prev] + out
    return out


def fold_table(panel: Panel, days: list, ledger) -> list:
    """Per-outer-fold §1 metrics slicing the continuous path."""
    rows = []
    for f in build_folds(panel):
        sl = slice_days(days, f.outer[0], f.outer[1])
        if len(sl) < 2:
            rows.append({"fold": f.k, "outer": list(f.outer),
                         "partial": f.partial, "error": "insufficient sessions"})
            continue
        m = path_metrics(panel, sl, ledger, cost_total=0.0, commission_total=0.0)
        m.update(fold=f.k, outer=list(f.outer), partial=f.partial)
        rows.append(m)
    return rows


def _bh_days(panel: Panel, symbol: str, account_size: float = 100_000.0) -> list:
    """Buy-and-hold reference path: all-in at the first close, no costs."""
    days = []
    shares = None
    for i, s in enumerate(panel.sessions):
        px = panel.close[symbol][i]
        if shares is None and px:
            shares = account_size / px
        nav = shares * px if shares else account_size
        days.append(DayRecord(s, nav, 0.0, 1.0 if shares else 0.0,
                              panel.rf_daily[i], 0.0))
    return days


def _cash_days(panel: Panel, account_size: float = 100_000.0) -> list:
    return [DayRecord(s, account_size, 0.0, 0.0, panel.rf_daily[i], account_size)
            for i, s in enumerate(panel.sessions)]


def _6040_days(panel: Panel, account_size: float = 100_000.0) -> list:
    """60% SPY / 40% IEF, re-weighted at each month's first close. No costs,
    no band — a reference index, not a tradable strategy (disclosed)."""
    days = []
    spy = ief = 0.0  # dollar values
    decided = None
    for i, s in enumerate(panel.sessions):
        mk = (s[:4], s[5:7])
        if mk != decided:
            decided = mk
            total = spy + ief or account_size
            spy, ief = 0.6 * total, 0.4 * total
        rs = panel.close["SPY"][i] / panel.close["SPY"][i - 1] - 1 if i else 0.0
        rb = panel.close["IEF"][i] / panel.close["IEF"][i - 1] - 1 if i else 0.0
        spy *= 1.0 + rs
        ief *= 1.0 + rb
        nav = spy + ief
        days.append(DayRecord(s, nav, 0.0, 1.0, panel.rf_daily[i], 0.0))
    return days


def b0_references(panel: Panel) -> dict:
    """B0 bookkeeping references (plan §8): zero-interest cash, Treasury
    reserve buy-and-hold, equity buy-and-hold, conventional 60/40."""
    out = {}
    for name, days in (("B0-cash", _cash_days(panel)),
                       ("B0-BIL", _bh_days(panel, "BIL")),
                       ("B0-SPY", _bh_days(panel, "SPY")),
                       ("B0-6040", _6040_days(panel))):
        out[name] = path_metrics(panel, days, ledger=None,
                                 cost_total=0.0, commission_total=0.0)
    return out


def run_report(panel: Panel, config) -> dict:
    """Full P3 report for one strategy config: whole-path metrics, per-fold
    table, B0 references, and honest disclosures."""
    r = run_strategy(panel, config)
    days, ledger = r["days"], r["ledger"]
    report = {
        "strategy": config.strategy,
        "config": {"reserve": config.reserve, "band": config.band,
                   "commission_schedule": config.commission_schedule,
                   "liquidate_at_end": config.liquidate_at_end},
        "path": path_metrics(panel, days, ledger),
        "folds": fold_table(panel, days, ledger),
        "b0_references": b0_references(panel),
        "disclosure": {
            "failed_fills": r["failed"],
            "warnings": r["warnings"],
            "partial_fills": [
                {"session": str(f.order.session), "symbol": f.order.symbol,
                 "side": f.order.side, "filled": f.shares_filled,
                 "requested": f.order.shares, "reason": f.resize_reason}
                for f in ledger.fills if f.status == "partial"],
            "rejected_fills": [
                {"session": str(f.order.session), "symbol": f.order.symbol,
                 "side": f.order.side, "requested": f.order.shares}
                for f in ledger.fills if f.status == "rejected"],
            "terminal_liquidation": (
                "included" if not any(p.shares > 0 for p in ledger.positions.values())
                else "skipped: panel ends at last mark (NAV pre-liquidation; "
                     "the next session does not exist yet)"),
            "pre_t0_status": ("retrospective development diagnostic; "
                              "not confirmation evidence"),
        },
    }
    return report
