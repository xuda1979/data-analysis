"""equity_fundamentals -- keyless fundamentals extractor for the equity research platform.

Deterministic data layer for the debate pipeline (M3). All numbers are computed
in Python from scraped pages -- the LLM writes prose only ("a writer, not a
knower"). Source: stockanalysis.com, keyless, rate-friendly, Mozilla UA.

Contracts
---------
* Every fetcher returns (data, err). On ANY failure the section is None and the
  error is described -- the pipeline guards each section and NEVER fabricates a
  number. A missing section is an abstention, not a hallucinated value.
* Price anchor comes from the panel cache (results/equity_research/panel/*.json,
  fresh 2026-11-10 close) instead of live Yahoo (HTTP 429).
* Parsing is row-based: each <tr> contributes label/value pairs after script and
  style removal, so linked labels (price targets, analyst ratings) parse fine.

Data availability (verified live 2026-11-10, AAPL):
  main page (https://stockanalysis.com/stocks/{sym}/)        -> 18 fields
  /statistics/ page (https://stockanalysis.com/stocks/{sym}/statistics/) -> 109 fields
"""
from __future__ import annotations

import datetime as _dt
import json as _json
import os as _os
import re as _re
import time as _time

from ..core import http_get, describe_err

try:
    import html as _H
except Exception:  # pragma: no cover
    _H = None

_BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

_PORTAL_RE = _re.compile("\u7528\u6237\u8ba4\u8bc1\u7cfb\u7edf|\u8ba4\u8bc1\u7cfb\u7edf|\u4e2a\u4eba\u8ba4\u8bc1|\u767b\u5f55\u9a8c\u8bc1")

_MAIN_URL = "https://stockanalysis.com/stocks/{sym}/"
_STATS_URL = "https://stockanalysis.com/stocks/{sym}/statistics/"

# ---------------------------------------------------------------------------
# Resilient fetch (same flaky-proxy caveat as altdata3/4/5)
# ---------------------------------------------------------------------------
def _clean_get(url, *, timeout=20, retries=3):
    """Fetch page text; returns (html_or_None, err_or_None)."""
    last_err = None
    for attempt in range(retries):
        try:
            txt = http_get(url, headers={"User-Agent": _BROWSER_UA}, timeout=timeout)
            if _PORTAL_RE.search(txt):
                last_err = "captive-portal"
                _time.sleep(0.5 * (attempt + 1))
                continue
            return txt, None
        except Exception as e:
            last_err = describe_err(e)
            _time.sleep(0.5 * (attempt + 1))
    return None, last_err


# ---------------------------------------------------------------------------
# Row-based label/value parser
# ---------------------------------------------------------------------------
def _cell_text(c):
    c = _re.sub(r"<[^>]+>", " ", c)
    if _H:
        c = _H.unescape(c)
    return _re.sub(r"\s+", " ", c).strip()


def parse_rows(html):
    """Parse <tr> rows into {label: value}. Verified: 18 fields on main page,
    109 on /statistics/ page."""
    html = _re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=_re.S | _re.I)
    html = _re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=_re.S | _re.I)
    rows = _re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=_re.S)
    out = {}
    for r in rows:
        tds = _re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, flags=_re.S)
        if len(tds) >= 2:
            lab = _cell_text(tds[0])
            val = _cell_text(" ".join(tds[1:]))
            if lab and val and lab not in out and len(lab) < 60 and len(val) < 120:
                out[lab] = val
    return out


_NUM_RE = _re.compile(r"[-+]?\d[\d,]*\.?\d*")


def _num(x):
    """Best-effort number extraction from a stats string (e.g. '1.23B', '-4.5%', '$344.62').

    Returns the raw magnitude; percentages and letter-suffix magnitudes are
    resolved here. Callers that want a decimal fraction apply /100 themselves
    (see _pct) so they are not double-divided.
    """
    if x is None:
        return None
    s = str(x)
    # currency markers may sit between a minus sign and the digits
    # ('-$76.56'); strip them so the regex captures the sign itself.
    for sym in ("$", "€", "£", "¥"):
        s = s.replace(sym, "")
    m = _NUM_RE.search(s)
    if not m:
        return None
    try:
        v = float(m.group(0).replace(",", ""))
    except ValueError:
        return None
    mag = s[m.end():]
    # 'x' ratio markers are informational only; percentages resolved by _pct
    if "T" in mag.upper():
        v *= 1e12
    elif "B" in mag.upper():
        v *= 1e9
    elif "M" in mag.upper():
        v *= 1e6
    elif "K" in mag.upper():
        v *= 1e3
    # negative sign lives before the number already
    if "%" in s:
        v = v / 100.0
    return v


