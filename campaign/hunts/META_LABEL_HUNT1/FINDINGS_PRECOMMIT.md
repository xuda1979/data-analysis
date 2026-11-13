# FINDINGS PRECOMMIT — META_LABEL_HUNT1 (meta-labeling bet-sizing on champion sleeves)

Date sealed: 2026-11-13. This document is committed BEFORE any bet-size is
computed on the champion grid, before any arm is built, and before any gate is
scored. All hyperparameters below are frozen at seal. No peeking, no re-tuning
after the arms run. Discovery record: `DISCOVERY.md` (same date, same seal).

## 1. Objective and law audit

Test AFML meta-labeling (survey technique #1; lineage mlfinlab
`bet_sizing/bet_sizing.py`, AFML ch3/7) as a **weight-rule change inside the
book**: each live sleeve's weight gains a bet-size multiplier
`b_{i,t} = f(P̂(sleeve i wins session t))` acting on `relw_i · b_{i,t}` within the
champion's NAV-drift mechanics. The champion of record is the exact `b ≡ 1`
identity.

- Lawful under #147/#148 as a rule change (weight-rule family precedent:
  ITER15/20/21/61). NOT a scalar de-risk overlay → no §4.3 environment-stability
  first stage (row-78 wall closes scalar overlays, not in-book weight rules).
- No prior meta-labeling/bet-sizing row in `campaign/results/DEAD_IDEAS.csv`
  (rows 1–79 audited at discovery).
- H1: sleeve-conditional win-probability carries sizing information beyond
  (a) the champion's static relw and (b) volatility targeting.
- Survey correction adopted: 12 sleeves (not 13); 11 live (CFX4 relw pinned 0).

## 2. Frozen data (sha16 pins, verified at run time)

Champion daily `campaign/results/GOAL100_RAWEW13v2_WEIGHTED_GEAR16_daily.csv`
**a8ed233bd0f6fd5d** (4806 rows, 2008-03-31..2026-08-28). Committed relw
`campaign/results/RAWEW13v2_IS_SR_weights.csv` **2b0f5fbc43113149**.
12 sleeve csvs pinned in `DISCOVERY.md` §3 (sha16 table). No other data enters.
All features are computed from sleeve return series alone (free-data law).

## 3. Pinned baseline and metric conventions

Champion PIN: SR 3.7844894672049048, CAGR 0.23860978396835986,
MDD −0.03304849169440516 (KW-sealed conventions: SR = mean/std(ddof=1)·√252;
CAGR = exp(252·mean(ln(1+r)))−1; MDD = min(NAV/cummax−1)).
Windows: IS label dates < 2017-01-01 (2286 champion rows); OOS
2017-01-02..2026-08-28 (2520 rows). Mechanics: NAV-drift T+1 causal weighting,
row-normalized to gross 1.0; cost = FULL |dW| at 6.4 bps (champion `BPS`);
margin 0 at gear 1.0. Champion turnover 4.1917 bp/yr (recon Path B).

## 4. Frozen methodology

### 4.1 Data prep
Load 12 sleeves via canonical builder PATHS (C5ngsum truncated ≤ 2026-08-24);
window 2008-03-31..2026-08-28; committed relw pinned (never refit); CFX4 relw 0.

