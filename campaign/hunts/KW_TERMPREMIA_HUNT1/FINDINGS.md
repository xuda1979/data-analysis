# FINDINGS — KW TERMPREMIA HUNT1 (rates-side direction 4)

**Date:** 2026-11-06. Pre-registered spec: FINDINGS_PRECOMMIT.md (commit e96d87c,
sha256 d64424e4a8a2ae75e5860d62b422f6c0b1a2662a1d9e57c33cda77a781ebadbe).
This document reports results exactly per the sealed spec, including the
pre-registered falsification criteria. No hyperparameter was changed after
seal; all numbers below are from the single frozen run (`run_arms.py`,
`work/arm_results.json`).

---

## VERDICT: NEGATIVE. No treatment arm passes G1–G6.

**H0 (KW TP state carries no prospective champion-timing information): NOT
REJECTED — H0 stands.**

**H1 (deeply compressed trailing-z term premia identify prospective champion
headwind regimes): REJECTED.** The de-risk episodes the signal selects are
slow, shallow, low-volatility drags — they reduce CAGR in near-exact
proportion to the volatility they remove, and they never overlap the
champion's only meaningful drawdown.

**G6 holds (P dSR −0.219, N dSR −0.132, both fail G1): the machinery is
VALID. This is an honest negative, not a defect.** Per the sealed decision
rule: FINDINGS.md negative + DEAD_IDEAS.csv row; advance to next axis.

The pre-registered refutation branch **"any pass driven by CAGR sacrifice >
0.5pp → fail G2, refuted"** was TRIGGERED by Arm B: its G1 pass (+0.246) is
bought with −3.88pp of CAGR — roughly 8× the allowed sacrifice.

---

## 1. Arm results (champion window 2008-03-31..2026-08-28, n=4806, identical
conventions/costs: T+1 causality, full-book |Δg| × 6.4 bps one-side, freed
capital 0%)

| | SR | dSR | CAGR | dCAGR (pp) | MDD | neg yrs | worst yr | half-turn (ann / roll-252) | toggles | % sessions de-risked |
|---|---|---|---|---|---|---|---|---|---|---|
| **Champion** | 3.7845 | — | 23.861% | — | −3.305% | 0 | +7.55% (2013) | — | — | — |
| **A** z<−1.0→0.7 | 3.9230 | +0.1385 | 21.013% | −2.848 | −3.305% | 0 | +6.13% | 0.142 / 0.60 | 18 | 30.1% |
| **B** z<−1.5→0.5 | 4.0304 | **+0.2459** | 19.982% | **−3.879** | −3.305% | 0 | +5.22% | 0.131 / 0.50 | 10 | 24.7% |
| **C** slope (TP10−TP1) | 3.9165 | +0.1320 | 21.026% | −2.835 | −3.305% | 0 | +6.13% | 0.110 / 0.45 | 14 | 29.6% |
| **P** placebo (time-reversed) | 3.5655 | −0.2190 | 20.548% | −3.313 | −3.305% | 0 | +5.00% | 0.299 / 1.50 | 38 | 47.8% |
| **N** random (seed 20261106) | 3.6525 | −0.1320 | 21.038% | −2.823 | −3.252% | 0 | +5.62% | 9.55 / 12.90 | 1214 | 18.2% |

Champion metrics verified byte-exact against the pinned series (daily sha16
`a8ed233bd0f6fd5d`): SR 3.784489, geometric CAGR 23.861%, MDD −3.3048%, 0
negative years — matching precommit §3 exactly.

## 2. Gate battery vs the sealed decision rule

| Gate | Criterion | A | B | C | P | N |
|---|---|---|---|---|---|---|
| G1 | dSR ≥ +0.15 | FAIL (+0.138) | **PASS** (+0.246) | FAIL (+0.132) | FAIL (−0.219) | FAIL (−0.132) |
| G2 | CAGR sacrifice ≤ 0.5pp | **FAIL** (−2.85) | **FAIL** (−3.88) | **FAIL** (−2.83) | FAIL | FAIL |
| G3 | MDD within champ+1pp | PASS | PASS | PASS | PASS | PASS |
| G4 | ann half-turn ≤ 1.0 | PASS | PASS | PASS | PASS | FAIL (9.55) |
| G5 | roll-252 ≤ 1.5 | PASS | PASS | PASS | PASS | FAIL (12.9) |
| **G6** | P and N both FAIL G1 | — | — | — | — | **PASS (machinery valid)** |

No treatment arm passes G1–G6: A and C fail G1 *and* G2; B passes G1 but
fails G2 catastrophically. Adoption requirements (moot, no candidate):
A-R1 FAILS for every arm (MDD identical to champion, never strictly
shallower); A-R2 holds everywhere (0 negative years preserved, all worst
years still positive).

Turnover gates G4/G5 were never binding: the hysteresis rule trades rarely
(10–18 toggles over 18.5 years). The failure is entirely in the
risk-adjusted-return economics, not in implementation cost.

## 3. Why the arms failed (falsification analysis)

