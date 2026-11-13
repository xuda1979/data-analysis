# DISCOVERY — META_LABEL_HUNT1 (meta-labeling bet-sizing on champion sleeves)

Date: 2026-11-13
Survey source: `campaign/research/GITHUB_QUANT_SURVEY_2026-11-13.md` (technique #1,
lines 16/25/44/48; lineage: mlfinlab `bet_sizing/bet_sizing.py` + `labeling/labeling.py`,
AFML ch3/7; qlib ScoreIC adjacent).

All discovery below was recorded BEFORE any pre-registration seal and BEFORE any
measurement. Nothing in §6 was done.

## 1. Law audit

- Campaign law #147/#148 (frontier closure): a new hunt needs a NEW data axis or a
  RULE CHANGE. This hunt is a **rule change**: the book's weight rule gains a
  sleeve-level bet-sizing multiplier `b_{i,t}` (AFML meta-labeling), acting on
  `relw_i * b_{i,t}` inside the NAV-drift mechanics. The champion is the exact
  `b ≡ 1` identity.
- Prior art: NO meta-labeling/bet-sizing row in `campaign/results/DEAD_IDEAS.csv`
  (rows 1–79 checked); no "meta-label" match anywhere in the repo (survey line 25).
  Weight-rule-change family is established lawful precedent: ITER15/ITER20/ITER21/
  ITER61 (ITER61's cap28 itself changed weights and shipped as champion).
- Framing that avoids the row-78 wall: the multiplier acts INSIDE the book on each
  sleeve's weight, NOT as a scalar `g_t` de-risk overlay on the champion return
  series. The row-78 wall (three independent confirmations: ICP 2026-11-08
  p_S ~2e-06; KW-via-ICP; F13F 2026-11-13 p_first 1.59e-06) closes scalar de-risk
  overlays gated on the champion's IS distribution — it does not close weight-rule
  changes inside the book. No §4.3-style environment-stability first stage applies.
- Survey correction: survey line 44 says "13 champion sleeves"; the actual count is
  **12** (POOL 10 + NEW 2), of which CFX4 has relw pinned 0 → 11 live sleeves.

## 2. Champion reconstruction (prerequisite, completed pre-seal)

Canonical builder `campaign/scripts/rawew13v2_build.py` imported via importlib;
the ONLY patch is `mod.ROOT` (Mac path → this machine). Two-path check
(`work/recon_check.py`, output `work/recon_stdout.txt`):

- **Path B (OPERATIVE)**: committed weights pinned, NAV-drift mechanics replicated
  → max|new−old| = **6.870e-16 IDENTICAL** vs committed daily CSV; weights diff
  0.000e+00; PIN stats SR 3.7844894672049048 / ann 0.23860978396835986 /
  mdd −0.03304849169440516 all match at 1e-9; gross exactly 1.0 (0 days >1.6);
  turnover 4.1917 bp/yr. **VERDICT GREEN.**
- **Path A (diagnostic only)**: full canonical `build()` with local SLSQP refit →
  max|new−old| = 5.019e-10, weights diff 9.576e-09. Cause: scipy SLSQP fit path is
  version-dependent (champion emitted on Mac). Recorded, NOT part of the verdict.

Consequence for the hunt: **the committed weights are PINNED and never refit**;
`b ≡ 1` reproduces the champion of record exactly (proven by Path B).

## 3. Frozen data (sha16 pins)

- Champion daily `campaign/results/GOAL100_RAWEW13v2_WEIGHTED_GEAR16_daily.csv`:
  **a8ed233bd0f6fd5d** (4806 rows, 2008-03-31..2026-08-28; IS <2017-01-01: 2286;
  OOS: 2520).
- Committed relw `campaign/results/RAWEW13v2_IS_SR_weights.csv`:
  **2b0f5fbc43113149** (CFX4 pinned 0.0).
- 12 sleeves (builder PATHS lines 77–105 authoritative):

| sleeve | path (under ROOT) | sha16 | relw (committed) |
|---|---|---|---|
| brwt10 | campaign/agents/chief/coord/CAMP_COST/sleeves/brwt10_2000__costfix.csv | b0a0bd99338e2bb4 | 0.10698899419106099 |
| brwt7 | campaign/agents/chief/coord/CAMP_COST/sleeves/brwt7__costfix.csv | 680c5468856361c8 | 0.09857308412971368 |
| brwt5 | campaign/agents/chief/coord/CAMP_COST/sleeves/brwt5__costfix.csv | ca5151f346524469 | 0.11613852898225518 |
| C5ng | campaign/agents/E1_20yspan/sleeves/E1_C5ng_weekday_prem.csv | 3d2b80691ef7a448 | 0.15290004106783203 |
| C5ngsum | campaign/agents/E1_20yspan/sleeves/E1_C5ng_summer_weekday.csv | 0f572f6f8fea2c0d | 0.127099958932168 |
| A5r2 | campaign/agents/A5_vol_cond/sleeves/A5_r2_contango_rateshock__vt024.csv | 7ec85336e7f7d00f | 0.026875082003004654 |
| a6r7 | campaign/agents/E1_20yspan/sleeves/E1_a6r7_bond2y_trend_1990.csv | e281e8c4cc5682fb | 0.09325158164297218 |
| QAxasts | campaign/agents/E1_20yspan/sleeves/E1_QAxasts_tsmom189__vt015.csv | c40d008ddbf7c579 | 0.05912117244154822 |
| carryv2 | campaign/agents/E1_20yspan/sleeves/E1_carryv2_GLD_2006.csv | 03f4d0e099da9759 | 0.02567372589478585 |
| dualmom | campaign/agents/A3_xs_quality/sleeves/QA_dualmom_band121.csv | 7462a8dfa391b18f | 0.06685776568309926 |
| diescrack | campaign/agents/loop_team/HUNT_BASIS2/sleeves/diescrack_L40Z20_net.csv | 1b07ad09049b0b11 | 0.12652006503156019 |
| CFX4 | campaign/agents/loop_team/HUNT_CARRYFX/sleeves/CFX4_DTF21_63_raw_daily.csv | 0e448b301fba08c7 | 0.0 |

- Sleeve coverage in the champion window (report-only; first/last/nonNaN):
  brwt10/brwt7/brwt5 2008-03-31..2026-08-28 (4580); C5ng/C5ngsum ..2026-08-24
  (4640); A5r2 2009-09-18..2026-08-11 (4249); a6r7 ..2026-08-27 (4607); QAxasts
  ..2026-08-12 (4624); carryv2 ..2026-08-03 (4786); dualmom ..2026-08-12 (4624);
  diescrack ..2026-08-28 (4618); CFX4 2019-09-10..2026-08-05 (1799).
- Champion yearly returns 2008–2026: **zero negative years in 19** (adoption gate
  must preserve this).

## 4. Hazards

1. **SLSQP version dependence** → weights pinned, never refit (§2).
2. **sklearn MISSING on this machine** (.venv Python 3.12.16, numpy 2.5.4,
   pandas 3.1.0, no sklearn) → the meta-classifier must be pure numpy/pandas,
   deterministic, fully pinned at seal.
3. **Vol-targeting degeneration**: `b` must not silently become a vol-targeting
   overlay; the precommit must include a discriminating comparison against a
   vol-target twin so the gate can tell meta-labeling apart from vol-targeting.
4. **Pro-cyclicality** (TVP-VECM HUNT1 lesson, binding): trailing-window
   credibility scores certify calm reverted regimes and block exactly the
   large-z dislocation entries a strategy trades. Any gate must score PROSPECT
   of the primary signal, not trailing realized performance alone.
5. **IS classifier overfit**: classifier trained IS<2017 only; tiny frozen
   feature set; OOS rows untouched until the single frozen run.
6. **C5ngsum truncation ≤2026-08-24** (ITER61 sealed vintage); CFX4 relw 0
   (discredited twelvedata feed) — b_{CFX4,t} is irrelevant by construction.
7. **Cost**: bet-size churn is charged FULL |dW| at 6.4 bps (champion convention).
8. **NaN/warmup**: sleeves have NaN gaps (A5r2 starts 2009-09-18; CFX4
   2019-09-10) → `b_{i,t} = 1` default whenever features are unavailable.

## 5. Design anchor (for precommit §1)

- AFML meta-labeling: the primary signal is sleeve i's own return stream (already
  the champion's alpha); a secondary model estimates P(win) for sleeve i's next
  session from features; bet size `b = f(2p̂−1)` clipped to a frozen band
  (candidate [0.5, 1.5]; frozen at seal). mlfinlab `bet_size_probability` lineage.
- Geometry: `W_{i,t} = relw_i · b_{i,t} · (NAV-drift row-normalized mechanics)` —
  inside-book weight-rule change; champion = `b ≡ 1` identity, byte-exact.
- Classifier: logistic regression, pure numpy (IRLS/Newton), deterministic;
  trained IS<2017 only; per-sleeve or pooled — frozen at seal.
- Feature candidates (to be FROZEN at seal): sleeve trailing vol; sleeve trailing
  Sharpe sign; sleeve drawdown state; sleeve recent win-rate; cross-sleeve
  correlation state. Exact set, lookbacks, and label definition frozen at seal.
- Gates: F13F G0–G6 template adapted to bet-sizing geometry; controls P/N with
  fresh N seed 20261113 (history: KW 20261106, ICP 20261107, F13F 20261108).

## 6. What was NOT done (pre-measurement integrity)

- No meta-label, feature, or `b_{i,t}` computed on the champion grid.
- No bet-sized book measured; no gate scored; no OOS statistics produced.
- The only champion-grid computation so far is the §2 identity reconstruction
  (verifying byte-identity of already-committed artifacts; not a candidate
  measurement).

## 7. Provenance

- Survey: `campaign/research/GITHUB_QUANT_SURVEY_2026-11-13.md`.
- Reconstruction: `work/recon_check.py`, `work/recon_stdout.txt` (Path B GREEN).
- Builder: `campaign/scripts/rawew13v2_build.py` (PATHS 77–105; build 319–360;
  emit 434–435; --verify 446–447).
- Environment: this Linux machine, .venv Python 3.12.16, numpy 2.5.4,
  pandas 3.1.0, scipy 1.18.1, NO sklearn.
