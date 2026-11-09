#!/usr/bin/env python3
"""Renaissance trio residual hunt (pre-seal, verification only).

For each ren filing: dump ALL table lines that _classify returns None on
(not just >=2-numeric ones), and locate the source line of the cont-1/800
row. Residuals to explain: ren2008 -5697, ren2012q3 -3471, ren2013q1 -4543.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from proto_text_parser import (_classify, DASH, HDR)  # noqa: E402

CASES = [
    ("ren2008",   "000103738908000003_mar0813frtllc.txt"),
    ("ren2012q3", "000103738912000066_ren_13f_q3_2012.txt"),
    ("ren2013q1", "000103738913000054_renaissance13Fq12013.txt"),
]
CACHE = Path(__file__).resolve().parent / "cache"

for tag, fn in CASES:
    text = (CACHE / fn).read_text(errors="replace")
    print("=" * 78)
    print(tag)
    tabs = re.findall(r"<TABLE>(.*?)</TABLE>", text, re.S | re.I)
    n_unc = 0
    for tab in tabs:
        for raw_line in tab.splitlines():
            line = re.sub(r"<[^>]+>", " ", raw_line)
            line = re.sub(r"[ \t\x0c]+", " ", line).strip()
            if not line or DASH.match(line) or HDR.search(line):
                continue
            row = _classify(line)
            if row is None:
                n_unc += 1
                print(f"  UNCLASSIFIED: {line[:150]}")
            elif row["kind"] == "cont" and row["value"] == 1:
                print(f"  CONT-SRC: {line[:150]}")
    print(f"  total unclassified: {n_unc}")
