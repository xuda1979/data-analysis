"""P3 panel loader: research/data/panel/*.json + DGS3MO.csv -> aligned tables.

Produces session-indexed open/close/volume/dollar-volume/dividend tables for the
8-fund universe on the common verified window (P1: 2007-07-26..2026-11-03,
4850 sessions), plus the daily DGS3MO risk-free reference (FRED keyless
fredgraph.csv snapshot, same fetch as P1; holiday nulls carried forward).

Semantics frozen from P1 verification (research/data/P1_QUALIFICATION.md):
- Bars (open/close/volume) are FULLY split-adjusted: the adjclose/close ratio
  shows zero jump across both split events (VWO 2:1 2008-06-18, BIL 1:2
  2017-11-30), i.e. the price series is continuous with no event-day step.
  Consequence for replay: splits are a NO-OP on positions -- the replay must
  NOT multiply shares on split dates (doing so would fabricate a return).
  The splits table is loaded for disclosure/audit only.
- Yahoo dividend amounts are already on the split-adjusted bar basis (implied
  dividends from adjclose/close ratio jumps match reported amounts within ~1%,
  including across both split boundaries). Replay credits shares*amount as
  settled cash on the ex-date; pay-lag not modeled (disclosed limitation).
  Holder convention: shares held entering the ex-date session receive the
  dividend (selling AT the ex-date open does not forfeit it).

Run: .venv/bin/python -m pytest research/baselines/ -q
"""
from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PANEL_DIR = ROOT / "research/data/panel"

UNIVERSE = ["SPY", "VEA", "VWO", "IEF", "TLT", "TIP", "GLD", "BIL"]


@dataclass
class Panel:
    sessions: list            # ISO date strings, strictly increasing
    open: dict                # symbol -> list[float | None]
    close: dict               # symbol -> list[float | None]
    volume: dict              # symbol -> list[float]  (shares; 0 if missing)
    dividends: dict           # symbol -> {session_index: amount_per_share}
    splits: dict              # symbol -> {session_index: (numerator, denominator)}
    rf_daily: list            # DGS3MO/100/252 per session (carried forward)
    rf_annual_pct: list       # DGS3MO in percent per session (None before carry)

    def n(self) -> int:
        return len(self.sessions)

    def idx(self, iso: str) -> int:
        """Index of session ISO string; ValueError if absent."""
        return self.sessions.index(iso)


def _load_symbol(symbol: str) -> dict:
    path = PANEL_DIR / f"{symbol}.json"
    if not path.exists():
        raise FileNotFoundError(f"panel snapshot missing: {path}")
    return json.loads(path.read_text())


def load_panel(start: str = "2007-07-26", end: str = "2026-11-03") -> Panel:
    """Load and align the 8-fund panel. start must be >= the latest first bar
    (common window start). Sessions outside [start, end] are dropped."""
    raw = {s: _load_symbol(s) for s in UNIVERSE}
    # union calendar then restrict to symbols' coverage; the common window has
    # zero gaps (P1 audit), so intersection == union within [start, end].
    session_set = set()
    per_symbol_sessions = {}
    for sym, snap in raw.items():
        ss = [b["record_id"] for b in snap["bars"]]
        per_symbol_sessions[sym] = set(ss)
        session_set.update(ss)
    sessions = sorted(s for s in session_set if start <= s <= end)
    # verify no holes against every symbol (fail-closed)
    for sym in UNIVERSE:
        missing = [s for s in sessions if s not in per_symbol_sessions[sym]]
        if missing:
            raise ValueError(f"{sym} missing {len(missing)} common sessions, "
                             f"first {missing[0]}; refusing to fabricate bars")
    n = len(sessions)

    open_, close, volume = {}, {}, {}
    dividends, splits = {}, {}
    for sym in UNIVERSE:
        bars = {b["record_id"]: b["data"] for b in raw[sym]["bars"]}
        o, c, v = [], [], []
        for s in sessions:
            d = bars[s]
            o.append(d["open"])
            c.append(d["close"])
            v.append(float(d["volume"]) if d["volume"] is not None else 0.0)
        open_[sym], close[sym], volume[sym] = o, c, v
        divs = {}
        for rec in raw[sym]["dividends"]:
            if rec["record_id"] in sessions:
                divs[sessions.index(rec["record_id"])] = float(rec["data"]["amount"])
        dividends[sym] = divs
        spl = {}
        for rec in raw[sym]["splits"]:
            if rec["record_id"] in sessions:
                spl[sessions.index(rec["record_id"])] = (
                    float(rec["data"]["numerator"]), float(rec["data"]["denominator"]))
        splits[sym] = spl

    rf_daily, rf_annual = _load_rf(sessions)
    return Panel(sessions, open_, close, volume, dividends, splits, rf_daily, rf_annual)


def _load_rf(sessions: list) -> tuple:
    """DGS3MO (percent, annual, simple) -> daily rate /252. Carry last observed
    value forward over holiday nulls ('' or '.'); before the first observation
    use the first observed value (pre-2007-07-26 is outside the window anyway)."""
    path = PANEL_DIR / "DGS3MO.csv"
    if not path.exists():
        raise FileNotFoundError(f"risk-free reference missing: {path}")
    obs = {}
    with path.open() as fh:
        for row in csv.DictReader(fh):
            val = row["DGS3MO"].strip()
            if val in ("", ".", "NaN"):
                continue
            obs[row["observation_date"]] = float(val) / 100.0
    rf_annual, rf_daily, last = [], [], None
    if not obs:
        raise ValueError("DGS3MO.csv has no observations")
    first_val = obs[sorted(obs)[0]]
    for s in sessions:
        if s in obs:
            last = obs[s]
        val = last if last is not None else first_val
        rf_annual.append(val)
        rf_daily.append(val / 252.0)
    return rf_daily, rf_annual


def dollar_volume(panel: Panel, symbol: str, i: int) -> float:
    return panel.volume[symbol][i] * panel.close[symbol][i]


def trailing_adv(panel: Panel, symbol: str, i: int, window: int = 20) -> float:
    """Trailing average dollar volume over the `window` sessions ending at i
    (inclusive). Uses only past/current data. Returns 0.0 if fewer than half
    the window is available (caller treats as unknown volume)."""
    lo = max(0, i - window + 1)
    vals = [dollar_volume(panel, symbol, j) for j in range(lo, i + 1)]
    if len(vals) < max(1, window // 2):
        return 0.0
    return sum(vals) / len(vals)
