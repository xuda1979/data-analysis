# P6 Record — prospective paper runner + append-only scorecard

**Status:** harness complete (2026-11-05); scorecard accruing. Plan §9 P6:
"Frozen daily paper runner and append-only scorecard | At least six months
of mechanical evidence; no live orders; continue longer confirmation
without claiming short-run Sharpe certainty."

**Scope:** `research/paper/run_daily.py` (harness),
`research/paper/scorecard.jsonl` (append-only evidence),
`research/paper/test_run_daily.py` (11 tests). No live orders — the
scorecard records mechanically replayed marks of frozen reference paths.

## Frozen paths (P5 verdict)

Only the two reference paths are tracked — **no candidate strategies**
(all failed promotion gate 2; adding one requires a new registry row
before any scoring):

| path | config | role |
|---|---|---|
| B1 | `RunConfig(strategy="B1", reserve="BIL")` | capped equal-weight monthly banded; strongest simple control (P3) |
| B4 | `RunConfig(strategy="B4", controller=H1Controller("b-cost-band"))` | forecasts + cost-band gate; primary control (P4 arm b) |

## Mechanics

After each US session close, the harness:
1. refreshes the 8-fund panel snapshots via the P1 fetcher (Yahoo v8
   chart; failures recorded, never fabricated),
2. cuts the panel at the **last completed session** — a session is
   completed only after its 16:00 America/New_York close has passed, so
   an in-progress (partial) bar is never scored,
3. replays B1 and B4 whole-history through the corrected runner (pure
   function of panel → full replay IS the incremental update;
   restart-invariant by construction),
4. appends rows for the trailing 3 sessions per path.

## Hash / correction semantics (append-only)

A session's marks depend only on data with `record_id <= session` (causal
runner), so the skip/correction key is a **per-session input hash**:
sha256 over the content of every snapshot record (record_id + data;
fetch metadata `fetched_at`/`response_sha256` excluded so re-fetching
identical data hashes identically) dated ≤ the session, plus DGS3MO
observations ≤ the session.

- **Idempotent:** unchanged upstream → 0 new rows (verified: second
  offline run appended nothing).
- **Growing panel:** appending future sessions never re-keys past rows.
- **Correction:** a genuine revision of a scored session's data (late
  print, FRED restatement) appends a `"correction": true` row; the old
  row is never rewritten or removed.
- Each row records per-symbol whole-snapshot content hashes (audit) and
  a whole-panel `input_hash` (legacy/audit) alongside
  `session_input_hash` (the skip key).

## Seed rows (development-history anchors)

The scorecard opened 2026-11-05 (offline, cached panel through
2026-11-03) with 6 rows — B1/B4 × 2026-10-30/11-02/11-03. Terminal NAVs
match the published P3/P5 records (B1 $320,685.50 vs record $320,686;
B4 $284,877.13 vs record $284,877) — same replay, same marks, confirming
the harness reproduces the development-history paths it extends.
Sessions before T0 = 2026-11-04 are development-history anchors;
**confirmation analysis uses post-T0 sessions only.**

## Disclosed limitations

- **DGS3MO staleness:** the risk-free reference is a manual FRED snapshot
  (last observation 2026-11-02 at P6 start); the loader carries the last
  observed rate forward, so fresh sessions may score with a stale rf
  until the file is refreshed. The harness warns after a 7-day gap.
- **Live-quote latency:** the 16:00 ET guard prevents scoring partial
  bars, but a run shortly after close could still precede provider
  publication of the final print; the per-session hash makes any later
  revision an explicit correction row rather than silent drift.
- **Scheduling:** accrual is operator-invoked (no automated scheduler on
  this machine); a skipped day is recovered by the next run (whole-
  history replay fills any gap; the trailing-3 window is a scoring
  convenience, not a data constraint).

## Confirmation rules (frozen)

- Minimum **six months of mechanical post-T0 evidence** before any
  confirmation claim; **no short-run Sharpe certainty** at any horizon.
- Any deviation (new path, rule change, hash-semantics change) is a new
  registry row / appended record note — never a rewrite.

## Test coverage

`research/paper/test_run_daily.py` (11): content hash stable across
fetch metadata; sensitive to bar/dividend/split revisions; record blob
excludes bookkeeping fields; per-session hash invariant to future
appends; sensitive to past revisions; ET guard basic/none/DST-boundary
cases (EST 21:00 UTC vs EDT 20:00 UTC); idempotent skip; correction-row
semantics (original row intact, exactly one appended correction);
scorecard key reads per-session hash. Full suite: 111 passed
(100 prior + 11).
