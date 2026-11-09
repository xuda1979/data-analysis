#!/usr/bin/env python3
"""F13F_CROWDING_HUNT1 — fetch_freeze_13f.py pre-run smoke (verification-only).

1. text dispatch on two cached filings (harness-pinned expectations):
   berkshire 2008Q1    -> 105 rows, value sum 66,461,224
   appaloosaOld 2008Q1 ->  28 rows, value sum  1,814,515
   (appaloosaOld pin is TABLE truth, verified two independent ways:
   tab-split extraction 28/28 exact + token parse; the filing's own
   cover says 1,814,514 -- filer cover error, delta 1 unit = $1,000)
2. xml dispatch on one live xml-era berkshire filing (first 13F-HR with
   .xml primaryDocument, report >= 2014, per the submissions cache):
   info-table discovery + parse, sanity-check row count + first row.
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # .../work
sys.path.insert(0, str(HERE.parent))            # hunt dir
import fetch_freeze_13f as F                    # noqa: E402

# --- 1. text dispatch (cached filings) ---
TEXT_CASES = [
    ("berkshire", 1067983, "000095014808000200", "v40691ae13fvhr.txt", 105, 66461224),
    ("appaloosaOld", 1006438, "000100643808000002", "a13f08q1.txt", 28, 1814515),
]
for mgr, cik, acc, doc, exp_n, exp_v in TEXT_CASES:
    text = F.fetch_text_filing(cik, acc, doc)
    rows, cover, _ = F.parse_text_infotable(text)
    s = int(round(sum(r["value"] for r in rows)))
    ok = len(rows) == exp_n and s == exp_v
    print(f"{'PASS' if ok else 'FAIL'} text {mgr} rows {len(rows)}/{exp_n} "
          f"sum {s}/{exp_v}")
    assert ok, f"text smoke FAIL {mgr}"

# --- 2. xml dispatch (live, one filing) ---
subs = json.loads((F.SUBS_CACHE / f"CIK{1067983:010d}.json").read_text())
target = None
for f in subs:
    pd = f.get("primaryDocument") or ""
    if (f.get("form") == "13F-HR" and pd.endswith(".xml")
            and (f.get("reportDate") or "") >= "2014-01-01"):
        target = f
        break
assert target is not None, "no xml-era 13F-HR in submissions cache"
acc = target["accessionNumber"].replace("-", "")
name, xml_bytes = F.find_infotable(1067983, acc)
assert xml_bytes is not None, f"no info table found for {acc}"
rows = F.parse_infotable(xml_bytes)
r0 = rows[0]
print(f"PASS xml berkshire {acc} report {target['reportDate']} file {name} "
      f"rows {len(rows)} sample cusip={r0['cusip']} value={r0['value']} "
      f"issuer={r0['nameOfIssuer'][:30]}")
assert len(rows) > 20 and len(r0["cusip"]) == 9 and r0["value"]
print("SMOKE PASS")
