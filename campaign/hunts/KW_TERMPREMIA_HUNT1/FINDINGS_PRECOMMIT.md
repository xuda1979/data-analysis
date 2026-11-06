# FINDINGS_PRECOMMIT — KW TERMPREMIA HUNT1 (rates-side direction 4)

**Sealed:** 2026-11-06, BEFORE any overlay measurement (repo convention: TVPVECM_HUNT1 /
ITER61_DDCON pattern). No backtest of any arm below has been run at seal time.

## 1. Objective and law audit

Test whether a Kim-Wright 10-year term-premia (THREEFYTP) state overlay improves the champion
of record (ITER61_DDCON A_cap28, pinned daily series sha16 `a8ed233bd0f6fd5d`) by the campaign
promotion standard.

**Law:** frontier-closure #147/#148 satisfied via NEW DATA — FRED KW term-premia series
(THREEFYTP1-10) have never been fetched or measured in this repo prior to 2026-11-06.
DEAD_IDEAS.csv audit (2026-11-06): no KW/term-premia/THREEFY exposure exists; prior rates
deaths (rows 28, 39, 51, 56, 60, 61, 63) are yield slope/steepener/shape/carry rules on
yields — not the market-implied forward decomposition. Hunt lawful.

**Mechanism (H1):** KW TP is a forward-looking, model-implied decomposition
(forward rate = E[spot] + TP), not a trailing realized quantity — consistent with the
2026-11-03 pro-cyclical gate lesson (gates must score prospect, not trailing reversion).
Hypothesis: episodes of deeply compressed trailing-z term premia identify prospective
champion headwind regimes; de-risking into them improves Sharpe enough to clear the
promotion margin. Null (H0): TP state carries no prospective champion-timing information.

## 2. Frozen data

| Series | Source | Window | Rows | sha256 (first 16) |
|---|---|---|---|---|
| THREEFYTP1..TP10 | FRED fredgraph.csv keyless, fetched 2026-11-06 | 1990-01-02..2026-10-30 | 9610 each | see data/ (pinned below) |
| THREEFY2/5/10 (rates levels, context only) | FRED fredgraph.csv keyless | 1990-01-02..2026-10-30 | 9610 each | see data/ |
| Champion daily | `campaign/results/GOAL100_RAWEW13v2_WEIGHTED_GEAR16_daily.csv` | 2008-03-31..2026-08-28 (n=4806) | 4806 | a8ed233bd0f6fd5d |

KW data covers the full champion window. TP10 range [−0.6587, 2.5157]; 415 NaN per series
(FRED "." convention). Data files sha256-pinned in `data/` at seal (full digests):
THREEFYTP1 11b825e1138d8b64, TP2 7aa72a0881c5a7d8, TP3 1ca2bf064eaf2518, TP4 714f2798c4c35040,
TP5 553f80498f08444c, TP6 4bec94333be0f6b9, TP7 4baf901b6e64a5ab, TP8 eef9f9492007ebf5,
TP9 485f5929a83fb071, TP10 2c8720a33b0e6302, THREEFY10 7853d7998e2efab0,
THREEFY5 2b803ca9cc85f2a3, THREEFY2 c3bd368a10c6f54d.

## 3. Pinned baseline and metric conventions (verified exactly on this machine 2026-11-06)

- SR = mean/std(ddof=1) × √252 → champion **3.784489**
- CAGR = exp(252 · mean(ln(1+r))) − 1 → champion **23.860978%** (geometric; arithmetic
  mean×252 = 21.5678% is NOT the headline convention)
- MDD = min(NAV/cummax(NAV) − 1), NAV = (1+r).cumprod() → champion **−3.30485%**
- Calendar years: (1+r).groupby(year).prod() − 1 → champion **0 negative years**, worst
  **+7.5530% (2013)**
- IS (<2017-01-01) / OOS (≥2017-01-01) split convention per CHAMPION_CARD (report-only here)
- Cost model: overlay exposure change costs FULL |Δg| × 6.4 bps (one-side, full book);
  champion's own internal costs are already embedded in the pinned series
- Freed capital (1−g) earns 0% (conservative; disclosed)
- T+1 causality: exposure g_t is set from signal data through t−1 (shift(1)); g_0 = 1.0
- tau_t = |g_t − g_{t−1}|/2; ann half-turn = (252/n)·Σtau; roll-252 = max trailing-252 Σtau

## 4. Frozen signal and overlay methodology

### 4.1 Signal
- z_t = (TP10_t − mean_1260) / std_1260(ddof=1) computed on the FULL FRED daily series
  (1990+, min_periods=252), THEN reindexed to champion dates (last obs ≤ date, ffill
  limit 5 business days). No warmup shortfall (18y history pre-champion).
