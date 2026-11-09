#!/usr/bin/env python3
"""F13F_CROWDING_HUNT1 — checksum census verification (verification-only).

Resolves the earlier census discrepancy: a prior ad-hoc run claimed 79
fires among the 33 s78-rejected Case-B candidate tokens were mod-10
checksum-VALID, contradicting manual arithmetic on 12621EAC7. This
script re-runs the census with the CANONICAL checksum function (copied
verbatim from the frozen-diag code, diag_defects.py cusip_check), first
validating it against known-good CUSIPs:

  - 037833100 (Apple)   -> expected VALID   (hand-verified check digit 0)
  - 594918104 (MSFT)    -> expected VALID   (hand-verified check digit 4)
  - 37045V100 (GM)      -> expected VALID   (hand-verified check digit 0)
  - 12621EAC7 (s78-rej) -> expected INVALID (hand-verified check digit 8 != 7)

Then it prints per-token (token, s78 verdict, check verdict) for every
distinct s78-rejected token with a digit-by-digit check computation, and
an s78-accepted-but-checksum-invalid residual census (junk that passes
the spec guard). Read-only; nothing modified. Result feeds the frozen
harness re-pin decision (Task #2 step 2).
"""
import importlib.util
import re
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"

spec = importlib.util.spec_from_file_location("ptp", HERE / "proto_text_parser.py")
ptp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ptp)
WORD = ptp.WORD
_num = ptp._num


def chk(c):
    """CUSIP mod-10 checksum (canonical, diag_defects.py cusip_check verbatim).
    Returns (format_ok, checksum_ok)."""
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


def chk_debug(c):
    """Digit-by-digit check-digit computation for one 9-char token."""
    c = c.upper()
    parts = []
    total = 0
    for i in range(8):
        ch = c[i]
        v = int(ch) if ch.isdigit() else ord(ch) - 55
        raw = v
        if i % 2 == 1:
            v *= 2
        vs = v // 10 + v % 10
        total += vs
        parts.append(f"{ch}({raw}{'*2' if i % 2 else ''}={v}->{vs})")
    cd = (10 - total % 10) % 10
    return f"sum {total} -> check {cd} vs last '{c[8]}' | " + " ".join(parts)


def g_ok(t, guard):
    if guard == "s78":
        return len(t) == 9 and t[6:8].isdigit()
    if guard == "any":
        return any(ci.isdigit() for ci in t)
    return True


def case_b_candidates(line):
    toks = [t for t in line.split(" ") if t]
    out = []
    for i, t in enumerate(toks):
        if (len(t) == 10 and WORD.match(t[:9])
                and (t[9] in "xX" or any(c.isalpha() for c in t[:9]))):
            t = t[:9]
        pre = ""
        if (len(t) == 12 and t[:3].isalpha() and WORD.match(t[3:])
                and any(c.isdigit() for c in t[3:])):
            t = t[3:]
        if WORD.match(t) and i + 1 < len(toks) and _num(toks[i + 1]) is not None:
            out.append((i, t))
    return out


# ---------------- 0. checksum function validation ----------------
print("### 0. chk() validation")
for c, exp in [("037833100", True), ("594918104", True), ("37045V100", True),
               ("12621EAC7", False), ("011568548", None)]:
    fok, ok = chk(c)
    verdict = "EXPECTED " + (str(exp) if exp is not None else "?") + f" -> got {ok}"
    print(f"  {c}: fmt_ok {fok} check_ok {ok}  [{verdict}]")
    print(f"      debug: {chk_debug(c)}")

# ---------------- 1. s78-rejected census with checksum ----------------
print("\n### 1. s78-rejected tokens x checksum")
import json
m = json.load(open(HERE / "fetch_manifest.json"))
text_filings = []
for mgr, mm in m["managers"].items():
    for f in mm["filings"]:
        if f.get("source") == "text":
            text_filings.append((mgr, f))

tok_stats = defaultdict(lambda: {"fires": 0, "mgrs": Counter(), "chk": Counter(),
                                 "samples": []})
for mgr, f in text_filings:
    p = CACHE / f"{f['accession']}_{f['filename']}"
    if not p.exists():
        continue
    text = p.read_text(errors="replace")
    tabs = re.findall(r"<TABLE>(.*?)</TABLE>", text, re.S | re.I) or [text]
    for tab in tabs:
        for raw_line in tab.splitlines():
            line = re.sub(r"<[^>]+>", " ", raw_line)
            line = re.sub(r"[ \t\x0c]+", " ", line).strip()
            if not line or ptp.DASH.match(line) or ptp.HDR.search(line):
                continue
            for _, t in case_b_candidates(line):
                st = tok_stats[t]
                st["fires"] += 1
                st["mgrs"][mgr] += 1
                fok, ok = chk(t)
                st["chk"]["fmt_bad" if not fok else ("ok" if ok else "FAIL")] += 1
                if len(st["samples"]) < 1:
                    st["samples"].append((f["accession"], line[:120]))

s78_rej = {t: st for t, st in tok_stats.items() if not g_ok(t, "s78")}
print(f"  distinct s78-rejected tokens: {len(s78_rej)}, "
      f"fires {sum(st['fires'] for st in s78_rej.values())}")
print(f"  checksum-VALID among s78-rejected: "
      f"{sum(1 for st in s78_rej.values() if st['chk']['ok'])}, "
      f"fires {sum(st['fires'] for st in s78_rej.values() if st['chk']['ok'])}")
for t, st in sorted(s78_rej.items(), key=lambda kv: -kv[1]["fires"]):
    ck = "VALID" if st["chk"]["ok"] else "invalid"
    print(f"    '{t}' fires {st['fires']} mgrs {dict(st['mgrs'])} chk[{ck}]")
    if len(st["samples"]) and st["chk"]["ok"]:
        acc, ln = st["samples"][0]
        print(f"        {acc}: {ln}")

# ---------------- 2. s78-ACCEPTED but checksum-invalid census ----------------
print("\n### 2. s78-accepted tokens that fail checksum (residual junk under s78)")
s78_acc_bad = {t: st for t, st in tok_stats.items()
               if g_ok(t, "s78") and not st["chk"]["ok"]}
print(f"  distinct: {len(s78_acc_bad)}, fires "
      f"{sum(st['fires'] for st in s78_acc_bad.values())}")
for t, st in sorted(s78_acc_bad.items(), key=lambda kv: -kv[1]["fires"])[:20]:
    acc, ln = st["samples"][0] if st["samples"] else ("", "")
    print(f"    '{t}' fires {st['fires']} mgrs {dict(st['mgrs'])} | {acc}: {ln}")

# letter-initial check
print("\n### 3. letter-initial s78-accepted x checksum (CINS kinship)")
li = {t: st for t, st in tok_stats.items()
      if g_ok(t, "s78") and t[0].isalpha()}
for t, st in sorted(li.items(), key=lambda kv: -kv[1]["fires"])[:15]:
    ok = st["chk"]["ok"]
    print(f"    '{t}' fires {st['fires']} chk[{'VALID' if ok else 'invalid'}]")
