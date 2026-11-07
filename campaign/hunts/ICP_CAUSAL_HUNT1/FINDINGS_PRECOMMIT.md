# ICP_CAUSAL_HUNT1 — Pre-registered Findings Commitment (Seal)

Sealed: 2026-11-06, BEFORE any ICP selection run and BEFORE any overlay measurement (repo convention: KW_TERMPREMIA_HUNT1 seal e96d87c / TVPVECM_HUNT1 / ITER61_DDCON pattern). No ICP selection and no arm backtest below has been run at seal time. Prerequisite **verification only** has been executed (`verify_prereqs.py` — constructs no z, runs no ICP, measures no overlay) and recorded in `work/prereqs_verified.json`.

## §1 Objective and law audit

**Objective.** Test whether an Invariant Causal Prediction (ICP; Peters, Bühlmann & Meinshausen 2016) **variable-selection** layer — a mechanism NEW to this repo — identifies a macro parent whose adverse state, traded as a one-directional de-risk overlay on the champion, clears the campaign promotion standard.

**Mechanism H1.** The champion's return stream is causally driven by a small set of macro-financial states. When a selected causal parent is in its adverse extreme (direction fitted in-sample), the champion's conditional return distribution shifts adversely; a hysteresis de-risk keyed to that parent reduces tail risk (MDD) without proportional CAGR sacrifice.

**Null H0.** No candidate parent yields an invariance-accepted causal selection whose overlay achieves dSharpe ≥ +0.15 under the §5 gate battery; or ICP selects the empty set / no accepted subset (mechanism failure).

