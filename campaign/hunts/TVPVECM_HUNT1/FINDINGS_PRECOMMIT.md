# FINDINGS_PRECOMMIT — TVP-VECM HUNT1 (Direction 5)

**Sealed:** 2026-11-03, BEFORE any backtest execution (repo convention: ITER61_DDCON pattern).
**Law:** frontier-closure #147/#148 satisfied via NEW RULE (time-varying cointegration + credibility
gate vs existing static-z sleeves) on FREE price data.

---

## 1. Objective

Test whether a time-varying cointegration model (TVP-VECM) with a pre-registered
"equilibrium credibility gate" beats the incumbent static banded-z spread idiom
(sleeve_library) on long-horizon weekly spread pairs, net of costs, with honest
out-of-sample discipline.

**Core hypothesis (H1):** The gate (mean-reversion half-life + rank credibility) improves
risk-adjusted returns by cutting exposure during structural-shift episodes, at the cost of
some entry opportunity. Net effect positive.

**Ablation hypothesis (H2):** Gate is the source of improvement (Arm B vs Arm C).
**Null hypothesis (H0):** TVP adds nothing over static z (Arm B vs Arm A).

## 2. Frozen universe — 5 pilot pairs (data verified on disk 2026-11-03)

| # | Pair (log y1 vs log y2) | y1 data | y2 data | Common window |
|---|---|---|---|---|
| P1 | WTI vs Brent | FRED DCOILWTICO (1986+, fetched 2026-11-03, ends 2026-10-27) | FRED DCOILBRENTEU (1987-05+, ends 2026-10-27) | 1990-01..2026-10 daily→weekly |
| P2 | Gold vs Silver | local xau.csv (2007-12-21+, ends 2026-09-22) | local slv.csv (2006-09-26+, ends 2026-09-22) | 2007-12..2026-09 daily→weekly |
| P3 | Gold vs Copper | local xau.csv | FRED PCOPPUSDM (monthly, 1992+, ends 2026-09) — NOT weekly-buildable; fallback local copper_monthly.csv (1992+, ends 2026-07) | 2007-12..2026-07 MONTHLY only |
| P4 | Heating oil crack (HO vs WTI) | FRED DHHNGSP 1997+ | FRED DCOILWTICO | 1997-01..2026-10 daily→weekly |
| P5 | IG vs HY credit spread | FRED BAMLC0A0CM (2003-06+, ends 2026-10-30) | FRED BAMLH0A0HYM2 (2003-06+, ends 2026-10-30) | 2003-06..2026-10 daily→weekly |

**Data-source downgrade log (sealed pre-hoc):**
- P3 gold-copper is monthly only (PCOPPUSDM). Run it as MONTHLY arm variant, exclude
  from weekly SR aggregation, report separately.
- Silver free daily was NOT obtainable 2026-11-03 (LBMA 403, stooq PoW+Access denied,
  FRED silver IDs 404). P2 uses repo-local xau/slv CSVs (stooq-sourced historically).
- DHHNGSP is actually Henry Hub spot, NOT heating oil — FRED has no free heating-oil
  series. **P4 redefined: Henry Hub natgas vs WTI (both spot, energy complex).**
  This is the "C5ng" relative-value idea in spot form.

**Pairs NOT run (and why, sealed):** SPX/RTY (SP500 FRED ends 2016+ only 10y window —
insufficient), 2s10s (yield curve level is not a price pair for log-ratio cointegration),
T10YIE (same), equity pairs (no free deep history verified today).

## 3. Frozen methodology

### 3.1 Panel construction
- Daily → weekly W-FRI resample, `last()`, no fill.
- Log prices. Pairs formed as log(y1) − β·log(y2). Spreads in log space.
- Monthly P3: month-end resample.

### 3.2 Estimation (per pair, expanding window from start+156w)
- **Static β (Arms A, and Arm B/C fixed-β fallback):** expanding OLS on first 156w, then
  rolling 156w re-fit ANCHORED at window end (standard).
- **TVP β (Arms B, C):** local-level state space:
  - State: [β_t, α_t], transition: identity + Q = diag(q_β, 0), α fixed.
  - Observation: y1_t = β_t·y2_t + α + ε_t, ε ~ N(0, s_ε²), s_ε EWMA(λ=0.94) on residuals.
  - q_β: ML-estimated on the FIRST 156w only, then frozen for the whole backtest
    (prevents q drift/regime-fitting). Floor 1e-8, cap 1e-2.
  - Filter (NOT smoother) only. Signal at t uses data through t−1.
- **Gregory-Hansen (diagnostic only, does not gate entries in HUNT1):** rolling 156w,
  scan τ∈[0.15, 0.85], min-ADF vs GH1996 5% critical value; recorded per week for
  FINDINGS analysis of when the gate fired vs breaks.
- **Kalman half-life:** h_t = ln(0.5)/ln(1−κ_t) where κ_t = filtered adjustment
  coefficient from AR(1) on spread residual: ε_t = ρ ε_{t−1} + u, h = ln(2)/−ln(ρ).

