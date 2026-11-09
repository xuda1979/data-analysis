#!/usr/bin/env python3
"""F13F_CROWDING_HUNT1 — 13F holdings fetch + freeze (verification-only).

Fetches ALL 13F-HR / 13F-HR/A filings for the 6-manager roster (DISCOVERY.md
§5) from SEC EDGAR, parses each information table to RAW position rows, and
freezes per-manager csv.gz + a manifest with sha256 pins. NO feature is
computed on the champion grid; no aggregation beyond raw-row extraction;
this is data provisioning for the precommit (FINDINGS_PRECOMMIT.md), which
is sealed BEFORE any measurement.

Chain (all verified in DISCOVERY.md, 2026-11-07):
  1. submissions JSON  https://data.sec.gov/submissions/CIK{cik:010d}.json
  2. pagination pages  CIK{cik}-submissions-001.json  (FLAT JSON at ROOT)
  3. filing directory  www.sec.gov/Archives/edgar/data/{cik}/{acc-no-dash}/
  4. XML era (primary doc .xml; report >= 2013Q2): primaryDocument is the
     COVER page (xslForm13F_X01/primary_doc.xml; 331/331 per chk_pd_ext.py
     2026-11-08), NOT the information table -> info table discovered by
     candidate probes (form13fInfoTable.xml, Form13FInfoTable.xml,
     infotable.xml) with a strict thirteenf/informationtable content check,
     then directory-index fallback probing every .xml (primary_doc.xml
     cover excluded by name; covers fail the content check regardless:
     their namespace is .../thirteenf/coverpage).
  5. TEXT era (primary doc .txt; report 1999..2013Q1, 2013's 6 txt are
     2013Q1 stragglers filed mid-2013): primary document contains the info
     table as <TABLE> text markup -> parsed by the verified
     work/proto_text_parser.py (19/19 harness PASS, three-method
     cross-verification, three filer-cover-error pins as overrides).
     Documents cached at work/cache/{acc}_{doc} (shared with the harness).

Parse scope: report periods >= 2006-01-01 (estimand window 2008Q1+ plus
8 quarters of warmup before grid start 2008-03-31). Filings with report
< 2006-01-01 OR missing primaryDocument are skipped and recorded in the
manifest (reasons pre_2006 / no_primary_document; the 28 no-pd entries
are report periods 1998-12-31..2000-03-31, all pre-2006). Roster census
(chk_pd_ext.py 2026-11-08): 771 HR+HR/A = 331 xml + 412 txt + 28 no-pd;
in scope 331 xml + 210 txt; skipped 230.

Rows are frozen EXACTLY as parsed with one documented exception (value
sanity below): text-era continuation rows (Berkshire sub-account pattern)
keep entry_kind="cont" and an EMPTY cusip; the forward-fill +
aggregate-by-cusip rule is sealed in the precommit, not applied here.

Value sanity (sealed 2026-11-09, census-quantified): rows whose parsed
`value` STRICTLY exceeds 1e12 under units 'K' (thousands) / 1e15 under
'D' (dollars) — the diag_defects.py convention — are source-corrupt and
DROPPED from the freeze; per filing the manifest records
`value_sanity_dropped` and `rows_parsed` (rows_parsed == rows +
value_sanity_dropped; on text-era rows_parsed reconciles to the cover
Entry Total, so the hard count gate still audits). Census: exactly 4 rows
over cap across all 541 filings, all in paulson 2007Q4 (accession
000103567408000001), all glued value+shares tokens VERBATIM in the SEC
text document (Alcoa "42946311750000 SH", Boston Scientific
"71854161783400 SH", Kinross "54045529344053 SH", Mirant
"73738118916900 SH"); they swelled paulson 2007Q4 value_sum to
242,584,124,525,341 vs cover 5,156,828. XML: 0 rows over cap. NO
non-integer or other plausibility rejection is applied.

Units-era rule (DISCOVERY.md §3): acceptance < 2023-01-03 -> value in
THOUSANDS; on/after -> whole DOLLARS. Recorded per row as `units` ('K'/'D');
normalization is a METHODOLOGY decision sealed in the precommit, not applied
here.

stdlib urllib only (no `requests` in .venv). Declared UA, <=10 req/s.
"""
import csv
import gzip
import hashlib
import io
import json
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
WORK = HERE / "work"
SUBS_CACHE = DATA / "submissions"

sys.path.insert(0, str(WORK))
from proto_text_parser import parse_text_infotable  # noqa: E402  (verified, frozen)

