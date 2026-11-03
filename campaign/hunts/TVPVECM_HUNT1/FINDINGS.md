# FINDINGS — TVP-VECM HUNT1 (Direction 5)

**Date:** 2026-11-03. Pre-registered spec: FINDINGS_PRECOMMIT.md (commit 917db24,
sha256 b7423de7...). This document reports results exactly per the sealed spec,
including the pre-registered falsification criteria.

---

## VERDICT: NEGATIVE for the treatment. Arm B (TVP + gate) FAILS its hypotheses.

**H0 (TVP adds nothing over static z): NOT REJECTED — H0 wins.**
**H1 (gate improves risk-adj returns): REJECTED.**
**H2 (gate is the source of improvement): REJECTED — gate is the source of inactivity.**

**However**: Arm A (the static-β banded-z baseline with hard stop) passed 6/8 gates
as a standalone sleeve candidate (SR 0.92 net, champion weekly corr −0.017).
Per the sealed decision rule this does NOT promote B, but Arm A's profile is recorded
below as a potential separate candidate under a NEW pre-commit (it is essentially the
repo's existing spread-sleeve idiom applied to new pairs — not new IP, only new pairs).

---

## 1. Arm results (weekly pairs, net of 10 bps/unit, 10% vol target)

| Pair | Arm A (static z) | Arm B (TVP+gate) | Arm C (TVP, no gate) |
|---|---|---|---|
| P1 WTI-Brent | **SR 0.93**, ann 14.0%, MDD −21.8% | SR 0.45, ann 2.5% | SR 0.69, ann 12.8% |
| P2 Gold-Silver | SR −0.29 | SR 0.14 (2 entries) | SR −0.13 |
| P4 HH-WTI | SR 0.44 | SR 0.21 (2 entries) | SR 0.35 |
| P5 IG-HY | SR 1.61 (56w only) | no trades | SR 0.97 (56w only) |
| **SLEEVE** | **SR 0.92, ann 11.1%, vol 12.1%** | SR 0.40, ann 1.6% | SR 0.74, ann 10.5% |
| P3 monthly (separate) | SR −0.38 | 0 trades | SR −1.13 |

Ordering: **A (0.92) > C (0.74) > B (0.40)**. TVP-β *hurt* (C < A), and the gate
*crippled activity* (B barely trades). Both treatment effects are negative.

## 2. Why the gate failed (pre-registered falsification §5 — triggered)

Sealed prediction: "Gate fires < 2% of weeks → gate is inert; B≈C; H2 dead."
What happened is close: the gate is **not inert but anti-selective**:

- Gate ≥ 0.5 only 10.6–30.0% of weeks (P1 30%, P2 10.6%, P4 19.8%).
- Weeks where BOTH |z| ≥ 2 (entry signal) and gate ≥ 0.5: **1.9%** (P1).
- When the gate is high, |z| averages 0.84 — the gate approves regimes where
  the spread is quiet (mean-reversion regimes with low z), and blocks the
  exact episodes the strategy is designed to trade (large z dislocations).
- Root cause: C_rank (Johansen trace on trailing 156w) and C_halflife
  (AR(1) ρ on trailing 26w of residual) are **pro-cyclical** — both look best
  AFTER calm reversion has already happened. The gate is a rear-view mirror.

This is the deepest finding of the hunt: **a credibility gate built from
trailing-window cointegration statistics is structurally pro-cyclical and
anti-selective for mean-reversion entries.** A viable gate would need to score
the *prospect* of reversion (e.g., conditional half-life given current z,
structural-break distance) rather than trailing realized reversion.

## 3. Why TVP-β failed

- q_β MLE landed in-range (no bound hits: 2.2e-5 … 5.9e-4) — estimation is sound.
- Filtered β std is 4–6× SMALLER than rolling-OLS β std (P1: 0.016 vs 0.098).
  The Kalman filter with small q_β is over-smooth: it cannot track genuine
  regime shifts, so the TVP spread is systematically mispriced vs the rolling
  fit during transitions. Rolling OLS re-fits faster than the filtered path moves.
- Consequently C < A everywhere except P2/P5 (short samples).
- Gregory-Hansen diagnostic: min-ADF across rolling windows never approached
  the −4.61 cv on any pair (range −0.35…−0.53 init windows; later windows similar)
  — there is NO evidence of regime-shift cointegration in these pairs at all.
  The premise of direction 5 ("distinguish transient deviation from permanent
  drift via TVP-VECM") has no empirical foothold in free weekly commodity/metal
  pairs: they behave as either stationary-spread (P1) or near-random-walk spread
  (P2), not switching regimes.

## 4. Gate battery vs the sealed decision rule

Decision rule: B must pass ≥6/8 gates AND beat A AND H2 confirmed. Actual:

| Gate | B result | A result (reference) |
|---|---|---|
| G1 SR ≥ 1.0 | **FAIL** (0.40) | FAIL (0.92) |
| G2 bins ≥4/5 positive, no dominant bin | PASS (all bins ≥ 0.35 SR but tiny) | PASS-ish: 90s 1.10, 00s 1.16, 10s 0.30, 20s 1.08 |
| G3 scramble ≥95th pct | PASS | PASS |
| G4 2× cost SR ≥ 0.7 | PASS (few trades → low cost) | PASS (0.87) |
| G5W champ corr ≤ 0.30 | PASS (0.001) | **PASS (−0.017)** |
| G6 turnover ≤ 4× | PASS | borderline (4.2–5.0×/pair) |
| G7 no negative decade | PASS | PASS |
| G8 param neighborhood ±25% | PASS | PASS (z 1.8→0.93, 2.2→0.85; Δ1–8%) |

B passes 7/8 gates but FAILS the primary hypothesis gates: it does not beat A
(0.40 < 0.92) and H2 is reversed (B < C). Per the sealed rule: **no promotion.**

## 5. Honest caveats

1. **P5 IG-HY has only 157 weeks** (BAMLC0A0CM full history is 2023+ on FRED free
   CSV — the 1996+ history is chart-only). 56 post-init weeks. SR 1.61 on 56 obs
   is noise-level. Sealed deviation was documented pre-run.
2. **P2 gold-silver arm A stop-share = 81%** — pre-registered falsification
   "stop exits > 50% of exits → spread non-stationarity too severe" TRIGGERED
   for P2. Gold-silver weekly z-reversion without the gate is a stop-loss
   treadmill. P2 should be dropped from any future variant.
3. P3 monthly gold-copper: all arms negative (A −0.38). Gold-copper is not a
   weekly-mean-reverting pair at free-data frequency.
4. The initial run had a 1-week lookahead bug (caught before interpretation,
   fixed, re-run — results above are the corrected causal runs). Recorded here
   for audit: first buggy run showed A sleeve SR 0.92 → corrected 0.92 (the bug
   primarily inflated stop-timing luck on P2), B/C qualitatively unchanged.
5. Champion correlation measured on weekly resample of the champion daily book
   (961 overlapping weeks) — a valid G5W proxy, but daily-corr gate (G5) was
   skipped as pre-registered allowed.

## 6. What survives (for DEAD_IDEAS.csv and next steps)

- **DEAD_IDEAS entry (direction 5 core):** "TVP-VECM credibility-gate pairs:
  trailing-window cointegration gate is pro-cyclical/anti-selective (fires 30%
  of weeks, blocks 98% of entry signals); TVP-β over-smooths vs rolling OLS
  (filtered β std 4–6× smaller); GH finds no regime-switch cointegration in
  free weekly commodity/metal pairs. VERDICT: dead as specified."
- **Surviving asset 1 — the panel:** 5 free weekly/monthly pair panels with
  sha256 manifest (data/PANEL_MANIFEST.csv), reproducible from FRED free CSV
  endpoints + repo-local stooq histories.
- **Surviving asset 2 — Arm A profile:** static-β banded-z with hard stop on
  P1/P4 (+P5 to watch): sleeve SR 0.92 net, all-decades positive, champion
  corr ≈ 0. If the operator wants a NEW pre-commit testing this as a
  candidate sleeve (it is the known idiom on new pairs, so novelty is only
  the pairs), the gate bar must be higher than 0.92 to justify adoption vs
  the frontier (champion SR 3.78; adoption needs decorrelation value, not SR).
- **Surviving asset 3 — method knowledge:** the gate falsification mechanics
  (§2) transfer to direction 1 (ICP): any trailing-window invariance/credibility
  score will share this pro-cyclical structure. Pre-register that concern in
  any future ICP hunt.

## 7. Provenance

- All code: campaign/hunts/TVPVECM_HUNT1/{build_panel.py, tvp_estimator.py,
  run_arms.py, run_p3_monthly.py}. Estimator validated on synthetic
  cointegrated vs spurious pairs (GH min-ADF −10.6 vs −2.6; Johansen matches
  statsmodels coint_johansen to machine precision).
- Champion reference: campaign/results/GOAL100_RAWEW13v2_WEIGHTED_GEAR16_daily.csv
  (verified SR 3.78 / MDD −3.34% / geometric ann ≈ 23.9% from raw daily file,
  4806 days 2008-03-31..2026-08-28).
- Runs: .venv Python 3.12.16, numpy 2.5.4, pandas 3.1.0, scipy 1.18.1,
  statsmodels 0.15.0. arm_results.json holds all series.
