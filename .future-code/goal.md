# Session Goal

## Goal
Improve the champion significantly using innovational ideas.

Champion of record (2026-10-12): **ITER61_DDCON A_cap28** — RAW-EW13v2 relw @1.6x gross; ann 23.86%, SR 3.78, MDD −3.30%, window 2008-03-31..2026-08-28; daily sha16 `a8ed233bd0f6fd5d`, weights `2b0f5fbc43113149`.

"Significantly" = the campaign promotion standard (dSharpe ≥ +0.15 and §1 turnover/roll gates, pre-registered, operator memo). "Innovational" = new data axis or new mechanism (frontier-closure law #147/#148: all on-disk axes are measured-closed; re-running closed axes is unlawful). Memory priority order (2026-11 reviews): (2-honest) conformal risk layer on existing H1 tail panel > (1) ICP causal overlay > (3) 13F holdings parsing > (4) rates-side term-premia (KW/ACM, free) > (5) TVP-VECM core DEAD 2026-11-03, only Arm-A pairs variant remains > (6) SFC scenario only.

## Checklist
- [x] 1. Baseline audit: champion verified byte-exact on this machine (daily sha16 `a8ed233bd0f6fd5d`, weights `2b0f5fbc43113149`); raw files missing here (~11,684) but series hash-pinned — comparisons run against the pinned series on identical windows/costs.
- [x] 2. H1 tail-factor panel ALIVE and growing: 25 trade dates (20260908..20261104, 20261103 permanent gap); daily harness restored 2026-11-05 (deleted never-in-git `cboe_options_dl.py` reconstructed + .gitignore root-cause fixed + committed); trade date 20261104 recovered 9/9; heartbeat green. HUNT_H1_TAILFACTOR adjudication needs ≥60 dates (~early Dec 2026) — paper-forward pre-registration is the lawful design.
- [x] 3. Rates-side axis (direction 4): KW_TERMPREMIA_HUNT1 executed 2026-11-06 — sealed precommit e96d87c BEFORE measurement; 5 arms (A/B/C/P/N) + champion scored identical windows/costs. NEGATIVE: all treatment arms fail G2 (CAGR sacrifice 2.83-3.88pp vs 0.5pp); B's G1 pass (+0.246) is the sealed CAGR-sacrifice refutation branch; G6 holds (machinery valid); de-risk windows never overlapped champion MDD (0/12 sessions in 2023-12 window). Evidence: FINDINGS.md + work/ + DEAD_IDEAS.csv row 77, commit 32a904e. KW data panel survives for conditioning use.
- [x] 4. Pre-register gates BEFORE measurement — DONE for KW hunt (FINDINGS_PRECOMMIT.md + sha256 sidecar, commit e96d87c); no gate edits after unblinding; DEAD_IDEAS.csv appended on refutation.
- [x] 5. Smallest evaluable artifact + negative controls — DONE: run_arms.py (frozen artifact, 4806-row champion pin) + placebo P (time-reversed) + random N (seed 20261106) controls; both controls failed G1 as required (G6 valid).
- [x] 6. Refuted → negative recorded (FINDINGS.md honest negative + DEAD_IDEAS.csv + commit 32a904e); advance to next axis.
- [ ] 7. Evidence hygiene: append-only scorecard/registry; no git push without explicit authorization; explicit-pathspec commits only.

## Unknowns to resolve first
- Is the champion daily/weights series on THIS machine (hash-pinnable) or only on the Mac?
- H1 panel date count as of today — does a conformal layer have enough panel dates to evaluate anything now?
- Does any free source give the champion's raw price history end-to-end on this machine (Yahoo v8 adapter exists for the 8-fund panel)?

## Standing constraints
- Champion trio STAGED-UNCHANGED; sealed engine code unchanged; no results/ metric touched without an honest beat.
- Free data only (FRED/BLS/EDGAR/TIC/CFTC/BIS/IMF/EIA/free-EOD); no paid feeds.
- Pro-cyclical gate lesson (2026-11-03): any gate must score prospect of reversion, not trailing realized reversion.
- HUNT_H1_TAILFACTOR adjudication ~early Dec 2026 (≥60 CBOE panel dates).
- Raw-data provenance manifest GREEN or deliberately re-pinned with ledger note.

## Status: in_progress
Round opened 2026-11-05 (innovation-focused). Items 1-6 complete for the KW rates axis (item 3): NEGATIVE recorded 2026-11-06, KW_TERMPREMIA_HUNT1 closed.

2026-11-06 KW hunt record: precommit sealed e96d87c → artifact run_arms.py → single frozen measurement → FINDINGS.md + DEAD_IDEAS row + evidence commit 32a904e. No treatment arm passes G1-G6 (all fail G2 on 5-8x CAGR over-sacrifice; A/C also fail G1; B's G1 pass is the sealed refutation branch). G6 machinery-valid. Structural lesson: market-implied TP levels do not time the champion's tail — de-risk episodes (2008-2021) never overlapped the champion MDD window (2023-12). Future de-risk hunts must first pass an in-sample drawdown-overlap pre-screen.

Next axis per memory priority order (2026-11 reviews): (1) ICP causal overlay — surviving TVPVECM lesson applies (trailing-window invariance scores are pro-cyclical; pre-register that concern), or (3) 13F holdings parsing (metadata already collected; holdings tables never parsed). (2-honest) conformal layer still blocked until ≥60 H1 panel dates (~Dec 2026).