**Law audit (frontier-closure law #147/#148).** NEW MECHANISM: "invariant causal prediction" has zero prior matches in this repository (grep verified 2026-11-06); no prior hunt performed invariance-based causal variable selection. Per the 2026-11 research-directions review, ICP has no published finance risk-premia application the operator is aware of (method references: Peters-Bühlmann-Meinshausen 2016; Heinze-Deml-Peters-Meinshausen 2018 nonlinear ICP; Pfister-Bühlmann-Peters 2019 sequential ICP) — deliberately frontier-low-crowding.

**Candidate parents (FRED, free) and prior-estimand disclosure:**

| Series | Prior use in repo | Estimand here |
|---|---|---|
| DTWEXBGS (broad dollar index) | NOT a DEAD_IDEAS row. Three prior estimands disclosed: (1) C5_newdata R1 idea 5: standalone dollar reversal/momentum engine lb 63/126/252 — FAIL; (2) A2_fx_carry r7 idea 39: dollar-fade FX basket (long EUR/GBP/CAD short JPY on DTWEXBGS z 63/126/252, 2006+) — FAIL; (3) A2 r7 ideas 39/41→41b: dollar-z→SPY timing, initially SR 1.19 (lb315, 2016+), honest 20y re-test SR 0.70 / H1 0.26 / p=0.05 — FAIL, regime artifact (**closest prior**) | parent of champion composite; invariance-selected; IS-fitted sign; z-state de-risk |
| T10YIE (10y breakeven inflation) | input-only in DEAD_IDEAS rows 27 (gold × macro maps) and 40 (credit-OAS momentum); never a parent-selection estimand | same |
| DGS3MO (3m Treasury bill) | rf proxy only; clean for a new estimand | same |

Closed-axis variables are excluded from the candidate set by law: VIX family (rows 32/45/59), NFCIRISK (row 53), WALCL (row 30), DFII10 (row 61), curve shapes (rows 28/39/51/56/60/63), KW term-premia levels (row 77). The ICP estimand differs from all disclosed priors in mechanism (invariance-based selection among candidates), target (champion composite, not SPY/FX baskets), and traded construction (1260d z-state hysteresis on the SELECTED variable only).

## §2 Frozen data

Fetched 2026-11-06 via FRED fredgraph CSV (keyless), rate limit honored. Convention: "rows" = post-NaN-drop observations. All three series: **100% champion-window coverage** under ffill ≤ 5 business days.

| Series | File | Window | Rows | sha256 (first 16) | Max staleness (bd) |
|---|---|---|---|---|---|
| DTWEXBGS | data/fred_DTWEXBGS.csv | 2006-01-02..2026-10-30 | 5222 | 908a19a96d1ba529 | 4 |
| T10YIE | data/fred_T10YIE.csv | 2003-01-02..2026-11-05 | 5966 | 5b669e4b20edd027 | 1 |
| DGS3MO | data/fred_DGS3MO.csv | 1981-09-01..2026-11-04 | 11294 | 488f612215354356 | 1 |

Full digests:
- DTWEXBGS `908a19a96d1ba529ef51ae559b8bc384bf8af4d4013185426e5ee9c3cca4213f`
- T10YIE `5b669e4b20edd027e94c36ae0654151d08afd22d7eed13f5d6f5ec9093942233`
- DGS3MO `488f612215354356411de73118868f7123ec588f133e5388d58fc0143edc9241`

Champion file: `campaign/results/GOAL100_RAWEW13v2_WEIGHTED_GEAR16_daily.csv`, sha256 `a8ed233bd0f6fd5dad4056fda8fbd4cdde10d87ca4886c104c25b93c8014fbf4` (`a8ed233bd0f6fd5d`).

KW collapse-branch comparators (g-series from `KW_TERMPREMIA_HUNT1/work/`):
- `g_A.csv` sha16 `cc49cfba4664cef5` — 1446/4806 sessions de-risked, levels {0.7, 1.0}
- `g_B.csv` sha16 `1f9d77019459089c` — 1188/4806, levels {0.5, 1.0}
- `g_C.csv` sha16 `b4fa8aefde66d8be` — 1422/4806, levels {0.7, 1.0}

## §3 Pinned baseline and metric conventions

Champion of record (ITER61_DDCON A_cap28 daily): 4806 rows, 2008-03-31..2026-08-28, column `ret`.
- SR 3.7844894672049048; CAGR 0.23860978396835986; MDD −0.03304849169440516; 0 negative years; worst year +0.07553011883208494.
- IS/OOS: IS = <2017-01-01 = 2286 rows (2008-03-31..2016-12-30); OOS ≥2017-01-01 = 2520 rows (2017-01-02..2026-08-28).

Metric conventions (KW-sealed, unchanged): SR = mean/std(ddof=1)·√252; CAGR = exp(252·mean(ln(1+r)))−1; MDD = min(NAV/cummax(NAV)−1); calendar years (1+r).groupby(year).prod()−1; overlay cost = FULL |Δg| × 6.4 bps one-side (champion's internal costs already embedded in `ret`); freed capital (1−g) earns 0%; T+1 causality (g_t from data through t−1); NaN signal → HOLD previous exposure (no toggle, no cost); τ = |Δg|/2; annualized half-turn = (252/n)·Στ; roll-252 = max trailing-252 Στ.

## §4 Frozen methodology

### 4.1 One-shot ICP selection (in-sample only)

- Grid: all 8 subsets S ⊆ {DTWEXBGS, T10YIE, DGS3MO}.
- Rows: IS sessions t with all parent grid-diffs defined.
- Response: champion return at t. Parents: 1-session change of each candidate, ΔX at t−1, where levels are first reindexed to the champion grid (last obs ≤ date, ffill ≤ 5 business days — numpy-safe `reindex_to_champ` pattern) and the diff is taken ON the champion grid (stale ffills → 0 diff, conservative). Parent for session t = grid-diff at t−1 (data through t−1, T+1-consistent).
- Environments: 4 equal-count IS blocks (authoritative `np.array_split` run values): b1 n=572 2008-03-31..2010-06-07; b2 n=572 2010-06-08..2012-08-15; b3 n=571 2012-08-16..2014-10-23; b4 n=571 2014-10-24..2016-12-30.
- Base learner: linear (OLS with intercept, pooled IS).
- Invariance test per subset: residuals of pooled-IS OLS; across the 4 blocks: (i) Alexander-Govern (equal residual means; heteroscedasticity-robust) and (ii) Levene center='median' (Brown-Forsythe; equal residual variances). p_S = max(p_AG, p_BF). Subset accepted iff p_S ≥ α = 0.05. (Faithful scipy-only linear-ICP invariance test: invariance requires both mean and variance stability.)
- Selection: Ŝ* = ∩ over accepted subsets. Pre-registered branches:
  - **No subset accepted** → misspecification branch → NEGATIVE (mechanism failure), no overlay measured.
  - **Ŝ* = ∅** → empty-set branch → NEGATIVE (no causal parent identified), no overlay measured.
  - **|Ŝ*| = 1** → arm A trades that variable.
  - **|Ŝ*| ≥ 2** → necessity ranking by leave-one-out p-value p(Ŝ*\{X_i}) (lower = removing it breaks invariance harder = more necessary); arm A = most necessary; arm C = runner-up; ties alphabetical (DTWEXBGS < DGS3MO < T10YIE).
- Selection runs ONCE, on IS rows only. No rolling or updated invariance score is ever traded (TVPVECM pro-cyclical-gate lesson, 2026-11-03).

### 4.2 Traded signal and overlay

- Traded state: z = 1260-business-day rolling z (min_periods 252) of the SELECTED variable's LEVEL, computed on the full raw FRED series (KW convention), then reindexed to champion sessions (`reindex_to_champ`, ffill ≤ 5 bd).
- Adverse side: from the pooled-IS OLS of champion returns on ALL of Ŝ* (for |Ŝ*| = 1, univariate): β_A = coefficient of arm-A's variable. If β ≥ 0: de-risk when z_{t−1} < −1.0; re-risk when z_{t−1} ≥ 0.7. If β < 0: mirror — de-risk when z_{t−1} > +1.0; re-risk when z_{t−1} ≤ +0.7. g_cut = 0.7 both sides. (Hysteresis parameters = KW arm-A template, repo-standard; no threshold tuning.) Arm C: identical rule with β_C = its coefficient in the same regression.
- Overlay return: r_t = g_t · champ_t − |g_t − g_{t−1}| · 0.00064. g_0 = 1.0. NaN z → HOLD.

### 4.3 Arms

| Arm | Definition |
|---|---|
| A | ICP-selected parent (or most-necessary of Ŝ*), §4.2 rule |
| C | runner-up parent, only if \|Ŝ*\| ≥ 2; else void |
| P | time-reversed control: arm-A variable's z reversed (z_rev = z.iloc[::-1] realigned to champion index, KW pattern), same hysteresis unmirrored (lo −1.0 / re 0.7 / cut 0.7) |
| N | random control: iid N(0,1), seed **20261107** (fresh; KW used 20261106), champion index, same hysteresis unmirrored |

### 4.4 Collapse branch (axis-closure guard)

After arms run: if any treatment arm's g-series matches a dead KW arm's g-series on ≥ 95% of the 4806 sessions (|g_ICP − g_KW| < 1e-6 per session), that arm is REFUTED on axis-closure grounds (the dead KW signal re-derived). Pearson + Spearman correlations vs each KW g-series are report-only.

## §5 Sealed gates

Scored on the FULL 4806-session window, T+1, 6.4 bps full |Δg|.

| Gate | Rule |
|---|---|
| G0 | Drawdown-overlap pre-screen (KW lesson, kill-switch): in ≥ 1 of the pinned decline windows — E1 2023-12-28..2024-01-11 (11 sess), E2 2018-06-20..2018-06-25 (4 sess), E3 2026-03-10..2026-03-17 (6 sess) — the arm must be de-risked (g < 1) on ≥ 50% of the window's sessions |
| G1 | dSR ≥ +0.15 vs champion |
| G2 | CAGR sacrifice ≤ 0.5 pp |
| G3 | \|MDD\| ≤ champion \|MDD\| + 1 pp (≤ 4.30485%) |
| G4 | annualized half-turn ≤ 1.0 |
| G5 | roll-252 half-turn ≤ 1.5 |
| G6 | controls P and N BOTH fail G1 (machinery validity) |

Disclosure: all three G0 windows are OOS (≥2017) while ICP selection is IS-only — invariance must extrapolate across the split. This is the central scientific risk (KW failed exactly here: its de-risk windows never touched the champion MDD).

Adoption requirements (beyond gates): A-R1 MDD strictly shallower than −3.30485%; A-R2 zero negative years preserved.

Report-only (no gating): IS/OOS dSR split; decade bins; cost stress 8/10 bps; toggles; fraction of sessions de-risked; ICP p-values for all 8 subsets; OLS coefficients; KW g-series correlations.

Sealed decision rule: any treatment arm (A or C) passing G0-G6 → promotion memo (operator decision, highest dSharpe, ITER61_DDCON pattern). None → NEGATIVE: FINDINGS.md honest negative + DEAD_IDEAS.csv row. P or N passing G1 → machinery INVALID, results void. Arms A and C both failing G0 → NEGATIVE with the KW-lesson structural finding.

## §6 Falsification criteria

- Empty-set branch or no-accepted-subset branch → NEGATIVE (mechanism failure).
- Activity band: fraction of de-risked sessions < 2% (inert) or > 60% (regime label, not a tail signal) → arm REFUTED. Activity within band is necessary, not sufficient.
- Collapse branch (§4.4) → arm REFUTED (axis closure).
- G6 violation → machinery void.
- All treatment arms fail G0 → NEGATIVE (the selected causal state does not time the champion's realized tails).

## §7 Budget and registry

- One ICP selection run (IS rows only); one frozen measurement run (`run_hunt.py` artifact — selection + arms + gates in one script, sha-recorded at the evidence commit); no re-runs, no re-tuning after unblinding (TVPVECM_HUNT1 precedent).
- Zero unlevered_v1 trial slots consumed (overlay on pinned champion series; `research/protocols/unlevered_v1.json` untouched).
- P6 paper runner and scorecard untouched.
- No git push without explicit operator authorization; explicit-pathspec commits only; append-only registries.
- data_exposure_v1 classification: FRED public data + repo-pinned champion series — same class as KW hunt.

## §8 Limitations disclosed at seal

1. ICP low power: with n=2286, 4 environments, 3 candidates, linear base learner, the empty set is a likely outcome even under true causality (Peters et al. 2016 §5). Acknowledged — a pre-registered branch, not a tuning target. Low power biases toward Ŝ* = ∅ (fail-closed).
2. Hidden confounders: the candidate set omits vol/credit/liquidity states; ICP invariance holds only with respect to the 4 IS blocks; block-invariant confounders are invisible.
3. Linear base learner: nonlinear invariance violations (Heinze-Deml 2018) are not tested; scipy-only linear ICP is sealed here.
4. Current-view FRED (fredgraph), not ALFRED vintages: same limitation as KW; staleness pinned (max 4/1/1 bd); publication-lag convention identical to KW (obs dated ≤ t−1 usable for g_t).
5. Composite-only: ICP runs on the champion composite; sleeve-level attribution is out of scope.
6. All G0 windows are OOS while selection is IS (see §5 disclosure).
7. A2 r7 lesson 3 (longest-window re-test): the overlay is measured on the full 18.6y champion window — the longest window in which all inputs exist — so the discipline is inherent here; the honest 20y SPY re-test of the closest prior (41b) is why the candidate set contains no equity-index signal.
8. The champion composite was itself developed on the IS window; the ICP response is therefore not pristine out-of-development data. The OOS 2017+ segment (52% of rows) and the OOS-only G0 windows carry the extrapolation burden.
9. DTWEXBGS has weekly-ish publication cadence in parts of the window (max 4 bd staleness verified); its z-state may be stale at trigger time — affects arm A only if DTWEXBGS is selected.

## §9 Provenance

- Prerequisite verification: `verify_prereqs.py` (verification-only; ran once 2026-11-06) → `work/prereqs_verified.json` (all pins above).
- Templates: KW_TERMPREMIA_HUNT1 `FINDINGS_PRECOMMIT.md` (seal e96d87c), `run_arms.py` (frozen artifact), `FINDINGS.md` (negative-report pattern).
- Method references: Peters, Bühlmann & Meinshausen (2016) JRSS-B 78(3):947-1012; Heinze-Deml, Peters & Meinshausen (2018) Scand J Statist 45:1448-1483; Pfister, Bühlmann & Peters (2019) arXiv:1906.00073.
- Environment: .venv Python 3.12; scipy 1.18.1 (`alexandergovern`, `levene` verified available); numpy 2.5.4; pandas 3.1.0.

Sealed by: operator goal directive (2026-11-06) — "improve the champion significantly using innovational ideas", campaign promotion standard unchanged. All hyperparameters above are frozen (α = 0.05; blocks b1-b4; thresholds lo ±1.0 / re ±0.7 / g_cut 0.7; N seed 20261107; cost 6.4 bps). No peeking, no re-tuning after arms run.
