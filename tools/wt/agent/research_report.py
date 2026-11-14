"""Agent debate -> EQUITY RESEARCH REPORT (not a trade ticket).

Extends the repo's multi-agent debate architecture (orchestrator.py) to
produce sell-side-style research reports. Architecture ideas adapted from
projects evaluated on 2026-08-22 (full citation list in RESEARCH_NOTES.md,
tier 2 additions):

- AlphaAnalyst (kbhujbal/AlphaAnalyst): schema-validated research memo;
  "the LLM is a writer, not a knower" -- every number is computed in
  Python from real data, the LLM only writes prose over those numbers.
- StockSense-AI (Spkap/StockSense-AI): anti-sycophancy debate mechanics --
  bull sees growth-positive data first, bear sees risk data first;
  mandatory rebuttal round; every claim is evidence-graded against the
  actual data sections.
- FinAgent (helloJamest/FinAgent): judge node with convergence detection
  and multi-criteria scoring.
- ai-hedge-fund v2 (virattt/ai-hedge-fund): PIT-honesty -- the LLM never
  touches the numbers; missing data => abstain, never fabricate.
- FINSABER / deeplearning-wisc/debate-or-vote (papers): debate only adds
  value over independent voting when claims are grounded and checked --
  hence the rule-based evidence-grading pass.

Data layer (2026-11-11 upgrade, bypasses the dead deepdive registrations):
  - price: results/equity_research/panel/{SYM}.json (2026-11-10 close)
  - fundamentals: stockanalysis.com keyless scraper (equity_fundamentals.py)
  - filings: SEC EDGAR submissions (altdata3.sec_recent_filings)
  - news: Google News RSS (altdata5.google_news)
  - hn_mentions: Hacker News Algolia (altdata3.hn_search)
  Every section is optional: a missing section is an abstention with a
  recorded error, never a fabricated number and never a hard crash.

Pipeline (stdlib-only, mirrors the repo's agent conventions):

  gather data -> bull / bear (anti-sycophancy data ordering)
              -> rebuttal round (each side answers the other's claims)
              -> evidence grading (rule-based, against real data)
              -> deterministic valuation (pure Python, no LLM)
              -> judge (convergence, rating, scenarios, price targets)
              -> report writer (deterministic Markdown assembly)

Every node degrades gracefully and returns None on failure -- the report
is built from whatever steps succeeded. Nothing here places orders; this
is research only.
"""
from __future__ import annotations
import json, os, re, sys, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from .llm_chat import chat, parse_json_response, available_provider
from .equity_fundamentals import fundamentals as _fetch_fundamentals, panel_price

# ---------------------------------------------------------------------------
# Output location
# ---------------------------------------------------------------------------

DEFAULT_OUT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))))),
    "results", "equity_research")

# Persistent fundamentals cache so 60-ticker runs do not re-fetch pages.
FUNDAMENTALS_CACHE_DIR = os.path.join(DEFAULT_OUT_DIR, "fundamentals")


@dataclass
class ReportResult:
    """Structured result of one equity-research report generation."""
    sym: str = ""
    generated_utc: str = ""
    price: Optional[float] = None
    data_sections: List[str] = field(default_factory=list)
    bull: Optional[Dict[str, Any]] = None
    bear: Optional[Dict[str, Any]] = None
    rebuttals: Dict[str, Any] = field(default_factory=dict)
    grading: Dict[str, Any] = field(default_factory=dict)
    valuation: Optional[Dict[str, Any]] = None
    judge: Optional[Dict[str, Any]] = None
    risk_manager: Optional[Dict[str, Any]] = None
    audit: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    elapsed_sec: float = 0.0
    report_path: Optional[str] = None
    json_path: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return {
            "sym": self.sym,
            "generated_utc": self.generated_utc,
            "price": self.price,
            "data_sections": self.data_sections,
            "bull": self.bull,
            "bear": self.bear,
            "rebuttals": self.rebuttals,
            "grading": self.grading,
            "valuation": self.valuation,
            "judge": self.judge,
            "risk_manager": self.risk_manager,
            "audit": self.audit,
            "errors": self.errors,
            "elapsed_sec": round(self.elapsed_sec, 2),
            "report_path": self.report_path,
            "json_path": self.json_path,
        }


# ---------------------------------------------------------------------------
# Data gathering
# ---------------------------------------------------------------------------

_SECTION_LABELS = {
    "quote": "current price/last close",
    "fundamentals": "valuation & quality: market cap, P/E, P/B, P/S, ROE, "
                    "margins, growth, cash/debt, 52w range, analyst targets",
    "news": "recent headlines with sources and timestamps",
    "filings": "recent SEC filings (8-K etc.)",
    "hn_mentions": "Hacker News mention count",
    "clusters": "theme clusters the stock belongs to",
}


def _gather(sym: str) -> Dict[str, Any]:
    """Gather every available data signal on the ticker (no LLM needed).

    Rewired 2026-11-11: deepdive.gather crashes (the old altdata registrations
    -- analyst_target, basic_metrics -- no longer exist). Each section is
    fetched independently and wrapped so a failure abstains that section
    (recorded in fetch_errors) instead of killing the report. Price comes from
    the panel cache (results/equity_research/panel, 2026-11-10 close);
    fundamentals come from the stockanalysis.com keyless scraper with a
    persistent disk cache.
    """
    sym = sym.upper()
    errors: List[str] = []
    out: Dict[str, Any] = {"sym": sym, "fetch_errors": errors}

    def _fund():
        return _fetch_fundamentals(sym, cache_dir=FUNDAMENTALS_CACHE_DIR)

    def _news():
        from wt import altdata5
        return altdata5.google_news(f"{sym} stock", limit=10)

    def _filings():
        from wt import altdata3
        return altdata3.sec_recent_filings(sym, limit=8)

    def _hn():
        from wt import altdata3
        return altdata3.hn_search(f"{sym} stock", limit=8)

    def _clusters():
        from wt import altdata3
        rows, err = altdata3.hn_search(f"{sym} stock", limit=50)
        if err or not rows:
            return None
        # cheap theme clusters: first significant token of each story title
        tags = []
        for r in rows:
            t = (r.get("title") or "").strip()
            m = re.match(r"(?i)[A-Z0-9]{2,}", t)
            if m:
                tags.append(m.group(0))
        return {"tags": sorted(set(tags))[:8]} if tags else None

    # 1. price from the panel cache (never touches the network)
    price, pdate = panel_price(sym)
    out["quote"] = {"c": price, "source": "results/equity_research/panel",
                    "as_of": pdate} if price is not None else None
    if price is None:
        errors.append("quote: no panel price cached for this ticker")

    # 2. everything else in parallel; each section abstains on failure
    jobs = {"fundamentals": _fund, "news": _news, "filings": _filings,
            "hn_mentions": _hn, "clusters": _clusters}
    with ThreadPoolExecutor(max_workers=5) as ex:
        fut = {ex.submit(fn): name for name, fn in jobs.items()}
        for f in as_completed(fut):
            name = fut[f]
            try:
                val = f.result()
            except Exception as e:  # noqa: BLE001 -- section abstains
                errors.append(f"{name}: {e!r}")
                continue
            if isinstance(val, tuple) and len(val) == 2:
                dat, err = val
                if err:
                    errors.append(f"{name}: {err}")
                if dat:
                    out[name] = dat
            elif isinstance(val, str):
                errors.append(val)
            elif val:
                out[name] = val

    return out


