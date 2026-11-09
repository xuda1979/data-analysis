#!/usr/bin/env python3
"""Line-aligned diff: for each table line, compare _classify() output vs an
independent regex (9-char CUSIP + first numeric). Reports only lines where
the two methods disagree on value or where either fires and the other
doesn't. ren2008 (+11) and ren2013q1 (-32)."""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from proto_text_parser import _classify, DASH, HDR  # noqa: E402

CASES = [
    ("ren2008",   "000103738908000003_mar0813frtllc.txt"),
    ("ren2013q1", "000103738913000054_renaissance13Fq12013.txt"),
]
CACHE = Path(__file__).resolve().parent / "cache"
RE_ROW = re.compile(r"\b([0-9A-Z]{9})\s+([\d,]+(?:\.\d+)?)\b")

for tag, fn in CASES:
    text = (CACHE / fn).read_text(errors="replace")
    tabs = re.findall(r"<TABLE>(.*?)</TABLE>", text, re.S | re.I)
    print("=" * 78)
    print(tag)
    n = 0
    for tab in tabs:
        for raw_line in tab.splitlines():
            line = re.sub(r"<[^>]+>", " ", raw_line)
            line = re.sub(r"[ \t\x0c]+", " ", line).strip()
            if not line or DASH.match(line) or HDR.search(line):
                continue
            row = _classify(line)
            m = RE_ROW.search(line)
            iv = float(m.group(2).replace(",", "")) if m else None
            ic = m.group(1) if m else None
            pv = row["value"] if row else None
            pc = row["cusip"] if row else None
            disagree = False
            if (row is None) != (m is None):
                disagree = True
            elif row is not None and (pc != ic or abs(pv - iv) > 1e-9):
                disagree = True
            if disagree:
                n += 1
                print(f"  DISAGREE: {line[:140]}")
                print(f"     parser: kind={row['kind'] if row else None} cusip={pc} value={pv}")
                print(f"     indep : cusip={ic} value={iv}")
    print(f"  disagreements: {n}")
