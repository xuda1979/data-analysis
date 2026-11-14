"""Build portfolios from the 60 completed equity research reports.

Two books, assembled deterministically from the report JSONs (no LLM):

  * long-only conviction book  — top names (from WATCHLIST "top") that clear
    the evidence bar: judge approved (or risk override applied) AND positive
    expected return to the effective base PT.
  * long/short market-neutral-ish book — long the conviction book, short the
    bottom-30 names with a negative expected return signal.

Ranking uses the SAME effective scenarios as build_index/build_top_picks
(report_view.effective_scenarios): the risk manager's deterministic override
when the judge was vetoed, else the judge's scenarios. A vetoed report that
was overridden to a positive expected value is NOT excluded -- the risk team
already supplied the corrected target and the veto check is 4/4-driven
(see _run_risk_manager in research_report.py: override applied per scenario).

Weights:
  * conviction book: equal weight, long only.
  * long/short: equal-weight dollar-long across longs and equal-weight
    dollar-short across shorts; expose the pure spread (longs 100% +
    shorts -100% of starting capital). Net exposure is the count difference
    only; we do not claim dollar-neutrality per name since targets are
    12-mo and share amounts are out of scope here.

Report JSON schema (see research_report.py ReportResult.as_dict):
  judge.scenarios.{base,bull,bear}.{pt,prob,thesis}
  risk_manager.verdict {approved|vetoed}, risk_manager.override_applied,
  risk_manager.override.scenarios (used when vetoed)
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
for p in (os.path.join(ROOT, "tools"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from wt.agent.report_view import (  # noqa: E402
    latest_json_per_sym, effective_scenarios, expected_return,
)
from wt.agent import build_index  # reuse RATING_ORDER / pct helpers  # noqa: E402

OUT_DIR = build_index.OUT_DIR
WATCHLIST = os.path.join(ROOT, "results", "equity_research", "WATCHLIST.json")


def _load_watchlist():
    with open(WATCHLIST) as f:
        w = json.load(f)
    top = [t["sym"] for t in w["top"]]
    bottom = [t["sym"] for t in w["bottom"]]
    assert len(top) == len(bottom) == 30
    return top, bottom


def _fmt_usd(x):
    if x is None:
        return "—"
    return f"${x:,.2f}"


def _fmt_pct(x):
    if x is None:
        return "—"
    return f"{x * 100:+.1f}%"


def build_books():
    top_syms, bottom_syms = _load_watchlist()
    reports = {}
    for path in latest_json_per_sym():
        with open(path) as f:
            d = json.load(f)
        reports[d["sym"]] = (d, path)

    rows = []  # one row per covered name
    for sym, (d, path) in sorted(reports.items()):
        sc = effective_scenarios(d)
        base_pt, exp = expected_return(sc, d.get("price"))
        rm = d.get("risk_manager") or {}
        rows.append({
            "sym": sym, "path": path, "price": d.get("price"),
            "rating": ((d.get("judge") or {}).get("rating") or "n/a"),
            "conv": (d.get("judge") or {}).get("conviction"),
            "base_pt": base_pt, "exp": exp,
            "verdict": rm.get("verdict"), "override_applied": rm.get("override_applied"),
            "errors": len(d.get("errors") or []),
        })

    # ---- long-only conviction book: top-30 names, positive signal --------
    longs = [r for r in rows if r["sym"] in top_syms and r["exp"] is not None
             and r["exp"] > 0.02 and r["errors"] == 0]
    longs.sort(key=lambda r: -(r["exp"] or 0))

    # ---- long/short: long conviction book, short bottom names w/ neg exp --
    shorts = [r for r in rows if r["sym"] in bottom_syms and r["exp"] is not None
              and r["exp"] < -0.02 and r["errors"] == 0]
    shorts.sort(key=lambda r: (r["exp"] or 0))  # most negative first

    return rows, longs, shorts


def main() -> int:
    rows, longs, shorts = build_books()
    L = ["# Portfolios — built from the agent-debate equity research", ""]
    L.append(
        "*Deterministic assembly from the 60 report JSONs (no LLM). Long book = "
        "WATCHLIST top-30 names with positive expected return to the effective "
        "base PT. Short book = WATCHLIST bottom-30 names with negative expected "
        "return. Weights are equal-weight within each book; target horizon "
        "12-mo. Research only; not investment advice.*")
    L.append("")

    # ---------------- long-only conviction book ----------------
    L.append("## Long-only conviction book")
    L.append("")
    if not longs:
        L.append("_No names cleared the conviction bar in this run._")
        L.append("")
    else:
        L.append("| Sym | Rating | Conv | Last px | Base PT | ExpReturn | Verdict |")
        L.append("|---|---|---|---|---|---|---|")
        for r in longs:
            L.append(
                f"| **{r['sym']}** | {r['rating']} | {r['conv']} | "
                f"{_fmt_usd(r['price'])} | {_fmt_usd(r['base_pt'])} | "
                f"**{_fmt_pct(r['exp'])}** | "
                f"{r['verdict'].upper() if r['verdict'] else '—'}"
                f"{' (override)' if r['override_applied'] else ''} |")
        L.append("")
        w = round(1.0 / len(longs) * 100, 1) if longs else 0
        L.append(f"_Equal weight: {w}% of the long book per name._")
        L.append("")

    # ---------------- long/short book ----------------
    L.append("## Long/short book (bottom-30 shorts)")
    L.append("")
    L.append("Long leg: the conviction book above. Short leg:")
    L.append("")
    if not shorts:
        L.append("_No bottom-30 name carried a negative expected-return "
                 "signal in this run._")
        L.append("")
    else:
        L.append("| Sym | Rating | Conv | Last px | Base PT | ExpReturn | Verdict |")
        L.append("|---|---|---|---|---|---|---|")
        for r in shorts:
            L.append(
                f"| **{r['sym']}** | {r['rating']} | {r['conv']} | "
                f"{_fmt_usd(r['price'])} | {_fmt_usd(r['base_pt'])} | "
                f"**{_fmt_pct(r['exp'])}** | "
                f"{r['verdict'].upper() if r['verdict'] else '—'}"
                f"{' (override)' if r['override_applied'] else ''} |")
        L.append("")
        w = round(1.0 / len(shorts) * 100, 1) if shorts else 0
        L.append(f"_Equal-weight dollar short: {w}% of short book per name_")
        L.append("")

    # ---------------- methodology / coverage ----------------
    L.append("## Coverage & method")
    L.append("")
    L.append(f"- {len(rows)} names covered; {len(longs)} long candidates, "
             f"{len(shorts)} short candidates.")
    L.append("- Expected return = effective base PT / last close − 1 "
             "(effective = risk-team override when the judge was vetoed).")
    L.append("- Evidence gate: `errors == 0` on the report; conviction bar is "
             "a positive expected return (≈2% floor), not a rating filter.")
    L.append("- Equal-weight sizing; no position-sizing or portfolio "
             "optimization — the debate reports are security selection input, "
             "not a full allocator.")
    L.append("")

    path = os.path.join(OUT_DIR, "PORTFOLIOS.md")
    with open(path, "w") as f:
        f.write("\n".join(L))
    print(f"wrote {path} ({len(longs)} longs, {len(shorts)} shorts, "
          f"{len(rows)} covered)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