# ---------------------------------------------------------------------------
# Data rendering for the LLM (anti-sycophancy ordering)
# ---------------------------------------------------------------------------

def _fmt_section(name: str, value: Any) -> str:
    """Render one data section for the LLM.

    List sections (news, filings, ...) render one JSON object PER LINE with a
    1-based row label `[i]`, so the LLM can cite a specific row as
    '<section>[i].<field>' (grammar taught in the research prompts) instead of
    guessing index conventions. Dict sections render as before.
    """
    if isinstance(value, list):
        try:
            lines = [json.dumps(r, indent=0, default=str) for r in value]
        except Exception:
            lines = [str(r) for r in value]
        body = "\n".join(f"[{i}] {s}" for i, s in enumerate(lines, start=1))
        if not lines:
            body = "[]"
    else:
        try:
            body = json.dumps(value, indent=0, default=str)
        except Exception:
            body = str(value)
    if len(body) > 1400:  # keep prompts bounded; truncate the tail
        body = body[:1400] + "...<truncated>"
    return f"[{name}] {_SECTION_LABELS.get(name, '')}\n{body}"


def _data_view(sym: str, data: Dict[str, Any], side: str) -> str:
    """Render the data for one side.

    Anti-sycophancy ordering (StockSense-AI): the BULL sees the
    growth-positive sections first and the risk sections last; the BEAR
    sees the opposite ordering. The content is identical.
    """
    growth = ["analyst", "analyst_target", "catalyst", "earnings",
              "fundamentals", "news", "gdelt_tone", "hn_mentions"]
    risk = ["insider", "filings", "technicals", "quote"]
    if side == "bull":
        order = growth + risk
    else:
        order = risk + growth
    parts = [f"TICKER: {sym}", f"ROLE: {side.upper()} case"]
    for k in order:
        if k in data:
            parts.append(_fmt_section(k, data[k]))
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# LLM node helpers
# ---------------------------------------------------------------------------

def _repair_truncated_json(text: Optional[str]) -> Optional[dict]:
    """Deterministic repair for responses cut off mid-JSON.

    The LLM (esp. fast models) occasionally stops mid-list, e.g.
    `... "strength": 0.8}` instead of `... "strength": 0.8}]}`. The first
    object is usually complete, so appending the missing closers recovers
    the payload with zero extra LLM cost. Only ever appends; never edits.
    """
    p = parse_json_response(text)
    if p is not None:
        return p
    if not text:
        return None
    for suffix in ("]}", "}]}", "]}", "]}]}", "}}", "]}}", '"}'):
        try:
            cand = text.strip() + suffix
            a, b = cand.find("{"), cand.rfind("}")
            if a >= 0 and b > a:
                d = json.loads(cand[a:b + 1])
                if isinstance(d, dict):
                    return d
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def _llm_json(system_prompt: str, user_prompt: str, errors: List[str],
              label: str, strong: bool = False,
              audit: Optional[Dict[str, Any]] = None) -> Optional[dict]:
    """Standard node pattern: LLM -> JSON, log errors, never raise.

    audit: optional dict mutated in place -- audit[label] persists the
    stage's prompt+response so every LLM node leaves a durable trace
    (per-stage audit trail; long texts truncated to keep the JSON modest).
    """
    if available_provider() is None:
        errors.append(f"{label}: no LLM provider configured (need "
                      "XAI_API_KEY or ANTHROPIC_API_KEY)")
        return None
    raw = chat(system_prompt, user_prompt, strong=strong,
               temperature=0.3, max_tokens=2200,
               disable_thinking=True)
    parsed = None
    if not raw:
        errors.append(f"{label}: LLM returned empty")
    else:
        parsed = _repair_truncated_json(raw)
        if parsed is None:
            # Still broken after repair: retry once with a larger budget. (A
            # brevity hint made this worse on deepseek-flash -- plain retry.)
            raw = chat(system_prompt, user_prompt, strong=strong,
                       temperature=0.3, max_tokens=4000,
                       disable_thinking=True)
            parsed = _repair_truncated_json(raw)
            if parsed is None:
                errors.append(f"{label}: failed to parse JSON (first 200 chars: "
                              f"{raw[:200]!r})" if raw else
                              f"{label}: retry returned empty")
    if audit is not None:
        def _clip(s: str, n: int = 900) -> str:
            s = s or ""
            return s if len(s) <= n else s[:n] + f"...<truncated {len(s)-n} chars>"
        audit[label] = {"system": _clip(system_prompt),
                        "user": _clip(user_prompt),
                        "response": _clip(raw, 1800),
                        "ok": parsed is not None}
    return parsed


_RESEARCHER_SYSTEM = (
    "You are the {side} case researcher for an equity research report. "
    "Your job is to argue the strongest honest {side} case for the ticker, "
    "based ONLY on the data provided. Rules:\n"
    "1. Every claim MUST be grounded in a specific data field. Cite it in "
    "the 'evidence' field as <section>.<field>, e.g. "
    "'fundamentals.pe_ttm' or 'catalyst.eps_est' or 'earnings.surprise_pct'. "
    "To cite a specific row of a list section (e.g. news or filings), use "
    "<section>[i].<field> with i the 1-based row number shown in the data, "
    "e.g. 'news[2].headline' for the second headline.\n"
    "2. If the data does not support a claim, do NOT make it. Missing data "
    "is a reason to stay silent or to say so explicitly.\n"
    "3. Do not hedge: this is your side's case. Pick the 4-6 strongest "
    "claims. No filler.\n"
    "4. Return ONLY the JSON object:\n"
    '{"stance": "bullish|bearish", "confidence": <0-1>, '
    '"claims": [{"claim": "<one sentence>", "evidence": "<section.field>", '
    '"impact": "positive|negative"}]}'
)

