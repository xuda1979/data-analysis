# FINDINGS — META_LABEL_HUNT1 (meta-labeling bet-sizing on champion sleeves)

**Date:** 2026-11-14. Pre-registered spec: FINDINGS_PRECOMMIT.md (commit
5a38038). Discovery record: DISCOVERY.md (same seal). This document reports
results exactly per the sealed spec. No hyperparameter was changed after
seal; all numbers below are from the single frozen run (`work/run_hunt.py`,
sha256
7318e895753a980880c32963e5c66ae044c6d043eeeac2bcccbfce4144c11531).

---

## VERDICT: NEGATIVE — G1 and G2 fail; 6/8 gates pass. Champion unchanged.

Per the sealed decision rule (precommit §5): ANY gate fail → NEGATIVE →
`campaign/results/DEAD_IDEAS.csv` row 80. Two gates failed:

- **G1 FAIL (near-miss):** OOS dSR(M) = **+0.137023** vs threshold ≥ +0.15.
- **G2 FAIL:** full-window CAGR sacrifice = **1.185 pp** vs threshold ≤ 0.5 pp.

The run is VALID (not INVALID): controls P (+0.081) and N (−0.687) both
pass G6 (each < +0.15), so the gate family discriminates. V did not pass
G1–G5 on its own (v_g1 +0.066 FAIL, v_g2 2.301 pp FAIL) → no vol-targeting
follow-up note required by §5.

Falsification branch fired (precommit §6, first bullet): *M fails G1 →
meta-labeling adds no OOS sizing value at this config.* Per §8 limitation 9,
one config measured; a NEGATIVE closes THIS configuration; the meta-labeling
family would need new pre-registration with a changed rule.

---

## 1. Gate table (single frozen run)

| gate | measured | threshold | verdict |
|---|---|---|---|
| G-1 identity | max\|b≡1 book − champion CSV\| = 6.870e−16 | < 1e−12 | PASS (fail-closed honored) |
| G0 drawdown windows | 3/3 strictly better (E1 −0.03078 vs −0.03337; E2 −0.02936 vs −0.03285; E3 −0.02640 vs −0.02775) | ≥ 1 of 3 | PASS |
| G1 OOS dSR(M) | +0.137023 | ≥ +0.15 | **FAIL** |
| G2 CAGR sacrifice | 1.1850 pp | ≤ 0.5 pp | **FAIL** |
| G3 MDD(M) | −0.030913 (champ −0.033048) | ≤ champ + 1 pp | PASS |
| G4 incremental cost | 6.345 bp/yr | ≤ 50 bp/yr | PASS |
| G5 max roll-252 incr cost | 13.133 bp | ≤ 75 bp | PASS |
| G6 controls P/N OOS dSR | P +0.081164; N −0.687006 | both < +0.15 | PASS |
| G7 dSR(M) − dSR(V) | +0.070533 | ≥ +0.05 | PASS |

## 2. Arm statistics (KW-sealed conventions)

| arm | full SR | full CAGR | full MDD | OOS SR | IS SR | turnover bp/yr | OOS dSR |
|---|---|---|---|---|---|---|---|
| champion | 3.784489 | 0.238610 | −0.033048 | 3.657593 | 4.194839 | 4.192 | — |
| M (treatment) | 3.826400 | 0.226760 | −0.030913 | 3.794615 | 4.073473 | 10.537 | +0.137023 |
| V (vol twin) | 3.819813 | 0.215599 | −0.030411 | 3.724083 | 4.181498 | 14.991 | +0.066490 |
| P (time-reversed) | 3.801481 | 0.223616 | −0.031716 | 3.738757 | 4.161467 | 10.704 | +0.081164 |
| N (iid, seed 20261113) | 2.929141 | 0.178250 | −0.042657 | 2.970586 | 3.007821 | 494.046 | −0.687006 |

Champion OOS CAGR 0.272187 vs M OOS CAGR 0.265274; champion OOS MDD
−0.033048 vs M −0.030913. Yearly returns: both champion and M have zero
negative calendar years (19/19 each; M 2024 0.35636 > champ 0.35529).

