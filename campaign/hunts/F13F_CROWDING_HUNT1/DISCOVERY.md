# DISCOVERY — F13F CROWDING HUNT1 (13F holdings axis, direction 3)

**Date:** 2026-11-07/08. Verification-only feasibility work performed BEFORE
any pre-registration seal and BEFORE any holdings-derived estimand was
measured against the champion. This document records the fetch/parse chain,
data-era rules, hazards, law audit, and manager- roster reconnaissance so
the precommit (FINDINGS_PRECOMMIT.md) can cite verified facts rather than
assumptions. Nothing in here constitutes a measurement: no feature was
constructed on the champion grid, no gate was scored, no arm was run.

---

## 1. Law audit (frontier-closure law #147/#148)

- Prior 13F work in this repo is FILINGS-METADATA ONLY:
  `sec_13f_recent_filings(manager_cik)` (tools/wt/altdata3.py, 2026-09-14)
  returns filing dates + EDGAR URLs; `docs/validation.md:49` states "SEC
  filing metadata includes 13F events; **13F holdings tables and full filing
  text are not parsed**."
- CONCLUSION: **the 13F holdings axis is lawful to hunt** — no
  holdings-derived estimand has ever been measured against the champion.

## 2. SEC EDGAR fetch chain (proven end-to-end, 2008–2026, both format eras)

1. **Submissions JSON**: `https://data.sec.gov/submissions/CIK{cik:010d}.json`
   — CIK must be ZERO-PADDED 10 DIGITS (9 digits → HTTP 403 empty body).
   Declared User-Agent required ("Hsu David research
   dhsoftware.contact@gmail.com" works; fair-access ~10 req/s).
2. **Pagination**: `filings.recent` holds only ~1000 most-recent filings.
   Older filings live in `filings.files` pages
   (`CIK{cik}-submissions-001.json`, fetched from the same directory).
   **Pagination pages are FLAT JSON — same array schema as `recent` but at
   the ROOT (no `filings`/`recent` wrapper).** Without pagination,
   pre-2017 filings (the champion IS window) are unreachable.
3. **Filing directory**: `www.sec.gov/Archives/edgar/data/{cik}/{accession-no-dashes}/`
   — information-table filename VARIES per filing (`form13fInfoTable.xml`,
   `infotable.xml`, numbered like `56757.xml`): must discover from the
   directory index each time.
4. **Information table**: one namespace across all eras
   (`http://www.sec.gov/edgar/document/thirteenf/informationtable`);
   stdlib `xml.etree.ElementTree` parses all. Fields: nameOfIssuer,
   titleOfClass, cusip, value, shrsOrPrnAmt/sshPrnamt(+sshPrnamtType),
   putCall (optional/None), investmentDiscretion, votingAuthority.

## 3. Value-units era rule (verified via implied-price cross-checks)

Filings ACCEPTED before 2023-01-03 report `<value>` in **THOUSANDS**;
filings accepted on/after report **WHOLE DOLLARS**. The switch keys on
filing ACCEPTANCE date, NOT report period. Verified: KO $63.61 = exact
2022-12-30 close (thousands era); $60.22 = exact 2023-06-30 close (dollars
era). Normalization: `value_dollars = value * 1000 if acceptance <
2023-01-03 else value`.

## 4. Hazards

- **Duplicate rows**: large positions split across multiple infoTable rows
  (sub-accounts) — position-level features MUST aggregate by cusip within
  each filing.
- **Amendments**: 13F-HR/A exist (e.g. Berkshire 2008-11-14 amendment for
  2008-06-30 period). Precommit must seal the handling rule.
- **Stale entities**: Baupost CIK 0001054420 is a stale /ADV entity (only 5
  recent 13F-HR despite 107 full-text-search hits) — excluded from roster.
- **Vanguard**: CIK 0000102909 (10-digit!) verified valid but impractical —
  recent window spans only ~15 months due to filing volume; 14 pagination
  pages; index-fund fit for a crowding panel is questionable anyway.
- **PIT anchor**: filing_date (13F due within 45 days of quarter-end).
  Champion IS is < 2017-01-01, so a 2016-12-31 report period (filed
  2017-02-14) lands OOS-side under filing-date anchoring; effective
  IS-usable signals span report periods 2008Q1..2016Q3.
- **www.sec.gov/cgi-bin/browse-edgar → 403** (use data.sec.gov JSON APIs +
  /Archives/ with declared UA).

## 5. Manager roster (reconnaissance COMPLETE — all verified live 2026-11-07)

Objective roster rule (to be sealed in precommit): 6 long-lived,
concentrated-position hedge-fund/money-manager style filers with full
champion-IS coverage, chosen for mechanism fit (13F-visible concentration
assets), NOT for measured champion correlation. All 6 cover **36/36 IS
quarters** (report periods 2008Q1..2016Q4):

| Manager | CIK(s) | IS qtrs | IS filings | Full earliest | Full latest | Full filings |
|---|---|---|---|---|---|---|
| Berkshire Hathaway | 0001067983 | 36/36 | 48 | 1999-05-17 | 2026-08-14 | 211 |
| Bridgewater | 0001350694 | 36/36 | 43 | 2006-02-14 | 2026-08-14 | 98 |
| Paulson & Co | 0001035674 | 36/36 | 36 | 2002-02-07 | 2026-08-14 | 106 |
| Renaissance Tech | 0001037389 | 36/36 | 38 | 1999-05-17 | 2026-08-13 | 128 |
| Southeastern AM | 0000807985 | 36/36 | 36 | 1999-05-13 | 2026-08-14 | 112 |
| Appaloosa | 0001656456, 0001006438 | 36/36 | 39 | 1999-05-07 | 2026-08-14 | 116 |

- Berkshire needs pagination (page CIK0001067983-submissions-001.json: 167
  13F-HR incl. 47 with 2008–2016 report periods; earliest IS filing
  2008-05-15 report 2008-03-31 accession 0000950148-08-000200).
  Renaissance and Southeastern each need 1 pagination page. Bridgewater,
  Paulson, Appaloosa (both CIKs) fit in `recent`.
- Download budget: ~771 total 13F filings across the roster — minutes at
  ≤10 req/s. Trivially feasible.

## 6. Design anchor (for precommit §1)

Koijen-Yogo demand-system (JPE 2019) + Gabaix-Koijen asset-demand framing
(memory: research directions review 2026-11, direction 3). Realistic
estimand: 13F-derived manager-portfolio concentration/crowding state as a
de-risk overlay on the champion. Precommit MUST include a first-stage
environment-stability/invariance test per DEAD_IDEAS row 78 lesson
(champion IS return distribution is block-non-stationary in mean AND
variance; any parent-selection mechanism must render the conditional
distribution environment-stable or it fails the same invariance wall).

## 7. What was NOT done (pre-measurement integrity)

No holdings-derived feature was computed on the champion grid; no overlay
was measured; no gate scored; no arm run; zero unlevered_v1 trial slots
consumed. Probes parsed a handful of XMLs (Berkshire quarterly, dual eras)
solely to verify format/units — no feature values were recorded or compared
to champion returns.
