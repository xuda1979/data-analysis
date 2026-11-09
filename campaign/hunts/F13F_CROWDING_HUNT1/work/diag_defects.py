#!/usr/bin/env python3
"""F13F_CROWDING_HUNT1 — pre-seal defect diagnosis (verification-only).

Source-level diagnosis of the audit-flagged filings (audit_row_quality.py
triage, classes A-H): for each case, print the manifest record, anomalous
parsed rows, top-value rows, a value-string-in-document test (parser
artifact vs source truth), and raw cached-source context around anomalies
(no network; work/cache/). Also: berkshire cont-row attribution analysis,
amendment-supersede poison census (per manager x report date), re-parse
cache completeness census, IS coverage cross-check, and the renaissance
2022+ XML value sanity check. NOTHING is computed on the champion grid;
nothing is modified. Informs the pre-seal remediation decision only.
"""
import csv
import gzip
import io
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
HUNT = HERE.parent
CACHE = HERE / "cache"

m = json.load(open(HERE / "fetch_manifest.json"))
fil = {}
for mgr, mm in m["managers"].items():
    for f in mm["filings"]:
        fil[(mgr, f["accession"])] = f


def fnum(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def cusip_check(c):
    c = (c or "").strip().upper()
    if len(c) != 9 or not c.isalnum() or not c[8].isdigit():
        return False, False
    total = 0
    for i in range(8):
        ch = c[i]
        v = int(ch) if ch.isdigit() else ord(ch) - 55
        if i % 2 == 1:
            v *= 2
        total += v // 10 + v % 10
    return True, (10 - total % 10) % 10 == int(c[8])


_rb = {}


def rows_by_acc(mgr):
    if mgr not in _rb:
        raw = gzip.decompress((HUNT / f"data/holdings_{mgr}.csv.gz").read_bytes()).decode()
        d = defaultdict(list)
        for r in csv.DictReader(io.StringIO(raw)):
            d[r["accession"]].append(r)
        _rb[mgr] = d
    return _rb[mgr]


def stats(mgr, acc):
    f = fil[(mgr, acc)]
    rs = rows_by_acc(mgr).get(acc, [])
    n = len(rs)
    n_new = sum(1 for r in rs if r["entry_kind"] != "cont")
    n_cont = n - n_new
    bad_fmt = bad_chk = abs_v = zero_v = non_v = 0
    prices = []
    for r in rs:
        if r["entry_kind"] != "cont":
            fok, cok = cusip_check(r["cusip"])
            if not fok:
                bad_fmt += 1
            elif not cok:
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
    med = prices[len(prices) // 2] if prices else None
    out_p = sum(1 for p in prices if not 0.5 <= p <= 100000.0)
    dE = None
    if f.get("source") == "text" and f.get("cover_entry_total") is not None:
        dE = n - f["cover_entry_total"]
    ratio = None
    if f.get("source") == "text" and f.get("cover_value_total"):
        ratio = f["value_sum"] / f["cover_value_total"]
    return {"n": n, "n_new": n_new, "n_cont": n_cont, "bad_fmt": bad_fmt,
            "bad_chk": bad_chk, "abs_v": abs_v, "zero_v": zero_v,
            "non_v": non_v, "med": med, "out_p": out_p, "dE": dE,
            "ratio": ratio}


allstats = {}
cases = []
for (mgr, acc), f in sorted(fil.items()):
    s = stats(mgr, acc)
    allstats[(mgr, acc)] = s
    src = f.get("source")
    rpt = f.get("report") or ""
    tags = []
    if s["abs_v"]:
        tags.append("absV")
    if s["bad_fmt"]:
        tags.append("bFmt")
    if s["non_v"]:
        tags.append("nV")
    if s["n"] == 0:
        tags.append("zero")
    if s["med"] is not None and s["med"] > 1e6:
        tags.append("medP")
    if mgr in ("berkshire", "appaloosa") and 0 < s["n"] <= 3:
        tags.append("skeletal")
    if mgr == "berkshire" and src == "text" and s["n_cont"] > 0 and (s["dE"] or 0) > 5:
        tags.append("contDE")
    if mgr == "bridgewater" and (
            (s["dE"] is not None and (s["dE"] < -20 or s["dE"] > 5))
            or (s["ratio"] is not None and not 0.9 <= s["ratio"] <= 1.1)):
        tags.append("bw")
    if mgr == "paulson" and s["dE"] not in (None, 0):
        tags.append("paulson_dE")
    if mgr == "renaissance" and src == "text" and rpt < "2009-01-01" \
            and s["ratio"] and s["ratio"] > 1.1:
        tags.append("ren_inflate")
    if mgr == "renaissance" and s["dE"] is not None and (s["dE"] < -100 or s["dE"] > 5):
        tags.append("ren_dE")
    if mgr == "southeastern" and src == "text" and rpt < "2008-01-01":
        tags.append("se_early")
    if mgr == "renaissance" and src == "xml" and s["out_p"] > 1000:
        tags.append("ren_xml2022")
    if tags:
        cases.append((mgr, acc, tags))

print(f"cases: {len(cases)}")
tc = Counter(t for _, _, ts in cases for t in ts)
print("tag counts:", dict(tc), "\n")

COMPACT = {"paulson_dE", "ren_xml2022", "nV"}


def doc_path(f, acc):
    if f.get("source") == "text":
        return CACHE / f"{acc}_{f['filename']}"
    return CACHE / f"xml_{acc}_{f['filename']}"


def rowstr(r):
    return (f"idx {r['row_idx']} kind {r['entry_kind']} cusip '{r['cusip']}' "
            f"name '{(r['nameOfIssuer'] or '')[:28]}' value '{r['value']}' "
            f"sh '{r['sshPrnamt']}' type '{r['sshPrnamtType']}' "
            f"putCall '{r['putCall']}'")


def detail(mgr, acc, tags):
    f = fil[(mgr, acc)]
    s = allstats[(mgr, acc)]
    compact = set(tags) <= COMPACT
    print("=" * 110)
    print(f"[{','.join(tags)}] {mgr} {acc} {f['form']} rpt {f['report']} "
          f"filed {f.get('filed')} acc {f['acceptance']} src {f['source']}")
    print(f"  manifest: rows {f.get('rows')} fn {f.get('filename')} "
          f"coverE {f.get('cover_entry_total')} coverV {f.get('cover_value_total')} "
          f"vsum {f.get('value_sum')} units {f.get('units')}")
    print(f"  stats: n {s['n']} new {s['n_new']} cont {s['n_cont']} "
          f"bFmt {s['bad_fmt']} bChk {s['bad_chk']} absV {s['abs_v']} "
          f"zV {s['zero_v']} nV {s['non_v']} medP {s['med']} outP {s['out_p']} "
          f"dE {s['dE']} ratio {s['ratio']}")
    rs = rows_by_acc(mgr).get(acc, [])

    def vof(r):
        v = fnum(r["value"])
        return abs(v) if v is not None else -1.0

    top = sorted(rs, key=vof, reverse=True)[:5]
    if top:
        print("  top |value| rows:")
        for r in top:
            print(f"    {rowstr(r)}")

    anoms = []
    for r in rs:
        if r["entry_kind"] != "cont":
            fok, _ = cusip_check(r["cusip"])
            if not fok:
                anoms.append((r, "cusip-fmt"))
        v = fnum(r["value"])
        if v is not None and v > (1e12 if r["units"] == "K" else 1e15):
            anoms.append((r, "abs-value"))
        elif v is None and r["value"] != "":
            anoms.append((r, "non-numeric"))
    if anoms:
        print(f"  anomalous rows ({len(anoms)}):")
        for r, why in anoms[:6]:
            print(f"    [{why}] {rowstr(r)}")

    if s["n_cont"] > 0:
        prev = None
        shown = 0
        print("  cont-row sample (cont vs preceding new):")
        for r in rs:
            if r["entry_kind"] == "new":
                prev = r
            elif r["entry_kind"] == "cont" and shown < 3:
                pn = (prev or {}).get("nameOfIssuer", "-")
                print(f"    cont idx {r['row_idx']} name "
                      f"'{(r['nameOfIssuer'] or '')[:28]}' value '{r['value']}' "
                      f"sh '{r['sshPrnamt']}' | prev-new name "
                      f"'{(pn or '')[:28]}' cusip "
                      f"'{(prev or {}).get('cusip', '-')}'")
                shown += 1

    dp = doc_path(f, acc)
    if not dp.exists():
        print(f"  cache MISSING: {dp.name}")
        return
    doc = dp.read_text(errors="replace")
    stripped = re.sub(r"[,\s]", "", doc)
    nve = sum(1 for r in rs if r["value"])
    nv = sum(1 for r in rs if r["value"] and r["value"] in stripped)
    nse = sum(1 for r in rs if r["sshPrnamt"])
    ns = sum(1 for r in rs if r["sshPrnamt"] and r["sshPrnamt"] in stripped)
    print(f"  cache {dp.name} ({len(doc)} chars); "
          f"value-str found {nv}/{nve}; share-str found {ns}/{nse}")
    if compact:
        return
    ctx = [(r, why) for r, why in anoms[:2]] or ([(top[0], "top-value")] if top else [])
    for r, why in ctx:
        nm = (r["nameOfIssuer"] or "").strip()
        i = doc.find(nm) if nm else -1
        if i >= 0:
            seg = doc[max(0, i - 220):i + 280].replace("\n", "\\n")
            print(f"  ctx[{why}] '{nm[:30]}': ...{seg}...")
        else:
            print(f"  ctx[{why}]: name '{nm[:30]}' NOT in doc")
    if s["n"] <= 3:
        print("  doc head:")
        print("    " + doc[:2000].replace("\n", "\\n"))


for mgr, acc, tags in cases:
    detail(mgr, acc, tags)

print("\n### berkshire cont-row attribution (all text filings with cont rows)")
for (mgr, acc), f in sorted(fil.items()):
    if mgr != "berkshire" or f.get("source") != "text":
        continue
    s = allstats[(mgr, acc)]
    if s["n_cont"] == 0:
        continue
    rs = rows_by_acc(mgr)[acc]
    named = sum(1 for r in rs if r["entry_kind"] == "cont"
                and (r["nameOfIssuer"] or "").strip())
    eq = 0
    neq = []
    prev = None
    for r in rs:
        if r["entry_kind"] == "new":
            prev = r
        elif r["entry_kind"] == "cont" and prev is not None:
            if (r["nameOfIssuer"] or "").strip() \
                    and r["nameOfIssuer"] == prev["nameOfIssuer"]:
                eq += 1
            elif len(neq) < 2:
                neq.append(f"idx{r['row_idx']} "
                           f"'{(r['nameOfIssuer'] or '')[:20]}' vs prev "
                           f"'{(prev['nameOfIssuer'] or '')[:20]}'")
    print(f"  rpt {f['report']} {acc} n {s['n']} new {s['n_new']} "
          f"cont {s['n_cont']} dE {s['dE']} ratio {s['ratio']} | "
          f"cont_named {named} cont_name==prev {eq} "
          f"neq {neq if neq else '-'}")

print("\n### amendment-supersede census (per manager x report date; "
      "multi-filing or skeletal quarters)")
for mgr in m["managers"]:
    by_rpt = defaultdict(list)
    for (mg, acc), f in fil.items():
        if mg == mgr:
            by_rpt[f["report"]].append((acc, f))
    for rpt in sorted(by_rpt):
        fl = by_rpt[rpt]
        maxrows = max(int(f.get("rows") or 0) for _, f in fl)
        if len(fl) == 1 and maxrows >= 10:
            continue
        fl_s = sorted(fl, key=lambda t: (t[1]["acceptance"], t[0]))
        wacc, wf = fl_s[-1]
        wrows = int(wf.get("rows") or 0)
        flag = ""
        if wrows < 10 and maxrows >= 10:
            flag = "  <== POISON (skeletal winner over big filing)"
        elif wrows < 10:
            flag = "  <== skeletal-only quarter"
        print(f"  {mgr} rpt {rpt}: n_filings {len(fl)} max_rows {maxrows} | "
              f"amended-wins {wacc} rows {wrows} form {wf['form']} "
              f"acc {wf['acceptance']}{flag}")
        if len(fl) > 1 or flag:
            for acc, f in fl_s:
                print(f"      {acc} {f['form']} rows {f.get('rows')} "
                      f"acc {f['acceptance']}")

print("\n### cache completeness (offline re-parse feasibility)")
miss = []
tot_t = tot_x = ok_t = ok_x = 0
for (mgr, acc), f in fil.items():
    if f.get("source") == "text":
        tot_t += 1
        if (CACHE / f"{acc}_{f['filename']}").exists():
            ok_t += 1
        else:
            miss.append(f"text {mgr} {acc} {f['filename']}")
    elif f.get("source") == "xml":
        tot_x += 1
        if (CACHE / f"xml_{acc}_{f['filename']}").exists():
            ok_x += 1
        else:
            miss.append(f"xml {mgr} {acc} {f['filename']}")
print(f"  text: {ok_t}/{tot_t} cached; xml: {ok_x}/{tot_x} cached")
for s in miss[:20]:
    print(f"    MISSING {s}")

print("\n### IS coverage cross-check (distinct report dates < 2017-01-01)")
for mgr, mm in m["managers"].items():
    rpts = sorted({f["report"] for f in mm["filings"]
                   if f["report"] and f["report"] < "2017-01-01"})
    if rpts:
        print(f"  {mgr}: {len(rpts)} ({rpts[0]}..{rpts[-1]})")
    else:
        print(f"  {mgr}: 0")
