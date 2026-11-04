# P4 Record — Controller framework, H1 hold/trade threshold arms, H2 turnover budget

**Status:** complete (P4a framework, P4b protocol, P4c H1, P4d H2, P4e
enumeration check). All results are **retrospective development
diagnostics** on 2007-07-26..2026-11-03 (4850 sessions); every pre-T0
interval is development history per the data-exposure registry
(T0 = 2026-11-04). Nothing here is confirmation evidence.

**Scope:** plan §5 (H1, H2), §6 (clocks/costs/turnover — inherited from the
P3 runner), §9 (tests). Protocol `research/protocols/unlevered_v1.json`.

## Framework (P4a/P4b, committed cd84009)

Frozen forecast module `forecasts.py` (identical inputs for every arm and
controller downstream — the ablation requirement):

- Trend ensemble: 63/126/252-session total-return windows, rf-detrended,
  scaled to HORIZON = 63 sessions, long-only `max(0, mu*H)`.
- Shrinkage covariance: 252-session lookback, shrink 0.25 (reuses the P3
  B3 machinery).
- Blocked-validation forecast error: 21-session blocks, trailing 8 blocks,
  EW decay 0.94; `None` before block_start+63 <= i (staleness explicit,
  never zero-filled).
- Capped long-only mean-variance targets: projected gradient, 200 iters,
  step 1/(ra*max_diag), `apply_caps` projection, ra = 4.0, mu/HORIZON
  daily scaling. **All-zero mu (negative trend everywhere) legitimately
  returns {} — the MV optimum is the reserve.**

Controller protocol (`base.py`, integrated in `runner.py`):
`decide(panel, i, ledger, nav, marks)` at monthly checkpoints (required);
`on_fill(fill, pretrade_nav)` after every fill attempt; `on_session(panel,
i, ledger)` every close. `controller=None` leaves the baseline path
structurally unchanged.

**Zero-mu semantics correction (2026-11-04, found during P4d):** the first
H1/H2 implementation conflated warmup (no covariance history) with the
all-zero-mu month (valid data, MV optimum = reserve): both returned {} from
`mean_variance_targets`, and the controllers' early `return {}` handed the
runner an empty target dict — which the runner's reserve routing reads as
"park 100% in BIL", i.e. a FULL LIQUIDATION every zero-mu month (13 of 232
decision months). Every arm therefore liquidated identically on exactly the
de-risking months the ablation was designed to distinguish, and (b)/(c)/(d)
also liquidated on warmup months mislabeled "hold-all". Fixed: warmup =
true hold (return drifted weights); zero-mu = explicit per-symbol 0.0
targets so each arm applies its own rule to the sells. All numbers below
are post-correction; the pre-correction H1 table and (d)-vs-(b) verdict
(supported on half-turn/MaxDD, refuted on CAGR) are retained in git history
and are superseded.

## H1 arms (P4c)

Four arms on the identical frozen forecasts; only the hold/trade rule
differs (`h1_hold.py`). Frozen constants: DELTA = 10bp, cost scenarios
(1.0, 2.0), 15bp round-trip floor.

| arm | rule |
|---|---|
| (a) monthly | trade to targets every decision |
| (b) cost-band | trade iff expected benefit > doubled-cost scenario (B4 control arm) |
| (c) error-band | (b) + blocked-validation error discount |
| (d) full | G = benefit − risk − error − cost; trade iff G > 10bp |

Whole-path results (2007-07-26 → 2026-11-03, $100k start, all-in costs):

| arm | NAV end | net CAGR | Sharpe | MaxDD | ann. half-turn | roll-252 max | trades |
|---|---|---|---|---|---|---|---|
| (a) monthly | $330,833 | 6.40% | 0.678 | 12.13% | 2.234 | 4.774 | 630 |
| (b) cost-band | $285,357 | 5.59% | 0.533 | 21.86% | 0.062 | 0.853 | 236 |
| (c) error-band | $292,709 | 5.73% | 0.605 | 21.64% | 0.085 | 0.897 | 91 |
| (d) full | $287,358 | 5.63% | 0.561 | 21.59% | 0.086 | 0.662 | 62 |

### Pre-registered ablation verdict (d) vs (b) — plan §5 H1

| margin | required | observed | verdict |
|---|---|---|---|
| half-turn reduction | ≥ 20% | **+38.4%** (0.062 → 0.086) | **refuted** |
| net CAGR loss | ≤ 0.5pp | +0.04pp (5.59% → 5.63%) | supported |
| MaxDD worsening | ≤ 1pp | −0.27pp (21.86% → 21.59%, improves) | supported |

Per-fold medians (16 development folds): half-turn −1.4% (7/16 folds
≤ −20%), CAGR +0.80pp (12/16 within −0.5pp), MaxDD −0.56pp (11/16 within
+1pp). **The pre-registered H1 hypothesis is REFUTED: (d) does not reduce
turnover ≥ 20% versus (b) once the zero-mu months route through each arm's
own rule.** The turnover margin fails because with (b) nearly idle after
2020 (0.062 ann. half-turn), (d)'s risk term (G includes the risk penalty)
admits MORE de-risking trades than (b)'s pure benefit>cost gate. Negative
result recorded; H1's added complexity is not justified on this window.

