#!/usr/bin/env python3
"""Row-level independent diff for ren2008 (+11) and ren2013q1 (-32).

Independent method: column-free regex extraction — CUSIP token followed by
first numeric token = value. Diff vs parser rows in file order. Also flag
non-integer value tokens and any row where the parser's glued-split fired
(value != raw first token after CUSIP).
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from proto_text_parser import parse_text_infotable  # noqa: E402

CASES = [
    ("ren2008",   "000103738908000003_mar0813frtllc.txt"),
    ("ren2013q1", "000103738913000054_renaissance13Fq12013.txt"),
]
CACHE = Path(__file__).resolve().parent / "cache"

# independent: 9-char CUSIP token, then first numeric token
RE_ROW = re.compile(r"\b([0-9A-Z]{9})\s+([\d,]+(?:\.\d+)?)\b")

for tag, fn in CASES:
    text = (CACHE / fn).read_text(errors="replace")
    tabs = re.findall(r"<TABLE>(.*?)</TABLE>", text, re.S | re.I)
    indep = []  # (cusip, raw_value_token, float)
    for tab in tabs:
        for raw_line in tab.splitlines():
            line = re.sub(r"<[^>]+>", " ", raw_line)
            line = re.sub(r"[ \t\x0c]+", " ", line).strip()
            m = RE_ROW.search(line)
            if m and "FORM 13F" not in line and "NAME OF ISSUER" not in line:
                indep.append((m.group(1), m.group(2),
                              float(m.group(2).replace(",", ""))))
    rows, cover, diag = parse_text_infotable(text)
    new_rows = [r for r in rows if r["kind"] == "new"]
    print("=" * 78)
    print(f"{tag}: indep rows {len(indep)}  parser new rows {len(new_rows)}")
    n_diff = 0
    for i, (ic, iraw, iv) in enumerate(indep):
        pv = new_rows[i]["value"] if i < len(new_rows) else None
        pc = new_rows[i]["cusip"] if i < len(new_rows) else None
        if pc != ic:
            n_diff += 1
            print(f"  CUSIP-MISMATCH idx {i}: indep {ic} raw {iraw} | parser {pc} val {pv}")
        elif abs(pv - iv) > 1e-9:
            n_diff += 1
            print(f"  VALUE-DIFF idx {i}: cusip {ic} raw {iraw} indep {iv} | parser {pv}")
        if "." in iraw:
            print(f"  DECIMAL idx {i}: cusip {ic} raw {iraw!r}")
    print(f"  diffs: {n_diff}")
    si_indep = sum(v for _, _, v in indep)
    si_parser = sum(r["value"] for r in rows)
    print(f"  indep sum  {si_indep:,.0f}  (int {int(round(si_indep)):,})")
    print(f"  parser sum {si_parser:,.0f}  (int {int(round(si_parser)):,})")
    print(f"  cover V    {cover['value_total']:,}")
