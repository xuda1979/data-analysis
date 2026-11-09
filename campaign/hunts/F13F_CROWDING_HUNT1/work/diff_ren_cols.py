#!/usr/bin/env python3
"""Third independent method: fixed-column-position slicing.

Detect the modal CUSIP column (boundary-delimited 9-char [0-9A-Z] runs) on
tag-stripped but NOT whitespace-collapsed lines, then read value = first
numeric token after the CUSIP slice. Compare per-line against _classify().
Genuinely independent failure modes vs token parsing on collapsed text
(detects column drift, collapse-induced token merges/splits).

Expected NO-COL-MATCH/COL-DIFF rows are exactly the 20 (ren2008) / 2
(ren2013q1) rows already hand-verified parser-correct via voting-column
arithmetic (10-char CUSIP+x, glued value+shares, 12-char prefix+CUSIP)."""
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from proto_text_parser import _classify, DASH, HDR, WORD  # noqa: E402

CASES = [
    ("ren2008",   "000103738908000003_mar0813frtllc.txt"),
    ("ren2013q1", "000103738913000054_renaissance13Fq12013.txt"),
]
CACHE = Path(__file__).resolve().parent / "cache"

for tag, fn in CASES:
    text = (CACHE / fn).read_text(errors="replace")
    tabs = re.findall(r"<TABLE>(.*?)</TABLE>", text, re.S | re.I)
    print("=" * 78)
    print(tag)
    # pline: tags removed, whitespace PRESERVED (column offsets valid);
    # line_s: collapsed+stripped (what the token parser sees)
    plines = []
    for tab in tabs:
        for raw_line in tab.splitlines():
            pline = re.sub(r"<[^>]+>", "", raw_line)
            line_s = re.sub(r"[ \t\x0c]+", " ", pline).strip()
            plines.append((pline, line_s))
    # pass 1: modal CUSIP column
    col_starts = []
    for pline, _ in plines:
        for i in range(1, len(pline) - 9):
            if (re.fullmatch(r"[0-9A-Z]{9}", pline[i:i + 9])
                    and pline[i - 1].isspace() and pline[i + 9].isspace()):
                col_starts.append(i)
    ccol = Counter(col_starts).most_common(1)[0][0]
    print(f"  modal CUSIP column: {ccol}  ({len(col_starts)} boundary hits)")
    n_rows = n_match = n_nomatch = 0
    p_total = c_total = 0.0
    for pline, line_s in plines:
        if not line_s or DASH.match(line_s) or HDR.search(line_s):
            continue
        row = _classify(line_s)
        if row is None:
            continue
        n_rows += 1
        p_total += row["value"]
        cv = None
        if len(pline) >= ccol + 10 and pline[ccol - 1].isspace():
            seg = pline[ccol:ccol + 9]
            if WORD.match(seg) and pline[ccol + 9].isspace():
                m = re.match(r"([\d,]+)", pline[ccol + 10:].lstrip())
                if m:
                    cv = float(m.group(1).replace(",", ""))
        if cv is None:
            n_nomatch += 1
            print(f"  NO-COL-MATCH: {line_s[:120]}")
            print(f"     parser value {row['value']}")
        elif abs(cv - row["value"]) > 1e-9:
            n_nomatch += 1
            print(f"  COL-DIFF: {line_s[:120]}")
            print(f"     col {cv} vs parser {row['value']}")
        else:
            n_match += 1
            c_total += cv
    print(f"  rows {n_rows}  3-way-match {n_match}  nomatch(expected known) {n_nomatch}")
    print(f"  parser total {p_total:,.0f}")
    print(f"  col-confirmed total {c_total:,.0f}  "
          f"(+ {p_total - c_total:,.0f} from hand-verified rows)")
