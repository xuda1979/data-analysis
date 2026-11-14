"""Shared read-layer over report JSONs for the M5 portfolio builders.

Every builder (build_index, build_top_picks, build_portfolios) must rank on
the SAME effective price targets. A vetoed report carries two scenario sets:
the judge's (risk-rejected) and the risk manager's deterministic override.
This module centralizes the choice so no builder can silently rank on a
rejected number.
"""
from __future__ import annotations

import glob
import json
import os

OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))),
    "results", "equity_research")


def latest_json_per_sym(out_dir=OUT_DIR):
    """All report JSONs, keeping only the newest date per symbol. Sorted by
    filename (sym)."""
    files = {}
    for f in glob.glob(os.path.join(out_dir, "*.json")):
        name = os.path.basename(f)
        if "_" not in name or not name.endswith(".json"):
            continue
        # '<SYM>_<YYYY-MM-DD>.json' -- split on the FIRST underscore: the
        # date itself contains '-' only, and non-report names like
        # TOP_PICKS_<date> keep an underscore in the first field, which a
        # ticker sym never has (rpartition would wrongly eat the date's last
        # underscore and let TOP_PICKS_<date> through).
        first, _, rest = name.partition("_")
        sym, date = first, rest[:-5]
        if sym == "INDEX" or sym == "TOP" or "PORTFOLIO" in sym or "_" in sym:
            continue
        if sym not in files or date > files[sym][0]:
            files[sym] = (date, f)
    return [t[1][1] for t in sorted(files.items())]  # deterministic, sorted by sym


def effective_scenarios(d):
    """Scenarios the risk team endorses: override when the judge was vetoed,
    else the judge's own. Returns dict with 'base'/'bull'/'bear' each
    {'pt': ..., 'prob': ...}; missing pieces are {} -- never None."""
    rm = d.get("risk_manager") or {}
    if rm.get("override_applied") and rm.get("override"):
        sc = (rm["override"].get("scenarios") or {})
    else:
        sc = ((d.get("judge") or {}).get("scenarios") or {})
    return sc


def expected_return(sc, price):
    base = (sc or {}).get("base") or {}
    pt = base.get("pt")
    if pt is None or not price:
        return None, None
    return pt, (pt / price - 1.0)


def load_report(path):
    """Parse a report JSON path -> (data, sym, date)."""
    with open(path) as f:
        d = json.load(f)
    name = os.path.basename(path)
    sym, _, date = name.rpartition("_")
    date = date[:-5]  # strip .json
    return d, sym, date
