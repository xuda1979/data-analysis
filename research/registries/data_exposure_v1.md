# Data-exposure registry — unlevered_v1

**Frozen:** 2026-11-04 (P0). Purpose: plan §7 requires an inventory of prior experiments before
performance claims, classifying which history is development history. This registry is that
inventory. It is append-only; entries are never removed after scoring begins.

## Classification rule

Per plan §7: *all dates used in prior repo model/strategy selection are **development history**,
even if an old report calls them OOS.* Renaming dates or changing cutoffs does not restore
independence. Consequence for this protocol: any historical window touched by the prior campaign
can be used for **development** (training, inner validation, hyperparameter selection) but can
never serve as the "fresh historical holdout" of promotion gate 4. Primary confirmation for this
protocol starts on the first eligible session after T0 = 2026-11-04, plus whatever genuinely
untouched history P1 certifies (see "Not development history" below).

## 1. Development history (prior campaign exposure)

| Prior use | Instruments / data | Approximate window | Evidence |
|---|---|---|---|
| GOAL100 campaign (60+ iters, champion ITER61_DDCON) | SPY, IEF, TLT, GLD, TIP, BIL + ~80 sleeve_library return series (CTA, credit-z, stat-arb pairs, factor momentum, merger arb, L/S, XGB1y, global macro, risk parity) | 2008-01..2026-08 daily | `campaign/results/sleeve_library/` (83 series, earliest 2008-01-03/2008-02-01), `BLOTTER_CHAMP_RAWEW13v2_GEAR16.csv` (2008-03-31..2026-08), `CHAMPION_CARD.md` |
| TVP-VECM HUNT1 (2026-11-03) | WTI/Brent spot, gold/silver, natgas/WTI, IG/HY credit spreads (FRED + local CSVs) | 1986..2026 weekly | `campaign/hunts/TVPVECM_HUNT1/` (executed end-to-end; NEGATIVE) |
| H1 tail-factor accrual | SPY/QQQ/... option-chain daily distribution features | 2026-09..present daily, forward-collected | `campaign/agents/H1_optiontail_results/`, `tools/quant/data/cboe_options/archive/` |
| Earlier hunts (DEAD_IDEAS.csv, 76 entries) | Equity factors, FX carry, energy spreads, vol overlays, macro gates, reversal/momentum L/S, gold macro maps, rates curve | mixed; includes 1926+ factor data, 1986+ credit, 2008+ equity sleeves | `campaign/results/DEAD_IDEAS.csv` |
| alphaportfolio_replication walk-forward | Long/short weights with half-turn cost convention | mixed | `alphaportfolio_replication/run_walkforward_realcost.py` |

**Operational consequence:** with Alpaca's free history starting 2016, the earliest usable price
history is 2016-01-04 at best. That entire window overlaps the prior campaign's evaluation
windows above. Therefore under this protocol, **2016..T0 is development history in full**; the
plan's 36m/12m/12m rolling design yields earliest outer evaluation ≈ 2020, and every outer
interval through T0 is a *retrospective development diagnostic*. Promotion gate 4 (confirmation)
can only be satisfied prospectively after T0, or on history certified untouched in §3.

## 2. Data never touched by prior selection

- Alpaca Basic daily OHLCV for the 8-fund universe (never fetched by this repo as of T0 —
  Alpaca adapter does not exist yet; P1 must certify actual entitlement/coverage).
- Any Twelve Data cross-check series (never fetched).
- ETF corporate-action records (splits/distributions) from issuers/SEC filings for the 8 funds
  (the repo has never parsed these; `campaign/TRADE_RECORD_STANDARD.md` uses synthetic fills).
- Explicit-vintage ALFRED panels (repo used FRED current-view fredgraph.csv only).
- Any session after T0 = 2026-11-04 (prospective by construction).

## 3. Claim boundary

A "fresh historical holdout" claim for any pre-T0 interval requires evidence that interval did
not inform prior selection. Absent that evidence, the interval is development history. This
registry currently certifies **no** pre-T0 interval as fresh. The system must be able to conclude
"no demonstrated edge yet."

## 4. Trial registry (append-only)

Max 24 development configurations for the first study (roles and seeds declared before scoring;
mechanical stress replays excluded). Registered at P0:

