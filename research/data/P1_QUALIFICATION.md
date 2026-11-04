# P1 data qualification record — unlevered_v1

**Date:** 2026-11-04. **Script:** `research/data/fetch_panel.py`. **Protocol:** `unlevered_v1` (P0, commit f969987).
Purpose (plan §9 P1): entitled price/action adapter test, small real fetch, coverage audit. No fake
successful downloads; failures recorded as failures.

## Source probes (all performed 2026-11-04 from this Linux machine)

| Source | Probe | Result |
|---|---|---|
| Alpaca data API | `GET /v2/stocks/SPY/bars` without credentials | **HTTP 401 — no entitled credentials on this machine** (`ALPACA_*` unset; prior smoke test ran on the Mac). Blocked until a free Alpaca key is registered here. |
| Twelve Data | `apikey=demo` | **HTTP 401** — demo key rejected; no key on this machine. Cross-check source blocked. |
| AlphaVantage | `apikey=demo` TIME_SERIES_DAILY | **Demo key restricted** — info response, no data. |
| stooq | `q/d/l/?s=spy.us` | **JavaScript/PoW challenge page** — confirmed blocked (matches 2026-11-03 log). |
| Yahoo v7 CSV download | `query1/v7/finance/download` | **HTTP 401 login required.** |
| **Yahoo v8 chart JSON** | `query1/v8/finance/chart/{sym}` keyless | **HTTP 200** — full daily OHLCV + adjclose + div/split events. Working keyless as of 2026-11-04. |
| FRED fredgraph.csv | keyless CSV | HTTP 200 (DGS10 1962..2026-11-02, sha256 a960c6...). Rates context available keyless. |
| US Treasury daily yield CSV | keyless | HTTP 200 (2026 file). |

## Qualification decision

The Yahoo v8 chart endpoint is the **only** price feed that passed keyless today. Per plan §3.3 it
is an *evaluated-only* source: unlabeled, no registered key, no published access contract. It is
admitted **for development-stage research** with mandatory conditions:

1. **Independent cross-check** against a different provider chain before any performance claim
   (done: local CBOE 2026-11-02 archive spots vs Yahoo 2026-11-02 closes below).
2. **Prospective re-fetch discipline**: the panel is a snapshot; final confirmation-period data must
   be re-collected at decision time, not from this file.
3. **Access-terms review** before any public claim or redistribution of derived data.
4. **No reliance for entitlement guarantees**: if the endpoint starts requiring cookies/keys
   (as v7 CSV already does), the market backtest is BLOCKED per the frozen blocking rule until an
   entitled free source (Alpaca registration) replaces it.

## Universe fetch (8/8 OK)

Window 2000-01-01..2026-11-03, per-symbol JSON snapshots under `research/data/panel/`
(sha256 in `coverage_report.json`; 36MB raw, gitignored as regenerable):

| Symbol | Bars | First | Last | Divs | Splits | Nulls | Gaps>10d |
|---|---:|---|---|---:|---:|---:|---:|
| SPY | 6750 | 2000-01-03 | 2026-11-03 | 108 | 0 | 0 | 0 |
| VEA | 4850 | 2007-07-26 | 2026-11-03 | 67 | 0 | 0 | 0 |
| VWO | 5448 | 2005-03-10 | 2026-11-03 | 63 | 1 | 0 | 0 |
| IEF | 6106 | 2002-07-30 | 2026-11-03 | 290 | 0 | 0 | 0 |
| TLT | 6106 | 2002-07-30 | 2026-11-03 | 288 | 0 | 0 | 0 |
| TIP | 5764 | 2003-12-05 | 2026-11-03 | 202 | 0 | 0 | 0 |
| GLD | 5524 | 2004-11-18 | 2026-11-03 | 0 | 0 | 0 | 0 |
| BIL | 4890 | 2007-05-30 | 2026-11-03 | 127 | 1 | 0 | 0 |

## Independent cross-check (Yahoo close vs CBOE spot, 2026-11-02)

| Symbol | CBOE spot | Yahoo close | Rel diff | Within 50bps |
|---|---:|---:|---:|---|
| SPY | 752.661 | 752.100 | 7.5bp | yes |
| GLD | 362.11 | 361.650 | 12.7bp | yes |
| TLT | 81.55 | 81.730 | 22.1bp | yes |

## Adjustment-semantics checks

- Bars are split-adjusted: BIL's 2017-11-30 1:2 reverse split shows no price jump across the event
  (daily closes 91.48 → 91.50); VWO's 2008-06-18 2:1 split likewise continuous.
- `adjclose` additionally reflects distributions: SPY last-bar adj/close = 1.000; 2000-01-03
  adj/close = 0.625 implies −1.74%/yr, consistent with SPY's ~1.2–1.5% dividend yield plus
  compounding over 26.8y. GLD adj = close (0 dividends — correct for the physically-backed trust).
- Dividend/split event feeds are complete per symbol (SPY 108 divs since 2000 ≈ quarterly; IEF/TLT
  monthly, matching their distribution schedules).
- Date ordering strictly monotonic; zero null OHLCV rows.

## Known limitations (carried forward, not resolved here)

- **Inception truncation**: fetch window starts 2000-01-01; SPY (1993), IEF/TLT (2002) lose pre-2000
  history. Protocol caps the study at the verifiable window anyway; the frozen plan's 36m train +
  12m inner + 12m outer from 2016-era Alpaca history is unaffected (Alpaca-era sensitivity is a P3
  diagnostic; Yahoo 2000+ is the development panel).
- **No point-in-time vintage**: Yahoo adjusts retroactively; today's snapshot is not what a 2015
  decision system would have seen. Development-stage only; the confirmation period must re-fetch at
  decision time.
- **BIL launch 2007-05-30**: the short Treasury reserve is unavailable before mid-2007; pre-2007
  cash legs must use a modeled cash rate (FRED/Treasury keyless) instead, labelled as such.
- **Single-provider risk**: all 8 symbols from one endpoint. The Alpaca free registration remains
  the required second source before promotion gate 1 (integrity) can pass.

**Verdict:** P1 development panel QUALIFIED for development-stage research with the four conditions
above. Integrity gate for promotion still requires an independent entitled source.
