#!/usr/bin/env python3
"""Diagnostics for remaining proto_text_parser failures (pre-seal, verification only).

Targets:
  1. Renaissance 2008 giant-value row (sum 191T vs expected 51.6M).
  2. Renaissance 2012Q3 / 2013Q1 cover targets (regex currently misses cover).
  3. Class C small offsets: paulson 2008 (+1), southeastern 2008 (-6),
     southeastern 2013Q1 (+1), appaloosaOld x3 (+1/-1/+3 thousands).
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from proto_text_parser import parse_text_infotable  # noqa: E402

CACHE = Path(__file__).resolve().parent / "cache"

CASES = [
    ("ren2008",       "000103738908000003_mar0813frtllc.txt"),
    ("ren2012q3",     "000103738912000066_ren_13f_q3_2012.txt"),
    ("ren2013q1",     "000103738913000054_renaissance13Fq12013.txt"),
    ("paulson2008",   "000103567408000009_pco033108.txt"),
    ("se2008",        "000080798508000035_f13f0308.txt"),
    ("se2013q1",      "000080798513000034_f13f0313.txt"),
    ("apo2008",       "000100643808000002_a13f08q1.txt"),
    ("apo2012q2",     "000100643812000006_a13f12q2.txt"),
    ("apo2013q1",     "000100643813000004_a13f13q1.txt"),
]

for tag, fn in CASES:
    p = CACHE / fn
    if not p.exists():
        p = CACHE / fn
    text = p.read_text(errors="replace")
    print("=" * 78)
    print(tag, fn, "exists" if p.exists() else "MISSING")
    # raw cover lines for regex design
    for line in text.splitlines():
        if re.search(r"total", line, re.I) and re.search(r"Entr|Value", line, re.I):
            print("  COVER-LINE:", line.strip()[:120])
    rows, cover, diag = parse_text_infotable(text)
    s = sum(r["value"] for r in rows)
    print(f"  parsed rows {len(rows)} sum {s:,.0f} cover E={cover['entry_total']} V={cover['value_total']}")
    # top values (giant hunt)
    big = sorted(rows, key=lambda r: -r["value"])[:6]
    for r in big:
        if r["value"] > 1e7:
            print(f"  BIG: kind={r['kind']} cusip={r['cusip']!r} name={r['name'][:40]!r} "
                  f"value={r['value']:,.0f} shares={r['shares']}")
    # cont rows
    for r in rows:
        if r["kind"] == "cont":
            print(f"  CONT: value={r['value']:,.0f} shares={r['shares']}")