### 4.2 Features and labels (per sleeve i, as-of s = t−1)
Label: `y_{i,t} = 1[r_{i,t} > 0]` (daily win = positive sleeve session return;
NOT triple-barrier — disclosed adaptation, §8).
Features (all rolling on sleeve's own return series, min_periods = window):
- F1 `vol63` = std(r, 63)·√252
- F2 `sharpe126` = mean(r, 126)/std(r, 126)·√252
- F3 `dd252` = sleeve NAV / 252d rolling max(NAV) − 1
- F4 `win21` = mean(1[r>0], 21)
- F5 `mom21` = mean(r, 21)
Any missing feature at s → no bet update (b stays at prior value; b=1 before
first availability). Standardization: pooled IS mean/std per feature, frozen.

### 4.3 Classifier and training (pure numpy; sklearn absent on this machine)
Logistic regression, pooled across the 11 live sleeves, intercept included,
Newton-IRLS, ridge 1e-6, max 50 iterations, gradient tol 1e-10 — deterministic.
Training rows: all (i,t) with label date t in IS, features at t−1 available.
One frozen classifier; applied unchanged across the full window (static-fit,
matching champion relw convention; no walk-forward).

### 4.4 Bet mapping and arms
`z_{i,s} = 2·p̂_{i,s} − 1` (p̂ from features at s); per sleeve
`zema_{i,s} = EMA(z, halflife=5 bdays)`; causal placement
`b_{i,t} = clip(1 + 2.5·zema_{i,t−1}, 0.5, 1.5)` (shift(1), b=1 warmup/NaN).
Book mechanics: identical to champion but `relw` becomes time-varying
`relw_i · b_{i,t}` (elementwise); row-normalization, cost, margin unchanged.

Arms (single frozen run, no variants):
- **M** (treatment): b as above.
- **V** (vol-target twin): `b^V_{i,t} = clip(v̄_i / vol63_{i,t−1}, 0.5, 1.5)`,
  `v̄_i` = IS mean of F1 per sleeve (frozen), shift(1), b=1 warmup.
- **P** (time-reversed control): `b^P_{i,t} = b^M_{i,T+1−t}` per sleeve.
- **N** (iid control): b ~ U(0.5, 1.5) per live sleeve-day, seed **20261113**
  (history: KW 20261106, ICP 20261107, F13F 20261108).

### 4.5 Identity check (run validity, fail-closed)
`b ≡ 1` book must reproduce the committed champion daily CSV to
max|new−old| < 1e-12 (recon Path B standard; provenance
`work/recon_stdout.txt`, GREEN 6.870e-16 pre-seal).

## 5. Sealed gates and decision rule

| gate | test | threshold |
|---|---|---|
| G-1 | identity: max\|b≡1 book − champion CSV\| | < 1e-12 (fail-closed) |
| G0 | drawdown-window pre-screen: M cum > champ cum in E1 2023-12-28..2024-01-11, E2 2018-06-20..2018-06-25, E3 2026-03-10..2026-03-17 | ≥ 1 of 3 strictly better |
| G1 | OOS dSR = SR_M,OOS − SR_champ,OOS | ≥ +0.15 |
| G2 | full-window CAGR sacrifice vs champion | ≤ 0.5 pp |
| G3 | full-window \|MDD_M\| | ≤ champ + 1 pp |
| G4 | incremental full-\|dW\| cost = (mean(to_M) − mean(to_champ))·252·6.4 bp | ≤ 50 bp/yr |
| G5 | max rolling-252 of incremental daily cost | ≤ 75 bp |
| G6 | controls validity: OOS dSR of P and of N | both < +0.15 |
| G7 | anti-degeneration: OOS dSR_M − OOS dSR_V | ≥ +0.05 |

Activity band (report-only): fraction of live sleeve-days with |b−1| > 0.01 in
[2%, 60%]. Report-only: IS dSR (in-sample, inflated), yearly returns, per-sleeve
mean b, bound-hit fraction, classifier coefficients + IS accuracy/AUC, OOS
calibration deciles, turnover decomposition.

**Sealed decision rule:** G-1 AND G0–G7 all pass → POSITIVE candidate →
promotion memo; adoption is its own operator round with the additional
requirements: full-window MDD strictly shallower than −3.304849% AND zero
negative calendar years preserved (champion: 19/19). ANY gate fail → NEGATIVE
→ `campaign/results/DEAD_IDEAS.csv` row 80. If P or N passes G1 → gates not
discriminating → run INVALID, recorded NEGATIVE, no promotion. V passing
G1–G5 on its own is recorded as a separate vol-targeting follow-up note, NOT a
meta-labeling promotion.

## 6. Falsification criteria

- M fails G1 → meta-labeling adds no OOS sizing value at this config.
- M passes G1 but fails G7 → any edge is volatility targeting, not
  meta-labeling (degeneration).
- M passes G1/G7 but fails G0 → no drawdown-window mechanism presence.
- M passes G1 but fails G4/G5 → value consumed by churn.
- P or N passes G1 → gate family non-discriminating; result void.
- All pass but adoption reqs fail → candidate not promotable; recorded.

## 7. Budget and registry

Single frozen run `work/run_hunt.py` (sha256 recorded at execution), outputs
`work/arm_results.json`, `work/run_stdout.txt`. Pre-measurement crash → fix and
re-run permissible (F13F precedent); post-measurement → never. No hyperparameter
variants; c = 2.5, band [0.5, 1.5], halflife 5 were frozen a priori at this
seal. Registry: `campaign/hunts/META_LABEL_HUNT1/`. Dead-row 80 reserved.

## 8. Limitations disclosed at seal

1. Daily-sign labels, not triple-barrier (sleeves are continuously-in-book;
   event-based primary signals do not exist here) — AFML adaptation.
2. Pooled classifier (11 sleeves), not per-sleeve.
3. Five hand-frozen features; no feature search performed (none permitted).
4. c = 2.5, band [0.5, 1.5], halflife 5 chosen a priori; no tuning after seal.
5. sklearn absent: numpy IRLS reimplementation (determinism pinned; library
   parity not claimed).
6. Trailing features (F2/F4/F5) carry pro-cyclicality risk (TVP-VECM HUNT1
   lesson); tested via P control and G7 only, not eliminated.
7. IS statistics are in-sample for the classifier — report-only by design.
8. OOS 2017–2026 shares the economic regime era of IS training.
9. One config measured: a NEGATIVE result closes THIS configuration; the
   meta-labeling family would need new pre-registration with a changed rule.
10. Vol-target twin V is one strawman (raw 63d ratio); passing G7 does not
    exclude all possible vol-targeting variants.

## 9. Provenance

- Champion/weights/sleeve sha16 pins: `DISCOVERY.md` §3 (verified pre-seal).
- Reconstruction GREEN: `work/recon_check.py`, `work/recon_stdout.txt`.
- Canonical builder: `campaign/scripts/rawew13v2_build.py` (importlib, ROOT
  patched to this machine; the only patch).
- Environment: .venv Python 3.12.16, numpy 2.5.4, pandas 3.1.0, scipy 1.18.1,
  NO sklearn.

Sealed: 2026-11-13, BEFORE any b_{i,t} computation, arm construction, or gate
scoring. All hyperparameters above are frozen. No peeking, no re-tuning after
arms run.