Honest headline: **plain monthly trading (a) dominates every threshold arm
on Sharpe (0.678 vs 0.53–0.61) and MaxDD (12.13% vs 21.6–21.9%)** at the
cost of 26–36x the turnover (2.234 vs 0.06–0.09 half-turn). The admission
rules do not distinguish good from bad trend trades on this window; their
main effect is to hold ~82% risky through 2022 (troughs: (b) 2022-10-20 at
21.86% vs (a) 2020-03-18 at 12.13%). The de-risking value of acting on
zero-mu months accrues to whichever arm actually trades them — (a).

### Rejected-buy disclosure (banded arms)

The band arms concentrate buys in strong-signal months with no accompanying
sells. Funded from settled cash alone, the deterministic universe order
lets the first buy absorb the cash; later same-rotation buys are
zero-fill rejected (conservative account rule, disclosed not retried).
Arm (a): 11 rejected buys. Partial fills: (a) 131. Zero failed fills and
zero invariant violations across all arms.

### Decision log (plan §5 completeness)

Every trade/hold row: session, arm, symbol, rejected target, drifted
weight, dw, action, constraint, predicted benefit, cost interval (lo, hi);
arms (c)/(d) add the error discount; (d) adds risk penalty and G. Holds
return the drifted weight so the runner emits no order (holds are real
holds). 23 warmup months per arm log hold-all with drifted weights
returned (no liquidation).

## H2 arms (P4d)

Three spending rules on the identical frozen forecasts, identical rolling
budget container (ANNUAL_BUDGET = 1.0 half-turn per rolling 252 sessions,
actual fill turnover spent via on_fill; refills as old spend expires; the
early-consumption penalty is structural) (`h2_budget.py`):

| arm | rule |
|---|---|
| uniform | no cost gate; descending-benefit admission until the pro-rata monthly allowance |
| fixed-bands | H1(b) cost gate, then admission until the remaining budget |
| persistence | cohort holds with live forecast (no order); risk-mandated exits on hypothesis failure override the budget; entries/top-ups ranked by net benefit per turnover |

Whole-path results (2007-07-26 → 2026-11-03, $100k start, all-in costs):

| arm | NAV end | net CAGR | Sharpe | MaxDD | ann. half-turn | roll-252 max | trades | median FIFO hold |
|---|---|---|---|---|---|---|---|---|
| uniform | $334,569 | 7.37% | 0.585 | 21.28% | 0.399 | 1.068 | 239 | 489d |
| fixed-bands | $310,276 | 5.59% | 0.533 | 21.86% | 0.062 | 0.853 | 236 | 579d |
| persistence | $199,961 | 4.81% | 0.559 | 10.61% | 1.051 | 1.753 | 296 | 911d |

Ablation reading (plan §5 H2: "compare equal turnover budgets with uniform
monthly spending, fixed bands, and persistence-based spending"):

- **uniform** achieves the highest net CAGR (7.37%) — spending the budget
  on the highest-expected-benefit trades each month regardless of costs
  beat every cost-aware rule on this window.
- **persistence** achieves the lowest MaxDD (10.61%, the only arm under
  the 15% gate) and the longest realized holding time (911d median FIFO)
  — its risk-mandated exits (420 over the path) de-risk when trends flip
  — but pays for it with the lowest CAGR (4.81%) and breaching the
  rolling-252 turnover gate (1.753 > 1.5): risk exits spend real turnover
  the budget cannot refuse.
- **fixed-bands** matches H1(b) identically by construction (same gate,
  budget never binds) — its budget container never constrains because the
  gate admits almost nothing.
- None of the three passes the §1 candidate gates (net CAGR ≥ 10%,
  excess Sharpe ≥ 1.00). No arm demonstrates that budget-aware spending
  beats uniform monthly spending on net CAGR; the only advantage found is
  persistence's drawdown control, which comes from its exit rule, not from
  budget allocation.

Disclosures: zero failed fills across all arms; persistence's
rolling-252 turnover gate breach (1.753 vs 1.5 max) is a gate failure,
recorded, not tuned away — risk-mandated exits are the design's stated
override ("risk-mandated reductions may override this threshold, but their
costs and turnover remain visible").

## Trial registry

Rows 5–7 (B4, A1, A2) remain registered. H1 arm (b) = B4's rule; H2
uniform = the A2-family's simplest instance. The refutations above mean:
A1 (H1 threshold on B4) is NOT justified on development evidence; A2's
budget mechanism shows no net-CAGR advantage over uniform spending, but
its persistence variant's MaxDD profile (10.61%) is the one result in P4
that would justify carrying a component forward to A4 evaluation on
risk-adjusted grounds — disclosed as a judgment call, not a gate pass.

## Test coverage

`research/controllers/test_forecasts.py` (7), `test_p4.py` (6, incl. the
hash-seed invariance regression), `test_h1_hold.py` (7),
`test_h2_budget.py` (8: budget spends actual fill turnover, risk-exit
override with visible negative remaining, live-cohort holds,
budget-blocked candidates logged with benefit (opportunity-lost proxy),
synthetic FIFO holding times, causality under future perturbation,
warmup-returns-drifted-weights regression), `test_enumeration.py` (3:
exact fee/rounding check against small-universe enumeration — commission
closed-form boundaries incl. the 1% cap region, enumerated 2-symbol
integer allocations fee-exact through the ledger with cash floor, runner
slice whole-share/cash invariants). Full suite: 80 passed.

Enumeration note (plan §5 H2): the runner's greedy whole-share flooring
is verified FEASIBLE against the enumerated set — it is not claimed to be
the optimum of the nonconvex integer problem ("do not claim a convex
optimum when ticket minima or discrete selection make the problem
nonconvex").
