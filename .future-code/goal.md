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
- [x] 7. Evidence hygiene: append-only scorecard/registry; no git push without explicit authorization; explicit-pathspec commits only.
- [x] 8. ICP_CAUSAL_HUNT1 axis (direction 1, ICP variable-selection mechanism — NEW to repo, frontier law-compliant): precommit sealed 9bb7b21 BEFORE measurement (sha 5ddfc3bac…); prerequisites verified GREEN; run_hunt.py frozen artifact (§4: 8-subset linear ICP, AG+BF invariance tests, 4 IS blocks; arms A/C/P/N seed 20261107; G0 kill-switch + G1-G6); single frozen run 2026-11-07. NEGATIVE — no-subset-accepted branch: ALL 8 subsets reject invariance (p_S 1.97e-06..2.96e-06 vs α=0.05); EMPTY-subset rejection shows champion IS distribution block-non-stationary in mean AND variance (AG ~2e-06 / BF ~1e-14), no parent absorbs it; ICP fail-closed per design; no overlay measured (pre-registered branch). Evidence: FINDINGS.md + work/icp_selection.json + work/arm_results.json + DEAD_IDEAS.csv row 78.
- [x] 9. Verdict recorded: FINDINGS.md honest negative (no-subset-accepted branch, per §4.1/§5 sealed rule) + DEAD_IDEAS.csv row 78 + evidence commit with explicit pathspec.
- [ ] 10. F13F_CROWDING_HUNT1 axis (direction 3, 13F holdings — NEW data axis, frontier law-compliant per DISCOVERY §1): law audit GREEN (prior 13F work was filings-metadata only); fetch/parse chain verified both format eras (submissions JSON + FLAT pagination, xml cover-vs-infotable discovery, text-era parser 19/19 harness + three-method cross-verification); units-era rule verified (acceptance <2023-01-03 = thousands); 4 filer cover errors documented (table truth authoritative); 6-manager roster verified 36/36 IS quarters; discovery committed 0e05ad6 BEFORE pre-registration; precommit sealed BEFORE measurement (FINDINGS_PRECOMMIT.md + sha256 sidecar, commit 0c0b63b, holds 541 filings / 6 managers, CUSIP checksum guard census, value-sanity drop census 4 rows). In progress: verify_prereqs.py GREEN (work/prereqs_verified.json: champion pin sha16 a8ed233bd0f6fd5d 4806 rows SR 3.7845 CAGR 23.86% MDD -3.30% 0 neg years; split 2286/2520; blocks 572/572/571/571; G0 windows 11/4/6; 6 holdings sha16+rows vs manifest 541 filings; KW g_A/g_B/g_C pins; env 3.12.16/1.18.1/2.5.4/3.1.0) → build run_hunt.py frozen artifact → single frozen run → verdict/DEAD_IDEAS row 79.

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
Round opened 2026-11-05 (innovation-focused). Items 1-6 complete for the KW rates axis: NEGATIVE recorded 2026-11-06, KW_TERMPREMIA_HUNT1 closed. Items 8-9 complete for the ICP causal axis: NEGATIVE recorded 2026-11-07 (no-subset-accepted branch), ICP_CAUSAL_HUNT1 closed.

2026-11-07 ICP hunt record: precommit sealed 9bb7b21 → verify_prereqs.py GREEN → run_hunt.py frozen artifact → single frozen measurement → FINDINGS.md + DEAD_IDEAS row 78. All 8 subsets reject invariance (p_S ~2e-06, 5-14 orders below α=0.05); EMPTY-subset rejection is the diagnostic: champion IS return distribution is block-non-stationary in mean AND variance and no FRED parent innovation absorbs it. ICP fail-closed per design — no spurious causal parent handed back. Structural lesson: any future parent-selection mechanism must ALSO render the champion's conditional distribution environment-stable, or it fails the same invariance wall.

Two innovation axes now measured-closed this round (KW rates overlay, ICP parent-selection). Third axis IN EXECUTION: **F13F_CROWDING_HUNT1 (13F holdings)** — discovery sealed 0e05ad6, precommit sealed 0c0b63b, prerequisites verified GREEN (2026-11-09). Next: build run_hunt.py frozen artifact (§4.1-§4.5), then ONE frozen measurement run, then verdict. (2-honest) conformal layer still blocked until ≥60 H1 panel dates (~early Dec 2026).