- NaN handling: if TP undefined at t after ffill(5) → signal undefined → HOLD previous
  exposure state (no toggle, no cost). Only defined observations can toggle.
- Slope variant (Arm C only): z computed identically on (TP10 − TP1).

### 4.2 Exposure rule (binary, hysteresis, de-risk only — no leverage added)
- Arm A (primary): g: 1.0 → 0.7 when z < −1.0; 0.7 → 1.0 when z ≥ −0.5.
- Arm B (deeper-cut variant): 1.0 → 0.5 when z < −1.5; 0.5 → 1.0 when z ≥ −0.75.
- Arm C (slope variant): Arm A rule on TP10−TP1 slope z.
- Arm P (placebo): Arm A rule on TIME-REVERSED TP10 z (prospective information destroyed;
  marginal structure approximately preserved).
- Arm N (random control): Arm A rule on iid N(0,1) noise, numpy seed 20261106, on the
  TP10 index, then same reindex. Expected to fail G1 and G4/G5 (churn).
- Overlay return: r_t = g_t · champ_t − |g_t − g_{t−1}| × 0.00064.

## 5. Frozen evaluation — promotion gates (all must hold)

Scored on the champion window 2008-03-31..2026-08-28, identical conventions/costs:

| Gate | Criterion |
|---|---|
| G1 | SR(arm) − SR(champ) ≥ +0.15 |
| G2 | CAGR(champ) − CAGR(arm) ≤ 0.5pp |
| G3 | \|MDD(arm)\| ≤ \|MDD(champ)\| + 1pp (≤ 4.30485%) |
| G4 | ann overlay half-turn ≤ 1.0 |
| G5 | roll-252 overlay half-turn ≤ 1.5 |
| G6 | discriminancy: P and N both FAIL G1 |

Adoption requirements (reported separately, both required for any operator memo):
A-R1 MDD(arm) strictly shallower than −3.30485% (ITER61 adoption-memo standard);
A-R2 0 negative calendar years preserved.

Report-only (for the memo, not gating): IS/OOS split, decade bins, cost stress 8 and
10 bps one-side, toggle rates, time-in-de-risk fraction.

**Decision rule (sealed):** any treatment arm (A/B/C) passing G1–G6 → promotion memo
with highest-dSharpe passer as candidate, others reported as neighborhood stability with
the multiple-comparison caveat disclosed. No arm passes → FINDINGS.md honest negative +
DEAD_IDEAS.csv row, advance to next axis. P or N passing G1 → machinery INVALID, all
results void, hunt re-engineered (defect, not refutation).

## 6. Pre-registered falsification criteria

- De-risk state active < 2% of sessions → mechanism inert → refuted.
- De-risk state active > 60% of sessions → z is a regime label, not timing → refuted
  (scrutinize before recording).
- All arms dSharpe < +0.15 → H0 stands → refuted (expected most likely outcome;
  champion SR 3.78 is a very high bar for macro timing).
- Any pass driven by CAGR sacrifice > 0.5pp → fail G2, refuted.

## 7. Budget and registry

- 5 arms (A, B, C, P, N) + champion baseline. No re-runs, no added arms, no threshold
  edits after unblinding. This hunt is a champion-campaign hunt (TVPVECM precedent) and
  consumes ZERO unlevered_v1 trial-registry slots.
- All pre-T0 history here is development history for the champion (data_exposure_v1
  classification): a pass is a development-stage pass; prospective confirmation would
  accrue post-T0 (paper path) before any adoption claim.

## 8. Limitations (disclosed at seal)

- Overlay operates on the pinned composite daily series; the champion's 12 sleeve series
  are absent on this machine (sleeve-level reallocation not locally evaluable). Any
  promotion is followed by a separate pre-registered integration round on the Mac.
- KW TP is current-view FRED (not ALFRED vintage): revision structure not tracked.
- Champion series assumed net of its internal trading costs (it is the published series).
- Binary g grid {0.7, 0.5} and thresholds {−1.0, −1.5} are a coarse pre-registered grid,
  not a tuned optimum — by design.

## 9. Provenance

- FRED fredgraph.csv keyless fetch 2026-11-06 (rate-limit ~1 req/8s honored); files under
  `campaign/hunts/KW_TERMPREMIA_HUNT1/data/` with sha256 pinned in §2 (data files out of
  git per repo convention).
- Champion series hash-verified 2026-11-06 (full sha256
  a8ed233bd0f6fd5dad4056fda8fbd4cdde10d87ca4886c104c25b93c8014fbf4).

**Sealed by:** operator goal directive 2026-11-06 (checklist item 3, goal.md Status order:
law audit → champion verify → KW fetch → pre-register gates → artifact → measure; first
three complete at seal). All hyperparameters above are frozen. No peeking, no re-tuning
after arms run.
