#!/usr/bin/env python3
"""F13F_CROWDING_HUNT1 — parser-guard design scan (verification-only).

Universe scan over all 210 cached text-era filings (no network; work/cache/):
  1. Shadow parser (verbatim parse pipeline + guard parameter at the two
     WORD-match sites: Case-C has_cusip and Case-B main test) validated
     against the frozen manifest (shadow(None) must reproduce every filing's
     row count and value sum EXACTLY).
  2. Guard variants: 'any' (token contains a digit) vs 's78' (CUSIP-spec
     issue-number positions 7-8 numeric). A naive 'digit-initial' guard was
     REJECTED pre-scan: letter-initial CINS cusips (G4776G101 etc.) are real
     positions, incl. inside the pinned berkshire 2008Q1 harness case.
  3. Token census: every Case-B candidate token (WORD + next-numeric, with
     the parser's 10/12-char pre-normalization) classified by variant
     verdict, with counts and sample source lines.
  4. Per-filing parse diff None vs s78: changed rows printed (old -> new).
  5. Post-fix cover reconciliation for the defect filings.
  6. Implausible-value rows under None (value > 1e12 or non-integer): source
     lines (the renaissance 2010 giants).
  7. Frozen-panel cusip census: letter-initial, s78-fail, check-fail counts.
Read-only; NOTHING is modified; informs the frozen-parser edit only.
"""
import csv
import gzip
import importlib.util
import io
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
HUNT = HERE.parent
CACHE = HERE / "cache"

spec = importlib.util.spec_from_file_location("ptp", HERE / "proto_text_parser.py")
ptp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ptp)
WORD = ptp.WORD
_num = ptp._num


def g_ok(t, guard):
    if guard is None:
        return True
    if guard == "any":
        return any(c.isdigit() for c in t)
    if guard == "s78":
        return len(t) == 9 and t[6:8].isdigit()
    raise ValueError(guard)


def _classify_g(line, guard):
    toks = line.split(" ")
    toks = [t for t in toks if t]
    if not toks:
        return None
    m = ptp.CUSIP_SP.search(line)
    if m:
        nums = []
        for t in line[m.end():].split():
            v = _num(t)
            if v is not None:
                nums.append(v)
                if len(nums) == 2:
                    break
        if nums:
            return {"kind": "new",
                    "cusip": (m.group(1) + m.group(2) + m.group(3)).upper(),
                    "name": line[:m.start()].strip(),
                    "value": nums[0],
                    "shares": nums[1] if len(nums) > 1 else None,
                    "sshPrnamtType": "", "putCall": "",
                    "investmentDiscretion": ""}
    n0, n1 = _num(toks[0]), _num(toks[1]) if len(toks) > 1 else None
    has_cusip = any(WORD.match(t) and g_ok(t, guard) and i + 1 < len(toks)
                    and _num(toks[i + 1]) is not None
                    for i, t in enumerate(toks))
    if n0 is not None and n1 is not None and not has_cusip:
        extra = {"sshPrnamtType": "", "putCall": "", "investmentDiscretion": ""}
        for t in toks[2:]:
            tu = t.upper().strip(":.,")
            if tu in ("SH", "PRN"):
                extra["sshPrnamtType"] = tu
            elif tu in ("PUT", "CALL"):
                extra["putCall"] = tu
            elif t.lower() in ptp.DISCR:
                extra["investmentDiscretion"] = t
        return {"kind": "cont", "cusip": "", "name": "", "value": n0,
                "shares": n1, **extra}
    for i, t in enumerate(toks):
        if (len(t) == 10 and WORD.match(t[:9])
                and (t[9] in "xX" or any(c.isalpha() for c in t[:9]))):
            t = t[:9]
        pre = ""
        if (len(t) == 12 and t[:3].isalpha() and WORD.match(t[3:])
                and any(c.isdigit() for c in t[3:])):
            pre, t = t[:3], t[3:]
        if WORD.match(t) and g_ok(t, guard) and i + 1 < len(toks) \
                and _num(toks[i + 1]) is not None:
            nums = []
            extra = {"sshPrnamtType": "", "putCall": "", "investmentDiscretion": ""}
            for tt in toks[i + 1:]:
                v = _num(tt)
                if v is not None:
                    nums.append((tt, v))
                    continue
                tu = tt.upper().strip(":.,")
                if tu in ("SH", "PRN"):
                    extra["sshPrnamtType"] = tu
                elif tu in ("PUT", "CALL"):
                    extra["putCall"] = tu
                elif tt.lower() in ptp.DISCR:
                    extra["investmentDiscretion"] = tt
            if nums:
                raw0, v0 = nums[0]
                rest = sum(v for _, v in nums[1:] if v >= 100)
                s0 = str(int(v0))
                if ("," not in raw0 and raw0.isdigit() and len(s0) >= 11
                        and rest > 0 and rest == int(rest)
                        and s0.endswith(str(int(rest)))
                        and len(s0) - len(str(int(rest))) >= 3):
                    v0 = int(s0[:-len(str(int(rest)))])
                return {"kind": "new", "cusip": t.upper(),
                        "name": " ".join(toks[:i] + ([pre] if pre else [])),
                        "value": v0,
                        "shares": nums[1][1] if len(nums) > 1 else None, **extra}
    return None