_REBUTTAL_SYSTEM = (
    "You are the {side} researcher responding to the OPPOSING case. "
    "Address each of the opposing side's claims head-on. For each one: "
    "either concede it, or rebut it using a specific counter-field from "
    "the data (evidence as <section>.<field>), or point out the inference "
    "gap. Be specific and numerical. Return ONLY:\n"
    '{"rebuttals": [{"target_claim": "<the claim you are answering>", '
    '"response": "<your counter-argument, 1-2 sentences>", '
    '"counter_evidence": "<section.field or null>", '
    '"concede": true|false, "strength": <0-1>}]}'
)

_JUDGE_SYSTEM = (
    "You are the head of a sell-side equity research team. You have read "
    "the bull case, the bear case, their rebuttals, the evidence grading, "
    "and a deterministic valuation computed in Python (never modify its "
    "numbers). Produce the final verdict.\n"
    "Rules:\n"
    "1. Scenarios: bull/base/bear 12-month price targets and probabilities. "
    "Base-case target MUST stay within +-25% of the deterministic "
    "valuation's base fair value when one exists. Probabilities must sum "
    "to 1.0.\n"
    "2. Rating scale: BUY / OVERWEIGHT / HOLD / UNDERWEIGHT / SELL.\n"
    "3. In the 'catalysts' list, when the data's 'catalyst' section has an "
    "explicit date (e.g. next earnings date), use it as the date; otherwise "
    "'unknown'.\n"
    "4. Convergence detection: if bull and bear largely agree on direction "
    "(or disagree on nothing material), set convergence true and keep "
    "conviction; if the debate is unresolved, convergence false and lower "
    "conviction.\n"
    "4. All facts must reference the data already gathered; no new "
    "facts.\n"
    'Return ONLY JSON: {"convergence": true|false, "rating": "<RATING>", '
    '"conviction": <0-1>, "scenarios": {"bull": {"prob": <0-1>, "pt": '
    '<number>, "thesis": "<1 sentence>"}, "base": {...}, "bear": {...}}, '
    '"catalysts": [{"catalyst": "<item>", "date": "<when or unknown>", '
    '"impact": "positive|negative"}], "risks": [{"risk": "<item>", '
    '"likelihood": "low|medium|high"}], "decision_rationale": "<2-3 '
    'sentences tying it together>"}'
)


# ---------------------------------------------------------------------------
# Evidence grading (rule-based, no LLM)
# ---------------------------------------------------------------------------

def _evidence_grounded(cit: str, data: Dict[str, Any]) -> Tuple[bool, str]:
    """Check a single evidence citation like 'fundamentals.roe' or 'quote.c'
    against the gathered data.

    Citations may be `section` or `section.field` where a dict section checks
    `field in section` and a list section (rows of dicts) checks field-in-row
    OR field-as-row-value (e.g. filings rows carry {'form': '8-K', ...}).
    A numbered list row may be cited as `news[2].headline` (1-based, matching
    the 'news[2]' labels used in the research prompts). The dot-index form
    `news.0.headline` (0-based) is also tolerated for robustness.
    """
    sec, _, fld = cit.partition(".")
    sections = set(data.keys())
    # Numbered list-row citation: base name + 1-based index, e.g. 'news[2]'.
    m = re.fullmatch(r"(\w+)\[(\d+)\]", sec)
    if m:
        base, idx = m.group(1), int(m.group(2))
        if base not in sections:
            return False, f"section '{base}' not present in gathered data"
        rows = data.get(base)
        if not isinstance(rows, list):
            return False, f"section '{base}' is not a list (cannot index '{sec}')"
        if idx < 1 or idx > len(rows):
            return False, (f"'{sec}' out of range (section '{base}' has "
                           f"{len(rows)} {'rows' if len(rows) != 1 else 'row'})")
        row = rows[idx - 1]
        if not isinstance(row, dict):
            return False, f"row {idx} of section '{base}' has no fields"
        if not fld:
            return True, "ok"
        if fld in row:
            return True, "ok"
        for v in row.values():
            if isinstance(v, str) and fld == v:
                return True, "ok"
        return False, f"field '{fld}' not found in {sec}"
    # Dot-index form: 'news.0.headline' (0-based) -- tolerated for robustness.
    dm = re.fullmatch(r"(\d+)(?:\.(.*))?", fld)
    if dm and sec in sections and isinstance(data.get(sec), list):
        idx = int(dm.group(1)) + 1  # 0-based -> row number
        subfld = dm.group(2) or ""
        rows = data[sec]
        if idx < 1 or idx > len(rows):
            return False, (f"'{sec}.{dm.group(1)}' out of range (section "
                           f"'{sec}' has {len(rows)} "
                           f"{'rows' if len(rows) != 1 else 'row'})")
        row = rows[idx - 1]
        if not isinstance(row, dict):
            return False, f"row {idx} of section '{sec}' has no fields"
        if not subfld:
            return True, "ok"
        if subfld in row:
            return True, "ok"
        for v in row.values():
            if isinstance(v, str) and subfld == v:
                return True, "ok"
        return False, f"field '{subfld}' not found in {sec}.{dm.group(1)}"
    if sec not in sections:
        return False, f"section '{sec}' not present in gathered data"
    val = data.get(sec)
    if not fld:
        return True, "ok"
    if isinstance(val, dict):
        return (fld in val,
                "ok" if fld in val else f"field '{fld}' not found in section '{sec}'")
    if isinstance(val, list):
        for i in val:
            if isinstance(i, dict):
                if fld in i:
                    return True, "ok"
                for v in i.values():
                    if isinstance(v, str) and fld == v:
                        return True, "ok"
        return False, f"'{fld}' not found in section '{sec}'"
    return False, f"'{fld}' not found in section '{sec}'"


