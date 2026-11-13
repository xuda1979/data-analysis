# FINDINGS — F13F CROWDING HUNT1 (13F holdings axis, direction 3)

Date: 2026-11-13
Precommit: `FINDINGS_PRECOMMIT.md`, sealed at commit `0c0b63b`, sha256 `4a3694887318a4bea8407912e16f1818fd4db02e90d3c18c0d1a72bb2c0ab238`.

This document reports results exactly per the sealed spec. No hyperparameter was
changed after seal; all numbers below are from the single frozen run
(`run_hunt.py`, sha256 `75606252c42a3e16ba16f0d27f98a177c7b601993e775256a84fae030c16539f`).

## VERDICT: NEGATIVE — first-stage environment-stability failure (row-78 wall). No overlay was measured.

H1 (high manager concentration = crowding = adverse → de-risk improves dSharpe)
is **not testable on this champion**: the §4.3 first-stage gate failed decisively
and the sealed fail-closed branch fired. Arms A/C/P/N were never constructed;
the N seed 20261108 was never drawn; gates G0–G6 were never scored; §4.5 collapse
branch never evaluated; no g-series was written.

The sealed decision rule (§5) reads: "First-stage failure (§4.3) → NEGATIVE
(mechanism failure), no overlay measured."

## 1. The first-stage run

IS-only OLS `champion_t ~ 1 + zA_{t-1}` (zA = composite 6-manager HHI z-state,
1260/252 rolling, as-of reindexed to champion grid); residuals across 4 pinned
IS blocks; Alexander-Govern (equal means) + Brown-Forsythe (equal variances);
`p_first = max(p_AG, p_BF)`; α = 0.05.

| quantity | value |
|---|---|
| reg rows (IS, after shift) | 2285 |
| dropped by shift(1) warmup | 1 |
| block ns (b1..b4) | 571, 572, 571, 571 |
| intercept | 0.000746780 |
| beta(zA_{t-1}) | 4.048e-05 |
| p Alexander-Govern | 1.594e-06 |
| p Brown-Forsythe | 1.120e-14 |
| **p_first** | **1.594e-06** |
| pass (p_first ≥ 0.05) | **False** |

Failure is categorical — 5 to 14 orders of magnitude below α — not borderline.
Block ns are (572,572,571,571) minus the shift-warmup row in b1, as expected.
The beta on zA_{t-1} (4.05e-05) shows the crowding state has essentially no
linear association with next-day champion IS returns.

## 2. Falsification analysis — the row-78 wall, third independent confirmation

The champion IS return distribution is block-non-stationary in mean (AG) AND
variance (BF). Conditioning on the 13F manager-concentration composite does
NOT absorb it:

- ICP_CAUSAL_HUNT1 (2026-11-08): empty-subset rejection — all 8 FRED-parent
  subsets reject invariance (p_S ~2e-06 AG / ~1e-14 BF comparable magnitudes).
- F13F_CROWDING_HUNT1 (this run): the same rejection appears with an entirely
  different conditioning axis (13F holdings-derived crowding state).
- Structural implication: this is a property of the CHAMPION's IS return
  distribution (regime-dependent mean/variance across 2008–2016 blocks), not of
  any particular candidate signal. Any future de-risk hunt on this champion
  must clear the environment-stability first stage before any overlay is
  measured — the first stage is now proven discriminating (it fired on KW's
  axis family via ICP, and now on the 13F axis).

The 13F crowding axis is measured-closed for de-risk overlays under the current
first-stage law. This does NOT close the axis for other overlay geometries
(e.g., cross-sectional or conditioning use) — those require new pre-registration.

## 3. Branch integrity (what was NOT done)

- Arms A (HHI), C (TOP10), P (time-reversed control), N (iid N(0,1) control)
  never constructed; no `g_*.csv` / `ret_*.csv` written.
- HIGH-side hysteresis rule (z>1.0 → g=0.7; z≤0.7 → g=1.0) never applied.
- Gates G0 (drawdown-overlap pre-screen), G1–G5, G6 (controls validity) never
  scored; activity band (§6) never applied.
- §4.5 collapse branch vs KW g-series never evaluated (KW comparators never
  loaded).
- N seed 20261108 unused.

## 4. Execution integrity

One pre-measurement crash occurred on the first execution attempt:
`TypeError: Cannot compare tz-naive and tz-aware datetime-like objects` at
`build_composite` (`step.searchsorted(acc)`), caused by UTC-suffixed
`acceptance_dt` strings parsing tz-aware against a tz-naive step grid.
Full traceback preserved: `work/run_stdout_crash1.txt`.

The crash was pre-measurement: `work/` contained NO measurement outputs at
crash time (verified by directory listing — no `first_stage.json`,
`arm_results.json`, `g_*`, `ret_*`). No gate, verdict, or diagnostic
information had been produced. The single-run integrity rule (pre-measurement
crash → fix and re-run permissible; post-measurement → never) applied. Fix:
`.dt.tz_localize(None)` inserted before `.dt.normalize()` in
`build_filing_features`. The re-run is the one frozen measurement run.

## 5. Panel-health diagnostics (report-only)

- Holdings: 0 rows dropped for null cusip/value (all 6 managers); 0 filings
  with zero total value; unique accessions: appaloosa 85, berkshire 110,
  bridgewater 94, paulson 84, renaissance 85, southeastern 82.
- Bridgewater shows 94 unique accessions vs 95 filings in the fetch manifest —
  one accession collision; the (manager, accession)-keyed per-filing aggregate
  merges both filings' rows. Report-only; measurement frozen regardless.
- Composite: step grid 5479 bdays (2006-01-02..2026-12-31); composite first
  valid 2006-05-15 (well before champion start 2008-03-31); all 6 managers
  active through the champion window (5383–5393 active days each).
- zA and zC: 0 NaN days on the champion grid (5-bd staleness guard never
  tripped).

## 6. What survives

- The frozen 6-manager holdings panel (541 filings, sha-pinned per
  `HOLD_SHA` in `run_hunt.py`) — the first parsed 13F holdings table in repo
  history (prior state: metadata only).
- The fetch chain (`data/fetch_freeze_13f.py`, `data/fetch_manifest.json`)
  and the text-era parser (`data/proto_text_parser.py`) — reusable for any
  future 13F work.
- Per-filing HHI/TOP10 features and the composite construction code —
  available for conditioning or cross-sectional use under new pre-registration.

## 7. Provenance

- Champion series sha-pinned: `a8ed233b...fbf4` (4806 rows, verified).
- Six holdings csv.gz sha-pinned and verified at run time.
- Frozen run: `work/first_stage.json`, `work/arm_results.json`,
  `work/run_stdout.txt` (crash log: `work/run_stdout_crash1.txt`).
- Prerequisite verification (GREEN, commit `f0634e8`): `work/prereqs_verified.json`.