UA = {"User-Agent": "Hsu David research dhsoftware.contact@gmail.com"}
MIN_INTERVAL = 0.15  # ~6.7 req/s, comfortably inside fair-access ~10 req/s
NS = "{http://www.sec.gov/edgar/document/thirteenf/informationtable}"
UNITS_SWITCH = "2023-01-03"  # acceptance-date key (DISCOVERY.md §3)
TEXT_REPORT_MIN = "2006-01-01"  # parse scope: estimand 2008Q1+ + 8q warmup

# Roster (DISCOVERY.md §5). value: [primary CIK, extra CIKs...]  — all 10-digit.
ROSTER = {
    "berkshire":    ["0001067983"],
    "bridgewater":  ["0001350694"],
    "paulson":      ["0001035674"],
    "renaissance":  ["0001037389"],
    "southeastern": ["0000807985"],
    "appaloosa":    ["0001656456", "0001006438"],
}
FORMS = ("13F-HR", "13F-HR/A")
FIELDS = ["nameOfIssuer", "titleOfClass", "cusip", "value", "sshPrnamt",
          "sshPrnamtType", "putCall", "investmentDiscretion", "votingAuthority"]
OUT_FIELDS = ["manager", "cik", "accession", "form", "filed_date",
              "acceptance_dt", "report_date", "units", "source", "filename",
              "row_idx", "entry_kind"] + FIELDS

_last = [0.0]


def get(url, binary=False):
    """Throttled GET with declared UA; retries transient transport errors
    AND HTTP 502/503/504 (EDGAR overload; mid-run 503 seen 2026-11-08).
    Other HTTPError passes through: 404s are semantic probe results."""
    dt = time.monotonic() - _last[0]
    if dt < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - dt)
    _last[0] = time.monotonic()
    req = urllib.request.Request(url, headers=UA)
    last_err = None
    for attempt in range(13):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                b = r.read()
            return b if binary else b.decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            if e.code in (502, 503, 504) and attempt < 12:
                last_err = e
                # capped 30..300s backoff: outlast multi-minute EDGAR 503
                # outages (both runs of 2026-11-08 died mid-renaissance
                # when 40s max backoff was not enough)
                time.sleep(min(30 * (attempt + 1), 300))
                continue
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
            time.sleep(min(15 * (attempt + 1), 120))
    raise last_err


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def submissions_for(cik):
    """Recent + paginated submissions merged; returns list of filing dicts.

    Both `recent` and pagination pages share the parallel-array schema;
    pagination pages are FLAT (no filings/recent wrapper).
    """
    text = get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
    js = json.loads(text)
    recent = js["filings"]["recent"]

    def arrays_to_dicts(d):
        keys = list(d.keys())
        n = len(d.get("accessionNumber", []))
        return [{k: d[k][i] for k in keys} for i in range(n)]

    out = arrays_to_dicts(recent)
    for extra in js["filings"].get("files", []):
        name = extra["name"]  # e.g. CIK0001067983-submissions-001.json
        ptext = get(f"https://data.sec.gov/submissions/{name}")
        pjs = json.loads(ptext)  # FLAT: parallel arrays at root
        out.extend(arrays_to_dicts(pjs))
    return out


def find_infotable(cik, accession_nodash):
    """Discover the information-table XML in the filing directory.

    XML-era primaryDocument is the COVER page (xslForm13F_X01/
    primary_doc.xml; chk_pd_ext.py 2026-11-08), not the info table.
    Candidate names first, then directory-index fallback probing every
    .xml; accept only on the strict verified namespace URI. Successful
    results are cached at work/cache/xml_{acc}_{name} so crash-restarts
    don't re-probe (EDGAR 503 mid-run 2026-11-08).
    """
    def is_infotable(b):
        return b"thirteenf/informationtable" in b[:4000]

    cdir = WORK / "cache"
    for old in sorted(cdir.glob(f"xml_{accession_nodash}_*.xml")):
        b = old.read_bytes()
        if is_infotable(b):
            return old.name.split("_", 2)[2], b
    for cand in ("form13fInfoTable.xml", "Form13FInfoTable.xml", "infotable.xml"):
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_nodash}/{cand}"
        try:
            b = get(url, binary=True)
            if is_infotable(b):
                (cdir / f"xml_{accession_nodash}_{cand}").write_bytes(b)
                return cand, b
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
    # Directory index fallback: probe every xml except the cover page.
    idx = get(f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_nodash}/")
    names = sorted({h.rsplit("/", 1)[-1]
                    for h in re.findall(r'href="([^"]+\.xml)"', idx, re.I)})
    for name in names:
        if name.lower() == "primary_doc.xml":
            continue
        url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_nodash}/{name}"
        try:
            b = get(url, binary=True)
            if is_infotable(b):
                (cdir / f"xml_{accession_nodash}_{name}").write_bytes(b)
                return name, b
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
    return None, None