def parse_g(text, guard):
    cover = {"entry_total": None, "value_total": None}
    m = re.search(r"Entr(?:y|ies) Total\D*([\d,]+)", text, re.I)
    if m:
        cover["entry_total"] = int(m.group(1).replace(",", ""))
    m = re.search(r"Value(?:[ \t]*\(x ?\$?1000\))?[ \t]*Total[^0-9\n]*\$?([\d,]+)", text, re.I)
    if m:
        cover["value_total"] = int(m.group(1).replace(",", ""))
    tabs = re.findall(r"<TABLE>(.*?)</TABLE>", text, re.S | re.I)
    if not tabs:
        tabs = [text]
    rows, dropped = [], []
    pending = ""
    for tab in tabs:
        for raw_line in tab.splitlines():
            line = re.sub(r"<[^>]+>", " ", raw_line)
            line = re.sub(r"[ \t\x0c]+", " ", line).strip()
            if not line or ptp.DASH.match(line) or ptp.HDR.search(line):
                pending = ""
                continue
            row = _classify_g(line, guard)
            if row is None:
                if sum(1 for t in line.split() if _num(t) is not None) >= 2:
                    dropped.append(line[:130])
                if not _num(line.split(" ")[0] if line.split() else ""):
                    pending = (pending + " " + line).strip()
                else:
                    pending = ""
                continue
            if row["kind"] == "new":
                if row["name"] and pending:
                    row["name"] = (pending + " " + row["name"]).strip()
            pending = ""
            rows.append(row)
    return rows, cover, {"dropped_suspicious": dropped[:20]}


def case_b_candidates(line):
    """All (idx, effective-token) passing WORD + next-numeric pre-guard,
    with the parser's 10/12-char pre-normalization replicated."""
    toks = [t for t in line.split(" ") if t]
    out = []
    for i, t in enumerate(toks):
        if (len(t) == 10 and WORD.match(t[:9])
                and (t[9] in "xX" or any(c.isalpha() for c in t[:9]))):
            t = t[:9]
        if (len(t) == 12 and t[:3].isalpha() and WORD.match(t[3:])
                and any(c.isdigit() for c in t[3:])):
            t = t[3:]
        if WORD.match(t) and i + 1 < len(toks) and _num(toks[i + 1]) is not None:
            out.append((i, t))
    return out


m = json.load(open(HERE / "fetch_manifest.json"))
text_filings = []
for mgr, mm in m["managers"].items():
    for f in mm["filings"]:
        if f.get("source") == "text":
            text_filings.append((mgr, f))
print(f"text filings: {len(text_filings)}")

# ---------- 1. shadow(None) must reproduce the frozen manifest exactly ----------
print("\n### 1. shadow(None) vs frozen manifest (exact rows + value_sum)")
bad = 0
for mgr, f in text_filings:
    p = CACHE / f"{f['accession']}_{f['filename']}"
    if not p.exists():
        print(f"  MISSING cache {p.name}")
        bad += 1
        continue
    rows, cover, _ = parse_g(p.read_text(errors="replace"), None)
    vsum = int(round(sum(r["value"] for r in rows)))
    if len(rows) != f["rows"] or vsum != f["value_sum"]:
        bad += 1
        print(f"  MISMATCH {mgr} {f['accession']}: shadow {len(rows)}/{vsum} "
              f"vs frozen {f['rows']}/{f['value_sum']}")
print(f"  shadow-fidelity mismatches: {bad}")