## 3. Classifier (pooled logistic, pure-numpy Newton-IRLS)

n_train = 22656 (IS<2017, 11 live sleeves); converged in 5 IRLS iterations,
final max-inf-norm gradient 1.178e−13. IS accuracy 0.6782, IS AUC 0.7179
(report-only, in-sample by design).

| feature | β |
|---|---|
| intercept | −0.640597 |
| vol63 | +0.063576 |
| sharpe126 | +0.029672 |
| dd252 | −0.054328 |
| win21 | **+0.844217** |
| mom21 | −0.226585 |

Dominant feature: trailing 21d win-rate (win21), i.e. the classifier is
largely a short-horizon momentum-of-sign estimator. OOS calibration deciles
are monotone-ish and informative: realized win-rate rises 0.046 → 0.599
across pooled p̂ deciles (n≈2600/decile) — the probability model carries
genuine OOS information, it simply does not clear the economic threshold
after band-clipping and costs.

## 4. Near-miss and mechanism analysis

1. **G1 near-miss anatomy.** OOS dSR +0.137 vs +0.15: M improves OOS SR
   (3.7946 vs 3.6576) AND shallows OOS MDD, but the full-window CAGR cost
   (23.86% → 22.68%, −1.185 pp) eats the SR gain's economic meaning. The
   improvement is OOS-concentrated: **IS dSR(M) is negative (−0.121)** —
   the bet-size rule *hurt* in-sample where the classifier was trained,
   and helped only OOS. This pattern (train-period underperformance,
   OOS outperformance) is the opposite of overfitting leakage, which
   supports the calibration evidence that the signal is real but small.
2. **Activity is extreme: 96.01%** of live sleeve-days have |b−1| > 0.01
   (report-only band [2%, 60%] blown through). The rule is not a sparse
   de-risker; it is a persistent re-weighter. Per-sleeve mean b: six
   sleeves are pinned at/near the 0.5 lower bound most of the time
   (brwt10 0.500/100% at bound; C5ngsum 0.500/99.5%; brwt7 0.527/94.6%;
   brwt5 0.527/94.6%; diescrack 0.527/94.6%; C5ng 0.514/95.4%) while
   carryv2 (1.230), a6r7 (1.158), QAxasts (1.034), dualmom (1.025),
   A5r2 (0.968) run above/near 1. The pooled classifier systematically
   de-weights the champion's carry/term-premia core (brwt/C5 family) and
   up-weights the commodity/metal sleeves.
3. **The CAGR sacrifice is the binding failure, and it is mechanical:**
   persistently holding the highest-relw sleeves (brwt10/brwt7/brwt5/
   C5ng/C5ngsum together ≈ 0.55 of committed relw) at b≈0.5 halves the
   book's core engine. A 1.2 pp CAGR tax for +0.137 SR and −21 bp MDD is
   a real trade-off, but it fails the sealed adoption economics.
4. **The edge is NOT mere volatility targeting (G7 +0.071).** M beats V on
   OOS dSR by +0.071 at HALF the incremental turnover (10.5 vs 15.0
   bp/yr... both trivially cheap). The meta-label carries sizing
   information beyond vol state — but not enough to clear +0.15.
5. **Drawdown mechanism present (G0 3/3).** All three sealed stress
   windows improved cum-return, and full MDD shallowed −3.30% → −3.09%.
   The bet-size rule does what meta-labeling promises in stress windows;
   the failure is the everyday CAGR tax, not stress behavior.
6. **Costs are a non-issue (G4/G5).** Incremental cost 6.3 bp/yr, worst
   rolling-252 13.1 bp — the failure is signal magnitude, not churn.

## 5. Honest caveats

1. All §8 precommit limitations stand (daily-sign labels not
   triple-barrier; pooled classifier; 5 frozen features; c=2.5/band
   [0.5,1.5]/halflife 5 frozen a priori; numpy IRLS not sklearn; OOS
   shares IS regime era; V is one vol-target strawman).
