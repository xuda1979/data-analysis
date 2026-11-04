"""P6 — frozen daily paper runner + append-only scorecard (plan §9 P6).

Prospective confirmation harness. After each US session close it:
  1. refreshes the 8-fund panel snapshots (Yahoo v8 chart, the P1
     evaluated-only source; fetch failures are recorded, never fabricated),
  2. rebuilds the aligned panel through the LAST COMPLETED session — a
     session is completed only after its 16:00 America/New_York close has
     passed, so an in-progress (partial) bar is never scored,
  3. replays the FROZEN reference paths (B1, B4) mechanically through the
     corrected runner over the full history (the runner is a pure function
     of the panel, so a daily full replay IS the incremental update and
     gives restart-invariance for free),
  4. appends one scorecard row per session per path to the append-only
     scorecard (research/paper/scorecard.jsonl).

Frozen paths (P5 verdict, 2026-11-05): B1 (capped equal-weight monthly
banded) and B4 (forecasts + cost-band gate, H1 arm b). NO candidate
strategies are tracked (all failed promotion gate 2); adding one requires
a new registry row before any scoring.

Idempotency / correction semantics: a session's marks depend only on
panel data with record_id <= that session (causal runner), so each row
keys on a PER-SESSION input hash — the sha256 over every snapshot record
(record_id + data, metadata excluded) dated <= the session, plus the
DGS3MO observations <= the session. Re-running with unchanged upstream
data skips (0 new rows); appending FUTURE sessions does not re-key past
rows; a genuine revision of a scored session's data (late print, FRED
restatement) appends a correction row — the old row is never rewritten
or removed. Snapshot-level content hashes (fetched_at and other fetch
metadata excluded) are recorded per row for audit.

Known limitation (disclosed): DGS3MO.csv is a manual FRED snapshot (last
observation 2026-11-02 at P6 start); the loader carries the last observed
rate forward, so fresh sessions may score with a stale risk-free reference
until the file is refreshed. A staleness warning prints after 7 days.

No live orders. At least six months of mechanical evidence is the minimum
before any confirmation claim (plan §9 P6); no short-run Sharpe certainty
is claimed at any horizon. Rows for sessions before T0 = 2026-11-04 are
development-history seed anchors; confirmation analysis uses post-T0
sessions only.

Usage: .venv/bin/python research/paper/run_daily.py [--offline]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.baselines.panel import UNIVERSE, load_panel
from research.baselines.runner import RunConfig, run_strategy
from research.controllers.h1_hold import H1Controller

PANEL_DIR = ROOT / "research/data/panel"
SCORECARD = ROOT / "research/paper/scorecard.jsonl"
ET = ZoneInfo("America/New_York")
CLOSE_ET = time(16, 0)          # US regular-session close
RF_STALE_DAYS = 7               # DGS3MO staleness warning threshold
T0 = "2026-11-04"               # data-exposure registry T0

FROZEN = {
    "B1": lambda: RunConfig(strategy="B1", reserve="BIL"),
    "B4": lambda: RunConfig(strategy="B4",
                            controller=H1Controller("b-cost-band")),
}


# ---------------- input hashing ------------------------------------------------

def _record_blob(record: dict) -> str:
    """Canonical string for one snapshot record: market content only
    (record_id + data). Fetch metadata (fetched_at, response_sha256,
    available_at, ...) is excluded so a re-fetch of identical data hashes
    identically."""
    return json.dumps([record["record_id"], record["data"]], sort_keys=True) + "\n"


def _sorted_records(snap: dict) -> list:
    """All (record_id, blob) of a symbol snapshot, sorted by record_id."""
    out = []
    for key in ("bars", "dividends", "splits"):
        for rec in snap.get(key, []):
            out.append((rec["record_id"], _record_blob(rec)))
    out.sort(key=lambda r: r[0])
    return out


def content_hash(snap: dict) -> str:
    """Whole-snapshot content hash (audit field; not the skip key)."""
    h = hashlib.sha256()
    for _, blob in _sorted_records(snap):
        h.update(blob.encode())
    return h.hexdigest()


def snapshot_content_hashes() -> dict:
    """{symbol: content_hash | None} + DGS3MO raw-file hash."""
    out = {}
    for sym in UNIVERSE:
        p = PANEL_DIR / f"{sym}.json"
        out[sym] = content_hash(json.loads(p.read_text())) if p.exists() else None
    rf = PANEL_DIR / "DGS3MO.csv"
    out["DGS3MO"] = hashlib.sha256(rf.read_bytes()).hexdigest() if rf.exists() else None
    return out


def _rf_rows() -> list:
    """Sorted (observation_date, canonical blob) rows of DGS3MO.csv
    (invalid/missing values skipped, mirroring the loader's carry rule)."""
    rows = []
    path = PANEL_DIR / "DGS3MO.csv"
    for line in path.read_text().splitlines()[1:]:
        parts = line.split(",")
        if len(parts) != 2 or parts[1].strip() in ("", ".", "NaN"):
            continue
        rows.append((parts[0].strip(), f"{parts[0].strip()}={parts[1].strip()}\n"))
    rows.sort(key=lambda r: r[0])
    return rows


def session_input_hashes(sessions: list, records: dict, rf_rows: list) -> dict:
    """Per-session input hash: sha256 over the content of every record with
    record_id <= session (all symbols, sorted) plus DGS3MO rows <= session.
    This is the causal upstream of a session's marks — the skip/correction
    key. Sessions must be a subset of the panel's sessions."""
    out = {}
    for s in sessions:
        parts = {}
        for sym in UNIVERSE:
            h = hashlib.sha256()
            for rid, blob in records[sym]:
                if rid > s:
                    break
                h.update(blob.encode())
            parts[sym] = h.hexdigest()
        h = hashlib.sha256()
        for rid, blob in rf_rows:
            if rid > s:
                break
            h.update(blob.encode())
        parts["DGS3MO"] = h.hexdigest()
        blob = json.dumps(parts, sort_keys=True).encode()
        out[s] = hashlib.sha256(blob).hexdigest()
    return out


def _input_hash(hashes: dict) -> str:
    blob = json.dumps(hashes, sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


# ---------------- session completion guard -------------------------------------

def last_completed_session(sessions: list, now: datetime | None = None) -> str | None:
    """Latest panel session whose 16:00 America/New_York close has passed.
    Sessions still in progress (or whose bar has not been published) are
    never scored. `now` is an aware datetime (UTC default)."""
    now = now or datetime.now(timezone.utc)
    out = None
    for s in sessions:
        close = datetime.combine(date.fromisoformat(s), CLOSE_ET, tzinfo=ET)
        if close <= now:
            out = s
        else:
            break
    return out


# ---------------- scorecard ----------------------------------------------------

def _existing_sessions() -> dict:
    """{(path, session): session_input_hash} from the current scorecard."""
    out = {}
    if not SCORECARD.exists():
        return out
    for line in SCORECARD.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        out[(row["path"], row["session"])] = row["session_input_hash"]
    return out


def append_scorecard_rows(fh, panel, name: str, days_by_session: dict,
                          sessions: list, sess_hashes: dict, existing: dict,
                          snapshot_hashes: dict, input_hash: str) -> int:
    """Append rows for `sessions` (one path). Skips sessions already scored
    with the identical per-session input hash; appends a correction row when
    the upstream hash changed. Returns the number of rows appended."""
    new_rows = 0
    for s in sessions:
        d = days_by_session.get(s)
        if d is None:
            continue
        prev = existing.get((name, s))
        if prev == sess_hashes[s]:
            continue   # already scored with identical upstream inputs
        row = {
            "path": name, "session": s, "nav": round(d.nav, 2),
            "tau": round(d.tau, 6),
            "gross_exposure": round(d.gross_exposure, 6),
            "rf_daily": d.rf_daily,
            "settled_cash": round(d.settled_cash, 2),
            "input_hash": input_hash,
            "session_input_hash": sess_hashes[s],
            "snapshot_hashes": snapshot_hashes,
            "scored_at": datetime.now(timezone.utc).isoformat(),
            "correction": bool(prev is not None and prev != sess_hashes[s]),
        }
        fh.write(json.dumps(row, sort_keys=True) + "\n")
        new_rows += 1
    return new_rows


# ---------------- harness ------------------------------------------------------

def _refresh_panel(offline: bool) -> tuple:
    """Re-fetch the panel snapshots (in place, P1 fetcher). Returns
    (ok, note)."""
    cmd = [sys.executable, str(ROOT / "research/data/fetch_panel.py")]
    if offline:
        cmd.append("--offline")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return r.returncode == 0, (r.stdout[-400:] + r.stderr[-400:]).strip()


def _rf_staleness_note(last_session: str) -> str:
    rows = _rf_rows()
    if not rows:
        return "DGS3MO.csv has no observations"
    last_obs = date.fromisoformat(rows[-1][0])
    gap = (date.fromisoformat(last_session) - last_obs).days
    if gap > RF_STALE_DAYS:
        return (f"WARNING: DGS3MO last observation {rows[-1][0]} is {gap} "
                f"calendar days behind session {last_session}; rf carried "
                f"forward — refresh the FRED snapshot")
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true",
                        help="replay from cached snapshots; no network fetch")
    args = parser.parse_args()

    note = ""
    if not args.offline:
        ok, note = _refresh_panel(False)
        if not ok:
            print(f"panel refresh FAILED (recorded, not fabricated): {note}",
                  file=sys.stderr)
            return 1
    snapshot_hashes = snapshot_content_hashes()
    if any(v is None for v in snapshot_hashes.values()):
        print("panel incomplete; refusing to score", file=sys.stderr)
        return 1
    input_hash = _input_hash(snapshot_hashes)

    # Load the full snapshot range, then cut at the last COMPLETED session
    # (16:00 ET guard): an in-progress session's partial bar must never be
    # scored. The reload through the frozen loader is the single source of
    # truth for panel semantics.
    full = load_panel(end="2099-12-31")
    last = last_completed_session(full.sessions)
    if last is None:
        print("no completed session yet; refusing to score", file=sys.stderr)
        return 1
    panel = load_panel(end=last) if full.sessions[-1] != last else full

    records = {sym: _sorted_records(
        json.loads((PANEL_DIR / f"{sym}.json").read_text())) for sym in UNIVERSE}
    rf_rows = _rf_rows()
    trailing = panel.sessions[-3:]
    sess_hashes = session_input_hashes(trailing, records, rf_rows)

    existing = _existing_sessions()
    new_rows = 0
    with SCORECARD.open("a") as fh:
        for name, cfg_factory in FROZEN.items():
            cfg = cfg_factory()
            r = run_strategy(panel, cfg)
            by_session = {d.session: d for d in r["days"]}
            new_rows += append_scorecard_rows(
                fh, panel, name, by_session, trailing, sess_hashes,
                existing, snapshot_hashes, input_hash)
    print(f"scorecard: {new_rows} new row(s); panel through {last}; "
          f"paths: {', '.join(FROZEN)}")
    stale = _rf_staleness_note(last)
    if stale:
        print(stale)
    if note:
        print(f"fetch note: {note[:200]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
