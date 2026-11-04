"""P6 harness tests: content hashing (fetch-metadata stability), per-session
input hashing (causality), ET close-completion guard, idempotent skip, and
correction-row semantics of the append-only scorecard.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timezone
from pathlib import Path

import pytest

from research.paper import run_daily as rd


# ---------------- fixtures ------------------------------------------------------

def _snap(records, symbol="TEST"):
    """Minimal snapshot dict shaped like a P1 panel file."""
    return {
        "symbol": symbol, "source": "yahoo-chart",
        "fetched_at": "2026-11-04T04:24:48+00:00",
        "window": ["2000-01-01", "2026-11-03"],
        "bars": [{"record_id": r, "data": d} for r, d in records],
        "dividends": [], "splits": [],
    }


def _bar(rid, close=100.0):
    return (rid, {"open": close, "close": close, "volume": 1e6})


BARS = [_bar("2026-10-29"), _bar("2026-10-30"), _bar("2026-10-31")]


# ---------------- content hashing ----------------------------------------------

def test_content_hash_ignores_fetch_metadata():
    """Re-fetching identical market data (new fetched_at/window) must not
    change the content hash — the idempotency requirement."""
    a = _snap(BARS)
    b = _snap(BARS)
    b["fetched_at"] = "2026-11-05T23:00:00+00:00"
    b["window"] = ["2000-01-01", "2026-11-04"]
    assert rd.content_hash(a) == rd.content_hash(b)


def test_content_hash_changes_on_data_revision():
    a = _snap(BARS)
    revised = list(BARS)
    revised[-1] = _bar("2026-10-31", close=101.0)
    assert rd.content_hash(a) != rd.content_hash(_snap(revised))


def test_content_hash_covers_dividends_and_splits():
    a = _snap(BARS)
    b = _snap(BARS)
    b["dividends"] = [{"record_id": "2026-10-30",
                       "data": {"amount": 0.25}}]
    assert rd.content_hash(a) != rd.content_hash(b)
    c = _snap(BARS)
    c["splits"] = [{"record_id": "2026-10-30",
                    "data": {"numerator": 2.0, "denominator": 1.0}}]
    assert rd.content_hash(a) != rd.content_hash(c)


def test_record_blob_excludes_non_data_fields():
    """A record carrying fetch bookkeeping (response_sha256, available_at)
    must hash identically to one without, when record_id and data match."""
    r1 = {"record_id": "2026-10-30", "data": {"close": 1.0},
          "response_sha256": "aaa", "fetched_at": "2026-11-04"}
    r2 = {"record_id": "2026-10-30", "data": {"close": 1.0},
          "response_sha256": "bbb", "fetched_at": "2026-11-05"}
    assert rd._record_blob(r1) == rd._record_blob(r2)


# ---------------- per-session input hashing (causality) -------------------------

def test_session_input_hash_invariant_to_future_data(tmp_path, monkeypatch):
    """Appending a FUTURE record (or re-fetching with a later window) must
    not change a past session's input hash — that is what keeps older rows
    skip-stable while the panel grows."""
    monkeypatch.setattr(rd, "PANEL_DIR", tmp_path)
    monkeypatch.setattr(rd, "UNIVERSE", ["TEST"])
    records = {"TEST": rd._sorted_records(_snap(BARS))}
    monkeypatch.setattr(rd, "_rf_rows", lambda: [("2026-10-30", "x\n")])
    h1 = rd.session_input_hashes(["2026-10-30"], records, rd._rf_rows())

    grown = list(BARS) + [_bar("2026-11-02", close=99.0)]
    records2 = {"TEST": rd._sorted_records(_snap(grown))}
    h2 = rd.session_input_hashes(["2026-10-30"], records2, rd._rf_rows())
    assert h1["2026-10-30"] == h2["2026-10-30"]
    # and the new session's hash differs (it includes the new record)
    h3 = rd.session_input_hashes(["2026-11-02"], records2, rd._rf_rows())
    assert h3["2026-11-02"] != h1["2026-10-30"]


def test_session_input_hash_changes_on_past_revision(monkeypatch):
    """A revision of a scored session's own data must change that session's
    hash — the correction-row trigger."""
    monkeypatch.setattr(rd, "UNIVERSE", ["TEST"])
    records = {"TEST": rd._sorted_records(_snap(BARS))}
    revised = list(BARS)
    revised[1] = _bar("2026-10-30", close=77.0)
    records2 = {"TEST": rd._sorted_records(_snap(revised))}
    rf = []
    h1 = rd.session_input_hashes(["2026-10-30"], records, rf)
    h2 = rd.session_input_hashes(["2026-10-30"], records2, rf)
    assert h1["2026-10-30"] != h2["2026-10-30"]


# ---------------- ET close-completion guard --------------------------------------

def test_last_completed_session_basic():
    sessions = ["2026-11-02", "2026-11-03", "2026-11-04"]
    # 2026-11-04 15:00 ET: session 11-04 still open -> last completed 11-03
    now = datetime(2026, 11, 4, 20, 0, tzinfo=timezone.utc)  # 15:00 ET
    assert rd.last_completed_session(sessions, now) == "2026-11-03"
    # 2026-11-04 21:00 UTC = 16:00 ET: close reached
    now = datetime(2026, 11, 4, 21, 0, tzinfo=timezone.utc)
    assert rd.last_completed_session(sessions, now) == "2026-11-04"


def test_last_completed_session_none_before_any_close():
    now = datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)  # 10:00 ET
    assert rd.last_completed_session(["2026-11-02"], now) is None


def test_last_completed_session_dst_boundary():
    """US close is 16:00 America/New_York year-round; the guard must track
    the DST offset (16:00 EST = 21:00 UTC; 16:00 EDT = 20:00 UTC)."""
    # January (EST): 2027-01-04 21:00 UTC == 16:00 EST exactly
    now = datetime(2027, 1, 4, 21, 0, tzinfo=timezone.utc)
    assert rd.last_completed_session(["2027-01-04"], now) == "2027-01-04"
    # July (EDT): 2027-07-01 20:00 UTC == 16:00 EDT exactly
    now = datetime(2027, 7, 1, 20, 0, tzinfo=timezone.utc)
    assert rd.last_completed_session(["2027-07-01"], now) == "2027-07-01"
    # July: 19:59 UTC is still 15:59 EDT -> not completed
    now = datetime(2027, 7, 1, 19, 59, tzinfo=timezone.utc)
    assert rd.last_completed_session(["2027-07-01"], now) is None


# ---------------- scorecard semantics ---------------------------------------------

def test_append_idempotent_skip_and_correction(tmp_path, monkeypatch):
    """Second append with identical per-session hashes -> skip; with a
    changed hash -> exactly one appended correction row; old row intact."""
    monkeypatch.setattr(rd, "SCORECARD", tmp_path / "scorecard.jsonl")

    class D:
        def __init__(self, nav):
            self.session = "2026-11-03"
            self.nav = nav
            self.tau = 0.0
            self.gross_exposure = 1.0
            self.rf_daily = 0.0001
            self.settled_cash = 0.0

    days = {"2026-11-03": D(100.0)}
    sess_hashes = {"2026-11-03": "hash-v1"}
    snaps = {"TEST": "s1", "DGS3MO": "r1"}
    existing = {}
    with rd.SCORECARD.open("a") as fh:
        n1 = rd.append_scorecard_rows(fh, None, "B1", days, ["2026-11-03"],
                                      sess_hashes, existing, snaps, "ih")
    assert n1 == 1
    rows = [json.loads(l) for l in rd.SCORECARD.read_text().splitlines()]
    assert rows[0]["correction"] is False

    existing = rd._existing_sessions()
    with rd.SCORECARD.open("a") as fh:
        n2 = rd.append_scorecard_rows(fh, None, "B1", days, ["2026-11-03"],
                                      sess_hashes, existing, snaps, "ih")
    assert n2 == 0  # identical upstream -> skip

    sess_hashes2 = {"2026-11-03": "hash-v2"}  # upstream revision
    existing = rd._existing_sessions()
    with rd.SCORECARD.open("a") as fh:
        n3 = rd.append_scorecard_rows(fh, None, "B1", days, ["2026-11-03"],
                                      sess_hashes2, existing, snaps, "ih")
    assert n3 == 1
    rows = [json.loads(l) for l in rd.SCORECARD.read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0]["session_input_hash"] == "hash-v1"   # original intact
    assert rows[1]["correction"] is True
    assert rows[1]["session_input_hash"] == "hash-v2"


def test_existing_sessions_reads_both_key_styles():
    """Rows carry both input_hash (legacy whole-panel) and
    session_input_hash; the skip key is the per-session one."""
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl",
                                     delete=False) as fh:
        fh.write(json.dumps({"path": "B1", "session": "s1",
                             "input_hash": "whole",
                             "session_input_hash": "per"}) + "\n")
        name = fh.name
    orig = rd.SCORECARD
    rd.SCORECARD = Path(name)
    try:
        assert rd._existing_sessions() == {("B1", "s1"): "per"}
    finally:
        rd.SCORECARD = orig
        Path(name).unlink()