def _grade_evidence(side: str, claims: List[Dict[str, Any]],
                    data: Dict[str, Any]) -> Dict[str, Any]:
    """Check every claim's evidence citation against the actual data.

    A claim is 'grounded' if its evidence string names a section that
    exists in the data (optionally section.field). Citations may be
    comma-separated (e.g. 'quote.c, fundamentals.price_target') -- the
    claim is grounded if ANY cited path resolves. Uncited or bogus
    citations are flagged -- this is the FINSABER/debate-or-vote lesson
    applied: an ungrounded claim contributes nothing to the debate.
    """
    graded = []
    sections = set(data.keys())
    for c in claims or []:
        ev = (c.get("evidence") or "").strip()
        if not ev:
            graded.append({"claim": c.get("claim", ""),
                           "evidence": "", "grounded": False,
                           "reason": "no evidence citation"})
            continue
        # Composite citations: grounded if ANY path resolves.
        parts = [p.strip() for p in ev.split(",") if p.strip()]
        results = [_evidence_grounded(p, data) for p in parts]
        ok = any(r[0] for r in results)
        reason = ("ok" if ok
                  else "; ".join(f"'{p}': {r[1]}"
                                 for p, r in zip(parts, results)))
        graded.append({"claim": c.get("claim", ""), "evidence": ev,
                       "grounded": ok, "reason": reason})
    grounded = sum(1 for g in graded if g["grounded"])
    return {
        "side": side,
        "n_claims": len(graded),
        "grounded": grounded,
        "ungrounded": len(graded) - grounded,
        "sections_cited": sorted({g["evidence"].split(",")[0].strip().split(".")[0]
                                  for g in graded if g["evidence"]}),
        "claims": graded,
    }


# ---------------------------------------------------------------------------
# Deterministic valuation (pure Python -- the LLM never writes numbers)
# ---------------------------------------------------------------------------

def _valuation(sym: str, data: Dict[str, Any],
               price: Optional[float]) -> Dict[str, Any]:
    """Deterministic valuation suite (pure Python -- the LLM never writes
    numbers). Input data comes ONLY from the gathered fundamentals dict
    (stockanalysis.com keyless scraper).

    Three independent anchors:
      1. P/E band      -- base EPS x (trailing P/E x 0.8 / 1.0 / 1.25)
      2. DCF-lite      -- 5-yr earnings-power value: base EPS projected at
                          a clamped growth rate, discounted at a beta-tilted
                          flat rate, exited at 0.9x the trailing multiple,
                          plus net cash per share.
      3. Scenario grid -- growth-scenario x P/E-band matrix whose base cell
                          is the headline fair value.

    Every input is logged; any missing input produces explicit N/A and the
    suite abstains (fair_value = None) rather than fabricate. Growth punches
    above a sane band or a missing growth forecast is clamped / held flat
    with a recorded note -- conservative, never invented.
    """
    out = {"sym": sym, "price": price, "deterministic": True,
           "inputs": {}, "outputs": {}, "notes": []}
    f = data.get("fundamentals") or {}

    def _put(label: str, val: Any):
        out["inputs"][label] = val

    # ---- raw inputs (logged verbatim; fractions for %-fields) ----
    eps_ttm = f.get("eps_ttm")
    eps_fwd = f.get("eps_forward")
    pe = f.get("pe_ttm")
    fwd_pe = f.get("forward_pe")
    eps_growth = f.get("eps_growth_yoy")      # 3Y forecast, decimal fraction
    rev_growth = f.get("revenue_growth_yoy")
    beta = f.get("beta")
    net_cash_ps = f.get("net_cash_per_share")
    roe = f.get("roe")
    roic = f.get("roic")
    debt_eq = f.get("debt_eq")
    fcf_margin = f.get("fcf_margin")
    _put("eps_ttm", eps_ttm)
    _put("eps_forward (consensus-derived)", eps_fwd)
    _put("pe_ttm", pe)
    _put("forward_pe", fwd_pe)
    _put("eps_growth_3y_fcst", eps_growth)
    _put("revenue_growth_3y_fcst", rev_growth)
    _put("beta", beta)
    _put("net_cash_per_share", net_cash_ps)

    # ---- quality signals (rendered as a compact row) ----
    q = {"roe": roe, "roic": roic, "debt_eq": debt_eq,
         "fcf_margin": fcf_margin, "beta": beta}
    out["outputs"]["quality_signals"] = {k: v for k, v in q.items()
                                         if v is not None}

    # ---- base EPS: trailing (ttm) is the projection base ----
    # Forward EPS already bakes in next-year growth; compounding it would
    # double-count, so it is only a fallback when ttm EPS is unavailable.
    base_eps = eps_ttm
    if base_eps is None and eps_fwd:
        base_eps = eps_fwd
        out["notes"].append("no trailing EPS on page; using consensus-derived "
                            "forward EPS as the projection base")
    if base_eps is None and pe and price:
        base_eps = price / pe
        out["notes"].append("no EPS on page; trailing EPS derived as "
                            "price / trailing P/E")
    # ---- valuation multiple: trailing P/E preferred, else forward P/E ----
    mult = pe or fwd_pe
    if base_eps is None or mult is None:
        out["outputs"]["fair_value"] = None
        out["outputs"]["peg"] = None
        out["notes"].append("no EPS and/or P/E available -- fair value NOT "
                            "computed (abstain, never fabricate)")
        return out
    base_eps = round(base_eps, 4)

    _put("base EPS used", base_eps)
    _put("valuation multiple (P/E) used", round(mult, 2))

    # ---- 1) P/E band ----
    bear_pe = round(mult * 0.8, 1)
    base_pe = round(mult, 1)
    bull_pe = round(mult * 1.25, 1)
    _put("P/E band (bear/base/bull)", f"{bear_pe} / {base_pe} / {bull_pe}")

    # ---- 2) DCF-lite (earnings-power value) ----
    # stockanalysis.com "EPS Growth Forecast (3Y)" is a CUMULATIVE 3-year
    # total, not a per-year CAGR (verified: eps_ttm*(1+G) ~= fwd_eps consensus
    # on MPC/TRGP/TGT/NFLX/AAPL). Convert to the per-year rate before use or
    # the 5-yr projection compounds a 3-yr total as if annual.
    g_raw = eps_growth if eps_growth is not None else rev_growth
    g = None
    if g_raw is not None:
        g = float(g_raw)
        if g > -1.0:
            g = (1.0 + g) ** (1.0 / 3.0) - 1.0   # cumulative-3Y -> CAGR
        else:
            g = -1.0  # absurd guard; clamped below anyway
    if g is None:
        g = 0.0
        out["notes"].append("no earnings/revenue growth forecast -- DCF-lite "
                            "holds EPS flat (conservative abstention on growth)")
    elif eps_growth is None:
        out["notes"].append("EPS growth forecast missing -- proxied by 3Y "
                            "revenue growth forecast (converted to CAGR)")
    else:
        out["notes"].append("3Y cumulative growth forecast converted to "
                            "per-year CAGR ((1+G)^(1/3)-1)")
    g = max(0.0, min(0.25, g))                 # clamp to a sane band (post-conversion)
    disc = 0.10
    if beta is not None:
        try:
            disc = max(0.07, min(0.14, 0.10 + (float(beta) - 1.0) * 0.02))
        except Exception:
            pass
    yrs = 5
    term_g = 0.025                              # conservative terminal growth
    exit_pe = max(8.0, mult * 0.9)              # 0.9x trailing multiple

    def _epv(growth: float, pe_exit: float) -> float:
        dcf_lite_growth = max(0.0, min(0.25, growth))  # grid cells may punch
        e = base_eps
        pv = 0.0
        for t in range(1, yrs + 1):
            e = base_eps * (1.0 + dcf_lite_growth) ** t
            pv += e / (1.0 + disc) ** t
        pv += (e * pe_exit) / (1.0 + disc) ** yrs
        if net_cash_ps:
            pv += net_cash_ps
        return pv

    dcf_fv = _epv(g, exit_pe)
    _put("DCF growth (5y)", round(g, 4))
    _put("DCF discount rate", round(disc, 4))
    _put("DCF exit P/E", round(exit_pe, 1))
    out["outputs"]["dcf_lite"] = {
        "method": "5-yr EPS power value discounted at beta-tilted flat rate, "
                  "terminal exit P/E + net cash/share",
        "growth_5y": round(g, 4),
        "discount_rate": round(disc, 4),
        "exit_pe": round(exit_pe, 1),
        "fair_value": round(dcf_fv, 2),
    }
    out["notes"].append("DCF-lite: growth clamped to [0%, 25%]; discount "
                        "10% base + 2pp per beta-unit above 1 (clamped "
                        "[7%,14%]); exit P/E 0.9x trailing; +net cash/share")

    # ---- 3) scenario grid: growth scenario x P/E band ----
    scen = {}
    for label, gp, pe_use in (("bear", g * 0.5, bear_pe),
                              ("base", g, base_pe),
                              ("bull", g * 1.5, bull_pe)):
        v = round(_epv(gp, pe_use), 2)
        cell = {"growth": round(gp, 4), "exit_pe": pe_use, "value": v}
        if price:
            cell["upside"] = round(v / price - 1.0, 3)
        scen[label] = cell
    out["outputs"]["scenario_grid"] = scen

    # ---- headline fair value = base grid cell ----
    base_fv = scen["base"]["value"]
    out["outputs"]["fair_value_basis"] = (
        "DCF-lite base scenario (5-yr EPS power value + net cash/share)")
    out["outputs"]["fair_value"] = {
        "bear": scen["bear"]["value"],
        "base": base_fv,
        "bull": scen["bull"]["value"],
    }
    if price:
        out["outputs"]["upside_base"] = round(base_fv / price - 1.0, 3)

    # ---- PEG (trailing P/E over annualized growth %) ----
    if g > 0 and pe:
        out["outputs"]["peg"] = round(pe / (g * 100), 2)
    else:
        out["outputs"]["peg"] = None

    return out


