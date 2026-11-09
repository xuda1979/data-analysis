#!/usr/bin/env python3
"""F13F_CROWDING_HUNT1 — pre-seal row-quality audit (verification-only).

Row-level plausibility scan of the six frozen holdings panels joined with
the per-filing cover records in work/fetch_manifest.json. Read-only;
informs the pre-seal remediation decision (parser defect vs filer cover
error vs source-document anomaly). No feature is computed on the champion
grid; nothing is modified.

Per-filing columns:
  rows/new/cnt  row counts by entry_kind (cnt = text-era continuation rows)
  bFmt  non-cont rows whose cusip is not 9 alnum ending in a digit
  bChk  9-alnum cusips FAILING the CUSIP check-digit algorithm
  absV  value beyond hard plausibility (units K: >1e12 thousands = $1e15;
        units D: >1e15 dollars) — no 13F position in this roster approaches
  zV    value <= 0
  nV    value cell not parseable as a number
  medP  median implied price = value*1000/shares (K) or value/shares (D)
  outP  priced rows with implied price outside [0.5, 100000]
  dE    rows - cover_entry_total (text filings; None -> blank)
  ratio manifest value_sum / cover_value_total (text; appaloosa covers are
        whole dollars -> ~0.001 is the known-benign units mismatch)

Flag rule (any): zero rows with non-zero cover; bFmt; bChk; absV; zV; nV;
outP > max(2, 2% of priced rows); dE != 0; ratio outside [0.9, 1.111].
The four documented filer cover errors and the appaloosa dollar-unit covers
re-flag by design; the audit interpretation distinguishes them.
"""
import csv
import gzip
import io
import json
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent          # .../F13F_CROWDING_HUNT1/work
HUNT = HERE.parent


def cusip_check(c):
    """Returns (fmt_ok, chk_ok).

    fmt_ok: 9 alnum chars, 9th a digit.  chk_ok: CUSIP check digit valid.
    'SPONSORED'/'RESTRICTE' fail fmt (9th char a letter); real cusips pass.
    """
    c = (c or "").strip().upper()
    if len(c) != 9 or not c.isalnum() or not c[8].isdigit():
        return False, False
    total = 0
    for i in range(8):
        ch = c[i]
        v = int(ch) if ch.isdigit() else ord(ch) - 55      # A=10 .. Z=35
        if i % 2 == 1:
            v *= 2
        total += v // 10 + v % 10                          # digit sum of v
    return True, (10 - total % 10) % 10 == int(c[8])


m = json.load(open(HERE / "fetch_manifest.json"))
fil = {}
for mgr, mm in m["managers"].items():
    for f in mm["filings"]:
        fil[(mgr, f["accession"])] = f

rows_by = defaultdict(list)
for mgr in m["managers"]:
    raw = gzip.decompress((HUNT / f"data/holdings_{mgr}.csv.gz").read_bytes()).decode()
    for r in csv.DictReader(io.StringIO(raw)):
        rows_by[(mgr, r["accession"])].append(r)


def fnum(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


print(f"{'mgr':<12}{'accession':<19}{'form':<9}{'report':<11}{'src':<5}"
      f"{'rows':>5}{'new':>4}{'cnt':>4}{'bFmt':>5}{'bChk':>5}{'absV':>5}"
      f"{'zV':>4}{'nV':>4}{'medP':>9}{'outP':>5}{'dE':>5}{'ratio':>8}")
n_flag = 0
flags_by_mgr = defaultdict(int)
for (mgr, acc), f in sorted(fil.items(),
                            key=lambda kv: (kv[0][0], kv[1].get("report") or "",
                                            kv[1]["accession"])):
    rs = rows_by.get((mgr, acc), [])
    n = len(rs)
    n_new = sum(1 for r in rs if r["entry_kind"] != "cont")
    n_cont = n - n_new
    bad_fmt = bad_chk = abs_v = zero_v = non_v = 0
    prices = []
    for r in rs:
        if r["entry_kind"] != "cont":
            fmt_ok, chk_ok = cusip_check(r["cusip"])
            if not fmt_ok:
                bad_fmt += 1
            elif not chk_ok:
                bad_chk += 1
        v = fnum(r["value"])
        if v is None:
            non_v += 1
            continue
        hard = 1e12 if r["units"] == "K" else 1e15
        if v > hard:
            abs_v += 1
            continue
        if v <= 0:
            zero_v += 1
            continue
        sh = fnum(r["sshPrnamt"])
        if sh and sh > 0:
            prices.append(v * (1000.0 if r["units"] == "K" else 1.0) / sh)
    prices.sort()
    med = prices[len(prices) // 2] if prices else float("nan")
    out_p = sum(1 for p in prices if not 0.5 <= p <= 100000.0)
    dE = None
    if f.get("source") == "text" and f.get("cover_entry_total") is not None:
        dE = n - f["cover_entry_total"]
    ratio = None
    if f.get("source") == "text" and f.get("cover_value_total"):
        ratio = f["value_sum"] / f["cover_value_total"]
    flag = ((n == 0 and (f.get("cover_entry_total") or 0) > 0) or bad_fmt
            or bad_chk or abs_v or zero_v or non_v
            or out_p > max(2, int(0.02 * len(prices)))
            or (dE is not None and dE != 0)
            or (ratio is not None and not 0.9 <= ratio <= 1.111))
    if flag:
        n_flag += 1
        flags_by_mgr[mgr] += 1
        dE_s = f"{dE:>5}" if dE is not None else "     "
        r_s = f"{ratio:>8.4f}" if ratio is not None else "        "
        med_s = f"{med:>9.0f}" if prices else " " * 9
        print(f"{mgr:<12}{acc:<19}{f['form']:<9}{f['report']:<11}{f['source']:<5}"
              f"{n:>5}{n_new:>4}{n_cont:>4}{bad_fmt:>5}{bad_chk:>5}{abs_v:>5}"
              f"{zero_v:>4}{non_v:>4}{med_s}{out_p:>5}{dE_s}{r_s}  <--")

print(f"\nflagged: {n_flag} / {len(fil)} filings")
for mgr, mm in m["managers"].items():
    print(f"  {mgr:<12} {flags_by_mgr[mgr]:>3} flagged / {len(mm['filings'])} filings")

print("\nzero-row filings (regardless of cover):")
for (mgr, acc), f in sorted(fil.items()):
    if not rows_by.get((mgr, acc)):
        print(f"  {mgr:<12}{acc} {f['form']} rpt {f['report']} src {f['source']}"
              f" coverE {f.get('cover_entry_total')} acc {f.get('acceptance')}")
