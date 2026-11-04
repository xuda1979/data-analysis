"""P1: fetch and qualify the unlevered_v1 8-fund universe panel.

Fetches daily bars + corporate actions via world_trader.sources.eod (Yahoo v8 chart,
evaluated-only source), writes per-symbol raw JSON snapshots + a coverage report +
sha256 manifest under research/data/panel/. No fabricated rows: every number comes
from a fetched response whose hash is recorded.

Run: .venv/bin/python research/data/fetch_panel.py [--offline]
"""
import argparse
import hashlib
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from world_trader.store import Store
from world_trader.transport import JsonClient
from world_trader.sources import eod

UNIVERSE = ["SPY", "VEA", "VWO", "IEF", "TLT", "TIP", "GLD", "BIL"]
PANEL_DIR = ROOT / "research/data/panel"
START, END = "2000-01-01", date.today().isoformat()
# Earliest true inception among candidates predates 2000 (SPY 1993-01-29); we cap
# the study window at 2000-01-01 per the frozen protocol (plan §3.2: begin with the
# shorter verifiable history; Alpaca-free-era sensitivity is a P3 diagnostic).


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true",
                        help="replay from cache only; no network")
    args = parser.parse_args()
    PANEL_DIR.mkdir(parents=True, exist_ok=True)
    store = Store(":memory:")
    client = JsonClient(store, offline=args.offline, timeout=40, attempts=3)

    report = {"fetched_at": datetime.now(timezone.utc).isoformat(), "symbols": {},
              "cross_check": {}}
    manifest = {}
    failures = []
    for symbol in UNIVERSE:
        try:
            rows = eod.daily(client, symbol, start=START, end=END)
        except Exception as exc:  # honest failure; no partial fabrication
            failures.append(f"{symbol}: {exc}")
            report["symbols"][symbol] = {"status": "FAIL", "error": str(exc)[:300]}
            continue
        bars = [r for r in rows if r.dataset == "daily_bars"]
        divs = [r for r in rows if r.dataset == "dividends"]
        splits = [r for r in rows if r.dataset == "splits"]
        snapshot = {
            "symbol": symbol, "source": "yahoo-chart", "fetched_at": report["fetched_at"],
            "window": [START, END], "bars": [r.to_dict() for r in bars],
            "dividends": [r.to_dict() for r in divs], "splits": [r.to_dict() for r in splits],
        }
        blob = json.dumps(snapshot, sort_keys=True, indent=1).encode()
        path = PANEL_DIR / f"{symbol}.json"
        path.write_bytes(blob)
        manifest[f"research/data/panel/{symbol}.json"] = hashlib.sha256(blob).hexdigest()
        dates = sorted(r.record_id for r in bars)
        gaps = [(a, b) for a, b in zip(dates, dates[1:])
                if (date.fromisoformat(b) - date.fromisoformat(a)).days > 10]
        report["symbols"][symbol] = {
            "status": "OK", "bars": len(bars), "dividends": len(divs), "splits": len(splits),
            "first": dates[0], "last": dates[-1],
            "gaps_over_10d": len(gaps), "largest_gaps": [
                {"from": a, "to": b, "days": (date.fromisoformat(b) - date.fromisoformat(a)).days}
                for a, b in sorted(gaps, key=lambda g: g[1] < g[0], reverse=False)[:0] or
                sorted(gaps, key=lambda g: (date.fromisoformat(g[1]) - date.fromisoformat(g[0])).days, reverse=True)[:5]],
            "null_closes": sum(1 for r in bars if r.data["close"] is None),
        }

    # Independent cross-check vs local CBOE archive spots (different provider chain).
    cboe_dir = ROOT / "tools/quant/data/cboe_options/archive/20261102"
    for symbol in ("SPY", "GLD", "TLT", "QQQ"):
        cboe_file = cboe_dir / f"{symbol}.csv"
        panel_file = PANEL_DIR / f"{symbol}.json"
        if not (cboe_file.exists() and panel_file.exists()):
            continue
        spot = None
        for line in cboe_file.read_text().splitlines():
            if line and line != "spot,exp,typ,strike,bid,ask,iv,open_interest,volume,delta,gamma,vega,theta,moneyness":
                spot = float(line.split(",")[0])
                break
        panel = json.loads(panel_file.read_text())
        match = [b for b in panel["bars"] if b["record_id"] == "2026-11-02"]
        if spot is not None and match:
            close = match[0]["data"]["close"]
            rel = abs(close - spot) / spot
            report["cross_check"][symbol] = {
                "cboe_spot_20261102": spot, "yahoo_close_20261102": close,
                "rel_diff": round(rel, 6), "within_50bps": rel <= 0.005,
            }

    report["failures"] = failures
    report["manifest"] = manifest
    report["window"] = [START, END]
    (PANEL_DIR / "coverage_report.json").write_text(json.dumps(report, indent=1))
    ok = sum(1 for s in report["symbols"].values() if s.get("status") == "OK")
    print(f"P1 fetch: {ok}/{len(UNIVERSE)} symbols OK; cross-checks: "
          f"{json.dumps(report['cross_check'])}")
    if failures:
        print("FAILURES:", *failures, sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
