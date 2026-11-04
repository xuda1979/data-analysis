"""Funded replay engine for unlevered_v1: cash/share/NAV ledger, commissions,
settlement, and causal timing (plan §6).

Invariants enforced at every mutation (fail-closed):
  - shares >= 0 for every position (long-only, no borrows)
  - cash >= 0 at all times (no margin; buys reserve fees and do not overdraw)
  - risky market value <= NAV (gross exposure <= 1x, instrument level)
  - every fill decreases cash by (notional + costs) exactly once; costs never double-counted
  - settlement modeled by trade date: unsettled proceeds are receivables, not spendable
    (conservative cash-account rule, plan §3.1)

Clocks (plan §6.1):
  - decide after session t close (signals use data through t)
  - order executes at session t+1 open (+ adverse cost model) when a valid open exists
  - the OLD portfolio owns the overnight move; new shares earn returns only after fill

Turnover (plan §6.4):
  - g_t = sum(|filled_shares * reference_price|) / pretrade_NAV (cash-bookkeeping moves excluded)
  - tau_t = g_t / 2 (half-turn); establishment from cash is g=1, tau=0.5
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

ANN = 252.0


class LedgerError(ValueError):
    pass


def settlement_days(trade_date: date) -> int:
    """US equity settlement: T+3 before 1995-06-07 is out of scope; T+3 until
    1995-06-07, T+2 until 2024-05-27, T+1 from 2024-05-28 (plan §3.1, R8)."""
    if trade_date >= date(2024, 5, 28):
        return 1
    if trade_date >= date(1995, 6, 7):
        return 2
    return 3


def commission(shares: float, price: float, schedule: str = "ibkr_pro_fixed") -> float:
    """IBKR Pro US whole-share commission in USD (plan §6.2 table).

    ibkr_pro_fixed:  USD 0.005/share, min USD 1.00, cap 1% of trade value
    ibkr_pro_tiered: USD 0.0035/share (<=300k shares/mo), min USD 0.35, cap 1% of trade value
    min(rate*|Q|, cap) is NOT applied: the cap limits the commission itself;
    the minimum is the floor. Model: min(max(rate*|Q|, minimum), 0.01*D).
    Zero shares -> zero commission. Schedule choice is a frozen study parameter.
    """
    shares = abs(float(shares))
    if shares == 0:
        return 0.0
    notional = shares * float(price)
    if notional < 0:
        raise LedgerError("Notional cannot be negative")
    if schedule == "ibkr_pro_fixed":
        rate, minimum = 0.005, 1.00
    elif schedule == "ibkr_pro_tiered":
        rate, minimum = 0.0035, 0.35
    else:
        raise LedgerError(f"Unknown commission schedule: {schedule}")
    return min(max(rate * shares, minimum), 0.01 * notional)


def price_impact_cost(shares: float, price: float, adv_dollars: float,
                      daily_vol: float, *, half_spread: float, extra_slippage: float,
                      impact_coeff: float = 1.0) -> float:
    """Adverse execution cost in USD, excluding commission (plan §6.2).

    C = D*(h + l + Y*sigma*sqrt(rho)),  rho = D/V, D = |Q|*P.
    All three price-friction terms are dimensionless rates on notional.
    adv_dollars <= 0 -> unknown volume -> raise (no capacity claim without volume).
    """
    shares = abs(float(shares))
    if shares == 0:
        return 0.0
    if adv_dollars <= 0:
        raise LedgerError("adv_dollars must be positive; unknown volume means no fill model")
    if not (0 <= half_spread and 0 <= extra_slippage and 0 <= daily_vol <= 5):
        raise LedgerError("Invalid cost parameters")
    notional = shares * float(price)
    rho = min(notional / adv_dollars, 1.0)
    return notional * (half_spread + extra_slippage +
                       impact_coeff * daily_vol * (rho ** 0.5))


@dataclass
class Order:
    symbol: str
    side: str            # "buy" | "sell"
    shares: float        # > 0
    ref_price: float     # pre-impact reference price for cost math
    session: date        # execution session t+1 (fill session)
    origin: str          # strategy/sleeve id for attribution
    decision_session: date  # session t when the decision was made

    def __post_init__(self):
        if self.side not in ("buy", "sell"):
            raise LedgerError("side must be buy or sell")
        if self.shares <= 0:
            raise LedgerError("shares must be positive")
        if self.ref_price <= 0:
            raise LedgerError("reference price must be positive")
        if self.session <= self.decision_session:
            raise LedgerError("fill session must be strictly after decision session (no same-day fill)")


@dataclass
class Fill:
    order: Order
    fill_price: float    # actual simulated execution price (includes adverse move)
    shares_filled: float
    commission_usd: float
    friction_usd: float  # spread/slippage/impact charged at fill
    settles_on: date
    status: str = "filled"   # filled | partial | rejected

    @property
    def notional(self) -> float:
        return self.shares_filled * self.fill_price


@dataclass
class Position:
    shares: float = 0.0
    cost_basis: float = 0.0  # total USD cost of open shares (for tax lots, not returns)

    def add(self, shares: float, price: float):
        if shares <= 0:
            raise LedgerError("add requires positive shares")
        self.cost_basis += shares * price
        self.shares += shares

    def reduce(self, shares: float, price: float):
        if shares <= 0:
            raise LedgerError("reduce requires positive shares")
        if shares > self.shares + 1e-9:
            raise LedgerError("sell exceeds held shares (no shorting)")
        shares = min(shares, self.shares)
        avg = self.cost_basis / self.shares if self.shares else 0.0
        self.cost_basis -= avg * shares
        self.shares -= shares
        if self.shares <= 1e-9:
            self.shares, self.cost_basis = 0.0, 0.0


@dataclass
class Ledger:
    """One account: positions, settled cash, unsettled receivables, cost ledger."""
    initial_cash: float
    commission_schedule: str = "ibkr_pro_fixed"
    positions: dict = field(default_factory=dict)
    settled_cash: float = 0.0
    unsettled_proceeds: dict = field(default_factory=dict)  # settle_date -> USD
    fills: list = field(default_factory=list)
    cost_total: float = 0.0
    commission_total: float = 0.0
    turnover_notional_total: float = 0.0  # sum |filled*ref_price| (g numerator, USD)
    participation_breaches: int = 0

    def __post_init__(self):
        if self.initial_cash <= 0:
            raise LedgerError("initial_cash must be positive")
        self.settled_cash = self.initial_cash

    # ---- settlement bookkeeping -------------------------------------------------
    def _receive_settlements(self, on_or_before: date):
        due = [d for d in self.unsettled_proceeds if d <= on_or_before]
        for d in sorted(due):
            self.settled_cash += self.unsettled_proceeds.pop(d)

    # ---- execution --------------------------------------------------------------
    def execute(self, order: Order, *, fill_price: float, adv_dollars: float,
                daily_vol: float, half_spread: float, extra_slippage: float,
                impact_coeff: float = 1.0, max_participation: float = 0.001) -> Fill:
        """Fill an order at `fill_price` (already the adverse simulated price for
        the shares' leg; friction is charged separately per the cost equation).

        Partial fills: if the order exceeds max_participation * adv_dollars / price,
        only the cap-sized part fills (status="partial"); the remainder is NOT
        silently filled overnight — the caller re-submits or abandons it.
        Rejects (status="rejected", zero shares): buys that would overdraw
        (notional + costs > spendable cash) or exceed the 1x gross exposure cap.
        """
        if fill_price <= 0:
            raise LedgerError("fill price must be positive")
        self._receive_settlements(order.session)
        pos = self.positions.setdefault(order.symbol, Position())

        cap_shares = max_participation * adv_dollars / fill_price
        requested = order.shares
        fillable = min(requested, cap_shares) if cap_shares > 0 else requested
        if fillable <= 0:
            fill = Fill(order, fill_price, 0.0, 0.0, 0.0,
                        settlement_days(order.session), "rejected")
            self.fills.append(fill)
            return fill

        commission_usd = commission(fillable, order.ref_price, self.commission_schedule)
        friction_usd = price_impact_cost(fillable, order.ref_price, adv_dollars, daily_vol,
                                         half_spread=half_spread,
                                         extra_slippage=extra_slippage,
                                         impact_coeff=impact_coeff)
        gross = fillable * fill_price
        cost = commission_usd + friction_usd

        if order.side == "buy":
            if gross + cost > self.settled_cash + 1e-9:
                # resize to what cash can afford (reserve fees), else reject
                budget = max(self.settled_cash - cost, 0.0)
                affordable = min(fillable, budget / fill_price)
                floor_shares = 1.0  # a sub-1-share fill is rejected as uneconomic
                if affordable < floor_shares:
                    fill = Fill(order, fill_price, 0.0, 0.0, 0.0,
                                settlement_days(order.session), "rejected")
                    self.fills.append(fill)
                    return fill
                fillable, gross = affordable, affordable * fill_price
                commission_usd = commission(fillable, order.ref_price, self.commission_schedule)
                friction_usd = price_impact_cost(fillable, order.ref_price, adv_dollars, daily_vol,
                                                 half_spread=half_spread,
                                                 extra_slippage=extra_slippage,
                                                 impact_coeff=impact_coeff)
                cost = commission_usd + friction_usd
                if gross + cost > self.settled_cash + 1e-9:
                    fill = Fill(order, fill_price, 0.0, 0.0, 0.0,
                                settlement_days(order.session), "rejected")
                    self.fills.append(fill)
                    return fill
            # 1x gross exposure cap: risky value after buy <= NAV (cash+risky).
            # NOTE: with nonnegative cash and fills at fill_price marks, funding
            # implies the 1x cap at fill time; the caller re-checks against daily
            # marks via assert_invariants (market-driven breaches are logged there).
            self.settled_cash -= gross + cost
            pos.add(fillable, fill_price)
        else:  # sell
            if fillable > pos.shares + 1e-9:
                if pos.shares <= 0:
                    fill = Fill(order, fill_price, 0.0, 0.0, 0.0,
                                settlement_days(order.session), "rejected")
                    self.fills.append(fill)
                    return fill
                fillable = pos.shares
                commission_usd = commission(fillable, order.ref_price, self.commission_schedule)
                friction_usd = price_impact_cost(fillable, order.ref_price, adv_dollars, daily_vol,
                                                 half_spread=half_spread,
                                                 extra_slippage=extra_slippage,
                                                 impact_coeff=impact_coeff)
                cost = commission_usd + friction_usd
            pos.reduce(fillable, fill_price)
            settle = order.session.toordinal() + settlement_days(order.session)
            settle_date = date.fromordinal(settle)
            # costs on a sell are deducted from proceeds immediately
            self.unsettled_proceeds[settle_date] = (
                self.unsettled_proceeds.get(settle_date, 0.0) + gross - cost)

        status = "partial" if fillable < requested - 1e-9 else "filled"
        fill = Fill(order, fill_price, fillable, commission_usd, friction_usd,
                    date.fromordinal(order.session.toordinal() + settlement_days(order.session)),
                    status)
        self.fills.append(fill)
        self.cost_total += cost
        self.commission_total += commission_usd
        self.turnover_notional_total += fillable * order.ref_price
        return fill

    # ---- marking ------------------------------------------------------------------
    def market_value(self, marks: dict) -> float:
        total = 0.0
        for symbol, price in marks.items():
            pos = self.positions.get(symbol)
            if pos and price:
                total += pos.shares * price
        return total

    def nav(self, marks: dict) -> float:
        return (self.settled_cash + sum(self.unsettled_proceeds.values())
                + self.market_value(marks))

    def assert_invariants(self, marks: dict):
        if self.settled_cash < -1e-6:
            raise LedgerError(f"negative settled cash: {self.settled_cash}")
        for symbol, pos in self.positions.items():
            if pos.shares < -1e-9:
                raise LedgerError(f"negative shares: {symbol} {pos.shares}")
            if pos.shares > 0 and pos.cost_basis <= 0:
                raise LedgerError(f"nonzero position with zero cost basis: {symbol}")
        risky = self.market_value(marks)
        total = self.nav(marks)
        if total <= 0:
            raise LedgerError(f"nonpositive NAV: {total}")
        if risky > total + 1e-6:
            raise LedgerError(f"1x gross exposure breach: risky {risky:.2f} > NAV {total:.2f}")
        return True
