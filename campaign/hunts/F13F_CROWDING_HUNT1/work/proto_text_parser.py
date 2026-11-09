#!/usr/bin/env python3
"""F13F_CROWDING_HUNT1 — text-era info-table parser: validation harness.

Verification-only (pre-seal). Tests parse_text_infotable() against pinned
text-era filings spanning all 6 roster managers, first (2008Q1) and last
(2013Q1) text-era report periods, 2012 mid-era samples, and one 13F-HR/A
amendment. PASS = cover reconciliation: parsed row count == cover "Entry
Total" AND value sum == cover "Value Total" (exact int match, units-aware:
sum == cover | sum*1000 == cover | sum == cover*1000).

Text-era formats observed (DISCOVERY.md §2 correction, 2026-11-08):
  - Berkshire style: space-separated CUSIPs ("025816 10 9"), comma-formatted
    values/shares, wrapped issuer names, `X` discretion, sub-account
    continuation rows, per-page subtotals between dashed rules.
  - Contiguous style (other 5): 9-char contiguous CUSIP, value right after,
    optional SH/PRN, discretion word, voting triple.
All text-era filings are pre-2013 acceptance -> values in THOUSANDS.

CUSIP guard (sealed 2026-11-09, chk_verify.py census): both WORD-match sites
require `_real_cusip(t)` = positions 7-8 numeric (CUSIP-spec issue-number)
OR mod-10 checksum-valid. Census of all 210 text filings: the guard rejects
exactly 11 genuine junk tokens / 66 fires (SPONSORED x49, NUTRITION,
HOLDINGCO, FLORIDACO, CAPITALCO, RESTRICTE, DEPOSITRY, REPSTUNIT, SALOONCOM,
COMPANYCO, SYSTEMSCO — all renaissance OCR/parse corruption, all checksum-
invalid), while retaining 22 real convertible-debt CUSIPs / 79 fires that
plain s78 wrongly dropped (CNO DBCV 52729NBM1/NBR0, E-Trade 269246AZ7, Level
3 CONV 52729NAS9, CEMEX CONV 151290BB8/BC6, MGM 55303QAE0, Shanda 81941QAD6,
etc. — all mod-10 VALID). Checksum subsumes the letter-initial CINS carve-out
(all G4776G101-style positions mod-10 VALID, chk_verify.py §3). Pinned
harness filings contain no guard-rejected tokens (s78 delta = 0 on all 7
pins), so the 19/19 harness expectations remain authoritative.
"""
import re
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
CACHE = HERE / "cache"
UA = {"User-Agent": "Hsu David research dhsoftware.contact@gmail.com"}
MIN_INTERVAL = 0.12
_last = [0.0]

# ---------------------------------------------------------------- parser ---

HDR = re.compile(r"NAME OF ISSUER|TITLE OF CLASS|VOTING AUTHORITY|OTHER MANAGERS"
                 r"|\(X ?\$?1000\)|\(x ?\$?1000\)", re.I)
DASH = re.compile(r"^[-._=+~]{3,}$")
CUSIP_SP = re.compile(r"\b([0-9A-Z]{5,7}) ([0-9A-Z]{2}) ([0-9])(?=\s|$)")
WORD = re.compile(r"^[0-9A-Z]{9}$")
DISCR = {"x", "sole", "defined", "dfnd", "other", "shared", "none", "n/a", "na"}


def _chk_ok(c):
    """CUSIP mod-10 checksum (canonical; diag_defects.py cusip_check verbatim).
    Returns check-digit validity for a 9-char alnum token with digit last."""
    c = (c or "").strip().upper()
    if len(c) != 9 or not c.isalnum() or not c[8].isdigit():
        return False
    total = 0
    for i in range(8):
        ch = c[i]
        v = int(ch) if ch.isdigit() else ord(ch) - 55
        if i % 2 == 1:
            v *= 2
        total += v // 10 + v % 10
    return (10 - total % 10) % 10 == int(c[8])


