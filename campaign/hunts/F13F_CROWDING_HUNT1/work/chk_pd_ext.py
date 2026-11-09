#!/usr/bin/env python3
"""F13F_CROWDING_HUNT1 — primaryDocument extension audit (verification-only).

Across all roster submissions-cache CIKs: extension cross-tab by report year
for 13F-HR + 13F-HR/A; non-txt/xml primary docs listed; missing
primaryDocument report periods; xml primaryDocument name distribution (is
primaryDocument the information table itself?); missing acceptanceDateTime.
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

SUBS = Path(__file__).resolve().parent.parent / "data" / "submissions"
FORMS = ("13F-HR", "13F-HR/A")

ext_by_year = defaultdict(Counter)
pd_xml = Counter()
odd, missing_pd, missing_acc = [], [], []
total = 0
for fp in sorted(SUBS.glob("CIK*.json")):
    cik = fp.stem[3:]
    for f in json.loads(fp.read_text()):
        if f.get("form") not in FORMS:
            continue
        total += 1
        pd = f.get("primaryDocument") or ""
        rp = f.get("reportDate") or "????"
        ext = pd.rsplit(".", 1)[-1].lower() if "." in pd else "(none)"
        ext_by_year[rp[:4]][ext] += 1
        if not pd:
            missing_pd.append((cik, f["accessionNumber"], f.get("form"), rp))
        elif ext == "xml":
            pd_xml[pd] += 1
        elif ext != "txt":
            odd.append((cik, f["accessionNumber"], f.get("form"), rp, pd))
        if not f.get("acceptanceDateTime"):
            missing_acc.append((cik, f["accessionNumber"], f.get("form"), rp))

print(f"total 13F-HR + 13F-HR/A filings in cache: {total}")
print("\nextension by report year:")
for yr in sorted(ext_by_year):
    print(f"  {yr}: " + "  ".join(f"{k}:{v}" for k, v in sorted(ext_by_year[yr].items())))
print(f"\nnon-txt/xml primaryDocument: {len(odd)}")
for o in odd:
    print("  ", o)
print(f"\nmissing primaryDocument: {len(missing_pd)}  report periods: "
      f"{sorted(set(m[3] for m in missing_pd))}")
print(f"missing acceptanceDateTime: {len(missing_acc)}")
for m in missing_acc[:10]:
    print("  ", m)
print(f"\nxml primaryDocument names ({len(pd_xml)} distinct, {sum(pd_xml.values())} filings):")
for name, n in pd_xml.most_common(50):
    print(f"  {n:4d}  {name}")
