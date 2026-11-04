# P3 Record — Baselines B0–B3 (walk-forward, funded, all-in costs)

**Status:** complete (development history; not confirmation evidence)
**Scope:** plan §6 (clocks, costs, turnover), §7 (walk-forward), §8 (baselines);
protocol `research/protocols/unlevered_v1.json`. B4 is deferred to P5 (it
needs H1–H3 forecasts). All results below are **retrospective development
diagnostics** on 2007-07-26..2026-11-03 (4850 common sessions); every
pre-T0 interval is development history per the data-exposure registry
(T0 = 2026-11-04).

## Setup

One continuous funded account per strategy: holdings, cash, and costs carry
through ALL fold boundaries (plan §7.4 — folds slice the same path for
reporting only). Baselines have no per-fold fitted parameters, so there is no
train/inner/outer distinction *inside* the runner; the fold calendar
(`research/baselines/folds.py`, 16 folds: 15 complete + fold 15 truncated at
the panel edge) slices the continuous path into reporting windows.

Clock (plan §6.1): decide after close of the first session of each calendar
month; sells fill at t+1 open, buys fill at the first session at/after the
sells' settlement (T+2 pre-2024-05-28 → buys at t+3; T+1 after → buys at
t+2), so unsettled proceeds are never spent (conservative cash account,
plan §3.1). Adverse cost model at fill: h=2bp, l=2bp, Y=1.0, participation
≤0.1% of trailing 20-session dollar volume, IBKR Pro Fixed whole-share
commissions (§6.2/§6.3 base grid).

Dividends are credited as settled cash on the ex-date to shares held entering
the session. Splits are a no-op (bars fully split-adjusted, P1-verified).

## Whole-path results (2007-07-26 → 2026-11-03, $100k start)

| strategy | NAV end | net CAGR | Sharpe | MaxDD | ann. half-turn | roll-252 half-turn max | gross exp max | trades | total costs |
|---|---|---|---|---|---|---|---|---|---|
| B1 equal-weight | $323,215 | 6.28% | 0.547 | 24.4% | 0.055 | 0.484 | 1.000 | 31 | $176 |
| B2 trend/RS (cash abstain) | $247,045 | 4.80% | 0.442 | 14.5% | 1.507 | 3.258 | 1.000 | 441 | $4,939 |
| B3-minvar | $232,666 | 4.48% | 0.564 | 16.8% | 0.145 | 0.877 | 1.000 | 124 | $480 |
| B3-ivvol | $230,101 | 4.42% | 0.504 | 18.6% | 0.084 | 0.877 | 1.000 | 52 | $235 |

## B0 references (bookkeeping paths, no costs)

| reference | net CAGR | Sharpe | MaxDD |
|---|---|---|---|
| Zero-interest cash | 0.00% | −13.02 (constant rf drag) | 0.0% |
| BIL buy-and-hold (Treasury reserve) | −0.03% | −1.93 | 1.4% |
| SPY buy-and-hold | 8.82% | 0.451 | 56.5% |
| 60/40 (SPY/IEF, monthly reweight, no costs) | 5.81% | 0.429 | 35.2% |

References are indices, not tradable strategies (no costs modeled). The
zero-interest cash Sharpe is a definitional artifact (flat NAV against a
positive risk-free path); it documents the rf-subtraction convention.

## Inner-window selection (plan §8: "strongest simple control on inner
development data, not the final test")

Per-fold inner-window metrics across the 16 folds (development data only):

| strategy | mean inner CAGR | median inner CAGR | mean inner Sharpe | worst inner MaxDD | mean inner half-turn |
|---|---|---|---|---|---|
| B1 | 6.74% | 6.41% | 0.655 | 15.1% | 0.022 |
| B2 | 5.07% | 4.50% | 0.429 | 14.5% | 1.578 |
| B3-minvar | 4.99% | 6.56% | 0.756 | 12.3% | 0.107 |
| B3-ivvol | 4.89% | 5.90% | 0.622 | 13.3% | 0.039 |

**Selected strongest simple control: B1 (capped equal-weight, monthly
banded).** Rationale (disclosed): B1 has the highest inner mean and median
CAGR; the §1 primary gate is net CAGR (≥10%), so "strongest" is ranked on
inner CAGR. B3-minvar wins inner Sharpe (0.799 vs 0.658) and inner drawdown;
if the P4/P5 controllers are instead evaluated on risk-adjusted terms, B3-
minvar is the disclosed alternative control. B2 is weakest on CAGR and
turnover; its trend rule churns (1.35 annual half-turn vs B1's 0.054) and its
abstention sits in literal cash (plan §8 "cash when ineligible"). No strategy
passes the §1 gates (net CAGR ≥10%, excess Sharpe ≥1.00, daily MaxDD ≤15%):
**the honest P3 conclusion is "no demonstrated edge in the simple controls,
as expected for baselines"** — the §1 gates apply to candidate strategies
(P4/P5), not baselines.

## Fold table (B1; others analogous — `.tmp/p3_reports.json` untracked)

16 folds, fold 15 outer truncated (2026-07-27..2026-11-03, partial,
disclosed not skipped). Per-fold §1 metrics slice the continuous path
(`research/baselines/report.py::fold_table`).

## Disclosures (all strategies)

- **Zero failed fills; zero invariant violations** across 4850 sessions.
- **Partial fills** (residual abandoned, disclosed not retried): B1: 5
  cash-constrained rotations + 1 participation-capped; B2: 41 (all
  cash-constrained); B3-minvar: 54 cash + 14 participation; B3-ivvol: 7 cash
  + 14 participation. Participation caps bind only on BIL (early-sample ADV
  ~$5–18M vs 0.1% cap) and one early VEA fill.
- **Rejected (zero-fill) buys** where settled cash could not cover even one
  lot: B1: 1, B2: 0, B3-minvar: 8, B3-ivvol: 1. Not retried (conservative
  account rule; plan §3.1 "reject or resize orders that would violate funding
  limits").
- **Terminal liquidation skipped**: the panel ends at the final mark
  (2026-11-03); the next session does not exist yet. All NAV figures are
  pre-liquidation. When the panel extends (P6 prospective), the runner
  liquidates at the next session's open and includes its costs/turnover in
  the all-in evaluation (plan §6.4).
- **Warmup abstention**: decisions before trailing ADV exists (first ~20
  sessions) abstain order-by-order with warnings; no doomed orders are
  generated.
- **B2 reserve semantics**: abstention months hold literal zero-interest cash
  (plan §8), not BIL (a Treasury ETF costs money to enter/exit, §6.2).
- **B3 covariance excludes dividends** (close-to-close proxy variance,
  disclosed plan §8).
- **Fold 15 is partial** (outer window truncated at the panel edge),
  disclosed, not skipped (§7.4).
- The 60/40 reference re-weights monthly at the close with no costs — an
  index, not a tradable path.

## Test coverage

`research/baselines/test_baselines.py` (20 tests) + `research/execution/
test_ledger.py` (29 tests), covering the §9 required evaluation tests (rf
subtraction incl. zero-variance Sharpe=None, constant-price cases,
loss/drawdown sign conventions, CAGR annualization, missing-fold behavior,
all-in vs ongoing turnover reconciliation), strategy causality (future-price
perturbation leaves decisions and past NAV paths unchanged), caps enforcement,
warmup abstention, band suppression, whole-share flooring, the B2 cash
reserve, and full-report disclosure keys.
