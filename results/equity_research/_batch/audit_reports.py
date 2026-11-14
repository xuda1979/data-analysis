#!/usr/bin/env python3
"""QA audit over completed report JSONs: newest-per-sym, verdicts, and the
objective's core contract (current price + base/bull/bear 12-mo targets).
"""
from __future__ import annotations
import glob
import json
import os
import sys

OUT = os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))  # results/equity_research
ROOT = os.path.dirname(os.path.dirname(OUT))
sys.path.insert(0, os.path.join(ROOT, "tools"))
from wt.agent.report_view import effective_scenarios  # noqa: E402


def scan():
    best = {}  # sym -> (date, path)
    for f in glob.glob(os.path.join(OUT, "*.json")):
        n = os.path.basename(f)
        if "_" not in n:
            continue
        first, _, rest = n.partition("_")
        date = rest[:-5] if rest.endswith(".json") else ""
        if not date or "_" in first or first in ("INDEX", "TOP"):
            continue
        if first not in best or date > best[first][0]:
            best[first] = (date, f)
    return best


def main() -> int:
    best = scan()
    rows, verdicts, missing_price, missing_pt, errs = [], {}, [], [], []
    incomplete = 0
    for sym in sorted(best):
        date, f = best[sym]
        with open(f) as fh:
            d = json.load(fh)
        rm = d.get("risk_manager") or {}
        j = d.get("judge") or {}
        v = rm.get("verdict")
        verdicts[v] = verdicts.get(v, 0) + 1
        sc = effective_scenarios(d)
        base = (sc.get("base") or {})
        if v != "approved":
            incomplete += 1
        if not d.get("price"):
            missing_price.append(sym)
        if not base.get("pt"):
            missing_pt.append(sym)
        if d.get("errors"):
            errs.append((sym, len(d["errors"])))
        rows.append((sym, date, v))
    print(f"newest-per-sym: {len(rows)} / 60")
    print("verdicts:", verdicts or "none yet")
    print("missing price:", missing_price or "none")
    print("missing effective base PT:", missing_pt or "none")
    print("reports with errors:", errs or "none")
    for sym, date, v in rows[:200]:
        print(f"  {sym:6s} {date} {v or 'n/a'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