def _pct(x):
    """Parse a percent string ('12.3%') into a decimal fraction; None if absent."""
    if x is None:
        return None
    v = _num(x)
    if v is None:
        return None
    if "%" in str(x):
        return v  # _num already divided by 100
    return v


# ---------------------------------------------------------------------------
# Fundamentals extraction from parsed label/value dicts
# ---------------------------------------------------------------------------
def extract_fundamentals(main, stats):
    """Merge main + statistics page dicts into a normalized dict of section data.

    All numbers are Python-parsed and unit-normalized; missing values are None
    (abstention) -- never fabricated.
    """
    get = lambda k: stats.get(k) or main.get(k)  # noqa: E731

    # ---- PE / valuation anchors ----------------------------------------
    pe = _num(get("PE Ratio"))
    fwd_pe = _num(get("Forward PE"))
    peg = _num(get("PEG Ratio"))
    ps = _num(get("PS Ratio"))
    pb = _num(get("PB Ratio"))
    pfcf = _num(get("P/FCF Ratio"))

    # ---- price ----------------------------------------------------------
    price = _num(get("Price")) or _num(get("Previous Close")) or _num(get("Open"))

    # ---- per-share anchors ---------------------------------------------
    diluted_eps_ttm = _num(get("Earnings Per Share (EPS)"))
    fwd_eps = None
    # Forward EPS not on page; derive from Forward PE
    if fwd_pe and price:
        fwd_eps = price / fwd_pe
    fcf_ps = _num(get("FCF Per Share"))
    book_value_share = _num(get("Book Value Per Share"))
    revenue_share = _num(get("Revenue / Share"))
    cash_total = _num(get("Cash & Marketable Securities"))
    net_cash_ps = _num(get("Net Cash Per Share"))
    shares_out = _num(get("Shares Outstanding")) or _num(get("Shares Float"))
    cash_share = (cash_total / shares_out) if (cash_total and shares_out) else net_cash_ps

    # fallback EPS from PE
    if diluted_eps_ttm is None and pe and price:
        diluted_eps_ttm = price / pe

    # ---- margins / profitability (percent strings on stats page) --------
    roe = _pct(get("Return on Equity (ROE)"))
    roa = _pct(get("Return on Assets (ROA)"))
    roic = _pct(get("Return on Invested Capital (ROIC)"))
    roce = _pct(get("Return on Capital Employed (ROCE)"))
    gross_margin = _pct(get("Gross Margin"))
    oper_margin = _pct(get("Operating Margin"))
    profit_margin = _pct(get("Profit Margin"))
    fcf_margin = _pct(get("FCF Margin"))
    ebitda_margin = _pct(get("EBITDA Margin"))
    pretax_margin = _pct(get("Pretax Margin"))

    # ---- growth ---------------------------------------------------------
    rev_growth_yoy = _pct(get("Revenue Growth Forecast (3Y)"))
    eps_growth_yoy = _pct(get("EPS Growth Forecast (3Y)"))

    # ---- cash / debt ----------------------------------------------------
    cash = _num(get("Cash & Marketable Securities"))
    debt = _num(get("Total Debt"))
    debt_eq = _num(get("Debt / Equity"))
    fcf = _num(get("Free Cash Flow"))
    ocf = _num(get("Operating Cash Flow"))
    capex = _num(get("Capital Expenditures"))
    net_cash = _num(get("Net Cash"))
    net_cash_ps = _num(get("Net Cash Per Share"))

    # ---- market data ----------------------------------------------------
    mcap = _num(get("Market Cap"))
    shares_out = _num(get("Shares Outstanding")) or _num(get("Shares Float"))
    beta = _num(get("Beta (5Y)")) or _num(get("Beta"))
    short_int_pct_float = _pct(get("Short % of Float")) or _pct(get("Short % of Shares Out"))
    short_ratio = _num(get("Short Ratio (days to cover)")) or _num(get("Short Ratio"))
    high_52w = _num(get("52-Week High"))
    low_52w = _num(get("52-Week Low"))
    price_target = _num(get("Price Target"))
    analyst_rec = get("Analyst Consensus")
    rev_ttm = _num(get("Revenue"))
    net_income_ttm = _num(get("Net Income"))
    oper_income_ttm = _num(get("Operating Income"))
    ebitda = _num(get("EBITDA"))
    div_yield = _pct(get("Dividend Yield"))
    div_ps = _num(get("Dividend Per Share"))
    payout = _pct(get("Payout Ratio"))
    fcf_yield = _pct(get("FCF Yield"))
    earnings_yield = _pct(get("Earnings Yield"))
    ev = _num(get("Enterprise Value"))
    ev_ebitda = _num(get("EV / EBITDA"))
    peg = peg or _num(get("PEG Ratio"))

    return {
        "price": price,
        "market_cap": mcap,
        "enterprise_value": ev,
        "pe_ttm": pe,
        "forward_pe": fwd_pe,
        "peg": peg,
        "ps_ttm": ps,
        "pb": pb,
        "pfcf": pfcf,
        "ev_ebitda": ev_ebitda,
        "eps_ttm": diluted_eps_ttm,
        "eps_forward": fwd_eps,
        "fcf_per_share": fcf_ps,
        "revenue_per_share": revenue_share,
        "cash_per_share": cash_share,
        "book_value_per_share": book_value_share,
        "roe": roe,
        "roa": roa,
        "roic": roic,
        "roce": roce,
        "gross_margin": gross_margin,
        "operating_margin": oper_margin,
        "profit_margin": profit_margin,
        "fcf_margin": fcf_margin,
        "ebitda_margin": ebitda_margin,
        "pretax_margin": pretax_margin,
        "revenue_growth_yoy": rev_growth_yoy,
        "eps_growth_yoy": eps_growth_yoy,
        "fcf": fcf,
        "ocf": ocf,
        "capex": capex,
        "cash": cash,
        "debt": debt,
        "net_cash": net_cash,
        "net_cash_per_share": net_cash_ps,
        "debt_eq": debt_eq,
        "beta": beta,
        "short_interest_pct_float": short_int_pct_float,
        "short_ratio": short_ratio,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "price_target": price_target,
        "analyst_recommendation": analyst_rec,
        "revenue_ttm": rev_ttm,
        "net_income_ttm": net_income_ttm,
        "operating_income_ttm": oper_income_ttm,
        "ebitda": ebitda,
        "dividend_yield": div_yield,
        "dividend_per_share": div_ps,
        "payout_ratio": payout,
        "fcf_yield": fcf_yield,
        "earnings_yield": earnings_yield,
        "shares_outstanding": shares_out,
        "source": "stockanalysis.com (keyless)",
        "fetched_at": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }
    mcap = _num(get("Market Cap"))
    shares_out = _num(get("Shares Outstanding")) or _num(get("Shares Float"))
    beta = _num(get("Beta"))
    short_int = _pct(get("Short Interest")) if get("Short Interest") else None
    short_ratio = _num(get("Short Ratio"))
    high_52w = _num(get("52-Week High"))
    low_52w = _num(get("52-Week Low"))
    price_target = _num(get("Price Target"))
    analyst_rec = get("Analyst Recommendation")
    rev_ttm = _num(get("Revenue (TTM)"))
    net_income_ttm = _num(get("Net Income (TTM)"))
    oper_income_ttm = _num(get("Operating Income (TTM)"))
    div_yield = _pct(get("Dividend Yield"))
    payout = _num(get("Payout Ratio"))

    return {
        "price": price,
        "market_cap": mcap,
        "pe_ttm": pe,
        "forward_pe": fwd_pe,
        "peg": peg,
        "ps_ttm": ps,
        "pb": pb,
        "eps_ttm": diluted_eps_ttm,
        "eps_forward": fwd_eps,
        "eps_basic": eps_basic,
        "revenue_per_share": revenue_share,
        "cash_per_share": cash_share,
        "book_value_per_share": book_value_share,
        "roe": roe,
        "roa": roa,
        "roic": roic,
        "roce": roce,
        "gross_margin": gross_margin,
        "operating_margin": oper_margin,
        "profit_margin": profit_margin,
        "fcf_margin": fcf_margin,
        "revenue_growth_yoy": rev_growth_yoy,
        "eps_growth_yoy": eps_growth_yoy,
        "fcf": fcf,
        "ocf": ocf,
        "cash": cash,
        "debt": debt,
        "debt_eq": debt_eq,
        "beta": beta,
        "short_interest": short_int,
        "short_ratio": short_ratio,
        "high_52w": high_52w,
        "low_52w": low_52w,
        "price_target": price_target,
        "analyst_recommendation": analyst_rec,
        "revenue_ttm": rev_ttm,
        "net_income_ttm": net_income_ttm,
        "operating_income_ttm": oper_income_ttm,
        "dividend_yield": div_yield,
        "payout_ratio": payout,
        "shares_outstanding": shares_out,
        "source": "stockanalysis.com (keyless)",
        "fetched_at": _dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def fundamentals(sym, *, cache=None, cache_dir=None, force=False):
    """Fetch and normalize fundamentals for a ticker.

    cache: optional in-memory dict {sym: fundamentals} to short-circuit.
    cache_dir: optional directory for a persistent JSON cache (one file per
        ticker, {SYM}.json). Writes on successful fetch so a 60-ticker run
        never re-pays the ~10-15s page fetch cost on re-runs.
    force: bypass disk cache and refetch.
    Returns (data_or_None, err_or_None). Both parse failures propagate as
    errors (fail-loud for the data layer, never silent fabrication).
    """
    if cache and sym in cache:
        return cache[sym], None
    if cache_dir is not None and not force:
        try:
            p = _os.path.join(cache_dir, f"{sym.upper()}.json")
            with open(p) as _f:
                cached = _json.load(_f)
            if cache is not None:
                cache[sym] = cached
            return cached, None
        except Exception:
            pass  # cache miss / corrupt entry -> refetch
    main_txt, e1 = _clean_get(_MAIN_URL.format(sym=sym))
    stats_txt, e2 = _clean_get(_STATS_URL.format(sym=sym))
    if main_txt is None and stats_txt is None:
        return None, f"both pages failed: main={e1 or '?'} stats={e2 or '?'}"
    main = parse_rows(main_txt) if main_txt else {}
    stats = parse_rows(stats_txt) if stats_txt else {}
    if not main and not stats:
        return None, "no rows parsed from either page"
    out = extract_fundamentals(main, stats)
    if cache is not None:
        cache[sym] = out
    if cache_dir is not None:
        try:
            _os.makedirs(cache_dir, exist_ok=True)
            with open(_os.path.join(cache_dir, f"{sym.upper()}.json"), "w") as _f:
                _json.dump(out, _f)
        except Exception:
            pass  # cache write failure never aborts a fetch
    return out, None


# ---------------------------------------------------------------------------
# Panel price anchors (results/equity_research/panel/{SYM}.json)
# ---------------------------------------------------------------------------
def panel_price(sym, panel_dir=None):
    """Last close from the panel cache. Returns (price, date_str) or (None, None)."""
    import os
    if panel_dir is None:
        # repo root: tools/ -> repo root
        panel_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__))))),
            "results", "equity_research", "panel")
    p = os.path.join(panel_dir, f"{sym.upper()}.json")
    try:
        with open(p) as f:
            d = _json.load(f)
        closes = d.get("adjclose") or d.get("close")
        dates = d.get("dates") or d.get("date")
        if not closes:
            return None, None
        last = closes[-1]
        date = dates[-1] if dates else None
        return last, date
    except Exception:
        return None, None


if __name__ == "__main__":
    import sys
    sym = (sys.argv[1] if len(sys.argv) > 1 else "AAPL").upper()
    f, err = fundamentals(sym)
    if err:
        print("ERROR:", err)
        sys.exit(1)
    print(json.dumps(f, indent=1, default=str))
