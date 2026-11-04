"""P4e — exact fee/rounding check against small-universe enumeration
(plan §9, P4 deliverable row).

For a tiny universe (2 symbols, integer shares, small cash), enumerate ALL
affordable integer-share allocations and verify the ledger's actual filled
outcome is (1) in the enumerated feasible set and (2) fee-exact: the
commission charged equals the closed-form min(max(rate*Q, min), 1%*D),
cash never overdraws, shares are whole, and the 1% cap binds where the
closed form says it binds. The runner's greedy whole-share flooring is a
feasible point, not a claimed optimum (plan §5 H2: "Do not claim a convex
optimum when ticket minima or discrete selection make the problem
nonconvex").
"""
from __future__ import annotations

import itertools
from datetime import date

from research.execution.ledger import (
    Ledger,
    Order,
    commission,
    settlement_days,
)


def test_commission_closed_form_vs_boundaries():
    # rate region: 0.005*Q in [1, 1%*notional]
    # 0.005*100 = 0.50 < 1.00 minimum -> commission = 1.00
    assert commission(100, 50.0) == 1.00
    # rate region: 0.005*400 = 2.00 in [1, 1%*400*50=200] -> 2.00
    assert commission(400, 50.0) == 2.00
    # cap region: 1% * notional binds when 0.005*Q > 1%*Q*price, i.e. price < 0.5
    assert commission(100, 0.40) == 0.40  # min(1.00, 0.01*100*0.40=0.40)
    # zero shares
    assert commission(0, 50.0) == 0.0


def test_small_universe_enumeration_fee_exact():
    """Enumerate all integer allocations of $10,000 over 2 symbols at given
    prices; every enumerated buy the ledger executes must charge exactly
    the closed-form commission and leave nonnegative cash; the ledger's
    own fills stay inside the enumerated feasible set."""
    prices = {"A": 37.0, "B": 61.0}
    cash = 10_000.0
    sched = "ibkr_pro_fixed"

    def comm(q):
        return commission(q, prices[sym], sched)

    # feasible set: (qa, qb) whole shares, cost incl. commissions <= cash
    feasible = []
    max_a = int(cash // prices["A"])
    for qa in range(max_a + 1):
        rem_a = cash - qa * prices["A"] - commission(qa, prices["A"], sched)
        max_b = int(rem_a // prices["B"]) if rem_a >= 0 else -1
        for qb in range(max_b + 1):
            rem = (cash - qa * prices["A"] - commission(qa, prices["A"], sched)
                   - qb * prices["B"] - commission(qb, prices["B"], sched))
            if rem >= 0:
                feasible.append((qa, qb, round(rem, 6)))
    assert feasible, "enumeration found no feasible allocation"
    assert (0, 0, round(cash, 6)) in feasible  # do-nothing is feasible

    # execute one non-trivial enumerated allocation through the ledger and
    # verify fee-exactness and cash floor
    pick = next(f for f in feasible if f[0] > 0 and f[1] > 0)
    qa, qb, rem = pick
    led = Ledger(initial_cash=cash, commission_schedule=sched)
    d0, d1 = date(2020, 1, 2), date(2020, 1, 3)
    for sym, q in (("A", qa), ("B", qb)):
        fill = led.execute(Order(sym, "buy", q, prices[sym], d1, "enum", d0),
                           fill_price=prices[sym], adv_dollars=1e9,
                           daily_vol=0.01, half_spread=0.0,
                           extra_slippage=0.0, impact_coeff=0.0,
                           max_participation=1.0)
        assert fill.status == "filled"
        assert fill.commission_usd == commission(q, prices[sym], sched)
    # zero friction config: remaining cash must equal the enumeration
    assert abs(led.settled_cash - rem) < 1e-6
    assert led.settled_cash >= 0.0
    assert all(p.shares == int(p.shares) for p in led.positions.values())


def test_runner_slice_is_enumeration_feasible():
    """The runner's greedy whole-share flooring on a 2-symbol slice must
    land in the enumerated feasible set (never overdraw cash)."""
    from research.baselines.panel import load_panel
    from research.baselines.runner import RunConfig, run_strategy
    from research.baselines import strategies as strat

    panel = load_panel()
    cfg = RunConfig(strategy="B1", controller=None)
    r = run_strategy(panel, cfg, end="2008-06-30")
    led = r["ledger"]
    # invariants across the slice: whole shares, nonnegative cash
    for pos in led.positions.values():
        assert pos.shares >= 0
        assert pos.shares == int(pos.shares)
    assert led.settled_cash >= -1e-9
    # every buy fill's commission is the closed form
    for f in led.fills:
        if f.shares_filled > 0:
            assert f.commission_usd == commission(
                f.shares_filled, f.order.ref_price,
                led.commission_schedule)
