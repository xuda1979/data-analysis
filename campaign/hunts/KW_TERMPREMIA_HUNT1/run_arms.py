#!/usr/bin/env python
"""KW_TERMPREMIA_HUNT1 — frozen-arm runner.

Implements FINDINGS_PRECOMMIT.md sections 3-5 EXACTLY. Sealed 2026-11-06
(sha256 sidecar in repo; commit e96d87c). No hyperparameter may change here.

Conventions (precommit sec. 3):
  SR   = mean/std(ddof=1) * sqrt(252)
  CAGR = exp(252 * mean(ln(1+r))) - 1          (geometric headline)
  MDD  = min(NAV/cummax(NAV) - 1), NAV = (1+r).cumprod()
  Years = (1+r).groupby(year).prod() - 1
  Cost: FULL |dg| * 6.4 bps one-side; freed capital earns 0%
  Causality: g_t set from data through t-1 (shift(1)); g_0 = 1.0
  NaN signal after ffill(5) -> HOLD previous exposure (no toggle, no cost)

Arms (precommit sec. 4): A, B, C, P (placebo time-reversed), N (random
seed 20261106). Gates G1-G6 + A-R1/A-R2 (precommit sec. 5).
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
WORK = HERE / "work"
CHAMP_CSV = HERE.parent.parent / "results" / "GOAL100_RAWEW13v2_WEIGHTED_GEAR16_daily.csv"

COST_BPS = 6.4  # one-side, full book, precommit sec. 3


def load_champion() -> pd.Series:
    s = pd.read_csv(CHAMP_CSV, index_col=0, parse_dates=True)["ret"]
    s = s.sort_index()
    if len(s) != 4806:
        raise SystemExit(f"champion rows {len(s)} != 4806 (hash pin broken?)")
    return s


def load_fred(series: str) -> pd.Series:
    df = pd.read_csv(DATA / f"fred_{series}.csv", index_col=0, parse_dates=True)
    return df[series].sort_index()


def zscore_full(s: pd.Series, win: int = 1260, minp: int = 252) -> pd.Series:
    """z on the FULL FRED daily series (1990+), precommit sec. 4.1."""
    m = s.rolling(win, min_periods=minp).mean()
    sd = s.rolling(win, min_periods=minp).std(ddof=1)
    return (s - m) / sd


def reindex_to_champ(z: pd.Series, champ: pd.Series) -> pd.Series:
    """Last defined obs <= date, ffill limit 5 BUSINESS days, precommit sec. 4.1."""
    z = z.dropna()
    z = z[~z.index.duplicated(keep="last")]
    idx = champ.index
    pos = z.index.searchsorted(idx, side="right") - 1
    ok = pos >= 0
    safe = np.where(ok, pos, 0)
    src_dates = z.index.values[safe].astype("datetime64[D]")
    vals = z.values[safe]
    gap_bdays = np.busday_count(src_dates, idx.values.astype("datetime64[D]"))
    stale = (~ok) | (gap_bdays > 5)
    return pd.Series(np.where(stale, np.nan, vals), index=idx)


def build_z_matrix(champ: pd.Series, rng_seed: int = 20261106) -> dict:
    """Return dict of raw (pre-shift) signal series on champion dates."""
    tp10 = load_fred("THREEFYTP10")
    tp1 = load_fred("THREEFYTP1")

    out = {}
    out["A_B_TP10"] = zscore_full(tp10)
    out["C_TP10mTP1"] = zscore_full(tp10 - tp1)

    # Arm P: time-reversed TP10 z (precommit sec. 4.2).
    z_fwd = zscore_full(tp10)
    z_rev = z_fwd.iloc[::-1].copy()
    z_rev.index = z_fwd.index  # reversed values on original dates
    out["P"] = z_rev

    # Arm N: iid N(0,1) noise, numpy seed 20261106, on the TP10 index.
    rng = np.random.default_rng(rng_seed)
    noise = pd.Series(rng.standard_normal(len(tp10)), index=tp10.index)
    out["N"] = noise
    return out


def run_arm(champ: pd.Series, z_raw: pd.Series, lo: float, re_hi: float,
            g_cut: float) -> dict:
    """Binary de-risk overlay with hysteresis. Returns metrics dict.

    g: 1.0 -> g_cut when z < lo ; g_cut -> 1.0 when z >= re_hi
    Causal: g_t from signal through t-1 (shift(1)); g_0 = 1.0.
    """
    z = reindex_to_champ(z_raw, champ)

    n = len(champ)
    g = np.ones(n)
    state = 1.0
    toggles = 0
    for i in range(1, n):
        zi = z.iloc[i - 1]  # data through t-1
        if not np.isnan(zi):
            if state == 1.0 and zi < lo:
                state = g_cut
                toggles += 1
            elif state == g_cut and zi >= re_hi:
                state = 1.0
                toggles += 1
        g[i] = state
    g = pd.Series(g, index=champ.index)

    dg = g.diff().fillna(g.iloc[0] - 1.0)
    cost = dg.abs() * (COST_BPS / 10000.0)
    r = g * champ - cost

    tau = dg.abs() / 2.0
    ann_half_turn = (252.0 / n) * tau.sum()
    roll252 = tau.rolling(252).sum().max()

    return {
        "ret": r, "g": g, "toggles": toggles,
        "ann_half_turn": ann_half_turn, "roll252_half_turn": roll252,
    }


def metrics(r: pd.Series) -> dict:
    sr = r.mean() / r.std(ddof=1) * np.sqrt(252)
    cagr = np.exp(252 * np.log1p(r).mean()) - 1
    nav = (1 + r).cumprod()
    mdd = (nav / nav.cummax() - 1).min()
    yr = (1 + r).groupby(r.index.year).prod() - 1
    return {
        "SR": sr, "CAGR": cagr, "MDD": mdd,
        "neg_years": int((yr < 0).sum()), "worst_year": yr.min(),
    }


def main() -> None:
    WORK.mkdir(exist_ok=True)
    champ = load_champion()
    base = metrics(champ)
    print("champion:", json.dumps({k: (v if isinstance(v, int) else round(float(v), 6))
                                   for k, v in base.items()}))

    zmat = build_z_matrix(champ)

    ARMS = {
        "A": ("A_B_TP10", -1.0, -0.5, 0.7),
        "B": ("A_B_TP10", -1.5, -0.75, 0.5),
        "C": ("C_TP10mTP1", -1.0, -0.5, 0.7),
        "P": ("P", -1.0, -0.5, 0.7),
        "N": ("N", -1.0, -0.5, 0.7),
    }

    results = {"champion": base, "arms": {}}
    for name, (zkey, lo, hi, cut) in ARMS.items():
        run = run_arm(champ, zmat[zkey], lo, hi, cut)
        m = metrics(run["ret"])
        frac_derisk = float((run["g"] < 1.0).mean())
        rec = {
            **m,
            "dSR": m["SR"] - base["SR"],
            "dCAGR_pp": (m["CAGR"] - base["CAGR"]) * 100,
            "dMDD_pp": (m["MDD"] - base["MDD"]) * 100,
            "ann_half_turn": run["ann_half_turn"],
            "roll252_half_turn": run["roll252_half_turn"],
            "toggles": run["toggles"],
            "frac_sessions_derisked": frac_derisk,
        }
        results["arms"][name] = rec
        print(f"arm {name}:", json.dumps({k: (v if isinstance(v, int) else round(float(v), 6))
                                          for k, v in rec.items()}))
        run["g"].to_csv(WORK / f"g_{name}.csv")
        run["ret"].to_csv(WORK / f"ret_{name}.csv")

    # Gates (precommit sec. 5)
    gates = {}
    for name, rec in results["arms"].items():
        g = {
            "G1_dSR_ge_0.15": rec["dSR"] >= 0.15,
            "G2_cagr_sacrifice_le_0.5pp": rec["dCAGR_pp"] >= -0.5,
            "G3_mdd_le_champ_plus_1pp": rec["MDD"] >= base["MDD"] - 0.01,
            "G4_ann_half_turn_le_1.0": rec["ann_half_turn"] <= 1.0,
            "G5_roll252_le_1.5": rec["roll252_half_turn"] <= 1.5,
        }
        gates[name] = g
    # G6 discriminancy: P and N both FAIL G1
    gates["G6_P_and_N_fail_G1"] = (not gates["P"]["G1_dSR_ge_0.15"]) and \
                                  (not gates["N"]["G1_dSR_ge_0.15"])

    results["gates"] = gates
    with open(WORK / "arm_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)

    print("\ngates:", json.dumps(gates, indent=2, default=str))

    # Falsification criteria (precommit sec. 6)
    for name in ("A", "B", "C"):
        rec = results["arms"][name]
        frac = rec["frac_sessions_derisked"]
        if frac < 0.02:
            print(f"FALSIFY {name}: de-risk active {frac:.4f} < 2% (inert)")
        elif frac > 0.60:
            print(f"FALSIFY {name}: de-risk active {frac:.4f} > 60% (regime label)")


if __name__ == "__main__":
    sys.exit(main())