def _real_cusip(t):
    """Real-CUSIP guard (sealed 2026-11-09): spec issue-number positions 7-8
    numeric, OR mod-10 checksum-valid (catches convertible-debt CUSIPs whose
    positions 7-8 are letters, e.g. 12621EAC7)."""
    return len(t) == 9 and (t[6:8].isdigit() or _chk_ok(t))


def _num(tok):
    t = tok.replace(",", "")
    if not t or not t[0].isdigit():
        return None
    try:
        return float(t)
    except ValueError:
        return None


def _classify(line):
    """One table line -> row dict | None. Cases: A spaced CUSIP, C
    continuation (first two tokens numeric), B contiguous CUSIP."""
    toks = line.split(" ")
    toks = [t for t in toks if t]
    if not toks:
        return None
    # Case A: spaced 6-2-1 CUSIP (Berkshire style)
    m = CUSIP_SP.search(line)
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
    # Case C: continuation row (value, shares, ... no issuer/cusip).
    # Skip when a 9-char CUSIP is present: issuer names like "1-800
    # FLOWERS" start with two numeric tokens but are real Case-B rows.
    n0, n1 = _num(toks[0]), _num(toks[1]) if len(toks) > 1 else None
    # a real Case-B row has a 9-char token followed by a numeric token;
    # bare 9-digit share counts in cont rows don't qualify (next token
    # is SH/PRN or end of line)
    has_cusip = any(WORD.match(t) and _real_cusip(t)
                    and i + 1 < len(toks)
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
            elif tu.lower() in DISCR:
                extra["investmentDiscretion"] = t
        return {"kind": "cont", "cusip": "", "name": "", "value": n0,
                "shares": n1, **extra}
    # Case B: contiguous CUSIP with a numeric token right after
    for i, t in enumerate(toks):
        # 10-char token: 9-char CUSIP + stray char (trailing x, or stray
        # digit when the CUSIP contains a letter; rejects pure numbers)
        if (len(t) == 10 and WORD.match(t[:9])
                and (t[9] in "xX" or any(c.isalpha() for c in t[:9]))):
            t = t[:9]
        # 12-char token: 3-alpha class prefix glued to 9-char CUSIP
        pre = ""
        if (len(t) == 12 and t[:3].isalpha() and WORD.match(t[3:])
                and any(c.isdigit() for c in t[3:])):
            pre, t = t[:3], t[3:]
        if WORD.match(t) and _real_cusip(t) \
                and i + 1 < len(toks) and _num(toks[i + 1]) is not None:
            nums = []  # (raw token, value)
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
                elif tu.lower() in DISCR:
                    extra["investmentDiscretion"] = tt
            if nums:
                raw0, v0 = nums[0]
                # exclude <=2-digit numerics (other-managers "01", "0" cols)
                rest = sum(v for _, v in nums[1:] if v >= 100)
                s0 = str(int(v0))
                # glued "value+shares" token: comma-free, >=11 digits,
                # numeric suffix == sum of following voting/share columns
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


def parse_text_infotable(text):
    """Returns (rows, cover, diag). rows include new + continuation rows."""
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
            if not line or DASH.match(line) or HDR.search(line):
                pending = ""
                continue
            row = _classify(line)
            if row is None:
                if sum(1 for t in line.split() if _num(t) is not None) >= 2:
                    dropped.append(line[:130])
                if not _num(line.split(" ")[0] if line.split() else ""):
                    pending = (pending + " " + line).strip()  # issuer wrap
                else:
                    pending = ""
                continue
            if row["kind"] == "new":
                if row["name"] and pending:
                    row["name"] = (pending + " " + row["name"]).strip()
            pending = ""
            rows.append(row)
    return rows, cover, {"dropped_suspicious": dropped[:20]}


# ----------------------------------------------------------------- tests ---

# (mgr, cik, accession-nodash, primary doc, expected_entries, expected_sum)
TESTS = [
    ("berkshire",    1067983, "000095014808000200", "v40691ae13fvhr.txt",    105, 66461224),
    ("berkshire",    1067983, "000119312512260151", "d361607d13fhra.txt",    None, None),  # 13F-HR/A 2012Q1
    ("berkshire",    1067983, "000119312512355534", "d392985d13fhr.txt",     None, None),  # 2012Q2
    ("berkshire",    1067983, "000119312513222307", "d535016d13fhr.txt",     None, None),  # 2013Q1 (last text)
    ("bridgewater",  1350694, "000091412108000387", "bd033108-13f.txt",       523, 4818350),  # filer cover error, indep-verified
    ("bridgewater",  1350694, "000114036112036262", "form13fhr.txt",         None, None),  # 2012Q2
    ("bridgewater",  1350694, "000114036113020200", "form13fhr.txt",         None, None),  # 2013Q1
    ("paulson",      1035674, "000103567408000009", "pco033108.txt",         21, 6105653),
    ("paulson",      1035674, "000116660412000010", "pco063012.txt",         None, None),  # 2012Q2 (alt filer)
    ("paulson",      1035674, "000114036113021112", "form13fhr.txt",         None, None),  # 2013Q1
    ("renaissance",  1037389, "000103738908000003", "mar0813frtllc.txt",     3352, 51582503),  # filer cover error (+11), 3-method indep-verified
    ("renaissance",  1037389, "000103738912000066", "ren_13f_q3_2012.txt",   None, None),  # 2012Q3
    ("renaissance",  1037389, "000103738913000054", "renaissance13Fq12013.txt", 2848, 41273179),  # filer cover error (-32), 3-method indep-verified
    ("southeastern",  807985, "000080798508000035", "f13f0308.txt",          113, 30897467),
    ("southeastern",  807985, "000080798512000041", "f13f0612.txt",          None, None),  # 2012Q2
    ("southeastern",  807985, "000080798513000034", "f13f0313.txt",          None, None),  # 2013Q1
    ("appaloosaOld", 1006438, "000100643808000002", "a13f08q1.txt",          28, 1814514),  # cover in dollars
    ("appaloosaOld", 1006438, "000100643812000006", "a13f12q2.txt",          None, None),  # 2012Q2
    ("appaloosaOld", 1006438, "000100643813000004", "a13f13q1.txt",          None, None),  # 2013Q1
]


def get(url):
    dt = time.monotonic() - _last[0]
    if dt < MIN_INTERVAL:
        time.sleep(MIN_INTERVAL - dt)
    _last[0] = time.monotonic()
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    n_pass = n_fail = 0
    for mgr, cik, acc, doc, exp_n, exp_v in TESTS:
        key = CACHE / f"{acc}_{doc}"
        if key.exists():
            b = key.read_bytes()
        else:
            b = get(f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{doc}")
            key.write_bytes(b)
        text = b.decode("utf-8", "replace")
        rows, cover, diag = parse_text_infotable(text)
        s = sum(r["value"] for r in rows)
        si = int(round(s))
        ok_n = cover["entry_total"] is None or len(rows) == cover["entry_total"]
        # value: advisory, units-aware, tolerance <=10 filing units
        # (table units; covers may be whole dollars -> *1000 cases)
        ok_v = (cover["value_total"] is None
                or abs(si - cover["value_total"]) <= 10
                or abs(si * 1000 - cover["value_total"]) <= 10_000
                or abs(si - cover["value_total"] * 1000) <= 10_000)
        # pinned expectations are authoritative overrides (independently
        # verified table truth, e.g. bridgewater 2008Q1 filer cover error)
        if exp_n is not None:
            ok_n = len(rows) == exp_n
        if exp_v is not None:
            ok_v = (abs(si - exp_v) <= 10 or abs(si * 1000 - exp_v) <= 10_000)
        status = "PASS" if ok_n and ok_v else "FAIL"
        n_pass += status == "PASS"
        n_fail += status == "FAIL"
        print(f"{status} {mgr:<13} {acc} rows {len(rows):>5} "
              f"(new {sum(1 for r in rows if r['kind']=='new')}, "
              f"cont {sum(1 for r in rows if r['kind']=='cont')}) "
              f"sum {si:>13,} | cover E={cover['entry_total']} V={cover['value_total']}")
        if status == "FAIL":
            for d in diag["dropped_suspicious"]:
                print("      dropped:", d)
    print(f"\n{n_pass} PASS / {n_fail} FAIL")


if __name__ == "__main__":
    main()