### 3.3 Credibility gate (frozen)
- C_rank = Φ((trace_{r=1} − cv5%)/se) from rolling Johansen on 156w window.
  If trace < cv, C_rank = 0. Cap at 1.
- C_halflife: h ≤ 8w → 1.0; 8w < h ≤ 52w → 8/h; h > 52w or ρ ≤ 0 → 0.
- **Gate_t = C_rank × C_halflife.**
- New position only if Gate ≥ 0.50.
- If open and Gate falls < 0.30 → cut position 50%. Gate < 0.15 → close all.
- Gate re-arm requires ≥ 8 consecutive weeks above 0.50.

### 3.4 Entry/exit/stop (frozen, matches repo idiom)
- Entry: |z| ≥ 2.0 where z = ε̂/(EWMA σ_ε, 26w). Direction: short spread if z > +2.
- Exit: |z| ≤ 0.5 (full exit at weekly close).
- **Hard stop: |z| ≥ 4.0 → close, 8-week cooldown** (≈2× trailing σ; LTCM rule).
- Cooldown also applies after gate-forced closures.
- One position per pair at a time. No pyramiding.

### 3.5 Portfolio construction
- 5 pairs equal-weight sleeve; each pair vol-targeted to 10% ann on entry, using
  trailing 26w spread σ (frozen at entry).
- Sleeve = mean of active pair returns. Cost model: 10 bps per unit turnover
  (5 bps/side), consistent with sleeve_library.
- Weekly marks; positions marked to close.

### 3.6 Arms (frozen)
- **Arm A (baseline):** static-β spread, banded z-entry 2.0/exit 0.5, hard stop 4.0,
  NO gate.
- **Arm B (treatment):** TVP-β + gate (§3.2–3.4). Static fallback: if q_β hits floor
  or cap, use static β that week (logged).
- **Arm C (ablation):** TVP-β, NO gate, same z-rules.

## 4. Frozen evaluation (8-gate battery)

| Gate | Criterion | Pass rule |
|---|---|---|
| G1 | Full-sample sleeve SR (net) | B ≥ 1.0 |
| G2 | G7 OOS decade bins (1999-2006, 07-11, 12-16, 17-21, 22-26 → use 5 bins given data) | ≥4/5 bins SR>0; no bin >50% of total P&L |
| G3 | Scramble control (1000 permuts of weekly sleeve rets) | true SR ≥ 95th pct of scrambled |
| G4 | Cost stress 2× (20 bps/unit) | SR ≥ 0.7 |
| G5 | Correlation vs champion daily book | daily corr ≤ 0.30 (weekly→daily interpolation not valid; use weekly champion rets if derivable, else SKIP w/ note) |
| G5W | Weekly corr vs champion (if daily not derivable) | ≤ 0.30 |
| G6 | Turnover | ≤ 4× ann |
| G7 | Decade sub-periods (same as G2) | no negative decade |
| G8 | Parameter neighborhood: z-entry {1.8, 2.0, 2.2}, gate {0.4, 0.5, 0.6} | max |ΔSR| ≤ 25% of B's SR |

**Decision rule (sealed):** Arm B passes ≥6/8 gates AND beats Arm A on net SR AND
H2 confirmed (B > C by ≥0.15 SR) → PROMOTE to candidate sleeve, proceed to
champion-integration analysis (separate pre-registered round).
Any other outcome → FINDINGS.md honest verdict, no promotion.

## 5. What would falsify this direction (pre-registered)

- q_β MLE piles at floor/cap → TVP is not identified on this data → direction weak.
- Gate fires < 2% of weeks → gate is inert; B≈C; H2 dead.
- Gate fires > 60% of weeks → gate is a volatility filter in disguise; re-examine.
- B does not beat A → static z idiom already captures the premium; direction dead
  (DEAD_IDEAS.csv entry).
- Hard stop dominates P&L (stop exits > 50% of all exits) → spread non-stationarity
  too severe; weekly pairs unsuitable.

## 6. Provenance
- FRED fredgraph.csv fetched 2026-11-03 (no API key): DCOILWTICO, DCOILBRENTEU,
  DHHNGSP, PCOPPUSDM, PALUMUSDM, POILBREUSDM, BAMLC0A0CM, BAMLH0A0HYM2,
  DGS10, DGS2, T10Y2Y, T10YIE, DFII10, GASREGW, SP500, IQ12260 (gold LBMA monthly
  1984+, backup for P3).
- Local repo CSVs (stooq-historical): xau, slv, copper_monthly, wti, brent, natgas
  under tools/quant/hedge_fund_strats/data_fred/.
- All fetched files saved under campaign/hunts/TVPVECM_HUNT1/data/ with sha256
  recorded post-build.

**Sealed by:** operator instruction 2026-11-03 ("you should do everything").
All hyperparameters above are frozen. No peeking, no re-tuning after arms run.