def fetch_text_filing(cik, accession_nodash, doc):
    """Text-era primary document, cached at work/cache/{acc}_{doc}
    (shared with the proto_text_parser harness cache)."""
    key = WORK / "cache" / f"{accession_nodash}_{doc}"
    if key.exists():
        return key.read_text(errors="replace")
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_nodash}/{doc}"
    b = get(url, binary=True)
    key.write_bytes(b)
    return b.decode("utf-8", errors="replace")


def parse_infotable(xml_bytes):
    """Raw rows from one XML-era information table."""
    rows = []
    root = ET.fromstring(xml_bytes)
    for i, it in enumerate(root.iter(f"{NS}infoTable")):
        row = {}
        for f in FIELDS:
            if f in ("sshPrnamt", "sshPrnamtType"):
                # nested under shrsOrPrnAmt (DISCOVERY.md §2)
                el = it.find(f"{NS}shrsOrPrnAmt/{NS}{f}")
                row[f] = (el.text or "").strip() if el is not None else ""
                continue
            el = it.find(f"{NS}{f}")
            if el is None:
                row[f] = ""
                continue
            if f == "votingAuthority":
                row[f] = ((el.findtext(f"{NS}Sole") or "").strip() + "|"
                          + (el.findtext(f"{NS}Shared") or "").strip() + "|"
                          + (el.findtext(f"{NS}None") or "").strip())
            else:
                row[f] = (el.text or "").strip()
        rows.append(row)
    return rows


def units_for(acceptance_dt):
    if not acceptance_dt:
        return "K"  # conservative default; sealed rule keys on acceptance
    return "D" if acceptance_dt[:10] >= UNITS_SWITCH else "K"


def _fmt_num(v):
    """Text-era numeric -> csv cell: integral floats without a '.0'
    (text-era values are integer thousands; None -> '')."""
    if v is None:
        return ""
    f = float(v)
    return str(int(f)) if f == int(f) else repr(f)


def text_row_to_out(r):
    """One parse_text_infotable row -> OUT_FIELDS-shaped dict (meta fields
    and entry_kind added by the caller)."""
    return {
        "nameOfIssuer": r["name"], "titleOfClass": "",
        "cusip": r["cusip"], "value": _fmt_num(r["value"]),
        "sshPrnamt": _fmt_num(r["shares"]),
        "sshPrnamtType": r["sshPrnamtType"], "putCall": r["putCall"],
        "investmentDiscretion": r["investmentDiscretion"],
        "votingAuthority": ""}


