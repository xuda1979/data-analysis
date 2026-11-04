# P5 Record — H3 slow risk budgets, A3/A4 study, stress tests

**Status:** complete (H3 controller + ablation, A3/A4 scoring, §6.3
stress/delay tests on the surviving candidate). All results are
**retrospective development diagnostics** on 2007-07-26..2026-11-03 (4850
sessions); every pre-T0 interval is development history per the
data-exposure registry (T0 = 2026-11-04). Nothing here is confirmation
evidence.

**Scope:** plan §5 H3, §8 candidate rows A3/A4/A4-loo, §6.3 stress grid
(mechanical replays, outside the 24-config trial budget); commits cf2c4d8
(H3 + runner monitor hook), fab3aab (A4 family).

## Framework

Runner `risk_targets` hook (`runner.py`): at every non-decision close the
controller's daily monitor may return mandate targets; these REPLACE
pending orders (newest decision wins; a de-risking cut cancels stale
buys) through the SAME order/ledger path with the no-trade band DISABLED
(predeclared reduction rule, plan §5 H3). Emergency fires append a
"risk monitor triggered" warning — the turnover is recorded, never hidden.
Base default None leaves P4 structurally unchanged (regression-tested).

`h3_risk.py` frozen constants (protocol): VOL_TARGET 10% annual,
DD_CAUTION 8% (m_dd→0.75), DD_REDUCE 12% (m_dd→0.50), RECOVERY 20 sessions
per +0.25 step, monitor breach tolerance 5% of NAV, 20-session realized
portfolio-vol forecast (shrinkage covariance). Monthly decide = B4's
cost-band gate on m-scaled targets, with one asymmetry exception: when the
budget SHRANK the target below the drifted weight (m < 1), the cut trades
regardless of the benefit-cost gate (risk budgets shrink fast). At m = 1
the static arm reproduces B4 exactly (NAV-path equality test).

