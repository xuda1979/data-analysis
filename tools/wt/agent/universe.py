"""Deterministic top-30 / bottom-30 US equity universe selector.

Milestone #2 of the 2026-11-10 platform goal. WHY: the 60-report run needs a
*reproducible* universe, not an LLM's pick. Ranking is pure Python on real
prices ("the LLM is a writer, not a knower" -- RESEARCH_NOTES.md 2026-08-22).

Pipeline (stdlib-only, consistent with tools/wt conventions):

  S&P 500 constituents (Wikipedia, cached)  ->  Yahoo v8 daily bars
  (cached per-symbol on disk, resumable)    ->  momentum/Sharpe/liquidity
  stats                                     ->  combined rank score
                                            ->  pinned WATCHLIST.json

Determinism contract:
  - Score = 0.5 * cross-sectional percentile rank(12-mo momentum)
          + 0.5 * cross-sectional percentile rank(annualized Sharpe)
    computed on each symbol's trailing window (>= MIN_BARS valid bars ending
    at that symbol's last bar). Ties broken by symbol (A-Z) so the artifact
    is byte-reproducible for the same panel cache.
  - Filters (fail-closed, symbol excluded, reason recorded):
      data    -- fewer than MIN_BARS valid bars
      liquid  -- median daily dollar volume < MIN_DOLLAR_VOL
      stale   -- last bar older than MAX_STALE_DAYS vs the panel's freshest bar
  - rf = 0 for the Sharpe rank (documented: ranking statistic, not a
    performance claim; consistent with repo policy against synthetic PnL).

Data source: Yahoo Finance v8 chart endpoint, keyless, exact UA
"Mozilla/5.0 (X11; Linux x86_64)" (the only UA verified working from this
machine, 2026-11-10; same endpoint wrapped by world_trader/sources/eod.py,
admission status: evaluated-only source). Panel cache files record the fetch
date; a same-day cache is reused, so a killed run resumes.

Usage:
  python3 tools/wt/agent/universe.py            # fetch panel + select
  python3 tools/wt/agent/universe.py select     # select from existing cache
  python3 tools/wt/agent/universe.py fetch      # fetch/refresh panel only
  python3 tools/wt/agent/universe.py --top 30 --bottom 30

This is research tooling, not financial advice.
"""
from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request

# Allow direct execution: python3 tools/wt/agent/universe.py
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from wt import core  # noqa: E402

# ------------------------------------------------------------------ config
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
OUT_DIR = os.path.join(REPO_ROOT, "results", "equity_research")
PANEL_DIR = os.path.join(OUT_DIR, "panel")
WATCHLIST_PATH = os.path.join(OUT_DIR, "WATCHLIST.json")

WIKI_URL = ("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")
YAHOO_BASE = "https://query1.finance.yahoo.com/v8/finance/chart"
YAHOO_UA = "Mozilla/5.0 (X11; Linux x86_64)"   # exact UA verified 2026-11-10

MIN_BARS = 200          # valid daily bars required in the window
WINDOW_BARS = 252       # trailing window length (trading days)
MIN_DOLLAR_VOL = 20e6   # median daily (close * volume) dollar floor
MAX_STALE_DAYS = 5      # calendar days vs freshest panel bar
FETCH_SLEEP = 1.2       # seconds between Yahoo calls (rate-safe)
RETRY_429_SLEEP = 45    # backoff when rate-limited

SP500_CACHE = os.path.join(PANEL_DIR, "_sp500.json")
PANEL_TTL_DAYS = 1      # same-day cache is reused


# ------------------------------------------------------------------ helpers
def _yahoo_symbol(sym: str) -> str:
    """Wikipedia dot notation -> Yahoo dash notation (BRK.B -> BRK-B)."""
    return sym.replace(".", "-")