# ---------- 2/3. token census over all filings ----------
print("\n### 2. Case-B candidate token census (pre-guard), guard verdicts")
tok_stats = defaultdict(lambda: {"n": 0, "s78": 0, "any": 0,
                                 "samples": [], "mgrs": Counter()})
for mgr, f in text_filings:
    p = CACHE / f"{f['accession']}_{f['filename']}"
    text = p.read_text(errors="replace")
    tabs = re.findall(r"<TABLE>(.*?)</TABLE>", text, re.S | re.I)
    if not tabs:
        tabs = [text]
    for tab in tabs:
        for raw_line in tab.splitlines():
            line = re.sub(r"<[^>]+>", " ", raw_line)
            line = re.sub(r"[ \t\x0c]+", " ", line).strip()
            if not line or ptp.DASH.match(line) or ptp.HDR.search(line):
                continue
            for _, t in case_b_candidates(line):
                st = tok_stats[t]
                st["n"] += 1
                st["s78"] += g_ok(t, "s78")
                st["any"] += g_ok(t, "any")
                st["mgrs"][mgr] += 1
                if len(st["samples"]) < 2:
                    st["samples"].append((f["accession"], line[:150]))

false_s78 = {t: st for t, st in tok_stats.items() if not st["s78"]}
false_any = {t: st for t, st in tok_stats.items() if not st["any"]}
print(f"  distinct candidate tokens: {len(tok_stats)}; "
      f"total candidate fires: {sum(st['n'] for st in tok_stats.values())}")
print(f"  tokens s78 REJECTS: {len(false_s78)} "
      f"({sum(st['n'] for st in false_s78.values())} fires)")
print(f"  tokens 'any' REJECTS: {len(false_any)} "
      f"({sum(st['n'] for st in false_any.values())} fires)")
print(f"  tokens s78 rejects but 'any' accepts: "
      f"{sorted(t for t in false_s78 if t not in false_any)}")
print("\n  s78-rejected tokens (the false-match universe):")
for t, st in sorted(false_s78.items(), key=lambda kv: -kv[1]["n"]):
    print(f"    '{t}' fires {st['n']} mgrs {dict(st['mgrs'])}")
    for acc, ln in st["samples"]:
        print(f"      {acc}: {ln}")
print("\n  letter-initial s78-ACCEPTED tokens (real CINS cusips kept):")
li = [(t, st) for t, st in tok_stats.items()
      if st["s78"] and t[0].isalpha()]
for t, st in sorted(li, key=lambda kv: -kv[1]["n"])[:15]:
    print(f"    '{t}' fires {st['n']} mgrs {dict(st['mgrs'])}")
print(f"    ... total distinct letter-initial accepted: {len(li)}")

# ---------- 4. per-filing parse diff None vs s78 ----------
print("\n### 3. per-filing parse diff: guard=None vs any")
n_changed = 0
diffs = {}
for mgr, f in text_filings:
    p = CACHE / f"{f['accession']}_{f['filename']}"
    text = p.read_text(errors="replace")
    r0, cov, _ = parse_g(text, None)
    r1, _, _ = parse_g(text, "any")
    if len(r0) != len(r1) or any(
            (a["kind"], a["cusip"], a["value"]) != (b["kind"], b["cusip"], b["value"])
            for a, b in zip(r0, r1)):
        n_changed += 1
        diffs[(mgr, f["accession"])] = (r0, r1, f)
print(f"  filings changed by any-guard: {n_changed} / {len(text_filings)}")
for (mgr, acc), (r0, r1, f) in diffs.items():
    s0 = int(round(sum(r["value"] for r in r0)))
    s1 = int(round(sum(r["value"] for r in r1)))
    print(f"\n  {mgr} {acc} rpt {f['report']} rows {len(r0)} -> {len(r1)} "
          f"vsum {s0:,} -> {s1:,} | coverE {f.get('cover_entry_total')} "
          f"coverV {f.get('cover_value_total')}")
    k = 0
    for j, (a, b) in enumerate(zip(r0, r1)):
        if (a["kind"], a["cusip"], a["value"]) != (b["kind"], b["cusip"], b["value"]):
            k += 1
            if k <= 6:
                print(f"    row {j}: '{(a['name'] or '')[:24]}' cus '{a['cusip']}' "
                      f"v {a['value']!r} sh {a['shares']!r}"
                      f"  ->  '{(b['name'] or '')[:24]}' cus '{b['cusip']}' "
                      f"v {b['value']!r} sh {b['shares']!r}")
    if len(r0) != len(r1):
        print(f"    (row-count change: {len(r0)} -> {len(r1)}; "
              f"cont rows {sum(1 for r in r0 if r['kind']=='cont')} -> "
              f"{sum(1 for r in r1 if r['kind']=='cont')})")

