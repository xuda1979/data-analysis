"""M4 batch driver: generate reports for all 60 WATCHLIST tickers.

Runs sequentially (rate-safe). Loads the sym list from
results/equity_research/WATCHLIST.json, calls generate_report for each,
writes one progress line per ticker to stdout and a summary to the log.
Never used in production paths; an operator-managed batch tool.

CLI: [--force] [--syms=A,B,C]   --syms regenerates only the listed tickers
(comma-separated) instead of the whole watchlist, e.g. to re-run affected
symbols after a fix without touching the clean ones.
"""
from __future__ import annotations

import json
import os
import sys
import time

# repo root so results/* resolves from any CWD; tools/ so `wt` package imports
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))
for p in (os.path.join(ROOT, "tools"), ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)
os.chdir(os.path.join(ROOT, "tools"))

from wt.agent.research_report import generate_report, DEFAULT_OUT_DIR  # noqa: E402

WATCHLIST = os.path.join(ROOT, "results", "equity_research", "WATCHLIST.json")


def _parse_syms(value: str):
    return [s.strip().upper() for s in value.split(",") if s.strip()]


def main():
    force = "--force" in sys.argv
    syms_arg = None
    for a in sys.argv[1:]:
        if a.startswith("--syms="):
            syms_arg = _parse_syms(a[len("--syms="):])
    with open(WATCHLIST) as f:
        w = json.load(f)
    syms = [t["sym"] for t in w["top"]] + [t["sym"] for t in w["bottom"]]
    assert len(syms) == 60, f"expected 60 tickers, got {len(syms)}"
    if syms_arg is not None:
        unknown = [s for s in syms_arg if s not in syms]
        if unknown:
            print(f"[batch] ERROR: not in universe: {unknown}", flush=True)
            return 1
        syms = syms_arg

    print(f"[batch] {len(syms)} tickers, force={force}, out={DEFAULT_OUT_DIR}",
          flush=True)
    t_start = time.time()
    ok, skipped, failed = [], [], []
    for i, sym in enumerate(syms, 1):
        t0 = time.time()
        try:
            r = generate_report(sym, force=force)
        except Exception as e:  # batch must survive a single crash
            failed.append((sym, repr(e)))
            print(f"[batch] {i:02d}/{len(syms)} {sym}: CRASH {e!r} "
                  f"({time.time()-t0:.0f}s)", flush=True)
            continue
        dt = time.time() - t0
        status = "done" if r.report_path else ("skipped" if r.errors else "failed")
        if status == "done":
            ok.append(sym)
        elif status == "skipped":
            skipped.append(sym)
        else:
            failed.append((sym, r.errors))
        line = (f"[batch] {i:02d}/{len(syms)} {sym}: {status} ({dt:.0f}s, "
                f"errors={len(r.errors)}) risk={getattr(r, 'risk_manager', None) and r.risk_manager.get('verdict')}")
        print(line, flush=True)
        if r.errors:
            for e in r.errors:
                print(f"       - {e}", flush=True)
        # throttle: sequential generation already includes LLM latency
    dt_total = time.time() - t_start
    print(f"[batch] COMPLETE in {dt_total/60:.1f} min: "
          f"ok={len(ok)} skipped={len(skipped)} failed={len(failed)}", flush=True)
    if skipped:
        print(f"[batch] skipped: {skipped}", flush=True)
    if failed:
        print(f"[batch] failed: {failed}", flush=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
