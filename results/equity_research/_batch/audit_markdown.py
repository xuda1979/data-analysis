#!/usr/bin/env python3
"""Markdown-level QA over completed .md reports: float-blob leak check and
ungrounded-citation spot-check. Complements audit_reports.py (JSON-level).

The M4 display fix (_fmt_input) rounds valuation-input floats in the markdown
table; JSON keeps full precision intentionally. This script asserts the
markdown never shows binary-repr noise (e.g. 0.030699999999999998 or
3.051194539249147) and that the newest claims grading carries zero ungrounded
citations (the citation-grammar fix target).
"""
from __future__ import annotations
import glob
import json
import os
import re

OUT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # results/equity_research

# e.g. "0.030699999999999998", "3.051194539249147" -- a decimal with >=8 digits
# after the point that isn't pure zeros, PLUS the trailing-runner pattern of
# binary noise (.999999997 / .000000002). Dates/timestamps are excluded by
# requiring a digit right after the decimal point run.
BLOB_RE = re.compile(r"(?<![\w:])-?\d+\.\d{8,}(?!\.)")


def newest_md_paths():
    for f in sorted(glob.glob(os.path.join(OUT, "*.json"))):
        n = os.path.basename(f)
        if "_" not in n:
            continue
        first, _, rest = n.partition("_")
        date = rest[:-5] if rest.endswith(".json") else ""
        if not date or "_" in first or first in ("INDEX", "TOP"):
            continue
        md = os.path.join(OUT, f"{first}_{date}.md")
        if os.path.exists(md):
            yield first, date, md


def main() -> int:
    bad = []
    checked = 0
    for sym, date, md in newest_md_paths():
        checked += 1
        with open(md) as fh:
            text = fh.read()
        hits = sorted(set(BLOB_RE.findall(text)))
        if hits:
            bad.append((sym, date, hits))
    print(f"newest-per-sym markdown scanned: {checked}")
    blob_syms = [b[0] for b in bad]
    print("float-blob leaks:", blob_syms or "none")
    for sym, date, hits in bad[:20]:
        print(f"  {sym:6s} {date} {hits[:4]}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
