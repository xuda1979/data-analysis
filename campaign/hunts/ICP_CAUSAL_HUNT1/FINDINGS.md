# FINDINGS — ICP CAUSAL HUNT1 (ICP variable-selection mechanism, direction 1)

**Date:** 2026-11-07. Pre-registered spec: FINDINGS_PRECOMMIT.md (commit
9bb7b21, sha256
5ddfc3bacc39b6664d3467ba838d07aff3b9e8a57f298ae106d2622c32aae897). This
document reports results exactly per the sealed spec. No hyperparameter was
changed after seal; all numbers below are from the single frozen run
(`run_hunt.py`, sha256
46f2a33064e4839e4c50d5ca9a971e0c0f81af82c2ebaf39b23c2c5088b45b6c).

---

## VERDICT: NEGATIVE — no-subset-accepted branch (mechanism failure). No overlay was measured.

**H0 (no candidate parent yields an invariance-accepted causal selection
whose overlay clears the gates) is NOT REJECTED in the strongest possible
form: ICP accepted NOTHING.** Per sealed §4.1, the misspecification branch
fires: **no subset — not even the EMPTY subset — passed the invariance test
at α = 0.05**, so Ŝ* is undefined-by-intersection and the hunt terminates
before any arm is constructed. This is the pre-registered fail-closed
outcome (§8 limitation 1 acknowledged low power biases toward failure; the
actual result failed harder than the low-power scenario — see §2).

Per the sealed decision rule: FINDINGS.md honest negative + DEAD_IDEAS.csv
row; advance to next axis. Controls P and N were never constructed (moot by
branch); G0–G6 were never scored (moot by branch).

---

## 1. The selection run (all 8 subsets, IS-only, n=2284 rows)

IS rows with all parents defined: 2284 (2286 − 2 warm-up sessions), blocks
b1 570 / b2 572 / b3 571 / b4 571 (pins b1 572 minus the 2 warm-up rows —
consistent). Invariance tests on pooled-IS OLS residuals across the 4
pinned blocks; p_S = max(p_AG, p_BF); accept iff p_S ≥ 0.05.

| Subset | p_AG | p_BF | p_S | Accepted |
|---|---|---|---|---|
| EMPTY | 2.00e−06 | 1.14e−14 | 2.00e−06 | NO |
| DTWEXBGS | 2.87e−06 | 7.78e−15 | 2.87e−06 | NO |
| DGS3MO | 1.98e−06 | 1.10e−14 | 1.98e−06 | NO |
| T10YIE | 2.01e−06 | 1.15e−14 | 2.01e−06 | NO |
| DTWEXBGS+DGS3MO | 2.84e−06 | 6.77e−15 | 2.84e−06 | NO |
| DTWEXBGS+T10YIE | 2.96e−06 | 7.20e−15 | 2.96e−06 | NO |
| DGS3MO+T10YIE | 1.97e−06 | 1.04e−14 | 1.97e−06 | NO |
| DTWEXBGS+DGS3MO+T10YIE | 2.91e−06 | 6.55e−15 | 2.91e−06 | NO |

Every p-value is 5–14 orders of magnitude below α. This is not a
borderline low-power outcome; it is a categorical misspecification verdict.

## 2. Why nothing was accepted (falsification analysis)

The EMPTY subset failing is the diagnostic key. The EMPTY model is
intercept-only: its residuals ARE the champion's IS returns. AG
(p ≈ 2e−06) says the champion's **mean return differs across the four IS
blocks**; Brown-Forsythe (p ≈ 1e−14) says its **variance differs across
blocks** — both catastrophically. Adding any parent (or all three) moves
the p-values by at most ~50%: none of DTWEXBGS/DGS3MO/T10YIE innovations
absorbs the block-level non-stationarity of the composite return stream.
Under ICP semantics, invariance of Y | X_S must hold in SOME environment
partition for causal-parent identification; here no conditioning set makes
the champion's return distribution block-stable, so the method correctly
refuses to identify ANY causal parent rather than false-selecting one.

**The structural finding: the champion's IS return distribution is
strongly non-stationary across 2008–2016 sub-periods in mean AND variance,
and no free FRED macro parent among {broad dollar, 3m T-bill, 10y
breakeven inflation} innovations removes that non-stationarity.** ICP
fail-closed behaved exactly as designed (Peters et al. 2016 §5): the
method's value here is that it did NOT hand back a spurious "causal"
dollar/rates/inflation timing variable of the kind a p-hacked z-threshold
search would have produced. The empty-intercept rejection is also
consistent with (and independently re-confirms) the campaign's accumulated
negative evidence that free macro states do not time this champion's tail
(KW structural finding 2026-11-06; TVP-VECM 2026-11-03).

## 3. What was NOT done (branch integrity)