| # | ID | Role | Status |
|---|---|---|---|
| 1 | B0 | Zero-interest cash / Treasury reserve / equity buy-and-hold / 60-40 reference | scored 2026-11-04 (P3 record `research/baselines/P3_BASELINES.md`; development history) |
| 2 | B1 | Capped equal-weight, monthly banded rebalance | scored 2026-11-04 (P3 record; selected strongest simple control on inner development data; numbers corrected same-day for the hash-seed determinism bug, see P3 record header) |
| 3 | B2 | Fixed 126-session trend/RS rule, long-only, monthly | scored 2026-11-04 (P3 record; literal-cash abstention per plan §8; corrected as above) |
| 4 | B3 | Shrinkage min-variance + capped inverse-vol, no borrowing | scored 2026-11-04 (P3 record; both variants under one trial row, per protocol; corrected as above) |
| 5 | B4 | Forecasts + fixed no-trade bands + realistic costs (primary control) | scored 2026-11-04 as H1 arm (b) (P4 record `research/controllers/P4_CONTROLLERS.md`; whole-path 5.59% CAGR / 21.86% MaxDD / 0.062 half-turn; development history) |
| 6 | A1 | B4 + H1 uncertainty/cost hold threshold | scored 2026-11-04 as H1 arms (c)/(d) (P4 record); pre-registered (d)-vs-(b) margins refuted on turnover (+38.4% vs required −20%); not justified on development evidence |
| 7 | A2 | B4 + H2 turnover budget | scored 2026-11-04 as H2 arms uniform/fixed-bands/persistence (P4 record); no net-CAGR advantage over uniform spending; persistence's MaxDD profile (10.61%) carried forward to A4 evaluation on risk-adjusted grounds (disclosed judgment call, not a gate pass) |
| 8 | A3 | B4 + H3 asymmetric risk budgets | scored 2026-11-05 (P5 record `research/controllers/P5_H3_COMBINED.md`); FAIL promotion gate 2 (dSharpe +0.031 < +0.15) and §1 turnover gates (roll-252 4.601 > 1.5); dd improvement −9.76pp survives the matched static-cash diagnostic |
| 9 | A4 | Combined controller | scored 2026-11-05 (P5 record); = B4 gate + H3 asymmetric + daily monitor; FAIL gate 2 (dSharpe +0.031); §1 turnover gates fail |
| 10 | A4-loo-* | Leave-one-component-out variants of A4 | scored 2026-11-05 (P5 record; loo-vol / loo-dd / loo-monitor); all FAIL gate 2; loo-monitor dominates full A4 (MaxDD 11.39% vs 12.16% at lower turnover — the daily monitor adds no dd value on this window) |

### Correction addendum (2026-11-04, post-P4, commit 26a4d3b)

Rows 1–7 were scored under a runner with two timing defects (P3 record's
second correction header documents both): (i) ALL pending orders filled at
t+1's open, so rotation buys spent same-rotation sells' unsettled proceeds
(plan §3.1 violation); (ii) ex-date dividends credited after fills instead
of before. All rows were re-scored the same day under the corrected
session-aware dispatch; rows are NOT consumed twice — the addendum
supersedes the original numbers in place, per the append-only rule
(entries are never removed; the correction is recorded, not hidden).

Corrected headline numbers (whole-path, development history):

| # | ID | corrected headline |
|---|---|---|
| 1 | B0 | unchanged (bookkeeping paths, no fills) |
| 2 | B1 | $320,686 / 6.23% CAGR / 0.550 Sharpe / 24.3% MaxDD |
| 3 | B2 | $248,939 / 4.85% / 0.450 / 14.6% |
| 4 | B3 | minvar $231,486 / 4.45% / 0.551 / 16.4%; ivvol $235,896 / 4.55% / 0.519 / 18.5% |
| 5 | B4 | $284,877 / 5.58% / 0.531 / 21.92% / 0.063 half-turn |
| 6 | A1 | refuted stands: (d)-vs-(b) half-turn +39.3% vs required −20%; CAGR +0.19pp, MaxDD +0.26pp within margins |
| 7 | A2 | uniform best CAGR (6.52%); persistence MaxDD 9.37%, rolling-252 breach 1.792 > 1.5 persists |

Every pre-registered verdict is unchanged by the correction.

Remaining budget: 14 unallocated slots. Every added candidate, failed run, manual rule change,
and abandoned family gets a row here before scoring. Combining winning parts is an additional
registered candidate, not a free improvement.