# ---------------------------------------------------------------------------
# The debate
# ---------------------------------------------------------------------------

def _run_researcher(side: str, sym: str, data: Dict[str, Any],
                    errors: List[str], strong: bool = True,
                    audit: Optional[Dict[str, Any]] = None) -> Optional[dict]:
    view = _data_view(sym, data, side)
    # .replace() not .format() -- the prompt contains literal JSON braces.
    return _llm_json(_RESEARCHER_SYSTEM.replace("{side}", side), view,
                     errors, label=f"{side}_researcher", strong=strong,
                     audit=audit)


def _run_rebuttal(side: str, opposing: Optional[dict], sym: str,
                  data: Dict[str, Any], errors: List[str],
                  audit: Optional[Dict[str, Any]] = None) -> Optional[dict]:
    if not opposing or not opposing.get("claims"):
        return None
    opp_claims = json.dumps(opposing.get("claims", []), ensure_ascii=False)
    view = _data_view(sym, data, side)
    user = (f"OPPOSING ({'bear' if side == 'bull' else 'bull'}) CLAIMS:\n"
            f"{opp_claims}\n\nDATA (same as before):\n{view}")
    # .replace() not .format() -- the prompt contains literal JSON braces.
    return _llm_json(_REBUTTAL_SYSTEM.replace("{side}", side), user, errors,
                     label=f"{side}_rebuttal", strong=False, audit=audit)


def _run_judge(sym: str, data: Dict[str, Any], price: Optional[float],
               bull: Optional[dict], bear: Optional[dict],
               rebuttals: Dict[str, Any], grading: Dict[str, Any],
               val: Dict[str, Any], errors: List[str],
               audit: Optional[Dict[str, Any]] = None) -> Optional[dict]:
    def _side_summary(side_result: Optional[dict], side: str) -> str:
        if not side_result:
            return f"{side}: (no output)"
        claims = "\n".join(
            f"- [{c.get('impact')}] {c.get('claim')} "
            f"(evidence: {c.get('evidence')})"
            for c in side_result.get("claims", []))
        return f"{side} (confidence {side_result.get('confidence')}):\n{claims}"

    rb = rebuttals.get("bull") or {}
    rbe = rebuttals.get("bear") or {}
    rebuttal_txt = (
        "Bull's answers to bear:\n" +
        ("\n".join(f"- {r.get('target_claim')} -> {r.get('response')}"
                   for r in rb.get("rebuttals", [])) or "(none)") +
        "\nBear's answers to bull:\n" +
        ("\n".join(f"- {r.get('target_claim')} -> {r.get('response')}"
                   for r in rbe.get("rebuttals", [])) or "(none)"))

    grading_txt = "\n".join(
        f"{g['side']}: {g['grounded']}/{g['n_claims']} claims grounded "
        f"(cited sections: {', '.join(g['sections_cited'])})"
        for g in grading.values() if isinstance(g, dict) and g.get("side"))

    user = (
        f"TICKER: {sym}\nPRICE: {price}\n\n"
        f"=== BULL CASE ===\n{_side_summary(bull, 'bull')}\n\n"
        f"=== BEAR CASE ===\n{_side_summary(bear, 'bear')}\n\n"
        f"=== REBUTTALS ===\n{rebuttal_txt}\n\n"
        f"=== EVIDENCE GRADING ===\n{grading_txt or '(no grading)'}\n\n"
        f"=== DETERMINISTIC VALUATION (computed in Python; do NOT alter) ===\n"
        f"{json.dumps(val, indent=1, default=str)}\n\n"
        f"Produce the final verdict JSON per your system rules."
    )
    return _llm_json(_JUDGE_SYSTEM, user, errors, label="judge", strong=True,
                     audit=audit)


# ---------------------------------------------------------------------------
# Risk-team review (post-judge gate -- the report's compliance layer)
# ---------------------------------------------------------------------------

_RATING_SCALE = ("BUY", "OVERWEIGHT", "HOLD", "UNDERWEIGHT", "SELL")


