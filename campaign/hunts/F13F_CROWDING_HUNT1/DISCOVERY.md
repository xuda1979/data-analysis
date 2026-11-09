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

## 2. SEC EDGAR fetch chain (all links verified 2026-11-07/08, both format eras)

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
   directory index each time. **Directory-index hrefs are FULL ABSOLUTE
   PATHS** (`/Archives/edgar/data/{cik}/{acc}/{file}`), not bare filenames
   — probe lists must extract basenames (bug found + fixed 2026-11-08).
4. **TWO format eras** (census `work/chk_pd_ext.py`, 2026-11-08: 771
   roster HR+HR/A filings = 412 txt + 331 xml + 28 missing
   primaryDocument; the 28 no-pd are report periods 1998-12-31..2000-03-31,
   all pre-parse-scope. Extension by report year: all txt through 2012;
   **2013 is the transition year: 6 txt + 19 xml** — the 6 txt are 2013Q1
   report stragglers filed mid-2013; xml only from 2014 on. Parse scope
   report ≥ 2006-01-01: in scope 541 = 331 xml + 210 txt; skipped 230):
   - **XML era** (primary doc .xml; report ≥ 2013Q2, plus 2013 transition
     filings): the submissions `primaryDocument` is the **COVER PAGE**
     (331/331; e.g. `xslForm13F_X01/primary_doc.xml`), NOT the information
     table. The info table is discovered by candidate-name probes
     (`form13fInfoTable.xml`, `Form13FInfoTable.xml`, `infotable.xml`)
     with a strict `thirteenf/informationtable` namespace content check,
     then a directory-index fallback probing every `.xml` (cover excluded
     by name; covers fail the content check regardless — their namespace
     is `.../thirteenf/coverpage`).
   - **TEXT era** (primary doc .txt; report 1999..2013Q1): the primary
     document contains the info table as `<TABLE>` text markup, parsed by
     the verified frozen `work/proto_text_parser.py` (19/19 harness PASS;
     three-method cross-verification: token parse on collapsed text,
     independent re-parse, fixed-column-position slicing on
     whitespace-preserved text). Two styles observed: **Berkshire style**
     (space-separated 6-2-1 CUSIPs, comma-formatted values/shares, wrapped
     issuer names, `X` discretion, sub-account continuation rows, per-page
     subtotals) and **contiguous style** (other 5 managers: 9-char
     contiguous CUSIP, value right after, optional SH/PRN, discretion
     word, voting triple).
5. **Information table (xml era)**: one namespace across all xml-era
   filings (`http://www.sec.gov/edgar/document/thirteenf/informationtable`);
   stdlib `xml.etree.ElementTree` parses all. Fields: nameOfIssuer,
   titleOfClass, cusip, value, shrsOrPrnAmt/sshPrnamt(+sshPrnamtType),
   putCall (optional/None), investmentDiscretion, votingAuthority
   (Sole|Shared|None).
6. **Filer cover errors (4 verified — parsed TABLE truth is
   authoritative; a filing's own cover page can be wrong)**:
   - bridgewater 2008Q1 (000091412108000387): table 523 rows / 4,818,350
     vs cover Entry=5232, Value=4,059,999.
   - renaissance 2008Q1 (000103738908000003): table 51,582,503 vs cover
     51,582,492 (+11).
   - renaissance 2013Q1 (000103738913000054): table 41,273,179 vs cover
     41,273,211 (−32).
   - appaloosaOld 2008Q1 (000100643808000002): table 28 rows / 1,814,515
     (thousands) vs cover 1,814,514,000 (dollars; /1000 → 1,814,514;
     table truth verified two independent ways).
   **Policy**: row count vs cover Entry Total is the hard verification
   gate; cover Value Totals are ADVISORY only — reconciliation deltas are
   recorded in the fetch manifest, never used to alter parsed rows.

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
  each filing. Text-era continuation rows (Berkshire sub-account pattern)
  are frozen with entry_kind="cont" and EMPTY cusip; the forward-fill +
  aggregate-by-cusip rule is sealed in the precommit, not applied at
  freeze.
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
- **Freeze parse scope** (fetch_freeze_13f.py): report periods ≥
  2006-01-01 — the estimand window 2008Q1+ plus 8 quarters of warmup
  before grid start 2008-03-31 — so the frozen panel holds 44 report
  periods per manager (2006Q1..2016Q4) on the IS side; the roster rule's
  36/36 estimand quarters (2008Q1..2016Q4) is unchanged.

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
consumed. Verification parsing (format/units probes, the text-era parser
harness and its three-method cross-verification, and the full freeze
fetch) touched filings solely to establish format, units, and parse
correctness — no feature values were recorded or compared to champion
returns.
