# FINDINGS PRECOMMIT — F13F CROWDING HUNT1 (13F holdings axis, direction 3)

**Sealed:** 2026-11-08, BEFORE any 13F-derived feature was computed on the champion grid and BEFORE any overlay was measured. Companion sidecar `FINDINGS_PRECOMMIT.sha256` pins this file. Discovery record: `DISCOVERY.md` (commit 0e05ad6, verification-only).

## §1 Objective and law audit

Objective: test whether SEC 13F-derived manager-portfolio concentration/crowding state improves the champion as a one-directional de-risk overlay, under the campaign promotion standard (dSharpe ≥ +0.15 and §5 gates, pre-registered, operator memo).

Mechanism (H1): when long-lived concentrated discretionary managers crowd into few positions (high portfolio concentration), the Koijen-Yogo demand-system price-of-risk compresses and the champion's vulnerability to adverse demand shocks rises; de-risking when crowding is extreme should improve dSharpe. H0: the 13F crowding state carries no champion-relevant timing information (arms fail gates; controls indistinguishable).

Law audit (frontier-closure law #147/#148): prior 13F work in this repo is filings-metadata only (`sec_13f_recent_filings`, tools/wt/altdata3.py; docs/validation.md:49 — holdings tables never parsed). No holdings-derived estimand has ever been measured against the champion. All on-disk axes measured-closed: KW rates overlay (DEAD_IDEAS row 77), ICP parent-selection (row 78). The 13F holdings axis is a NEW data axis — lawful to hunt. Roster chosen for mechanism fit (6 long-lived concentrated filers, 36/36 IS quarters), NOT for measured champion correlation (DISCOVERY §5).

Design anchor: Koijen & Yogo (2019) demand-system approach; Gabaix-Koijen asset-demand framing. Estimand: 6-manager composite concentration (cusip-level HHI, arm A) and large-position share (top-10 weight share, arm C) as de-risk states.

Row-78 lesson (structural, binding): the champion IS return distribution is block-non-stationary in mean AND variance (ICP: AG ~2e-06, BF ~1e-14); any new mechanism must render the conditional distribution environment-stable or it fails the same invariance wall. §4.3 makes this a first-stage gate.

## §2 Frozen data

| Series | Source | Window | Rows | sha256 (first 16) |
|---|---|---|---|---|
| Champion daily returns | campaign/results/GOAL100_RAWEW13v2_WEIGHTED_GEAR16_daily.csv | 2008-03-31..2026-08-28 | 4806 | a8ed233bd0f6fd5d |
| holdings_berkshire.csv.gz | SEC EDGAR, fetch_freeze_13f.py | report ≥ 2006-01-01 | 11344 | 2a2c15902adbf519 |
| holdings_bridgewater.csv.gz | " | " | 39906 | 52260cb344cf884d |
| holdings_paulson.csv.gz | " | " | 4416 | f809d2d46de50f7e |
| holdings_renaissance.csv.gz | " | " | 273190 | 0479a3f421f13bd0 |
| holdings_southeastern.csv.gz | " | " | 6310 | 525227641ead1538 |
| holdings_appaloosa.csv.gz | " | " | 3559 | 59118438797d1c90 |

Fetch summary (run 3, 2026-11-08T17:19:08Z, manifest-authoritative): 541 filings fetched (331 xml + 210 txt — exact census match), 230 skipped (202 pre_2006 + 28 no_primary_document). All six managers IS report periods 44 (2006-03-31..2016-12-31). Determinism: managers 1-4 re-frozen with byte-identical sha256s across fetch runs 1-3 (crash-restarts after EDGAR 503s; no row drift).

Authoritative pins: `work/fetch_manifest.json` (per-manager sha256, row counts, IS report periods, skip records, advisory cover reconciliations). Fetch chain, format eras, units-era rule, filer cover errors: DISCOVERY.md §2-§3. Text-era parser frozen (`work/proto_text_parser.py`, 19/19 harness). Parsed TABLE truth is authoritative over filer cover pages (4 documented cover errors); row-count vs cover Entry Total is the hard verification gate; cover Value reconciliation is advisory only.

KW g-series comparators (axis-closure, §4.5): `KW_TERMPREMIA_HUNT1/work/g_A.csv` sha16 cc49cfba4664cef5; `g_B.csv` 1f9d77019459089c; `g_C.csv` b4fa8aefde66d8be.

## §3 Pinned baseline and metric conventions

Champion of record: ITER61_DDCON A_cap28 — ann 23.860978396835986%, SR 3.7844894672049048, MDD −3.304849169440516%, window 2008-03-31..2026-08-28, 4806 rows. IS < 2017-01-01: 2286 rows (2008-03-31..2016-12-30). OOS: 2520 rows (2017-01-02..2026-08-28). Zero negative calendar years (worst +7.5530%, 2013). Champion internal costs are embedded in the return series.

Metric conventions (KW-sealed, verbatim): SR = mean/std(ddof=1) × √252. CAGR = exp(252·mean(ln(1+r))) − 1 (geometric). MDD = min(NAV/cummax(NAV) − 1), NAV = (1+r).cumprod(). Calendar years: (1+r).groupby(year).prod() − 1. Overlay return r_t = g_t·champ_t − |g_t − g_{t−1}|·0.00064 (FULL |Δg| at 6.4 bps one-side; freed capital (1−g) earns 0%). T+1: g_t driven by data through t−1 (shift(1)); g_0 = 1.0. NaN signal → HOLD previous exposure (no toggle, no cost). τ = |Δg|/2; annualized half-turn = (252/n)·Στ; roll-252 half-turn = max trailing-252 Στ.

## §4 Frozen methodology

### 4.1 Holdings panel (from frozen csv.gz; no network at measurement time)

- Units normalization: `value_dollars = value × 1000` if `units == 'K'` else `value`. The `units` field is frozen per row (acceptance < 2023-01-03 → 'K'; on/after → 'D'; missing acceptance → 'K' conservative). DISCOVERY §3.
- Text-era continuation rows (`entry_kind == "cont"`, empty cusip): forward-fill cusip from the preceding `new` row within the same filing (Berkshire sub-account pattern); rows still lacking a cusip after forward-fill are dropped from position aggregates (count reported, not fixed).
- Aggregation: per filing, position value by cusip = Σ value_dollars over that cusip's rows (sub-account splits merged). All rows included regardless of putCall/sshPrnamtType — value-based concentration is instrument-blind (disclosed, §8.7).
- Amendment rule: per manager, sort filings by (report_date, acceptance); the active filing at session t is the LAST in this order with acceptance ≤ t−1 (most-recent-quarter, amended-version-wins; acceptance DateTime truncated to date).

### 4.2 Crowding features and traded state

- Per filing: HHI = Σ_i (v_i / Σv)² over cusip-level positions; TOP10 = Σ of the 10 largest v_i / Σv (all positions if fewer than 10).
- Composite step series (business-day index 2006-01-02..2026-12-31): per manager, active filing as of day d (acceptance ≤ d); composite_HHI(d) = equal-weight mean of per-manager HHI over managers with an active filing; NaN if < 3 managers active. Same for composite_TOP10. (Freeze parse scope report ≥ 2006-01-01 gives ~2 years of z warmup before the champion grid starts 2008-03-31.)
- Traded state: z = 1260-business-day rolling z (min_periods 252) of the composite LEVEL, computed on the full step series (KW convention), reindexed to champion sessions (as-of, last obs ≤ date). g_t driven by z_{t−1} (shift(1)).
- Direction is MECHANISM-FIXED (no β-sign peeking): HIGH concentration = crowding = adverse. De-risk when z_{t−1} > +1.0 → g = 0.7; re-risk when z_{t−1} ≤ +0.7 → g = 1.0. g_cut = 0.7. (Hysteresis = KW/ICP arm-A template, mirrored to the high side; no threshold tuning.)

### 4.3 First-stage environment-stability test (row-78 lesson; fail-closed)

- IS rows only: champion_t regressed on 1 + zA_{t−1} (OLS, pooled IS; zA = arm-A traded state).
- Residuals across the 4 IS blocks (authoritative np.array_split values, ICP-identical): b1 n=572 2008-03-31..2010-06-07; b2 n=572 2010-06-08..2012-08-15; b3 n=571 2012-08-16..2014-10-23; b4 n=571 2014-10-24..2016-12-30.
- Tests: (i) Alexander-Govern (equal residual means, heteroscedasticity-robust); (ii) Levene center='median' (Brown-Forsythe, equal residual variances). p_first = max(p_AG, p_BF).
- **p_first ≥ 0.05 → arms measured (§4.4). p_first < 0.05 → NEGATIVE (mechanism failure: the crowding state does not render the champion's conditional distribution environment-stable — the row-78 wall), no overlay measured.** All p-values reported either way.

### 4.4 Arms (measured only if §4.3 passes; single frozen run)

| Arm | Definition |
|---|---|
| A | composite_HHI z-state, §4.2 rule (de-risk z_{t−1} > +1.0 → 0.7; re-risk ≤ +0.7) |
| C | composite_TOP10 z-state, identical rule |
| P | time-reversed control: zA_rev = zA.iloc[::-1] realigned to champion index (KW pattern), same rule as A (de-risk z_rev > +1.0, re ≤ +0.7) |
| N | random control: iid N(0,1), seed **20261108** (fresh; KW 20261106, ICP 20261107), champion index, same rule as A |

### 4.5 Collapse branch (axis-closure guard)

After arms run: if any treatment arm's g-series matches a dead KW arm's g-series on ≥ 95% of the 4806 sessions (|g_F13F − g_KW| < 1e-6 per session), that arm is REFUTED on axis-closure grounds (the dead KW signal re-derived). Pearson + Spearman correlations vs each KW g-series are report-only.

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

Disclosure: all three G0 windows are OOS (≥2018) while the mechanism's validation span is IS-only; the 13F composite itself updates continuously through 2026-08 (acceptance-anchored, no staleness gap), but the IS-usable developmental span is report periods 2008Q1..2016Q3 (45-day filing lag, DISCOVERY §4). Extrapolation across the split carries the burden. This is the central scientific risk (KW failed exactly here: its de-risk windows never touched the champion MDD).

Adoption requirements (beyond gates): A-R1 MDD strictly shallower than −3.30485%; A-R2 zero negative years preserved.

Report-only (no gating): IS/OOS dSR split; decade bins; cost stress 8/10 bps; toggles; fraction of sessions de-risked; first-stage p-values; per-manager composite contributions; KW g-series correlations.

Sealed decision rule: any treatment arm (A or C) passing G0-G6 → promotion memo (operator decision, highest dSharpe, ITER61_DDCON pattern). None → NEGATIVE: FINDINGS.md honest negative + DEAD_IDEAS.csv row 79. P or N passing G1 → machinery INVALID, results void. First-stage failure (§4.3) → NEGATIVE (mechanism failure), no overlay measured. Arms A and C both failing G0 → NEGATIVE with the KW-lesson structural finding.

## §6 Falsification criteria

- First-stage failure (p_first < 0.05) → NEGATIVE (mechanism failure, row-78 wall; no overlay measured).
- Activity band: fraction of de-risked sessions < 2% (inert) or > 60% (regime label, not a tail signal) → arm REFUTED. Activity within band is necessary, not sufficient.
- Collapse branch (§4.5) → arm REFUTED (axis closure).
- G6 violation → machinery void.
- All treatment arms fail G0 → NEGATIVE (the crowding state does not time the champion's realized tails).

## §7 Budget and registry

- One frozen measurement run (`run_hunt.py` artifact — first stage + arms + gates in one script, sha recorded at the evidence commit); no re-runs, no re-tuning after unblinding (TVPVECM_HUNT1 precedent).
- Zero unlevered_v1 trial slots consumed (overlay on pinned champion series; `research/protocols/unlevered_v1.json` untouched).
- P6 paper runner and scorecard untouched.
- No git push without explicit operator authorization; explicit-pathspec commits only; append-only registries.
- data_exposure_v1 classification: SEC EDGAR public data + repo-pinned champion series — same class as KW/ICP hunts. EDGAR fair-access compliant (declared UA, ≤ 6.7 req/s).

## §8 Limitations disclosed at seal

1. 45-day filing lag: the PIT anchor is acceptance date; IS-usable report periods are 2008Q1..2016Q3 (2016Q4 filed 2017-02 lands OOS-side). Quarterly information is inherently slower than the daily grid.
2. Quarterly granularity: the composite steps only at acceptance events (~63 bd apart); de-risk states persist long between updates — the overlay is a slow regime gate by construction.
3. Six-manager roster: the composite is a mean over 6 idiosyncratic books; single-manager noise (Bridgewater's macro book, Renaissance's quant book) is imperfectly aligned with the long-only concentration mechanism.
4. Roster selection is mechanism-fit-based, disclosed but not random; survivorship (all 6 still filing 2026) is acknowledged.
5. The champion composite was itself developed on the IS window; the response is not pristine out-of-development data. The OOS 2017+ segment (52% of rows) and the OOS-only G0 windows carry the extrapolation burden.
6. All G0 windows are OOS (see §5 disclosure).
7. Value-based concentration is instrument-blind: option rows (putCall Put/Call) and PRN entries enter the value aggregate; hedged books may read as concentrated.
8. Text-era parse risk: 210 in-scope text filings parsed by the frozen three-method-verified parser (19/19 harness); residual parse risk is acknowledged, not correctable post-seal.
9. Filer cover errors (4 documented): parsed TABLE truth is authoritative; cover reconciliation is advisory only and never alters rows.
10. Units-era rule keys on acceptance date: a mis-keyed acceptance would shift value scale by 1000×; mitigated by the implied-price verification (DISCOVERY §3) and the per-row frozen `units` field.

## §9 Provenance

- Discovery: `DISCOVERY.md` (commit 0e05ad6, 2026-11-07/08) — fetch chain, format eras, units-era rule, cover errors, roster reconnaissance; verification-only, pre-measurement.
- Data provisioning: `fetch_freeze_13f.py` (frozen artifact) → `data/holdings_{mgr}.csv.gz` × 6 + `work/fetch_manifest.json` (sha256 pins; deterministic gzip).
- Prerequisite verification: `verify_prereqs.py` (verification-only, one run) → `work/prereqs_verified.json` (champion pin, manifest pins, KW comparator pins, environment versions).
- Templates: KW_TERMPREMIA_HUNT1 `FINDINGS_PRECOMMIT.md` (seal e96d87c); ICP_CAUSAL_HUNT1 `FINDINGS_PRECOMMIT.md` (seal 9bb7b21) — gates, metric conventions, arms structure, collapse branch reused verbatim.
- Method references: Koijen & Yogo (2019), "A Demand System Approach to Asset Pricing", Journal of Political Economy; Gabaix & Koijen (2024), "Asset Demand of US Households", Journal of Political Economy.
- Environment: .venv Python 3.12.16; scipy 1.18.1 (`alexandergovern`, `levene`); numpy 2.5.4; pandas 3.1.0.

Sealed by: operator goal directive (2026-11-05) — "improve the champion significantly using innovational ideas", campaign promotion standard unchanged. All hyperparameters above are frozen (α = 0.05; blocks b1-b4; thresholds de-risk +1.0 / re-risk +0.7 / g_cut 0.7; N seed 20261108; cost 6.4 bps; first-stage p_first = max(p_AG, p_BF) ≥ 0.05; activity band 2%-60%). No peeking, no re-tuning after arms run.