Warmup / stale data = true hold (drifted weights, no blind liquidation);
zero-mu months = explicit per-symbol 0.0 targets through the risk-cut
path (P4's correction semantics carried over).

## H3 ablation (four arms, identical frozen forecasts)

Whole-path (2007-07-26 → 2026-11-03, $100k start, all-in costs):

| arm | NAV end | net CAGR | Sharpe | MaxDD | ann. half-turn | roll-252 max | trades | monitor fires |
|---|---|---|---|---|---|---|---|---|
| static (= B4) | $284,877 | 5.58% | 0.531 | 21.92% | 0.063 | 0.860 | 236 | 0 |
| vol-only | $291,232 | 5.70% | 0.543 | 18.35% | 0.622 | 3.361 | 574 | 45 |
| symmetric | $238,353 | 4.61% | 0.462 | 11.80% | 1.819 | 6.155 | 838 | 68 |
| asymmetric | $283,529 | 5.56% | 0.562 | 12.16% | 1.630 | 4.601 | 784 | 60 |

2020/2022 slices (risk episodes, plan §5 H3 "including 2020 and 2022"):

| arm | 2020 CAGR / SR / DD | 2022 CAGR / SR / DD |
|---|---|---|
| static | 14.68% / 1.489 / 12.40% | −14.01% / −1.449 / 21.73% |
| vol-only | 5.35% / 0.547 / 13.61% | −12.20% / −1.634 / 18.08% |
| symmetric | 8.56% / 1.042 / 10.08% | −6.67% / −1.750 / 9.98% |
| asymmetric | 7.51% / 0.783 / 12.16% | −3.73% / −0.971 / 8.01% |

Time underwater: static 669 sessions (90.3%), asymmetric 650 (89.4%) —
the monitor trims the depth of drawdowns, not their duration.

### Matched static-cash diagnostic (pre-registered rejection test)

A daily-rebalanced 53.0%-static / 47.0%-cash blend matches the asymmetric
arm's whole-path MaxDD (12.16%) but delivers only 3.00% CAGR / 0.362
Sharpe versus asymmetric's 5.56% / 0.562. **The drawdown improvement is
NOT explained by a matched static cash allocation** — the rejection test
in the H3 pre-registration passes. (The blend's hindsight risk match is
an explanatory diagnostic, not an investable rule; disclosed.)

### A3 verdict (trial row 8: B4 + H3 asymmetric risk budgets)

| promotion gate 2 margin | required | observed | verdict |
|---|---|---|---|
| Sharpe improvement over B4 | ≥ +0.15 | **+0.031** | **fail** |
| CAGR sacrifice | ≤ 0.5pp | −0.03pp | pass |
| drawdown deterioration | ≤ 1pp | −9.76pp (improves) | pass |

§1 candidate gates: net CAGR 5.56% < 10% (fail), Sharpe 0.562 < 1.00
(fail), MaxDD 12.16% ≤ 15% (pass), ann. half-turn 1.630 > 1.0 (fail),
rolling-252 4.601 > 1.5 (fail). **A3 fails promotion gate 2** — the
drawdown control is real and survives the cash-blend diagnostic, but the
Sharpe margin is absent and the monitor's emergency turnover breaches both
turnover gates. Negative result recorded.

## A4 family (trial rows 9-10)

A4 = B4 gate + H3 asymmetric budgets + daily monitor (the combination is
H3's asymmetric arm; H1/H2 components were refuted in P4 and are not
recombined). Leave-one-out variants isolate each component's marginal
contribution:

| variant | net CAGR | Sharpe | MaxDD | ann. half-turn | roll-252 max | dSharpe vs B4 | dDD vs B4 |
|---|---|---|---|---|---|---|---|
| A4 (full) | 5.56% | 0.562 | 12.16% | 1.630 | 4.601 | +0.031 | −9.76pp |
| A4-loo-vol | 5.08% | 0.446 | 15.22% | 1.416 | 5.360 | −0.085 | −6.71pp |
| A4-loo-dd | 5.70% | 0.543 | 18.35% | 0.622 | 3.361 | +0.012 | −3.58pp |
| A4-loo-monitor | 5.17% | 0.541 | 11.39% | 1.399 | 3.487 | +0.009 | −10.54pp |

Readings (disclosed judgment, not gate passes):

- The **drawdown term does the risk work** (loo-dd loses most of the dd
  improvement); the **vol term does the return work** (loo-vol costs
  0.48pp CAGR and 0.116 Sharpe).
- The **daily monitor adds little**: A4-loo-monitor (monthly risk cuts
  only) achieves a BETTER whole-path MaxDD (11.39% vs 12.16%) at lower
  turnover — the daily monitor's emergency sells add turnover without
  adding drawdown protection on this window. The asymmetric design's
  "separate daily risk monitor" (plan §5 H3) is not justified by this
  evidence; monthly decision cadence suffices.
- No variant passes promotion gate 2 (best dSharpe +0.031 < +0.15) or the
  §1 turnover gates. **A4 and every loo variant fail; no component
  combination beats the refuted parts.**

## §6.3 stress/delay tests (mechanical replays, outside trial budget)

Run on the strongest development candidate by drawdown (A4-loo-monitor)
and on B4 as control (whole-path, all-in costs):

| stress | B4 CAGR / DD / SR | A4-loo-monitor CAGR / DD / SR | reversal? |
|---|---|---|---|
| costs doubled (4bp+4bp, 2x impact) | 5.57% / 21.91% / 0.530 | 5.16% / 11.52% / 0.540 | no |
| costs tripled (6bp+6bp, 3x impact) | 5.59% / 21.90% / 0.532 | 4.90% / 11.56% / 0.508 | no |
| execution +1 session delay | 5.59% / 21.89% / 0.533 | 5.09% / 11.20% / 0.534 | no |
| account $10k | 4.66% / 22.68% / 0.419 | 5.66% / 11.50% / 0.598 | no |
| account $25k | 4.89% / 22.32% / 0.448 | 5.23% / 11.58% / 0.538 | no |
| account $1M | 5.87% / 22.14% / 0.573 | 5.29% / 12.81% / 0.558 | no |

The drawdown advantage is cost-, delay- and size-stable; at $10k the
A4-loo-monitor actually beats B4 on all three headline metrics (its
risk cuts avoid the 2022 commission drag that B4's idle holdings eat).
No stress reverses the economic conclusion (the dd improvement persists
under every stress; the promotion-gate Sharpe margin never appears —
the $10k cell's +0.18 dSharpe is a commission artifact at a stressed
size, not the §6 base-size gate). Detailed disclosures:
`.tmp/p5_stress.json`, `.tmp/p5_delay.json` (untracked).

## P5 conclusion

H3's asymmetric risk budgets deliver a real, cash-blend-surviving,
stress-stable drawdown improvement (−10.5pp MaxDD) at near-zero CAGR
cost, but **no configuration clears promotion gate 2's Sharpe margin
(+0.15) or the §1 turnover gates on development data**. Per the plan's
admission sequence, nothing advances to confirmation (P6) as a candidate;
the honest P5 headline is a negative result with one validated diagnostic:
drawdown control via asymmetric budgets works mechanically, and its
monthly-only form dominates the daily-monitor form. The next session of
the study (P6) continues with the strongest simple control (B1) and B4 as
reference paths — no candidate claims.

## Trial registry rows scored here

Row 8 (A3): scored 2026-11-05, FAIL gate 2 (table above). Row 9 (A4):
scored 2026-11-05, FAIL gate 2. Row 10 (A4-loo-*): scored 2026-11-05 as
the three-variant family, all FAIL gate 2. Registry updated in
`research/registries/data_exposure_v1.md`.

## Test coverage

`research/controllers/test_h3_risk.py` (14): static==B4 NAV-path equality,
tier boundaries (float-safe), fast-shrink/gradual-recovery arithmetic,
monthly decision risk-cut gating (only when m < 1), warmup true-hold,
monitor replace-pending-orders with band disabled, monitor sells-only and
allocation respect, tolerance silence, monitor silent before first
decision, causality under future perturbation, emergency turnover
recorded, base-default None leaves P4 unchanged. Full suite: 100 passed
(86 prior + 14 H3).