**Pre-registered activity bounds:** de-risk active 24.7–30.1% of sessions —
inside the sealed 2%–60% band. Neither "inert" nor "regime label"
falsification triggered. The mechanism fires, and fires moderately; it just
doesn't fire where it pays.

**The structural finding — the signal never meets the champion's tail.**
The champion's only meaningful drawdown is −3.30% over 2023-12-27..
2024-01-11. During that 12-session window, Arm A was de-risked **0 of 12
sessions** (B and C likewise): TP10 z was above every de-risk threshold.
The KW compression episodes the signal does select (2008–2021, last toggle
2021-02-26 for Arm A) are slow, shallow, low-volatility drags. De-risking
into them cuts volatility and CAGR in near-proportion, which is why MDD is
byte-identical to the champion on every arm and dSR is small. **A
forward-looking market-implied TP level is a rate-regime label, not a
champion-tail timing signal: the champion's tail events happen at ordinary
TP levels.**

**Where the (failed) improvement concentrates — post-2020.** Report-only
bins: IS (<2017) dSR is slightly negative on all treatment arms (−0.03..
−0.05); OOS (≥2017) dSR positive (A +0.194, B +0.326, C +0.192); all of it
post-2020 (2020–2026 bins: A +0.244, B +0.373, C +0.247), while 2014–2019
bins ≈ −0.15 and 2008–2013 ≈ 0. Even the in-window improvement is a single
regime episode (the 2020–2021 rate compression + 2022 repricing cycle), not
a distributed effect. With IS negative, this profile could never support a
promotion even if the full-window gates had passed.

**Cost stress (report-only):** 8 and 10 bps one-side move Arm B dSR by
<0.002 (+0.245 / +0.244). The negative verdict is not a cost artifact — it
is a signal-quality result.

## 4. Honest caveats

1. KW TP is current-view FRED (not ALFRED vintage); revision structure not
   tracked (disclosed at seal).
2. The overlay operates on the pinned composite daily series; sleeve-level
   reallocation was not locally evaluable (disclosed at seal). This cannot
   rescue the result: the composite-level dSR/dCAGR/MDD deficits are far
   larger than any plausible sleeve-level refinement.
3. The g grid {0.7, 0.5} and thresholds {−1.0, −1.5} are a coarse
   pre-registered grid, not a tuned optimum — by design. A finer grid might
   find a marginally better point, but G2 fails by 5–8× the allowed margin;
   no plausible grid refinement closes that.
4. One execution note for audit: the first `run_arms.py` run crashed before
   producing any metrics (numpy datetime/float promotion error in
   reindexing, fixed before interpretation). All reported numbers are from
   the corrected single run; no arm output was ever observed pre-fix.

## 5. What survives (for DEAD_IDEAS.csv and next steps)

- **DEAD_IDEAS entry (this hunt):** see row appended 2026-11-06 —
  KW term-premia (THREEFYTP) trailing-z de-risk overlay on champion.
- **Surviving asset 1 — the data panel:** 13 KW/ACM-adjacent FRED series
  (THREEFYTP1–10, THREEFY2/5/10), daily 1990-01-02..2026-10-30, sha256
  pinned in precommit §2, under `data/`. Lawfully re-usable for any future
  *conditioning* use (e.g., regime stratification of other signals) under a
  new pre-registration — the axis is dead as a *direct champion-timing
  overlay*, not as data.
- **Surviving asset 2 — method knowledge:** the negative has a sharp,
  transferable structure — **market-implied term-premia levels do not
  time this champion's tail.** Combined with HUNT_VOL2/VXV_TERM (vol-surface
  gates) and HUNT_TREASFUT (curve shape), the evidence now says the
  champion's −3.3% MDD is not reachable ex-ante from any free rates/vol
  state variable tested to date. Any future de-risk hunt should first
  demonstrate *in-sample overlap with the champion's actual drawdown
  windows* before scoring gates (a necessary-condition pre-screen).
- **Trial registry:** zero unlevered_v1 slots consumed (champion-campaign
  hunt, TVPVECM precedent). No re-runs, no added arms.

## 6. Provenance

- Code: `campaign/hunts/KW_TERMPREMIA_HUNT1/run_arms.py` (frozen artifact,
  implements precommit §3–§5 exactly; champion row-count pin 4806 enforced).
- Data: `data/fred_{THREEFYTP1..10,THREEFY2,THREEFY5,THREEFY10}.csv`
  (FRED fredgraph keyless fetch 2026-11-06, sha256 pins in precommit §2);
  champion `campaign/results/GOAL100_RAWEW13v2_WEIGHTED_GEAR16_daily.csv`
  (sha16 `a8ed233bd0f6fd5d`, verified at run).
- Outputs: `work/arm_results.json` (all metrics + gates),
  `work/{g,ret}_{A,B,C,P,N}.csv` (exposure/return series).
- Run environment: .venv Python 3.12, numpy 2.x, pandas 3.x.
- Seal: commit e96d87c (FINDINGS_PRECOMMIT.md + .sha256 sidecar) BEFORE
  any measurement; measurement run 2026-11-06 after seal.