- No overlay was measured; no g-series was constructed; arms A/C/P/N were
  never run; the N seed 20261107 remains unused. No G-gate was scored.
- The G0 drawdown-overlap kill-switch, collapse branch (§4.4), activity
  band, and KW g-series comparisons are all moot by branch.
- Zero unlevered_v1 trial slots consumed; P6 paper runner and scorecard
  untouched.

## 4. Honest caveats

1. **Selection-power interpretation:** the no-acceptance result does NOT
   prove "no causal parent exists" — it proves none is identifiable from
   THIS candidate set × THIS base learner (linear) × THESE 4 IS blocks ×
   n=2284 at α=0.05 (§8 limitations 1–3 disclosed at seal). A nonlinear
   ICP (Heinze-Deml 2018) or an expanded candidate/environment set could
   in principle accept something; per §7 budget (one selection run), that
   is a NEW pre-registered hunt, not a re-run of this one.
2. **Environment granularity:** 4 blocks is the sealed minimum for AG/BF;
   the intercept-only rejection (variance ratio across blocks) is so
   extreme (p ~ 1e−14) that finer partitions would only reject harder.
3. **Current-view FRED (fredgraph), not ALFRED vintages** (§8 limitation 4,
   disclosed at seal).
4. **One execution note for audit:** the first `run_hunt.py` run crashed
   BEFORE any measurement (pandas 3.x removed `DatetimeIndex.iloc`,
   AttributeError at the block-boundary pin check, line 198 — no ICP
   computation, no arm output). Mechanical fix (`champ.index[is_m]` as
   `is_idx`, index directly) + single re-run, KW FINDINGS.md caveat-4
   precedent. All reported numbers are from the corrected single run; no
   selection or arm output was ever observed pre-fix.
5. **Mirror/sign logic moot:** adverse-side β signs were never used (no
   selection), so the DTWEXBGS sign-flip risk (§8 limitation 9) never
   materialized.

## 5. What survives (for DEAD_IDEAS.csv and next steps)

- **DEAD_IDEAS entry (this hunt):** see row appended 2026-11-07 — ICP
  linear variable-selection de-risk overlay on champion, FRED parent set
  {DTWEXBGS, DGS3MO, T10YIE}.
- **Surviving asset 1 — the data panel:** three sha-pinned FRED series
  (DTWEXBGS, DGS3MO, T10YIE) under `data/`, 100% champion-window coverage.
  Lawfully re-usable for conditioning/regime-stratification uses under a
  new pre-registration; dead as an ICP-selected direct champion-timing
  overlay.
- **Surviving asset 2 — method knowledge:** (a) linear ICP fail-closed
  correctly refuses to identify a causal parent for this composite — the
  repo now has a one-line invariance-based falsification of the "free
  macro parent" hypothesis class; (b) the champion's IS return
  distribution is block-non-stationary in mean AND variance (AG p≈2e−06,
  BF p≈1e−14, intercept-only) — a constraint any FUTURE parent-selection
  mechanism (nonlinear ICP, 13F-derived states, conformal layers) must
  confront: whatever predicts this champion must ALSO render its
  conditional distribution environment-stable, or it will fail the same
  invariance wall.
- **Next axis per memory priority order (2026-11 reviews):** (3) 13F
  holdings parsing. (2-honest) conformal layer remains blocked until ≥60
  H1 panel dates (~early Dec 2026).

## 6. Provenance

- Code: `campaign/hunts/ICP_CAUSAL_HUNT1/run_hunt.py` (frozen artifact,
  sha256 46f2a33064e4839e4c50d5ca9a971e0c0f81af82c2ebaf39b23c2c5088b45b6c,
  implements precommit §4–§6 exactly; champion sha/metric/split/block/FRED
  pins enforced at run, all GREEN).
- Verification-only prerequisite run: `verify_prereqs.py` →
  `work/prereqs_verified.json` (2026-11-06, all pins GREEN, before seal).
- Data: `data/fred_{DTWEXBGS,T10YIE,DGS3MO}.csv` (FRED fredgraph keyless
  fetch 2026-11-06, sha256 pins in precommit §2); champion
  `campaign/results/GOAL100_RAWEW13v2_WEIGHTED_GEAR16_daily.csv` (sha16
  `a8ed233bd0f6fd5d`, verified at run).
- Outputs: `work/icp_selection.json` (all 8 subsets, p-values, branch),
  `work/arm_results.json` (branch + mechanical verdict; no arms by
  branch).
- Run environment: .venv Python 3.12, numpy 2.5.4, pandas 3.1.0, scipy
  1.18.1.
- Seal: commit 9bb7b21 (FINDINGS_PRECOMMIT.md + .sha256 sidecar) BEFORE
  any ICP selection or overlay measurement; measurement run 2026-11-07
  after seal.