# ---------- 5. post-fix reconciliation for defect filings ----------
print("\n### 4. any-guard parse vs cover (defect filings)")
DEFECTS = {
    ("renaissance", "000103738910000311"), ("renaissance", "000103738910000312"),
    ("renaissance", "000103738911000099"), ("renaissance", "000103738906000002"),
    ("renaissance", "000103738906000003"), ("renaissance", "000103738906000004"),
    ("renaissance", "000103738907000001"),
    ("southeastern", "000080798506000036"), ("southeastern", "000080798506000043"),
    ("southeastern", "000080798506000053"), ("southeastern", "000080798507000024"),
    ("paulson", "000103567408000001"), ("bridgewater", "000091412110000565"),
}
for mgr, f in text_filings:
    if (mgr, f["accession"]) not in DEFECTS:
        continue
    p = CACHE / f"{f['accession']}_{f['filename']}"
    rows, cov, _ = parse_g(p.read_text(errors="replace"), "any")
    s1 = int(round(sum(r["value"] for r in rows)))
    ce, cv = f.get("cover_entry_total"), f.get("cover_value_total")
    okn = len(rows) == ce if ce is not None else True
    okv = cv is not None and (abs(s1 - cv) <= 10 or abs(s1 * 1000 - cv) <= 10_000
                              or abs(s1 - cv * 1000) <= 10_000)
    print(f"  {mgr:<13} {f['accession']} rpt {f['report']}: rows {len(rows)} "
          f"(coverE {ce} {'=' if okn else '!=' }) vsum {s1:,} "
          f"(coverV {cv:,} {'=' if okv else '!='})")

# ---------- 6. implausible-value rows under None ----------
print("\n### 5. implausible rows under None (value > 1e12 or non-integer)")
n_impl = 0
for mgr, f in text_filings:
    p = CACHE / f"{f['accession']}_{f['filename']}"
    text = p.read_text(errors="replace")
    rows, _, _ = parse_g(text, None)
    tabs = re.findall(r"<TABLE>(.*?)</TABLE>", text, re.S | re.I) or [text]
    srclines = []
    for tab in tabs:
        for raw_line in tab.splitlines():
            line = re.sub(r"<[^>]+>", " ", raw_line)
            line = re.sub(r"[ \t\x0c]+", " ", line).strip()
            if line and not ptp.DASH.match(line) and not ptp.HDR.search(line):
                srclines.append(line)
    for r in rows:
        if r["value"] > 1e12 or r["value"] != int(r["value"]):
            n_impl += 1
            hits = [ln[:150] for ln in srclines
                    if (r["cusip"] or " ")[:5] in ln or r["name"][:12] in ln]
            print(f"  {mgr} {f['accession']} rpt {f['report']}: "
                  f"'{(r['name'] or '')[:24]}' cus '{r['cusip']}' "
                  f"v {r['value']!r} sh {r['shares']!r}")
            for h in hits[:2]:
                print(f"      src: {h}")
print(f"  implausible rows total: {n_impl}")

# ---------- 7. frozen-panel cusip census ----------
print("\n### 6. frozen-panel text-row cusip census")


def cusip_chk(c):
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


for mgr in m["managers"]:
    raw = gzip.decompress((HUNT / f"data/holdings_{mgr}.csv.gz").read_bytes()).decode()
    n = letter = s78fail = chkfail = 0
    examples = defaultdict(int)
    for r in csv.DictReader(io.StringIO(raw)):
        if r["source"] != "text" or r["entry_kind"] == "cont":
            continue
        n += 1
        c = (r["cusip"] or "").strip().upper()
        if len(c) == 9 and c[0].isalpha():
            letter += 1
            examples[c] += 1
        if len(c) == 9 and not c[6:8].isdigit():
            s78fail += 1
            examples["s78FAIL:" + c] += 1
        fmt, ok = cusip_chk(c)
        if fmt and not ok:
            chkfail += 1
            examples["CHKFAIL:" + c] += 1
    top = sorted(examples.items(), key=lambda kv: -kv[1])[:8]
    print(f"  {mgr:<13} new-rows {n:>6} letter-init {letter:>4} "
          f"s78-fail {s78fail:>3} check-fail {chkfail:>3} | {top}")
