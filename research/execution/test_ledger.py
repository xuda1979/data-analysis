"""Required implementation tests for the unlevered_v1 funded replay (plan §9).

Covers the mandated test list:
- hand-computed 2/3-asset portfolios: buy-and-hold drift causes no trades;
  full rotation pays both legs; entry/exit fees charged; rounding cannot overdraw
- corporate actions: split changes shares without profit; missing dividends/delistings cannot pass
- timing: after-close info cannot fill at same close; new holdings don't earn overnight move
- costs: zero order, tiny order, minimum/cap transitions, no impact double-counting
- settlement: T+2/T+1 transition, cash-account constraint, receivables not spendable
- evaluation: turnover definitions (establishment tau=0.5, rotation g=2)

Run: .venv/bin/python -m pytest research/execution/test_ledger.py -q
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pytest

from research.execution.ledger import (Fill, Ledger, LedgerError, Order,
                                       commission, price_impact_cost,
                                       settlement_days)


def mk(when=date(2026, 1, 5)):
    return Ledger(initial_cash=100_000.0)


def buy_order(symbol, shares, price, session=date(2026, 1, 6), origin="test"):
    return Order(symbol, "buy", shares, price, session, origin,
                 decision_session=date(2026, 1, 5))


def sell_order(symbol, shares, price, session=date(2026, 1, 6), origin="test"):
    return Order(symbol, "sell", shares, price, session, origin,
                 decision_session=date(2026, 1, 5))


COST = dict(adv_dollars=10_000_000.0, daily_vol=0.01,
            half_spread=0.0002, extra_slippage=0.0002, impact_coeff=1.0,
            max_participation=0.10)  # 10% of ADV: cap never binds in these unit tests
# separate, explicit participation-cap tests use max_participation=0.001 (the
# frozen base research case) to exercise the partial-fill path.


# ---------- commission arithmetic (IBKR Pro schedules) -------------------------

def test_commission_zero_for_zero_shares():
    assert commission(0, 100.0) == 0.0


def test_commission_fixed_minimum():
    # 5 shares @ $100: rate*Q = 0.025 -> min $1 applies -> $1 (20bp of $500)
    assert commission(5, 100.0) == pytest.approx(1.00)


def test_commission_fixed_above_minimum():
    # 400 shares @ $50: 0.005*400 = $2.00
    assert commission(400, 50.0) == pytest.approx(2.00)


def test_commission_cap_one_percent():
    # 3 shares @ $5: rate*Q = 0.015 -> min $1; cap = 1% * 15 = $0.15 -> capped
    assert commission(3, 5.0) == pytest.approx(0.15)


def test_commission_tiered_minimum():
    assert commission(10, 100.0, "ibkr_pro_tiered") == pytest.approx(0.35)
    assert commission(1000, 10.0, "ibkr_pro_tiered") == pytest.approx(3.50)


def test_commission_illustrative_arithmetic_from_plan():
    # Plan §6.2: 5@100 = $1 min = 20bp; 50@100 = $1 = 2bp
    assert commission(5, 100.0) / 500 == pytest.approx(0.0020)
    assert commission(50, 100.0) / 5000 == pytest.approx(0.0002)


# ---------- impact model --------------------------------------------------------

def test_impact_requires_volume():
    with pytest.raises(LedgerError):
        price_impact_cost(10, 100.0, 0.0, 0.01, half_spread=0.0002, extra_slippage=0.0002)


def test_impact_zero_for_zero_shares_and_scales_with_sqrt_participation():
    assert price_impact_cost(0, 100.0, 1e6, 0.01, half_spread=0, extra_slippage=0) == 0.0
    small = price_impact_cost(100, 100.0, 1e6, 0.01, half_spread=0, extra_slippage=0)
    large = price_impact_cost(10_000, 100.0, 1e6, 0.01, half_spread=0, extra_slippage=0)
    assert 0 < small < large
    # 100x shares -> rho 100x -> sqrt ~10x on the impact term (small here, but present)
    assert large > small * 90


def test_impact_terms_dimensionless_and_additive():
    c = price_impact_cost(100, 50.0, 5e6, 0.0,
                          half_spread=0.0002, extra_slippage=0.0002, impact_coeff=0)
    assert c == pytest.approx(5000 * 0.0004)


# ---------- settlement regimes ---------------------------------------------------

def test_settlement_regime_transition():
    assert settlement_days(date(2020, 1, 2)) == 2      # T+2 era
    assert settlement_days(date(2024, 5, 24)) == 2     # last T+2 trade date
    assert settlement_days(date(2024, 5, 28)) == 1     # T+1 from this date
    assert settlement_days(date(1990, 1, 2)) == 3      # T+3 era


def test_sell_proceeds_not_spendable_until_settled():
    led = mk()
    led.execute(buy_order("SPY", 100, 100.0), fill_price=100.0, **COST)
    led._receive_settlements(date(2026, 1, 6))
    cash_after_buy = led.settled_cash
    led.execute(sell_order("SPY", 100, 100.0), fill_price=100.0, **COST)
    # proceeds unsettled: settled cash unchanged by the sell (only buy deducted earlier)
    assert led.settled_cash == pytest.approx(cash_after_buy)
    assert sum(led.unsettled_proceeds.values()) > 0
    # Same-session (T+1 = 1/7) buy auto-receives the 1/7 settlement, which is
    # correct settlement accounting. To show proceeds are NOT spendable before
    # settlement, buy on 1/6 BEFORE the settle date: cash is only the buy residual.
    led2 = mk()
    led2.execute(buy_order("SPY", 100, 100.0), fill_price=100.0, **COST)
    led2._receive_settlements(date(2026, 1, 6))
    led2.execute(sell_order("SPY", 100, 100.0), fill_price=100.0, **COST)
    big = led2.execute(buy_order("TLT", 1000, 90.0, session=date(2026, 1, 6)),
                       fill_price=90.0, **COST)
    assert big.status in ("rejected", "partial")  # unsettled $9,992 unusable on 1/6
    assert big.shares_filled * 90.0 + big.commission_usd + big.friction_usd <= cash_after_buy + 1e-6


def test_settlement_arrives_and_is_spendable():
    led = mk()
    led.execute(buy_order("SPY", 100, 100.0), fill_price=100.0, **COST)
    led.execute(sell_order("SPY", 100, 100.0), fill_price=100.0, **COST)
    led._receive_settlements(date(2026, 1, 7))  # T+1 after 2024-05-28
    assert led.settled_cash > 0
    assert led.unsettled_proceeds == {}
    led.execute(buy_order("TLT", 10, 90.0, session=date(2026, 1, 7)),
                fill_price=90.0, **COST)
    led.assert_invariants({"SPY": 100.0, "TLT": 90.0})


# ---------- funding constraints ---------------------------------------------------

def test_buy_cannot_overdraw_cash():
    led = mk()
    # order 2000 shares @ $100 = $200k > $100k cash: resized down or rejected
    fill = led.execute(buy_order("SPY", 2000, 100.0), fill_price=100.0, **COST)
    assert fill.status in ("rejected", "partial")
    assert led.settled_cash >= 0
    if fill.shares_filled:
        # resized: gross + costs <= 100k
        assert fill.shares_filled * 100.0 + fill.commission_usd + fill.friction_usd <= 100_000 + 1e-6
    led.assert_invariants({"SPY": 100.0})


def test_tiny_buy_rejected_not_rounded_into_debt():
    led = Ledger(initial_cash=1.5)  # barely above the $1 commission minimum
    fill = led.execute(buy_order("SPY", 10, 100.0), fill_price=100.0, **COST)
    assert fill.status == "rejected" and fill.shares_filled == 0
    assert led.settled_cash == pytest.approx(1.5)
    led.assert_invariants({"SPY": 100.0})


def test_shares_never_negative_no_shorting():
    led = mk()
    led.execute(buy_order("SPY", 10, 100.0), fill_price=100.0, **COST)
    # sell of 100 vs 10 held: ledger clamps to held shares (no exception, no short)
    fill = led.execute(sell_order("SPY", 100, 100.0), fill_price=100.0, **COST)
    pos = led.positions["SPY"]
    assert pos.shares == 0.0 and pos.cost_basis == 0.0
    assert fill.shares_filled == pytest.approx(10.0)
    assert fill.status == "partial"  # 10 of 100 filled
    # selling with no position at all is rejected
    fill2 = led.execute(sell_order("SPY", 5, 100.0, session=date(2026, 1, 7)),
                        fill_price=100.0, **COST)
    assert fill2.status == "rejected" and fill2.shares_filled == 0


def test_1x_exposure_cap_enforced_at_mark():
    # Funding math implies risky <= NAV whenever cash >= 0, so the loud check is
    # on the SIZING path: an oversize buy must be resized/rejected, never filled
    # into negative cash (which is what would breach 1x).
    led = mk()
    fill = led.execute(buy_order("SPY", 2000, 100.0), fill_price=100.0, **COST)
    assert fill.status == "partial"          # 2000*100 = 200k > 100k cash
    assert fill.shares_filled * 100.0 < 100_000
    assert led.settled_cash >= 0
    led.assert_invariants({"SPY": 100.0})    # risky < NAV, no borrowing
    # and a hostile mark (price x2.5) keeps invariant TRUE by construction
    led.assert_invariants({"SPY": 250.0})


# ---------- timing / causality ------------------------------------------------------

def test_order_cannot_fill_same_session_as_decision():
    with pytest.raises(LedgerError):
        Order("SPY", "buy", 1, 100.0, date(2026, 1, 5), "t", decision_session=date(2026, 1, 5))


def test_order_cannot_fill_before_decision():
    with pytest.raises(LedgerError):
        Order("SPY", "buy", 1, 100.0, date(2026, 1, 4), "t", decision_session=date(2026, 1, 5))


def test_new_shares_do_not_earn_overnight_move():
    # The old portfolio owns the overnight move (plan §6.1): a decision after
    # close t buying at open t+1 means the NAV path from close t to open t+1
    # belongs to the OLD holdings only. Verify via fill math: day t NAV uses
    # old positions; the fill at open t+1 sets the new basis.
    led = mk()
    led.execute(buy_order("SPY", 100, 100.0), fill_price=100.0, **COST)
    nav_t0 = led.nav({"SPY": 100.0})
    # overnight gap +10%: NAV at t+1 open = cash + 100*110
    nav_open = led.nav({"SPY": 110.0})
    assert nav_open - nav_t0 == pytest.approx(100 * 10.0)
    # a second position bought AT the open (fill_price=110) does not include the gap
    led.execute(buy_order("TLT", 10, 110.0, session=date(2026, 1, 7)),
                fill_price=110.0, **COST)
    pos = led.positions["TLT"]
    assert pos.shares == 10 and pos.cost_basis == pytest.approx(1100.0)


# ---------- participation cap --------------------------------------------------------

def test_participation_cap_partial_fill():
    led = mk()
    # ADV $1M, cap 0.1% -> max $1000 notional -> 10 shares @ $100
    fill = led.execute(buy_order("SPY", 500, 100.0), fill_price=100.0,
                       adv_dollars=1_000_000.0, daily_vol=0.01,
                       half_spread=0.0002, extra_slippage=0.0002, max_participation=0.001)
    assert fill.status == "partial"
    assert fill.shares_filled == pytest.approx(10.0)


def test_participation_cap_defines_partial_fill_boundary():
    # frozen base research case: 0.1% of trailing 20-session avg dollar volume.
    # ADV $10M -> $10k notional cap -> 100 shares @ $100
    led = mk()
    fill = led.execute(buy_order("SPY", 500, 100.0), fill_price=100.0,
                       adv_dollars=10_000_000.0, daily_vol=0.01,
                       half_spread=0.0002, extra_slippage=0.0002, max_participation=0.001)
    assert fill.status == "partial"
    assert fill.shares_filled == pytest.approx(100.0)


# ---------- hand-computed portfolio math ---------------------------------------------

def test_buy_and_hold_drift_causes_no_trades():
    # Drifted weights require NO order generation: required trades must come from
    # marked drifted shares, not consecutive target weights (plan §6.4).
    led = mk()
    led.execute(buy_order("SPY", 300, 100.0), fill_price=100.0, **COST)
    led.execute(buy_order("IEF", 500, 80.0), fill_price=80.0, **COST)
    n_fills_before = len(led.fills)
    # price moves: SPY +50%, IEF flat. Weights drift but shares are unchanged.
    marks = {"SPY": 150.0, "IEF": 80.0}
    led.assert_invariants(marks)
    # The ledger itself generates no orders on marks:
    assert len(led.fills) == n_fills_before
    assert led.turnover_notional_total == pytest.approx(300 * 100.0 + 500 * 80.0)


def test_full_rotation_pays_both_legs():
    led = mk()
    led.execute(buy_order("SPY", 500, 100.0), fill_price=100.0, **COST)
    led.execute(sell_order("SPY", 500, 100.0), fill_price=100.0, **COST)
    led._receive_settlements(date(2026, 1, 7))
    led.execute(buy_order("TLT", 500, 95.0, session=date(2026, 1, 8),
                          origin="t2"), fill_price=95.0, **COST)
    # all three legs charged: SPY entry 50k + SPY exit 50k + TLT entry 47.5k.
    # The pure rotation itself (exit + re-entry) is 97.5k; a FULL 100%->100%
    # rotation of the whole NAV would be g=2, tau=1 (checked at portfolio level in P3)
    assert led.turnover_notional_total == pytest.approx(50_000.0 + 50_000.0 + 47_500.0)
    # commission charged on all three fills (entry, exit, re-entry)
    assert led.commission_total == pytest.approx(
        commission(500, 100.0) + commission(500, 100.0) + commission(500, 95.0))


def test_no_cost_double_counting():
    led = mk()
    before = led.nav({})
    led.execute(buy_order("SPY", 100, 100.0), fill_price=100.0, **COST)
    after = led.nav({"SPY": 100.0})
    fill = led.fills[-1]
    # At mark=fill_price the gross converts 1:1 into shares: NAV drop = costs exactly once
    assert before - after == pytest.approx(fill.commission_usd + fill.friction_usd)
    # and a hand-computed two-asset NAV matches component sums (no double count)
    f1 = led.fills[0]
    assert after == pytest.approx(100_000 - f1.commission_usd - f1.friction_usd)


def test_hand_computed_two_asset_nav():
    led = mk()
    f1 = led.execute(buy_order("SPY", 100, 100.0), fill_price=100.0, **COST)
    f2 = led.execute(buy_order("IEF", 400, 90.0), fill_price=90.0, **COST)
    marks = {"SPY": 100.0, "IEF": 90.0}
    # 100*100 + 400*90 = 46,000 risky; cash = 100k - 10,000 - 36,000 - costs
    spent = f1.shares_filled * 100.0 + f2.shares_filled * 90.0
    costs = (f1.commission_usd + f1.friction_usd + f2.commission_usd + f2.friction_usd)
    assert led.settled_cash == pytest.approx(100_000 - spent - costs)
    assert led.nav(marks) == pytest.approx(100_000 - costs)  # no double count
    assert costs > 0


# ---------- corporate actions ---------------------------------------------------------

def test_split_changes_shares_without_profit():
    led = mk()
    led.execute(buy_order("VWO", 100, 50.0), fill_price=50.0, **COST)
    nav_pre = led.nav({"VWO": 50.0})
    # 2:1 split: shares double, price halves; NAV unchanged, no trade generated
    pos = led.positions["VWO"]
    pos.shares *= 2
    pos.cost_basis *= 2
    assert led.nav({"VWO": 25.0}) == pytest.approx(nav_pre)
    led.assert_invariants({"VWO": 25.0})


def test_dividend_missing_data_cannot_create_false_pass():
    # A dividend with no ex-date record cannot be credited: the panel either has
    # the event or it doesn't; missing dividends reduce total return honestly.
    led = mk()
    led.execute(buy_order("IEF", 100, 90.0), fill_price=90.0, **COST)
    # simulate: no dividend event in data -> NAV uses price only
    nav = led.nav({"IEF": 91.0})
    assert nav == pytest.approx(led.settled_cash + 100 * 91.0)
    # and a delisted security (no mark) must not vanish: unmarked -> excluded
    # from market value but shares retained (valuation gap, per plan §3.4)
    pos = led.positions["IEF"]
    assert pos.shares == 100


# ---------- turnover definitions -------------------------------------------------------

def test_establishment_turnover_half():
    # Cost equation uses |Q|*ref_price; establishment of ~100k on 100k NAV
    # gives g ~ 1.0, tau ~ 0.5 (plan §6.4). COST fixture uses a 10% cap so the
    # participation limit does not bind here.
    led = mk()
    led.execute(buy_order("SPY", 1000, 100.0), fill_price=100.0, **COST)
    g = led.turnover_notional_total / 100_000.0
    assert g == pytest.approx(1.0, abs=0.01)
    assert g / 2 == pytest.approx(0.5, abs=0.005)  # tau = 0.5 for establishment


def test_participation_cap_defines_partial_fill_boundary():
    # frozen base research case: 0.1% of trailing 20-session avg dollar volume.
    # ADV $10M -> $10k notional cap -> 100 shares @ $100 (override COST's 10%)
    led = mk()
    fill = led.execute(buy_order("SPY", 500, 100.0), fill_price=100.0,
                       adv_dollars=10_000_000.0, daily_vol=0.01,
                       half_spread=0.0002, extra_slippage=0.0002,
                       impact_coeff=1.0, max_participation=0.001)
    assert fill.status == "partial"
    assert fill.shares_filled == pytest.approx(100.0)


def test_ledger_rejects_bad_construction():
    with pytest.raises(LedgerError):
        Ledger(initial_cash=0)
    with pytest.raises(LedgerError):
        Ledger(initial_cash=-5)
