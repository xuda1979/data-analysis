"""CBOE delayed-quotes option-chain helpers (RECONSTRUCTED 2026-11-05).

Provenance: the original module was never committed to git and was deleted
from disk ~2026-11-05, breaking the daily H1 collect run (ImportError,
consecutive_failures=1 in campaign/logs/h1_status.json). This file is a
contract-faithful reconstruction, reverse-pinned from:

  * h1_collect.py — the sole API consumer (BASE/UA/chain_rows/lint_snapshot/
    write_snapshot_csv call sites);
  * all 212 archived snapshot CSVs, 24 trade dates 20260908..20261102:
    CRLF line endings including a trailing CRLF at EOF, 14-column header,
    per-row spot as first column, `%g` numeric format (14,482,028 numeric
    cells round-trip byte-exact, 3 legitimate sci-notation cells), sort
    order (exp ascending, C before P, strike ascending);
  * 9 live CBOE payloads captured 2026-11-05 (option dicts: all numeric
    fields float, zero None values; `iv` is a decimal, payload-level `iv30`
    is a percent).

Documented reconstruction choices:

  * moneyness: plain strike rule (C: strike <= spot -> itm_call else
    otm_call; P: strike <= spot -> otm_put else itm_put). No global rule
    reproduces the original stored labels exactly — band-threshold,
    grid-multiple and delta-threshold families were all refuted against
    the archive (ITM/OTM boundary regions overlap, so no pure
    (typ, strike, spot) threshold exists); the strike rule agrees with
    99.802% of 1,316,548 archived rows. The label has ZERO analytical
    consumers (recompute_day/build_symbol never read the moneyness
    column) — the 0.198% deviation is cosmetic only.
  * lint_snapshot: minimal gates (rows non-empty, spot > 0, iv30 > 0).
    There are zero lint failures in the entire archived history (the only
    fetch failures ever recorded are SSL/read timeouts), so nothing
    further is observable from evidence.

Stdlib-only: this module is imported at test-module level.
"""

import re

BASE = "https://cdn.cboe.com/api/global/delayed_quotes/options"
UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")

# standard OCC option symbol: ROOT + YYMMDD + C/P + 8-digit strike/1000
# (non-standard issues, e.g. B1-prefixed adjacents, fail this and drop out)
_OCC = re.compile(r"^([A-Z.]+)([0-9]{6})([CP])([0-9]{8})$")

_NUM_KEYS = ("bid", "ask", "iv", "open_interest", "volume",
             "delta", "gamma", "vega", "theta")

_HEADER = ("spot,exp,typ,strike,bid,ask,iv,open_interest,volume,"
           "delta,gamma,vega,theta,moneyness")


def _moneyness(typ, strike, spot):
    if typ == "C":
        return "itm_call" if strike <= spot else "otm_call"
    return "otm_put" if strike <= spot else "itm_put"


def chain_rows(options_list, spot):
    """Parse CBOE delayed-quotes option dicts into snapshot row dicts.

    Filters to standard OCC symbols, parses expiry/strike from the symbol
    (YYMMDD -> "20YY-MM-DD", last 8 digits / 1000), reads quotes/greeks as
    floats, dedupes on (exp, typ, strike) keeping the first occurrence.
    """
    rows, seen = [], set()
    for o in options_list:
        m = _OCC.match(str(o.get("option") or ""))
        if not m:
            continue
        ymd = m.group(2)
        exp = "20%s-%s-%s" % (ymd[:2], ymd[2:4], ymd[4:6])
        typ = m.group(3)
        strike = int(m.group(4)) / 1000.0
        key = (exp, typ, strike)
        if key in seen:
            continue
        seen.add(key)
        r = {"exp": exp, "typ": typ, "strike": strike}
        for k in _NUM_KEYS:
            r[k] = float(o.get(k) or 0.0)
        r["moneyness"] = _moneyness(typ, strike, spot)
        rows.append(r)
    return rows


def lint_snapshot(rows, spot, iv30):
    """Minimal snapshot sanity gates -> {"pass": bool, "reason": str}."""
    if spot <= 0:
        return {"pass": False, "reason": "spot<=0"}
    if not rows:
        return {"pass": False, "reason": "no-rows"}
    if iv30 <= 0:
        return {"pass": False, "reason": "no-iv30"}
    return {"pass": True, "reason": ""}


def write_snapshot_csv(buf, sym, spot, rows):
    """Write one symbol's snapshot CSV to `buf` (text mode).

    Format (byte-pinned against all 212 archived snapshots): CRLF line
    endings including a trailing CRLF at EOF, header
    spot,exp,typ,strike,bid,ask,iv,open_interest,volume,delta,gamma,
    vega,theta,moneyness; every numeric cell via `%g`; spot written
    per-row as the first column; rows sorted (exp asc, C before P,
    strike asc). `sym` is kept in the signature for API symmetry.
    """
    ordered = sorted(rows, key=lambda r: (r["exp"],
                                          0 if r["typ"] == "C" else 1,
                                          r["strike"]))
    buf.write(_HEADER + "\r\n")
    for r in ordered:
        cells = ["%g" % spot, r["exp"], r["typ"], "%g" % r["strike"]]
        cells += ["%g" % r[k] for k in _NUM_KEYS]
        cells.append(r["moneyness"])
        buf.write(",".join(cells) + "\r\n")