def main():
    DATA.mkdir(exist_ok=True)
    WORK.mkdir(exist_ok=True)
    SUBS_CACHE.mkdir(exist_ok=True)
    manifest = {"fetched_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "managers": {}, "ua": UA["User-Agent"]}
    grand_total = 0

    for mgr, ciks in ROSTER.items():
        mgr_rows = []
        mgr_filings = []
        mgr_skipped = []
        for cik in ciks:
            # cache submissions JSONs (they are large; roster recon used them)
            sfile = SUBS_CACHE / f"CIK{int(cik):010d}.json"
            if sfile.exists():
                js_all = json.loads(sfile.read_text())
            else:
                js_all = submissions_for(cik)
                sfile.write_text(json.dumps(js_all))
            for f in js_all:
                if f.get("form") not in FORMS:
                    continue
                acc = f["accessionNumber"].replace("-", "")
                acceptance = f.get("acceptanceDateTime", "")
                filed = f.get("filingDate", "")
                report = f.get("reportDate", "")
                units = units_for(acceptance)
                pd = f.get("primaryDocument") or ""
                base = {"cik": cik, "accession": acc, "form": f.get("form"),
                        "filed": filed, "acceptance": acceptance,
                        "report": report, "units": units}
                # skip-with-record (census: 28 no-pd, all report 1998..2000;
                # pre-2006 reports are text-era stragglers 1999..2005)
                if not pd:
                    mgr_skipped.append({**base,
                                        "reason": "no_primary_document"})
                    continue
                if report < TEXT_REPORT_MIN:
                    mgr_skipped.append({**base, "reason": "pre_2006",
                                        "primaryDocument": pd})
                    continue
                ext = pd.rsplit(".", 1)[-1].lower()
                if ext == "xml":
                    name, xml_bytes = find_infotable(int(cik), acc)
                    if xml_bytes is None:
                        print(f"  !! no info table for {mgr} {cik} {acc} "
                              f"({f.get('form')} filed {filed})", flush=True)
                        mgr_filings.append({**base, "source": "xml",
                                            "filename": None, "rows": 0})
                        continue
                    rows = parse_infotable(xml_bytes)
                    meta = {"manager": mgr, "cik": cik, "accession": acc,
                            "form": f.get("form"), "filed_date": filed,
                            "acceptance_dt": acceptance,
                            "report_date": report, "units": units,
                            "source": "xml", "filename": name}
                    for ri, r in enumerate(rows):
                        mgr_rows.append({**meta, "row_idx": ri,
                                         "entry_kind": "new", **r})
                    mgr_filings.append({**base, "source": "xml",
                                        "filename": name,
                                        "rows": len(rows)})
                elif ext == "txt":
                    text = fetch_text_filing(int(cik), acc, pd)
                    trows, cover, _ = parse_text_infotable(text)
                    vsum = 0.0
                    meta = {"manager": mgr, "cik": cik, "accession": acc,
                            "form": f.get("form"), "filed_date": filed,
                            "acceptance_dt": acceptance,
                            "report_date": report, "units": units,
                            "source": "text", "filename": pd}
                    for ri, r in enumerate(trows):
                        vsum += r["value"]
                        mgr_rows.append({**meta, "row_idx": ri,
                                         "entry_kind": r["kind"],
                                         **text_row_to_out(r)})
                    # advisory cover reconciliation (facts, not verdicts;
                    # the three verified filer cover errors are pinned in
                    # the harness, not corrected here)
                    mgr_filings.append({**base, "source": "text",
                                        "filename": pd, "rows": len(trows),
                                        "cover_entry_total": cover["entry_total"],
                                        "cover_value_total": cover["value_total"],
                                        "value_sum": int(round(vsum))})
                else:
                    mgr_skipped.append({**base, "reason": "odd_extension",
                                        "primaryDocument": pd})
                    continue
                grand_total += 1
                if len(mgr_filings) % 25 == 0:
                    print(f"  {mgr}: {len(mgr_filings)} filings, "
                          f"{len(mgr_rows)} rows", flush=True)

        # freeze per-manager csv.gz
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=OUT_FIELDS, extrasaction="ignore")
        w.writeheader()
        for r in mgr_rows:
            w.writerow(r)
        raw = buf.getvalue().encode()
        gz_path = DATA / f"holdings_{mgr}.csv.gz"
        with open(gz_path, "wb") as fh:
            fh.write(gzip.compress(raw, 9, mtime=0))  # deterministic freeze
        gz_sha = sha256_bytes(gz_path.read_bytes())

        # per-manager IS coverage stats (verification-only reporting)
        is_reports = sorted({f["report"] for f in mgr_filings
                             if f["report"] and f["report"] < "2017-01-01"})
        manifest["managers"][mgr] = {
            "ciks": ciks, "n_filings": len(mgr_filings),
            "n_rows": len(mgr_rows), "n_skipped": len(mgr_skipped),
            "file": f"data/holdings_{mgr}.csv.gz", "sha256": gz_sha,
            "is_report_periods": len(is_reports),
            "is_first": is_reports[0] if is_reports else None,
            "is_last": is_reports[-1] if is_reports else None,
            "filings": mgr_filings, "skipped": mgr_skipped,
        }
        print(f"{mgr}: {len(mgr_filings)} filings, {len(mgr_skipped)} skipped, "
              f"{len(mgr_rows)} rows, IS report periods {len(is_reports)} "
              f"({is_reports[0] if is_reports else '-'}.."
              f"{is_reports[-1] if is_reports else '-'})", flush=True)

    manifest["total_filings_fetched"] = grand_total
    (WORK / "fetch_manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"\nTOTAL filings fetched: {grand_total}")
    for mgr, m in manifest["managers"].items():
        print(f"  {mgr}: sha256 {m['sha256'][:16]}  rows {m['n_rows']}")


if __name__ == "__main__":
    sys.exit(main())