2. **One execution note for audit:** the first `run_hunt.py` execution
   attempt was blocked pre-run by a preemptive fix to the OOS calibration
   block (positional `.to_numpy()` construction to avoid pandas
   duplicate-axis reindex on pooled sleeve-date labels). The fix was
   applied BEFORE the run executed; the single frozen run then completed
   cleanly in one shot. No measurement was observed pre-fix. (ICP hunt
   caveat-4 precedent; precommit §7 pre-measurement fix clause.)
3. The G1 threshold (+0.15) and G2 threshold (0.5 pp) were sealed BEFORE
   the run; the near-miss (+0.137) is reported as a fail without
   exception or re-thresholding. No post-hoc "promotable" claim is made.
4. sklearn absence means library parity is not claimed for the logistic
   fit; determinism is pinned (IRLS, 5 iterations, gradient 1.2e−13).

## 6. What survives (for DEAD_IDEAS.csv and next steps)

- **DEAD_IDEAS entry (row 80):** AFML meta-labeling bet-sizing on
  champion sleeves at this config (pooled logistic, 5 features, b =
  clip(1+2.5·EMA(z,hl5), 0.5, 1.5), M/V/P/N arms, N seed 20261113).
- **Surviving asset 1 — calibration evidence:** the pooled win-probability
  model is genuinely informative OOS (decile monotonicity 0.046→0.599,
  G7 pass over the vol twin). Any FUTURE sizing/overlay hunt can cite
  this as proof the sleeve-return feature base carries signal.
- **Surviving asset 2 — structural lesson:** the champion's core carry
  sleeves are systematically "low P(win)" under trailing-feature
  classifiers (win21-dominant) yet are the CAGR engine — persistent
  de-weighting of low-win-rate/high-mean sleeves trades CAGR for SR/MDD.
  Future sizing rules must target the tails, not the everyday mean, to
  avoid this tax (G0 3/3 + MDD shallower show the tail mechanism exists).
- **Surviving asset 3 — run infrastructure:** `work/run_hunt.py` is a
  complete, verified, deterministic in-book bet-sizing harness (identity
  check, 4-arm construction, gate scoring, JSON emit) re-usable under new
  pre-registration for any time-varying relw·b rule.
- **Family status:** meta-labeling closed at THIS config (§8.9). A new
  config (e.g. triple-barrier labels, tail-only activation, per-sleeve
  classifiers, different c/band) requires fresh pre-registration.
- **Survey pipeline status:** technique #1 (meta-labeling) of the
  2026-11-13 survey is now measured-and-closed. The survey's remaining
  lawful directions are documented in
  `campaign/research/GITHUB_QUANT_SURVEY_2026-11-13.md`.

## 7. Provenance

- Code: `work/run_hunt.py` (frozen, sha256
  7318e895753a980880c32963e5c66ae044c6d043eeeac2bcccbfce4144c11531;
  implements precommit §4–§5 exactly; 14 pins verified at run time, all
  GREEN; G-1 identity 6.870e−16 fail-closed honored before any arm).
- Outputs: `work/arm_results.json` (10835 bytes, full machine-readable
  record), `work/run_stdout.txt` (execution log, 2026-11-14 15:33 CST).
- Data: champion daily CSV sha16 a8ed233bd0f6fd5d; committed relw sha16
  2b0f5fbc43113149; 12 sleeve csvs sha-pinned in DISCOVERY.md §3 — all
  verified at run.
- Seal: commit 5a38038 (DISCOVERY.md + FINDINGS_PRECOMMIT.md +
  work/recon_check.py + work/recon_stdout.txt) BEFORE any b computation,
  arm construction, or gate scoring. Reconstruction Path B GREEN
  (6.870e−16) pre-seal.
- Run environment: .venv Python 3.12.16, numpy 2.5.4, pandas 3.1.0,
  scipy 1.18.1, NO sklearn. Execution 2026-11-14 15:33 CST.