def _num0(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def _risk_checks(judge: Dict[str, Any], val: Dict[str, Any],
                 price: Optional[float]) -> Dict[str, Any]:
    """Rule-based compliance checks against the judge's verdict. Returns
    {"passed": bool, "checks": {name: {ok, detail}}} -- no LLM involved."""
    checks: Dict[str, Any] = {}

    # 1. base PT within +-25% of the deterministic base fair value
    fv = (val.get("outputs") or {}).get("fair_value") or {}
    base_fv = fv.get("base")
    sc = judge.get("scenarios") or {}
    base_pt = (sc.get("base") or {}).get("pt")
    if base_fv is not None and base_pt is not None:
        dev = abs(base_pt - base_fv) / base_fv
        checks["base_pt_within_25pct"] = {
            "ok": dev <= 0.25,
            "detail": (f"judge base PT {base_pt} vs deterministic base "
                       f"fair value {base_fv} (deviation {dev*100:.1f}%)"),
        }
    elif base_fv is None:
        checks["base_pt_within_25pct"] = {
            "ok": True,
            "detail": "no deterministic fair value (valuation abstained) "
                      "-- constraint not applicable",
        }
    else:
        checks["base_pt_within_25pct"] = {
            "ok": False,
            "detail": "judge produced no base-case price target",
        }

    # 2. probabilities sum to 1.0 (within tolerance)
    probs = [_num0((sc.get(k) or {}).get("prob")) for k in ("bull", "base", "bear")]
    if any((sc.get(k) or {}) for k in ("bull", "base", "bear")):
        total = sum(probs)
        checks["probs_sum_1"] = {
            "ok": abs(total - 1.0) <= 0.02,
            "detail": f"bull/base/bear probs sum to {total:.3f}",
        }
    else:
        checks["probs_sum_1"] = {"ok": False, "detail": "no scenarios present"}

    # 3. rating on the sanctioned scale
    rating = (judge.get("rating") or "").strip().upper()
    checks["rating_in_scale"] = {
        "ok": rating in _RATING_SCALE,
        "detail": f"rating '{judge.get('rating')}'" +
                  ("" if rating in _RATING_SCALE else f" not in {_RATING_SCALE}"),
    }

    # 4. conviction is a sane 0-1 probability
    conv = judge.get("conviction")
    checks["conviction_01"] = {
        "ok": conv is not None and 0.0 <= _num0(conv) <= 1.0,
        "detail": f"conviction {conv}",
    }
    return {"passed": bool(checks) and all(c["ok"] for c in checks.values()),
            "checks": checks}


def _run_risk_manager(sym: str, judge: Optional[Dict[str, Any]],
                      val: Dict[str, Any], price: Optional[float],
                      errors: List[str]) -> Dict[str, Any]:
    """Risk-team node: vets the judge's verdict against deterministic rules.

    architecture: research team proposes (bull/bear debate + judge),
    risk team disposes. The judge never writes final numbers -- the risk
    manager overrides price targets with the deterministic scenario grid
    whenever the judge's out-of-bound numbers would reach the page.

    Fail-closed contract: if the judge's verdict fails any hard check, the
    risk manager does NOT drop it silently -- it vetoes the offending
    numbers and substitutes the deterministic values (abstain-never-
    fabricate: a number on the page is either data-grounded or
    deterministically derived, never LLM-fabricated).
    """
    checks = _risk_checks(judge or {}, val, price)
    out = {"sym": sym, "verdict": "approved" if checks["passed"] else "vetoed",
           "checks": checks["checks"], "n_checks_passed": None, "n_checks": None}
    fv = (val.get("outputs") or {}).get("fair_value") or {}
    sc_vals = (val.get("outputs") or {}).get("scenario_grid") or {}
    n_pass = sum(1 for c in checks["checks"].values() if c["ok"])
    out["n_checks_passed"] = n_pass
    out["n_checks"] = len(checks["checks"])

    if checks["passed"]:
        out["override_applied"] = False
        out["reason"] = "all deterministic checks passed; judge verdict stands"
        return out

    # ---- veto: fail-closed fallback onto deterministic numbers ----
    out["override_applied"] = True
    violations = [name for name, c in checks["checks"].items() if not c["ok"]]
    out["reason"] = ("judge verdict failed checks: " + ", ".join(violations) +
                     ". Price targets overridden with the deterministic "
                     "scenario grid (abstain-never-fabricate); rating and "
                     "narrative left as judge proposed.")
    fixed_scenarios = {}
    jdg_sc = (judge or {}).get("scenarios") or {}
    if sc_vals or fv:
        for k, det in (("bull", sc_vals.get("bull")),
                       ("base", sc_vals.get("base")),
                       ("bear", sc_vals.get("bear"))):
            override_pt = (fv or {}).get(k) if not det else det.get("value")
            j = jdg_sc.get(k) or {}
            fixed_scenarios[k] = {
                "pt": _round2(override_pt) if override_pt is not None else j.get("pt"),
                "prob": j.get("prob") or (1.0 / 3.0),
                "thesis": j.get("thesis") or f"{k}-case (deterministic)",
            }
        out["override"] = {"scenarios": fixed_scenarios,
                           "basis": "deterministic P/E-band x scenario-grid fair values"}
    if judge is None:
        out["reason"] = "judge produced no verdict; risk team could not approve numbers"
    return out


def _round2(x: Any) -> Any:
    try:
        return round(float(x), 2)
    except Exception:
        return x


# ---------------------------------------------------------------------------
# Report writer (deterministic assembly -- no LLM numbers)
# ---------------------------------------------------------------------------

def _fmt_pct(x: Any) -> str:
    try:
        return f"{float(x) * 100:.1f}%"
    except Exception:
        return "n/a"


def _fmt_input(label: str, v: Any) -> str:
    """Display formatting for one valuation-input row (markdown table only).

    The JSON report keeps the verbatim value (full precision, f/audit); the
    markdown shows floats without binary-repr noise (0.030699999999999998)
    and renders rate/growth fractions as percents so the table reads like a
    human wrote it.
    """
    if v is None:
        return "n/a"
    if isinstance(v, float):
        if "growth" in label or "rate" in label or label.endswith("_fcst"):
            return f"{v * 100:.2f}%"
        return f"{v:.2f}"
    return str(v)


def _render_markdown(res: ReportResult) -> str:
    sym = res.sym
    val = res.valuation or {}
    judge = res.judge or {}
    rm = res.risk_manager or {}
    # Effective scenarios (research team proposes, risk team disposes): a
    # vetoed judge's price targets must never reach the page -- the headline
    # shows the deterministic override instead. Same contract as
    # report_view.effective_scenarios, which the portfolio builders rank on.
    if rm.get("override_applied") and (rm.get("override") or {}).get("scenarios"):
        sc = rm["override"]["scenarios"]
    else:
        sc = judge.get("scenarios") or {}
    L = ["# %s — Equity Research Report (agent debate)" % sym, ""]
    L.append(f"*Generated {res.generated_utc} UTC | "
             f"data sections: {', '.join(res.data_sections) or 'none'}*")
    L.append("")
    L.append("> Research only. Not financial advice. All numbers computed "
             "deterministically from gathered data; LLM writes no numbers.")
    L.append("")

    # --- Expected-return headline (current price -> predicted 1-yr price) ---
    base_pt = (sc.get("base") or {}).get("pt")
    exp_ret = ((base_pt / res.price - 1.0) if (base_pt and res.price) else None)
    L.append("## 1. Expected return (current → predicted 1-yr price)")
    L.append("")
    L.append("| Current price | Predicted price (12-mo) | Expected return |")
    L.append("|---|---|---|")
    price_str = f"{res.price:.2f}" if isinstance(res.price, (int, float)) else (res.price or 'n/a')
    L.append(f"| {price_str} | {base_pt or 'n/a'} | "
             f"**{_fmt_pct(exp_ret)}** |")
    L.append("")
    if exp_ret is None:
        L.append("> _No predicted 12-mo price is claimed: this name has no "
                 "forward-consensus EPS anchor in the free data, so the "
                 "valuation abstains (never fabricate). Expected return is "
                 "listed as n/a._")
        L.append("")
    elif base_pt == (res.price or 0):
        L.append("> _Predicted price = current price: the deterministic "
                 "trailing-EPS valuation is ambiguous on direction, so the "
                 "judge holds at spot. Treat as no edge signal._")
        L.append("")
    if sc:
        L.append("| Scenario | Prob | 12-mo PT | Thesis |")
        L.append("|---|---|---|---|")
        for k in ("bull", "base", "bear"):
            s = sc.get(k) or {}
            L.append(f"| {k} | {_fmt_pct(s.get('prob'))} | "
                     f"{s.get('pt', 'n/a')} | {(s.get('thesis') or '')[:100]} |")
        L.append("")

    # Rating & price targets
    L.append("## 2. Rating")
    L.append("")
    rating = judge.get("rating") or "n/a"
    conv = judge.get("conviction")
    L.append(f"| Rating | Conviction | Convergence |")
    L.append(f"|---|---|---|")
    L.append(f"| **{rating}** | {conv if conv is not None else 'n/a'} | "
             f"{'yes' if judge.get('convergence') else 'no'} |")
    L.append("")

    # Thesis
    if judge.get("decision_rationale"):
        L.append("## 3. Investment thesis")
        L.append("")
        L.append(judge["decision_rationale"])
        L.append("")

    # The debate
    L.append("## 4. The debate")
    L.append("")
    for side, sr in (("BULL", res.bull), ("BEAR", res.bear)):
        L.append(f"### {side} case")
        if not sr:
            L.append("_(no output)_")
            continue
        for c in sr.get("claims", []):
            L.append(f"- [{c.get('impact')}] {c.get('claim')} "
                     f"`{c.get('evidence')}`")
        L.append("")
    L.append("### Rebuttals")
    for side in ("bull", "bear"):
        rb = (res.rebuttals.get(side) or {}).get("rebuttals") or []
        L.append(f"**{side} answering the opposite side:**")
        if not rb:
            L.append("_(none)_")
        for r in rb:
            tag = "concede" if r.get("concede") else "rebut"
            L.append(f"- [{tag}] {r.get('target_claim')} → "
                     f"{r.get('response')} `{r.get('counter_evidence') or ''}`")
        L.append("")

    # Evidence grading
    L.append("## 5. Evidence grading (rule-based, against gathered data)")
    L.append("")
    for side in ("bull", "bear"):
        g = res.grading.get(side) or {}
        if not g:
            continue
        L.append(f"**{side}:** {g.get('grounded')}/{g.get('n_claims')} "
                 f"claims grounded | cited sections: "
                 f"{', '.join(g.get('sections_cited') or []) or 'none'}")
        for c in g.get("claims", []):
            mark = "✅" if c.get("grounded") else "⚠️"
            L.append(f"- {mark} {c.get('claim')} (`{c.get('evidence')}`) "
                     f"— {c.get('reason')}")
        L.append("")

    # Valuation
    L.append("## 6. Deterministic valuation (pure Python)")
    L.append("")
    L.append("| Input | Value |")
    L.append("|---|---|")
    for k, v in (val.get("inputs") or {}).items():
        L.append(f"| {k} | {_fmt_input(k, v)} |")
    L.append("")
    fv = (val.get("outputs") or {}).get("fair_value")
    if fv:
        up = (val.get("outputs") or {}).get("upside_base")
        L.append(f"| Fair value (bear/base/bull) | {fv['bear']} / "
                 f"{fv['base']} / {fv['bull']} |")
        L.append(f"| Implied upside to base | {_fmt_pct(up)} |")
    else:
        L.append("_Fair value not computed (insufficient data — abstain "
                 "rather than fabricate)._")
    L.append("")
    qs = (val.get("outputs") or {}).get("quality_signals") or {}
    L.append("PEG: %s | quality: ROE %s, ROIC %s, D/E %s, FCF margin %s" % (
        (val.get("outputs") or {}).get("peg") or "n/a",
        _fmt_pct(qs.get("roe")) if qs.get("roe") is not None else "n/a",
        _fmt_pct(qs.get("roic")) if qs.get("roic") is not None else "n/a",
        qs.get("debt_eq") if qs.get("debt_eq") is not None else "n/a",
        _fmt_pct(qs.get("fcf_margin")) if qs.get("fcf_margin") is not None else "n/a"))
    L.append("")
    for n in val.get("notes", []):
        L.append(f"- _note: {n}_")
    L.append("")

    # Risk-manager review (rule-based gate; research team proposes, risk team disposes)
    if rm:
        verdict = (rm.get("verdict") or "n/a").upper()
        n_pass = rm.get("n_checks_passed")
        n_tot = rm.get("n_checks")
        checks = rm.get("checks") or {}
        L.append("## 7. Risk manager review (rule-based gate)")
        L.append("")
        L.append("> _Research team proposes, risk team disposes. The risk manager "
                 "is a deterministic post-judge gate (no LLM call) that vets the "
                 "judge's numbers against the valuation and abstains-never-"
                 "fabricates: on veto it overrides price targets with the "
                 "deterministic scenario grid._")
        L.append("")
        outcome = ("judge verdict stands" if rm.get("override_applied") is False
                   else "overridden with deterministic scenario grid")
        L.append("| Verdict | Checks | Outcome |")
        L.append("|---|---|---|")
        L.append(f"| **{verdict}** | {n_pass}/{n_tot} passed | {outcome} |")
        L.append("")
        if checks:
            L.append("| Check | Result | Detail |")
            L.append("|---|---|---|")
            for name, c in checks.items():
                mark = "✅" if c.get("ok") else "❌"
                L.append(f"| {name} | {mark} | {c.get('detail') or ''} |")
            L.append("")
        if rm.get("reason"):
            L.append(f"Reason: {rm['reason']}")
            L.append("")
        if rm.get("override_applied"):
            ov = rm.get("override") or {}
            ov_sc = ov.get("scenarios") or {}
            L.append("**Override applied** (fail-closed):")
            L.append("")
            L.append("| Scenario | Override PT |")
            L.append("|---|---|")
            for k in ("bull", "base", "bear"):
                o = ov_sc.get(k) or {}
                L.append(f"| {k} | {o.get('pt', 'n/a')} |")
            L.append("")
            L.append(f"_Basis: {ov.get('basis') or 'n/a'}_")
            L.append("")

    # Catalysts & risks
    L.append("## 8. Catalysts & risks")
    L.append("")
    if judge.get("catalysts"):
        L.append("| Catalyst | Date | Impact |")
        L.append("|---|---|---|")
        for c in judge["catalysts"]:
            L.append(f"| {c.get('catalyst')} | {c.get('date')} | "
                     f"{c.get('impact')} |")
        L.append("")
    if judge.get("risks"):
        L.append("| Risk | Likelihood |")
        L.append("|---|---|")
        for r in judge["risks"]:
            L.append(f"| {r.get('risk')} | {r.get('likelihood')} |")
        L.append("")

    # Data appendix
    L.append("## 9. Data appendix")
    L.append("")
    for k in res.data_sections:
        L.append(f"- `{k}` — {_SECTION_LABELS.get(k, '')}")
    L.append("")
    L.append("## 10. Disclaimer")
    L.append("")
    L.append("Generated by the world-trader agent debate pipeline. "
             "Research only; not investment advice. Markets move fast — "
             "verify live prices and current filings before any decision.")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# Top level
# ---------------------------------------------------------------------------

def generate_report(sym: str, force: bool = False,
                    out_dir: str = DEFAULT_OUT_DIR) -> ReportResult:
    """Run the full debate and write an equity research report for `sym`.

    Skips (returns an empty ReportResult with an error note) if a report
    for the same day already exists, unless force=True.
    """
    t0 = time.time()
    res = ReportResult(sym=sym.upper(),
                       generated_utc=datetime.utcnow().isoformat(timespec="seconds") + "Z")
    os.makedirs(out_dir, exist_ok=True)
    today = datetime.utcnow().strftime("%Y-%m-%d")
    md_path = os.path.join(out_dir, f"{res.sym}_{today}.md")
    js_path = os.path.join(out_dir, f"{res.sym}_{today}.json")
    if not force and os.path.exists(md_path):
        res.errors.append(f"report for {res.sym} already exists for {today} "
                          f"(use force=True to regenerate)")
        res.elapsed_sec = time.time() - t0
        return res

    # 1. data
    data = _gather(res.sym)
    res.data_sections = [k for k in _SECTION_LABELS if k in data]
    price = None
    q = data.get("quote") or {}
    price = q.get("c") or q.get("price")
    res.price = price

    # 2. bull & bear (anti-sycophancy ordering)
    res.bull = _run_researcher("bull", res.sym, data, res.errors,
                               audit=res.audit)
    res.bear = _run_researcher("bear", res.sym, data, res.errors,
                               audit=res.audit)

    # 3. rebuttal round
    res.rebuttals["bear"] = _run_rebuttal("bear", res.bull, res.sym, data,
                                          res.errors, audit=res.audit)
    res.rebuttals["bull"] = _run_rebuttal("bull", res.bear, res.sym, data,
                                          res.errors, audit=res.audit)

    # 4. evidence grading (rule-based)
    if res.bull:
        res.grading["bull"] = _grade_evidence("bull", res.bull.get("claims"),
                                              data)
    if res.bear:
        res.grading["bear"] = _grade_evidence("bear", res.bear.get("claims"),
                                              data)

    # 5. deterministic valuation
    res.valuation = _valuation(res.sym, data, price)

    # 6. judge
    res.judge = _run_judge(res.sym, data, price, res.bull, res.bear,
                           res.rebuttals, res.grading, res.valuation,
                           res.errors, audit=res.audit)

    # 7. risk-team review (post-judge gate, rule-based -- fail-closed)
    res.risk_manager = _run_risk_manager(res.sym, res.judge, res.valuation,
                                         price, res.errors)

    # 8. write
    md = _render_markdown(res)
    with open(md_path, "w") as f:
        f.write(md)
    with open(js_path, "w") as f:
        json.dump(res.as_dict(), f, indent=2, default=str)
    res.report_path = md_path
    res.json_path = js_path
    res.elapsed_sec = round(time.time() - t0, 1)
    return res


def generate_watchlist(tickers: List[str], force: bool = False,
                       out_dir: str = DEFAULT_OUT_DIR) -> List[ReportResult]:
    """Generate reports for several tickers, sequentially (rate-safe)."""
    results = []
    for t in tickers:
        r = generate_report(t, force=force, out_dir=out_dir)
        results.append(r)
        status = "done" if r.report_path else ("skipped" if r.errors else "failed")
        print(f"[research-report] {t}: {status} "
              f"({r.elapsed_sec}s, errors={len(r.errors)})")
        if r.errors:
            for e in r.errors:
                print(f"    - {e}")
    return results


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(
        description="agent debate -> equity research report")
    ap.add_argument("sym", nargs="?", help="ticker to cover")
    ap.add_argument("--watchlist", default=None,
                    help="comma-separated tickers to cover in sequence")
    ap.add_argument("--force", action="store_true",
                    help="regenerate today's report if it exists")
    args = ap.parse_args()
    if args.watchlist:
        generate_watchlist([s.strip().upper() for s in
                            args.watchlist.split(",") if s.strip()])
    elif args.sym:
        r = generate_report(args.sym.upper(), force=args.force)
        print(json.dumps(r.as_dict(), indent=2, default=str))
        if r.report_path:
            print("\n---\nreport:", r.report_path)
    else:
        ap.print_help()