def _http_get(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": YAHOO_UA,
                                               "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


# ------------------------------------------------------------- constituents
def fetch_sp500(force: bool = False) -> list:
    """Return [(symbol, name)], cached same-day. Raises on fetch/parse failure."""
    cached = _read_json(SP500_CACHE)
    if cached and not force and cached.get("date") == _today():
        return [(r[0], r[1]) for r in cached["rows"]]
    raw = _http_get(WIKI_URL)
    table = raw.split("<table", 2)[1]
    rows = []
    for chunk in re.split(r"<tr[^>]*>", table)[1:]:
        cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", chunk, re.S)
        if len(cells) < 2:
            continue
        sym = re.sub(r"<[^>]+>", "", cells[0]).strip()
        name = re.sub(r"<[^>]+>", "", cells[1]).strip()
        sym, name = html.unescape(sym), html.unescape(name)
        if re.fullmatch(r"[A-Z]{1,5}(\.[A-Z]{1,2})?", sym):
            rows.append([sym, name])
    if len(rows) < 400:
        raise RuntimeError(f"S&P 500 parse suspicious: only {len(rows)} rows")
    os.makedirs(PANEL_DIR, exist_ok=True)
    _write_json(SP500_CACHE, {"date": _today(), "rows": rows})
    return [(r[0], r[1]) for r in rows]


# ------------------------------------------------------------------- panel
def _read_json(path: str):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _write_json(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def fetch_panel(symbol: str, force: bool = False) -> dict:
    """Fetch (or reuse same-day cache of) daily bars for one symbol.

    Returns {date, yahoo_sym, dates[], close[], adjclose[], volume[]}
    with None entries dropped (only bars where close and adjclose are both
    present are kept). Raises on HTTP/schema failure (fail loud -- the
    selector records the exclusion reason instead of guessing).
    """
    ysym = _yahoo_symbol(symbol)
    cache_path = os.path.join(PANEL_DIR, f"{ysym}.json")
    cached = _read_json(cache_path)
    if cached and not force and cached.get("date") == _today():
        return cached

    end = int(time.time())
    start = end - 370 * 86400   # 370 calendar days covers 252 trading days
    url = (f"{YAHOO_BASE}/{ysym}?period1={start}&period2={end}"
           f"&interval=1d&events=div,split")
    for attempt in (1, 2, 3):
        try:
            doc = json.loads(_http_get(url))
            break
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 3:
                print(f"  [panel] {ysym}: HTTP 429, backing off "
                      f"{RETRY_429_SLEEP}s", flush=True)
                time.sleep(RETRY_429_SLEEP)
                continue
            raise
    result = ((doc.get("chart") or {}).get("result") or [None])[0]
    if not result or (result.get("meta") or {}).get("symbol", "").upper() != ysym.upper():
        raise RuntimeError(f"empty/invalid chart payload for {ysym}")
    ts = result.get("timestamp") or []
    quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
    adj = ((result.get("indicators") or {}).get("adjclose") or [{}])[0]
    adjclose = adj.get("adjclose") or []
    dates, closes, adjcloses, volumes = [], [], [], []
    for i, raw_ts in enumerate(ts):
        c = (quote.get("close") or [None] * len(ts))[i]
        a = adjclose[i] if i < len(adjclose) else None
        if c is None or a is None:
            continue
        d = dt.datetime.fromtimestamp(raw_ts, dt.timezone.utc).date().isoformat()
        dates.append(d)
        closes.append(float(c))
        adjcloses.append(float(a))
        v = (quote.get("volume") or [None] * len(ts))[i]
        volumes.append(float(v) if v is not None else 0.0)
    payload = {"date": _today(), "yahoo_sym": ysym, "dates": dates,
               "close": closes, "adjclose": adjcloses, "volume": volumes}
    os.makedirs(PANEL_DIR, exist_ok=True)
    _write_json(cache_path, payload)
    return payload


def fetch_all_panel(constituents, force: bool = False) -> dict:
    """Fetch panel for every constituent. Returns {symbol: status-string}."""
    statuses = {}
    ok = 0
    for idx, (sym, _name) in enumerate(constituents, 1):
        try:
            p = fetch_panel(sym, force=force)
            statuses[sym] = f"ok({len(p['dates'])} bars)"
            ok += 1
        except Exception as e:  # noqa: BLE001 -- record and continue
            statuses[sym] = f"error: {core.describe_err(e) if isinstance(e, (urllib.error.URLError, urllib.error.HTTPError, TimeoutError)) else str(e)[:80]}"
        if idx % 25 == 0 or idx == len(constituents):
            print(f"[panel] {idx}/{len(constituents)} fetched, {ok} ok", flush=True)
        if sym != constituents[-1][0]:
            time.sleep(FETCH_SLEEP)
    return statuses


# ------------------------------------------------------------------ stats
def compute_stats(panel: dict) -> dict:
    """Deterministic per-symbol stats from a panel payload.

    Window: last WINDOW_BARS adjclose bars. Returns {} if data-quality
    filter fails (reason in the 'excluded' key).
    """
    adj = panel["adjclose"]
    closes = panel["close"]
    vols = panel["volume"]
    dates = panel["dates"]
    if len(adj) < MIN_BARS:
        return {"excluded": f"data: only {len(adj)} valid bars < {MIN_BARS}"}
    w_adj = adj[-WINDOW_BARS:]
    w_close = closes[-WINDOW_BARS:]
    w_vol = vols[-WINDOW_BARS:]
    w_dates = dates[-WINDOW_BARS:]

    momentum = w_adj[-1] / w_adj[0] - 1.0
    rets = [(w_adj[i] / w_adj[i - 1] - 1.0) for i in range(1, len(w_adj))]
    sd = statistics.pstdev(rets) if len(rets) > 2 else 0.0
    sharpe = (statistics.fmean(rets) / sd * (252 ** 0.5)) if sd > 0 else 0.0
    vol_ann = sd * (252 ** 0.5)
    dollar_vol = statistics.median([c * v for c, v in zip(w_close, w_vol)])
    if dollar_vol < MIN_DOLLAR_VOL:
        return {"excluded": (f"liquid: median dollar vol "
                             f"${dollar_vol:,.0f} < ${MIN_DOLLAR_VOL:,.0f}")}
    # max drawdown on the adjusted series (context stat for reports)
    peak, mdd = w_adj[0], 0.0
    for a in w_adj:
        peak = max(peak, a)
        mdd = min(mdd, a / peak - 1.0)
    return {
        "last_date": w_dates[-1],
        "last_close": round(w_close[-1], 4),
        "momentum_12m": round(momentum, 6),
        "sharpe_ann": round(sharpe, 4),
        "vol_ann": round(vol_ann, 4),
        "max_dd_12m": round(mdd, 4),
        "dollar_vol_median": round(dollar_vol, 0),
        "bars": len(w_adj),
    }


def _pct_ranks(values: dict) -> dict:
    """Average-rank percentiles in [0,1]; missing keys excluded. Deterministic.

    Sorts keys by VALUE ascending (not alphabetically) before assigning
    ranks, so the best performer gets the highest percentile. The tie
    groupings below rely on equal values being adjacent after this sort.
    """
    keys = sorted(values, key=values.get)
    n = len(keys)
    if n <= 1:
        return {k: 0.5 for k in keys}
    # average ranks for ties
    ranks = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and values[keys[j + 1]] == values[keys[i]]:
            j += 1
        avg = (i + j) / 2.0
        for k in keys[i:j + 1]:
            ranks[k] = avg
        i = j + 1
    return {k: ranks[k] / (n - 1) for k in keys}


def select(top_n: int = 30, bottom_n: int = 30,
           constituents=None) -> dict:
    """Compute the pinned watchlist artifact from the panel cache.

    Returns the artifact dict (also written to WATCHLIST_PATH).
    """
    if constituents is None:
        constituents = fetch_sp500()
    names = {s: n for s, n in constituents}
    stats, excluded = {}, {}
    for sym, _name in constituents:
        panel = _read_json(os.path.join(PANEL_DIR, f"{_yahoo_symbol(sym)}.json"))
        if not panel:
            excluded[sym] = "no panel cache"
            continue
        st = compute_stats(panel)
        if "excluded" in st:
            excluded[sym] = st["excluded"]
        else:
            stats[sym] = st
    if not stats:
        raise RuntimeError("no symbols passed filters -- run fetch first")

    freshest = max(s["last_date"] for s in stats.values())
    fresh_d = dt.date.fromisoformat(freshest)
    for sym in list(stats):
        last = dt.date.fromisoformat(stats[sym]["last_date"])
        if (fresh_d - last).days > MAX_STALE_DAYS:
            excluded[sym] = (f"stale: last bar {stats[sym]['last_date']} vs "
                             f"freshest {freshest}")
            del stats[sym]

    rank_mom = _pct_ranks({s: v["momentum_12m"] for s, v in stats.items()})
    rank_sh = _pct_ranks({s: v["sharpe_ann"] for s, v in stats.items()})
    for s, v in stats.items():
        v["rank_momentum"] = round(rank_mom[s], 4)
        v["rank_sharpe"] = round(rank_sh[s], 4)
        v["score"] = round(0.5 * rank_mom[s] + 0.5 * rank_sh[s], 4)

    order = sorted(stats, key=lambda s: (-stats[s]["score"], s))
    top = order[:top_n]
    bottom = sorted(order[-bottom_n:], key=lambda s: (stats[s]["score"], s))

    artifact = {
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "as_of": freshest,
        "methodology": {
            "universe": "S&P 500 constituents (Wikipedia, fetch-dated)",
            "window": f"trailing {WINDOW_BARS} trading days, adjusted close",
            "score": "0.5*pct_rank(momentum_12m) + 0.5*pct_rank(sharpe_ann, rf=0)",
            "filters": {"min_bars": MIN_BARS,
                        "min_dollar_vol_median": MIN_DOLLAR_VOL,
                        "max_stale_days": MAX_STALE_DAYS},
            "tie_break": "symbol A-Z",
            "source": "Yahoo v8 chart (evaluated-only, UA-pinned), panel cache "
                      "in results/equity_research/panel/",
        },
        "counts": {"constituents": len(constituents), "scored": len(stats),
                   "excluded": len(excluded)},
        "top": [{"sym": s, "name": names.get(s, ""), **stats[s]} for s in top],
        "bottom": [{"sym": s, "name": names.get(s, ""), **stats[s]} for s in bottom],
        "excluded_detail": excluded,
    }
    _write_json(WATCHLIST_PATH, artifact)
    return artifact


# --------------------------------------------------------------------- CLI
def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    top_n = int(argv[argv.index("--top") + 1]) if "--top" in argv else 30
    bottom_n = int(argv[argv.index("--bottom") + 1]) if "--bottom" in argv else 30
    cmd = next((a for a in argv if a in ("fetch", "select")), "all")

    constituents = fetch_sp500()
    print(f"[universe] {len(constituents)} S&P 500 constituents "
          f"(cache {SP500_CACHE})")
    if cmd in ("fetch", "all"):
        statuses = fetch_all_panel(constituents)
        errs = {s: v for s, v in statuses.items() if v.startswith("error")}
        print(f"[universe] panel fetch done, {len(errs)} errors")
        for s, v in sorted(errs.items())[:20]:
            print(f"    {s}: {v}")
    if cmd in ("select", "all"):
        art = select(top_n=top_n, bottom_n=bottom_n, constituents=constituents)
        print(f"[universe] watchlist as_of {art['as_of']}: "
              f"{art['counts']['scored']} scored, "
              f"{art['counts']['excluded']} excluded")
        print(f"[universe] TOP {top_n}:")
        for r in art["top"]:
            print(f"    {r['sym']:6s} score={r['score']:.3f} "
                  f"mom={r['momentum_12m']:+.1%} sharpe={r['sharpe_ann']:+.2f} "
                  f"${r['last_close']:.2f}")
        print(f"[universe] BOTTOM {bottom_n}:")
        for r in art["bottom"]:
            print(f"    {r['sym']:6s} score={r['score']:.3f} "
                  f"mom={r['momentum_12m']:+.1%} sharpe={r['sharpe_ann']:+.2f} "
                  f"${r['last_close']:.2f}")
        print(f"[universe] artifact: {WATCHLIST_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
