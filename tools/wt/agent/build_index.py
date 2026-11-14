#!/usr/bin/env python3
"""Build results/equity_research/INDEX.md from all report JSONs.

Ranks covered names by the effective base-case 12-mo price target: the
risk manager's deterministic override for vetoed reports, else the
judge's scenarios (see report_view.effective_scenarios). Re-run after any
batch:
    python tools/wt/agent/build_index.py
"""
from __future__ import annotations
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
for p in (os.path.join(ROOT, "tools"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from wt.agent.report_view import (  # noqa: E402
    OUT_DIR, latest_json_per_sym, effective_scenarios,
)

RATING_ORDER = {"BUY": 0, "OVERWEIGHT": 1, "HOLD": 2, "UNDERWEIGHT": 3, "SELL": 4}


def _pct(x) -> str:
    if x is None:
        return "n/a"
    return f"{x * 100:+.1f}%"


def _num(x) -> str:
    """Format a price/PT at 2dp — never leak binary floats like
    886.510009765625 onto the page."""
    if x is None:
        return "n/a"
    return f"{x:,.2f}"


def main() -> int:
    rows = []
    for f in latest_json_per_sym():
        d = json.load(open(f))
        j = d.get("judge") or {}
        sc = effective_scenarios(d)
        base = sc.get("base") or {}
        bull = sc.get("bull") or {}
        bear = sc.get("bear") or {}
        price = d.get("price")
        base_pt = base.get("pt")
        exp_ret = (base_pt / price - 1.0) if (base_pt and price) else None
        rows.append({
            "sym": d["sym"], "date": f.rsplit("_", 1)[-1].replace(".json", ""),
            "price": price, "rating": j.get("rating") or "n/a",
            "conv": j.get("conviction"), "convg": j.get("convergence"),
            "base_pt": base_pt, "exp_ret": exp_ret,
            "bull_pt": bull.get("pt"), "bear_pt": bear.get("pt"),
            "rationale": (j.get("decision_rationale") or "")[:140],
            "fair": ((d.get("valuation") or {}).get("outputs") or {})
                .get("fair_value"),
            "errors": len(d.get("errors") or []),
        })

    rows.sort(key=lambda r: (-(r["exp_ret"] if r["exp_ret"] is not None
                                else -999), RATING_ORDER.get(r["rating"], 9)))

    L = ["# Equity research coverage — index (agent debate reports)", ""]
    L.append(f"*{len(rows)} names covered. Ranks by the effective base-case "
             f"12-mo PT (risk-team deterministic override when the judge was "
             f"vetoed, else the judge's target) vs last price = the report's "
             f"expected-return estimate. Updated "
             f"{__import__('datetime').datetime.now(__import__('datetime').timezone.utc).strftime('%Y-%m-%d')} "
             f"UTC. Research only; not investment advice.*")
    L.append("")

    # Top picks: names with a real positive expected-return signal (base PT
    # above price) AND a forward-EPS valuation anchor.
    picks = [r for r in rows
             if r["exp_ret"] is not None and r["exp_ret"] > 0.02
             and (r["fair"] or {}).get("base")]
    if picks:
        L.append("## Top picks (positive expected return, forward-EPS anchor)")
        L.append("")
        for r in picks:
            L.append(f"- **{r['sym']}** — {r['rating']} ({r['conv']}), base PT "
                     f"{_num(r['base_pt'])} → **{_pct(r['exp_ret'])}** vs price "
                     f"{_num(r['price'])}; bear-case PT {_num(r['bear_pt'])} caps the "
                     f"downside scenario.")
        L.append("")
        L.append("> Caveat: single-run LLM ratings vary between runs (e.g. "
                 "MU was BUY then HOLD). The durable output is the "
                 "evidence-graded debate in each report.")
        L.append("")
    L.append("| Rank | Sym | Current price | Predicted 1-yr price | ExpRet→ | Rating | Conv | Bear PT | Convergence |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(rows, 1):
        L.append(
            f"| {i} | **{r['sym']}** | {_num(r['price'])} | "
            f"{_num(r['base_pt'])} | {_pct(r['exp_ret'])} | "
            f"{r['rating']} | {r['conv'] or 'n/a'} | "
            f"{_num(r['bear_pt'])} | {'yes' if r['convg'] else 'no'} |")
    L.append("")
    L.append("## Rationales (judge)")
    for r in rows:
        L.append(f"- **{r['sym']}** — {r['rationale']}")
    L.append("")
    L.append("## Notes")
    L.append("- Screening: top names by 12-mo Sharpe on the repo's US price "
             "panel, diversified across sectors.")
    L.append("- Base PT = the effective 12-mo base-case target: the judge's "
             "target when the risk manager approved it, else the risk team's "
             "deterministic override (anchored to the Python valuation; see "
             "per-report valuation notes for basis: forward vs trailing EPS).")
    L.append("- Convergence 'no' means the bull/bear debate was genuinely "
             "unresolved — treat those ratings as lower-confidence.")
    L.append("- Full reports: `results/equity_research/<SYM>_<date>.md` "
             "(JSON alongside).")
    L.append("")

    path = os.path.join(OUT_DIR, "INDEX.md")
    with open(path, "w") as f:
        f.write("\n".join(L))
    print(f"wrote {path} ({len(rows)} names)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
