"""P3 walk-forward runner: B0-B4 (and later A1-A4) through the P2 Ledger.

Implements plan §6 (clocks, costs, turnover), §7 (walk-forward), §8 (baselines)
on the P1 panel. One continuous funded account per run: holdings, cash, costs
carry through ALL fold boundaries (no free reset, plan §7.4); folds slice the
same path for reporting only. Baselines have no per-fold fitted parameters.

Clock (plan §6.1): decisions after close of session t (first session of each
calendar month), orders fill at session t+1 open with the adverse cost model.
Old portfolio owns the overnight move; new shares earn returns after fill.

Costs (plan §6.2/§6.3 base): h=2bp, l=2bp, Y=1.0, participation <= 0.1% of
trailing 20-session dollar volume; IBKR Pro Fixed whole-share commissions.

Funding realism (plan §3.1 conservative cash account): sells settle T+1/T+2,
so a monthly rotation's buys cannot be same-session-funded by its sells.
The runner therefore splits each decision into (1) sells at t+1 open,
(2) buys at the first session at/after the sells' settlement (t+3 under
T+2, t+2 under T+1; buy-only decisions wait to t+2), using settled cash
only. Each pending order fills ONLY at its own fill session's open
(session-aware dispatch); unsettled-sale proceeds are never spent (T+1
from 2024-05-28: a t+1 sell settles on t+2's date, so t+2 buys spend it
only after _receive_settlements on that session — which the ledger does
inside execute()).

Dividends: credited as settled cash on the ex-date to shares held entering
that session (selling at the ex-date open does not forfeit; verified P1
semantics: amounts on split-adjusted basis).

Splits: bars are fully split-adjusted (P1: zero jump at both events), so
splits are a no-op on positions.

Turnover (plan §6.4): g_t = sum(|filled*ref_price|)/pretrade_NAV per session,
tau = g/2; establishment g=1; full rotation g=2. Per-session pretrade NAV is
captured before each session's fills.

Terminal liquidation (plan §6.4): the run liquidates at the next session's
open after the final mark; its costs and turnover are included in the all-in
evaluation.

All pre-T0 outer intervals are retrospective development diagnostics
(data-exposure registry); nothing here is confirmation evidence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date

from research.baselines import strategies as strat
from research.baselines.folds import build_folds
from research.baselines.panel import Panel, trailing_adv
from research.execution.ledger import Ledger, LedgerError, Order, settlement_days

BASE_COSTS = dict(half_spread=0.0002, extra_slippage=0.0002,
                  impact_coeff=1.0, max_participation=0.001)


@dataclass
class RunConfig:
    strategy: str                    # "B1" | "B2" | "B3-minvar" | "B3-ivvol"
    account_size: float = 100_000.0
    band: float = 0.05               # weight-band for banded variants (None disables)
    reserve: str = "BIL"             # residual sink: "BIL" | "cash" (B2: cash)
    costs: dict = field(default_factory=lambda: dict(BASE_COSTS))
    commission_schedule: str = "ibkr_pro_fixed"
    commission_multiplier: float = 1.0
    liquidate_at_end: bool = True    # terminal liquidation included (plan §6.4)
    controller: object = None        # P4: overrides strategy fn at monthly checkpoints


DEFAULT_CONFIGS = {
    # B2 abstains to literal cash per plan §8 ("cash when ineligible"); a
    # Treasury ETF costs money to enter/exit (plan §6.2), so routing B2's
    # abstention through BIL would misstate its costs (disclosed choice).
    "B1": RunConfig(strategy="B1", reserve="BIL"),
    "B2": RunConfig(strategy="B2", reserve="cash"),
    "B3-minvar": RunConfig(strategy="B3-minvar", reserve="BIL"),
    "B3-ivvol": RunConfig(strategy="B3-ivvol", reserve="BIL"),
}


@dataclass
class DayRecord:
    session: str
    nav: float
    tau: float                # session half-turn g/2 on pretrade NAV
    gross_exposure: float     # risky/NAV at close
    rf_daily: float
    settled_cash: float


def _strategy_fn(name: str):
    return {
        "B1": strat.b1_equal_weight,
        "B2": strat.b2_trend_rs,
        "B3-minvar": strat.b3_minvar,
        "B3-ivvol": strat.b3_inverse_vol,
    }[name]


def month_key(iso: str) -> tuple:
    return int(iso[:4]), int(iso[5:7])


def _daily_vol(panel: Panel, symbol: str, i: int, window: int = 20) -> float:
    c = panel.close[symbol]
    lo = max(0, i - window)
    rs = [c[j] / c[j - 1] - 1.0 for j in range(lo + 1, i + 1)]
    if len(rs) < 2:
        return 0.0
    mean = sum(rs) / len(rs)
    var = sum((x - mean) ** 2 for x in rs) / (len(rs) - 1)
    return math.sqrt(var)


def _credit_dividends(ledger: Ledger, panel: Panel, i: int) -> None:
    """Ex-date dividends go to shares held ENTERING the session, credited
    before that session's fills: selling at the ex-date open does not
    forfeit the dividend; buying at the ex-date open does not receive it."""
    for sym, dmap in panel.dividends.items():
        amt = dmap.get(i)
        pos = ledger.positions.get(sym)
        if amt and pos and pos.shares > 0:
            ledger.settled_cash += pos.shares * amt


def _execute_at_open(ledger: Ledger, panel: Panel, orders: list, i: int,
                     costs: dict, warnings: list, failed: list,
                     controller=None) -> float:
    """Fill `orders` at session i's open; returns pretrade NAV (captured before
    the first fill of the session). Failed/partial fills recorded, never
    silently skipped. `controller.on_fill(fill, pretrade_nav)` fires after
    every fill attempt (P4: H2 budget spends actual turnover)."""
    marks_all = {s: panel.close[s][i - 1] for s in panel.close}
    pretrade_nav = ledger.nav(marks_all)
    for order in orders:
        sym = order.symbol
        try:
            adv = trailing_adv(panel, sym, i - 1)
            vol = _daily_vol(panel, sym, i - 1)
            fill = ledger.execute(order, fill_price=panel.open[sym][i],
                                  adv_dollars=adv, daily_vol=vol, **costs)
            if fill.status == "partial":
                warnings.append(
                    f"{panel.sessions[i]} partial {sym}: {fill.shares_filled:.0f} of "
                    f"{order.shares:.0f} shares (participation cap); residual abandoned")
            if controller is not None:
                controller.on_fill(fill, pretrade_nav)
        except LedgerError as e:
            failed.append({"session": panel.sessions[i], "symbol": sym,
                           "error": str(e)})
    return pretrade_nav


def _decision_orders(ledger: Ledger, panel: Panel, i: int, targets: dict,
                     config: RunConfig, warnings: list) -> tuple:
    """Split a decision into (sell_orders for t+1, buy_orders for t+2), from
    marked drifted shares (plan §6.4), band-gated, dust-filtered, capped.
    Sells at t+1 fund buys at t+2 (settled cash; conservative account).
    Liquidity qualification at decision time (protocol universe rule 3):
    a symbol with no trailing ADV yet is not orderable -> warmup abstention,
    disclosed via warnings; doomed orders are never generated."""
    n = len(panel.sessions)
    marks = {s: panel.close[s][i] for s in panel.close}
    nav = ledger.nav(marks)
    sells: list[Order] = []
    buys: list[Order] = []
    if nav <= 0:
        return sells, buys
    # liquidity qualification: trailing ADV must exist at decision time
    held = {sym for sym, pos in ledger.positions.items() if pos.shares > 0}
    qualified = {s for s in set(targets) | held
                 if trailing_adv(panel, s, i) > 0}
    unqualified = sorted(set(targets) - qualified)
    if unqualified:
        warnings.append(f"{panel.sessions[i]} warmup abstention "
                        f"(no trailing ADV yet): {unqualified}")
    targets = {s: w for s, w in targets.items() if s in qualified}
    # reserve routing: "BIL" parks the residual in the Treasury ETF (its own
    # trailing ADV must exist at decision time, else the account abstains in
    # cash — funded abstention, plan §7.4 — instead of generating a doomed
    # reserve order); "cash" parks the residual in literal zero-interest
    # cash (B2, plan §8 "cash when ineligible") — no reserve orders at all.
    reserve_ok = (config.reserve == "BIL"
                  and trailing_adv(panel, strat.RESERVE, i) > 0)
    dec = date.fromisoformat(panel.sessions[i])
    sell_s = date.fromisoformat(panel.sessions[i + 1])

    cur = {}
    for sym, pos in ledger.positions.items():
        if pos.shares > 0 and marks.get(sym):
            cur[sym] = pos.shares * marks[sym] / nav
    tgt = dict(targets)
    reserve_w = max(0.0, 1.0 - sum(tgt.values())) if reserve_ok else cur.get(strat.RESERVE, 0.0)
    all_tgt = dict(tgt)
    if reserve_ok:
        all_tgt[strat.RESERVE] = reserve_w

    band = config.band if config.band is not None else 0.0
    orderable = qualified | ({strat.RESERVE} if reserve_ok else set())
    # Deterministic symbol order (universe order, reserve LAST: the reserve is
    # the residual sink, so in a settled-cash crunch the risky buys fill
    # first and BIL absorbs the remainder). P3 bug fix: this loop previously
    # iterated a set, whose order depends on PYTHONHASHSEED; when buys
    # competed for settled cash, the fill sequence -- and hence the whole
    # path -- varied across processes. Any fixed order is a disclosed choice;
    # hash order is not.
    delta_syms = [s for s in (*strat.NON_RESERVE, strat.RESERVE)
                  if s in (set(all_tgt) | set(cur)) & orderable]
    # pass 1: compute deltas (which symbols sell, which buy, at what weight)
    deltas = []
    for sym in delta_syms:
        d = all_tgt.get(sym, 0.0) - cur.get(sym, 0.0)
        if abs(d) <= band or abs(d) * nav < 250.0:
            continue
        shares = abs(d) * nav / marks[sym]
        shares = math.floor(shares)
        if shares < 1:
            continue
        deltas.append((sym, d, shares))

    # buy session: first session at/after the sells' settlement (regime-aware;
    # plan §3.1 "a rotation may require waiting for sales to settle"). T+2
    # (pre-2024-05-28): a t+1 sell settles t+3 calendar -> buys at t+3. T+1
    # (from 2024-05-28): settles t+2 calendar -> buys at t+2. Buys funded by
    # already-settled cash are unaffected (they wait with the rotation).
    k = i + 2
    if any(d < 0 for _, d, _ in deltas):
        settle = settlement_days(sell_s)
        while k < n and date.fromisoformat(panel.sessions[k]).toordinal() \
                < sell_s.toordinal() + settle:
            k += 1
    buy_s = date.fromisoformat(panel.sessions[k]) if k < n else None

    # pass 2: build orders
    if buy_s is None and any(dd > 0 for _, dd, _ in deltas):
        warnings.append(f"{panel.sessions[i]} buys dropped: no fill session "
                        f"remains in the panel after the settlement wait")
    for sym, d, shares in deltas:
        if d < 0:
            held = ledger.positions.get(sym)
            if not held or held.shares < 1:
                continue
            shares = min(shares, math.floor(held.shares))
            sells.append(Order(sym, "sell", float(shares), marks[sym],
                               sell_s, config.strategy, dec))
        else:
            if buy_s is None:
                continue
            buys.append(Order(sym, "buy", float(shares), marks[sym],
                              buy_s, config.strategy, dec))
    return sells, buys


def run_strategy(panel: Panel, config: RunConfig,
                 start: str | None = None, end: str | None = None) -> dict:
    """Run one funded walk-forward path over [start, end] (default: common
    window). Returns days/folds/ledger/failed/warnings/pretrade NAVs."""
    sessions = panel.sessions
    i0 = panel.idx(start) if start else 0
    i1 = panel.idx(end) if end else len(sessions) - 1
    ledger = Ledger(initial_cash=config.account_size,
                    commission_schedule=config.commission_schedule,
                    commission_multiplier=config.commission_multiplier)
    days: list[DayRecord] = []
    warnings: list[str] = []
    failed: list[dict] = []
    strat_fn = None if config.controller is not None else _strategy_fn(config.strategy)
    controller = config.controller

    pending_sells: list[Order] = []   # decided t, fill t+1 open
    pending_buys: list[Order] = []    # decided t, fill t+2 open (post-settle)
    decided_month: tuple | None = None

    for i in range(i0, i1 + 1):
        s = sessions[i]
        # ---- dividends on ex-date (shares held entering the session) --------
        # BEFORE the session's fills (timing fix 2026-11-04): previously ran
        # after fills, so an ex-date open sell forfeited its dividend and an
        # ex-date open buy wrongly received it.
        _credit_dividends(ledger, panel, i)

        # ---- open: fills ---------------------------------------------------
        # Session-aware dispatch (timing-bug fix, 2026-11-04): each pending
        # order fills ONLY at its own fill session (sells t+1, buys at the
        # post-settlement session k) and at that session's open. This block
        # previously executed ALL pending orders at t+1, so buys filled at
        # t+1's open and Ledger.execute's _receive_settlements(order.session)
        # pulled the same-rotation sells' UNSETTLED proceeds forward at t+1
        # -- the exact violation the sell/buy split exists to prevent (plan
        # §3.1). Orders whose fill session lies beyond the run window expire
        # unfilled (never fire early); disclosed after the loop.
        d = date.fromisoformat(s)
        session_orders = ([o for o in pending_sells if o.session == d]
                          + [o for o in pending_buys if o.session == d])
        pretrade_nav = None
        if session_orders:
            pretrade_nav = _execute_at_open(ledger, panel, session_orders, i,
                                            config.costs, warnings, failed,
                                            controller)
        pending_sells = [o for o in pending_sells if o.session != d]
        pending_buys = [o for o in pending_buys if o.session != d]

        # ---- close: mark + record ------------------------------------------
        close_marks = {sym: panel.close[sym][i] for sym in ledger.positions}
        try:
            ledger.assert_invariants(close_marks)
        except LedgerError as e:
            failed.append({"session": s, "error": f"invariant: {e}"})
        nav = ledger.nav(close_marks)
        if pretrade_nav is None:
            pretrade_nav = nav
        g_usd = sum(f.shares_filled * f.order.ref_price
                    for f in ledger.fills
                    if f.order.session == date.fromisoformat(s)
                    and f.shares_filled > 0)
        tau = (g_usd / pretrade_nav) / 2.0 if pretrade_nav > 0 else 0.0
        risky = ledger.market_value(close_marks)
        days.append(DayRecord(s, nav, tau, risky / nav if nav > 0 else 0.0,
                              panel.rf_daily[i], ledger.settled_cash))

        # ---- after close: monthly decision ---------------------------------
        if controller is not None:
            controller.on_session(panel, i, ledger)
        mk = month_key(s)
        if mk != decided_month and i + 1 < len(sessions) and (i < i1 or not config.liquidate_at_end):
            decided_month = mk
            if controller is not None:
                marks = {sym: panel.close[sym][i] for sym in panel.close}
                nav_now = ledger.nav(marks)
                targets = controller.decide(panel, i, ledger, nav_now, marks)
            else:
                targets = strat_fn(panel, i)
            sells, buys = _decision_orders(ledger, panel, i, targets, config,
                                           warnings)
            pending_sells, pending_buys = sells, buys

    # ---- expired orders (fill session beyond the run window) ---------------
    for o in (*pending_sells, *pending_buys):
        warnings.append(f"{o.session.isoformat()} expired unfilled: {o.side} "
                        f"{o.symbol} (decided {o.decision_session.isoformat()}; "
                        f"fill session beyond run window; never fired early)")

    # ---- terminal liquidation (plan §6.4) ----------------------------------
    if config.liquidate_at_end and i1 + 1 < len(sessions):
        liq_session = date.fromisoformat(sessions[i1 + 1])
        dec = date.fromisoformat(sessions[i1])
        marks = {sym: panel.close[sym][i1] for sym in ledger.positions}
        liq_orders = []
        for sym, pos in ledger.positions.items():
            if pos.shares >= 1:
                liq_orders.append(Order(sym, "sell", math.floor(pos.shares),
                                        marks[sym], liq_session,
                                        f"{config.strategy}-liq", dec))
        if liq_orders:
            pretrade_nav = _execute_at_open(ledger, panel, liq_orders, i1 + 1,
                                            config.costs, warnings, failed)
            # mark the liquidation session too (post-fill NAV at its close)
            j = i1 + 1
            close_marks = {sym: panel.close[sym][j] for sym in ledger.positions}
            ledger.assert_invariants(close_marks)
            nav = ledger.nav(close_marks)
            g_usd = sum(f.shares_filled * f.order.ref_price
                        for f in ledger.fills
                        if f.order.session == liq_session and f.shares_filled > 0)
            tau = (g_usd / pretrade_nav) / 2.0 if pretrade_nav > 0 else 0.0
            risky = ledger.market_value(close_marks)
            days.append(DayRecord(sessions[j], nav, tau,
                                  risky / nav if nav > 0 else 0.0,
                                  panel.rf_daily[j], ledger.settled_cash))

    return {"days": days, "folds": build_folds(panel), "ledger": ledger,
            "config": config, "failed": failed, "warnings": warnings}
