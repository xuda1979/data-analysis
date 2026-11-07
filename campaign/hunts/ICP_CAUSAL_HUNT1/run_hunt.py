#!/usr/bin/env python3
"""ICP_CAUSAL_HUNT1 — frozen measurement artifact (SINGLE RUN, precommit §4-§6).

Implements FINDINGS_PRECOMMIT.md EXACTLY: §4.1 one-shot 8-subset linear ICP
(AG+BF invariance, 4 date-pinned IS blocks, alpha=0.05); §4.2 z-state hysteresis
overlay (1260/252 rolling z of LEVEL, lo -1.0 / re 0.7 / g_cut 0.7, mirror if
beta<0, 6.4 bps full |dg|, T+1, NaN->HOLD); §4.3 arms A/C/P/N (N seed 20261107);
§4.4 collapse branch vs dead KW g-series (>=95% match at 1e-6 -> refuted);
§5 gates G0-G6 + adoption extras (report-only) + report-only sections; §6
activity band 2%-60%. Selection runs ONCE, IS-only. No re-runs, no re-tuning
after unblinding (TVPVECM_HUNT1 precedent; KW_TERMPREMIA_HUNT1 pattern).
"""
import hashlib
import json
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
WORK = HERE / "work"
CHAMP_CSV = HERE.parent.parent / "results" / "GOAL100_RAWEW13v2_WEIGHTED_GEAR16_daily.csv"
KW_WORK = HERE.parent / "KW_TERMPREMIA_HUNT1" / "work"

COST_BPS = 6.4           # one-side, full |dg| (§3)
ALPHA = 0.05             # ICP acceptance level (§4.1)
N_SEED = 20261107        # arm N seed (§4.3; KW used 20261106)
Z_WIN, Z_MINP = 1260, 252
LO, RE_HI, G_CUT = -1.0, 0.7, 0.7
ACT_MIN, ACT_MAX = 0.02, 0.60
CANDIDATES = ["DTWEXBGS", "DGS3MO", "T10YIE"]   # alphabetical tie-break order (§4.1)
CAND_RANK = {"DTWEXBGS": 0, "DGS3MO": 1, "T10YIE": 2}

CHAMP_SHA = "a8ed233bd0f6fd5dad4056fda8fbd4cdde10d87ca4886c104c25b93c8014fbf4"
FRED_SHA = {
    "DTWEXBGS": "908a19a96d1ba529ef51ae559b8bc384bf8af4d4013185426e5ee9c3cca4213f",
    "T10YIE": "5b669e4b20edd027e94c36ae0654151d08afd22d7eed13f5d6f5ec9093942233",
    "DGS3MO": "488f612215354356411de73118868f7123ec588f133e5388d58fc0143edc9241",
}
PIN = {"SR": 3.7844894672049048, "CAGR": 0.23860978396835986,
       "MDD": -0.03304849169440516}
BLOCK_END = ["2010-06-07", "2012-08-15", "2014-10-23", "2016-12-30"]  # b1..b4 (§4.1)
G0_WINDOWS = [("E1", "2023-12-28", "2024-01-11", 11),
              ("E2", "2018-06-20", "2018-06-25", 4),
              ("E3", "2026-03-10", "2026-03-17", 6)]
KW_ARMS = ["A", "B", "C"]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_fred(path):
    """Defensive FRED loader (verify_prereqs.py pattern; pinned row counts)."""
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    s = df.iloc[:, 0].apply(pd.to_numeric, errors="coerce")
    s = s.replace([np.inf, -np.inf], np.nan).dropna()
    return s.sort_index()


def zscore_full(s, win=Z_WIN, minp=Z_MINP):
    m = s.rolling(win, min_periods=minp).mean()
    sd = s.rolling(win, min_periods=minp).std(ddof=1)
    return (s - m) / sd


def reindex_to_champ(z, champ):
    """numpy-safe last-obs<=date, ffill <= 5 bd (KW pattern)."""
    z = z.dropna()
    z = z[~z.index.duplicated(keep="last")]
    idx = champ.index
    pos = z.index.searchsorted(idx, side="right") - 1
    ok = pos >= 0
    safe = np.where(ok, pos, 0)
    src = z.index.values[safe].astype("datetime64[D]")
    vals = z.values[safe]
    gap = np.busday_count(src, idx.values.astype("datetime64[D]"))
    stale = (~ok) | (gap > 5)
    return pd.Series(np.where(stale, np.nan, vals), index=idx)


def metrics(r):
    sr = r.mean() / r.std(ddof=1) * np.sqrt(252)
    cagr = np.exp(252 * np.log1p(r).mean()) - 1
    nav = (1 + r).cumprod()
    mdd = float((nav / nav.cummax() - 1).min())
    yrs = (1 + r).groupby(r.index.year).prod() - 1
    return {"SR": float(sr), "CAGR": float(cagr), "MDD": mdd,
            "neg_years": int((yrs < 0).sum()), "worst_year": float(yrs.min())}


def run_arm(champ, z, lo, re_hi, g_cut):
    """Hysteresis de-risk on champion-grid z. T+1 (z at t-1); NaN -> HOLD."""
    n = len(champ)
    g = np.ones(n)
    state, toggles = 1.0, 0
    for i in range(1, n):
        zi = z.iloc[i - 1]
        if not np.isnan(zi):
            if state == 1.0 and zi < lo:
                state, toggles = g_cut, toggles + 1
            elif state == g_cut and zi >= re_hi:
                state, toggles = 1.0, toggles + 1
        g[i] = state
    g = pd.Series(g, index=champ.index)
    dg = g.diff().fillna(g.iloc[0] - 1.0)
    r = g * champ - dg.abs() * (COST_BPS / 10000.0)
    tau = dg.abs() / 2.0
    return {"ret": r, "g": g, "toggles": int(toggles),
            "ann_half_turn": float((252.0 / n) * tau.sum()),
            "roll252_half_turn": float(tau.rolling(252).sum().max())}


def ols_fit(y, X):
    """OLS with intercept. X: list of 1-d arrays (may be empty)."""
    M = np.column_stack([np.ones(len(y))] + list(X)) if X else np.ones((len(y), 1))
    beta, *_ = np.linalg.lstsq(M, y, rcond=None)
    return beta, y - M @ beta


def run_icp(df):
    """§4.1 one-shot linear ICP on IS rows (df: y + candidate parents)."""
    y = df["y"].values
    cols = {c: df[c].values for c in CANDIDATES}
    b_arr = np.array([np.datetime64(d) for d in BLOCK_END])
    dates = df.index.values.astype("datetime64[D]")
    blk = np.searchsorted(b_arr, dates, side="left")  # 0..3 by pinned boundaries
    if blk.max() != 3 or blk.min() != 0:
        raise SystemExit(f"IS block assignment broken: {np.bincount(blk)}")
    subsets, p_by, accepted, coef_by = [], {}, [], {}
    for k in range(len(CANDIDATES) + 1):
        for S in combinations(CANDIDATES, k):
            beta, resid = ols_fit(y, [cols[c] for c in S])
            groups = [resid[blk == b] for b in range(4)]
            p_ag = float(stats.alexandergovern(*groups).pvalue)
            p_bf = float(stats.levene(*groups, center="median").pvalue)
            p_s = max(p_ag, p_bf)
            subsets.append({"subset": "+".join(S) if S else "EMPTY",
                            "p_AG": p_ag, "p_BF": p_bf, "p_S": p_s,
                            "accepted": bool(p_s >= ALPHA),
                            "coef": {"intercept": float(beta[0]),
                                     **{c: float(b) for c, b in zip(S, beta[1:])}}})
            p_by[frozenset(S)] = p_s
            coef_by[frozenset(S)] = {c: float(b) for c, b in zip(S, beta[1:])}
            if p_s >= ALPHA:
                accepted.append(frozenset(S))
    out = {"n_rows": int(len(y)),
           "block_ns": {f"b{i+1}": int((blk == i).sum()) for i in range(4)},
           "subsets": subsets}
    if not accepted:
        out.update({"branch": "no_subset_accepted", "S_star": [],
                    "verdict": "NEGATIVE_MECHANISM_FAILURE"})
        return out
    s_star = set.intersection(*accepted)
    if not s_star:
        out.update({"branch": "empty_set", "S_star": [],
                    "verdict": "NEGATIVE_EMPTY_SET"})
        return out
    out["S_star"] = sorted(s_star)
    out["beta"] = coef_by[frozenset(s_star)]  # pooled-IS OLS on ALL of S*
    if len(s_star) == 1:
        out.update({"branch": "selected_single",
                    "A": next(iter(s_star)), "C": None, "verdict": None})
    else:
        loo = {v: p_by[frozenset(s_star - {v})] for v in s_star}
        ranked = sorted(s_star, key=lambda v: (loo[v], CAND_RANK[v]))
        out.update({"branch": "selected_multi", "A": ranked[0], "C": ranked[1],
                    "loo_p": {v: float(loo[v]) for v in loo}, "verdict": None})
    return out


def sr_of(r):
    return float(r.mean() / r.std(ddof=1) * np.sqrt(252))


def main():
    WORK.mkdir(exist_ok=True)
    if sha256_file(CHAMP_CSV) != CHAMP_SHA:
        raise SystemExit("champion sha256 pin broken")
    champ = pd.read_csv(CHAMP_CSV, index_col=0, parse_dates=True)["ret"].sort_index()
    if len(champ) != 4806:
        raise SystemExit(f"champion rows {len(champ)} != 4806")
    base = metrics(champ)
    for k in ("SR", "CAGR", "MDD"):
        if not np.isclose(base[k], PIN[k], atol=1e-9):
            raise SystemExit(f"champion {k} pin broken: {base[k]}")
    is_m = champ.index < pd.Timestamp("2017-01-01")
    if int(is_m.sum()) != 2286 or int((~is_m).sum()) != 2520:
        raise SystemExit("IS/OOS split pin broken")
    pos4 = np.array_split(np.arange(int(is_m.sum())), 4)
    is_idx = champ.index[is_m]
    bounds = [str(is_idx[p[-1]].date()) for p in pos4]
    if bounds != BLOCK_END:
        raise SystemExit(f"IS block boundaries drifted: {bounds}")

    for c in CANDIDATES:
        if sha256_file(DATA / f"fred_{c}.csv") != FRED_SHA[c]:
            raise SystemExit(f"FRED {c} sha256 pin broken")
    raw = {c: load_fred(DATA / f"fred_{c}.csv") for c in CANDIDATES}
    level = {c: reindex_to_champ(raw[c], champ) for c in CANDIDATES}
    parent = {c: level[c].diff().shift(1) for c in CANDIDATES}  # dX at t-1 on champ grid

    # §4.1 ICP row set: IS sessions with ALL parent grid-diffs defined
    df = pd.DataFrame({"y": champ, **parent})
    df = df[champ.index < pd.Timestamp("2017-01-01")].dropna()
    sel = run_icp(df)
    (WORK / "icp_selection.json").write_text(json.dumps(sel, indent=2))
    print("ICP branch:", sel["branch"], "| S* =", sel.get("S_star"),
          "| rows", sel["n_rows"], "| block_ns", sel["block_ns"])
    for s in sel["subsets"]:
        print(f"  {s['subset']:<22} p_AG={s['p_AG']:.4f} p_BF={s['p_BF']:.4f} "
              f"p_S={s['p_S']:.4f} accepted={s['accepted']}")

    results = {"branch": sel["branch"], "icp": sel, "baseline": base,
               "cost_bps": COST_BPS, "n_seed": N_SEED}
    if sel["verdict"]:  # selection-negative branch: NO overlay measured (§4.1)
        results["mechanical_verdict"] = sel["verdict"]
        (WORK / "arm_results.json").write_text(json.dumps(results, indent=2))
        print("VERDICT:", sel["verdict"], "— no overlay measured (§4.1 branch)")
        return

    # §4.2 traded signals: z of LEVEL on full raw FRED series -> champ grid
    z_champ = {c: reindex_to_champ(zscore_full(raw[c]), champ) for c in CANDIDATES}
    beta = sel["beta"]
    arms, treat = {}, ["A"]
    arms["A"] = run_arm(champ, -z_champ[sel["A"]] if beta[sel["A"]] < 0
                        else z_champ[sel["A"]], LO, RE_HI, G_CUT)
    if sel["C"]:
        arms["C"] = run_arm(champ, -z_champ[sel["C"]] if beta[sel["C"]] < 0
                            else z_champ[sel["C"]], LO, RE_HI, G_CUT)
        treat.append("C")
    z_p = pd.Series(z_champ[sel["A"]].values[::-1], index=champ.index)  # time-reversed
    arms["P"] = run_arm(champ, z_p, LO, RE_HI, G_CUT)  # unmirrored
    rng = np.random.default_rng(N_SEED)
    arms["N"] = run_arm(champ, pd.Series(rng.standard_normal(len(champ)),
                                         index=champ.index), LO, RE_HI, G_CUT)

    kw_g = {a: pd.read_csv(KW_WORK / f"g_{a}.csv", index_col=0,
                           parse_dates=True).iloc[:, 0] for a in KW_ARMS}
    mdd_lim = abs(PIN["MDD"]) + 0.01
    recs = {}
    for name, arm in arms.items():
        m = metrics(arm["ret"])
        g = arm["g"]
        frac = float((g < 1.0).mean())
        g0w = {}
        for tag, d0, d1, nn in G0_WINDOWS:
            msk = (g.index >= pd.Timestamp(d0)) & (g.index <= pd.Timestamp(d1))
            if int(msk.sum()) != nn:
                raise SystemExit(f"G0 window {tag} sessions {int(msk.sum())} != {nn}")
            g0w[tag] = float((g[msk] < 1.0).mean())
        rec = {"metrics": m, "dSR": m["SR"] - base["SR"],
               "dCAGR_pp": (m["CAGR"] - base["CAGR"]) * 100.0,
               "dMDD_pp": (m["MDD"] - base["MDD"]) * 100.0,
               "toggles": arm["toggles"], "frac_derisked": frac,
               "ann_half_turn": arm["ann_half_turn"],
               "roll252_half_turn": arm["roll252_half_turn"],
               "G0_windows_frac_derisked": g0w,
               "G0": any(v >= 0.5 for v in g0w.values()),
               "G1": bool(m["SR"] - base["SR"] >= 0.15),
               "G2": bool((base["CAGR"] - m["CAGR"]) <= 0.005),
               "G3": bool(abs(m["MDD"]) <= mdd_lim),
               "G4": bool(arm["ann_half_turn"] <= 1.0),
               "G5": bool(arm["roll252_half_turn"] <= 1.5),
               "activity_band_ok": bool(ACT_MIN <= frac <= ACT_MAX)}
        if name in treat:
            match = {a: float(((g - kw_g[a]).abs() < 1e-6).mean()) for a in KW_ARMS}
            rec["kw_match_fraction"] = match
            rec["collapse_refuted"] = any(v >= 0.95 for v in match.values())
            rec["kw_corr"] = {a: {"pearson": float(stats.pearsonr(g, kw_g[a]).statistic),
                                  "spearman": float(stats.spearmanr(g, kw_g[a]).statistic)}
                              for a in KW_ARMS}
            rec["A_R1_mdd_strictly_shallower"] = bool(m["MDD"] > base["MDD"])
            rec["A_R2_zero_neg_years"] = bool(m["neg_years"] == 0)
        recs[name] = rec
        g.rename("g").to_csv(WORK / f"g_{name}.csv")
        arm["ret"].rename("ret").to_csv(WORK / f"ret_{name}.csv")

    # report-only sections for treatment arms (§5)
    for n in treat:
        r = arms[n]["ret"]
        ro = {}
        for tag, msk in (("IS", is_m), ("OOS", ~is_m)):
            sc, sa = sr_of(champ[msk]), sr_of(r[msk])
            ro[tag] = {"champ_SR": sc, "arm_SR": sa, "dSR": sa - sc}
        recs[n]["is_oos_dSR"] = ro
        dec = np.asarray(champ.index.year) // 10 * 10
        bins = {}
        for d in sorted(set(dec.tolist())):
            msk = dec == d
            if int(msk.sum()) < 252:
                continue
            sc, sa = sr_of(champ[msk]), sr_of(r[msk])
            bins[str(d)] = {"n": int(msk.sum()),
                            "champ_cum": float((1 + champ[msk]).prod() - 1),
                            "arm_cum": float((1 + r[msk]).prod() - 1),
                            "champ_SR": sc, "arm_SR": sa, "dSR": sa - sc}
        recs[n]["decade_bins"] = bins
        dg = arms[n]["g"].diff().fillna(0.0)
        stress = {}
        for bps in (8.0, 10.0):
            rs = arms[n]["g"] * champ - dg.abs() * (bps / 10000.0)
            sa = sr_of(rs)
            stress[f"{bps:.0f}bps"] = {"arm_SR": sa, "dSR": sa - base["SR"]}
        recs[n]["cost_stress"] = stress

    ctrl_pass = [n for n in ("P", "N") if recs[n]["G1"]]
    g6 = len(ctrl_pass) == 0
    if not g6:
        verdict = "MACHINERY_INVALID_VOID (control passed G1: " + ",".join(ctrl_pass) + ")"
    else:
        eligible = [n for n in treat if recs[n]["activity_band_ok"]
                    and not recs[n]["collapse_refuted"]
                    and all(recs[n][gk] for gk in ("G0", "G1", "G2", "G3", "G4", "G5"))]
        verdict = ("PROMOTION_CANDIDATE:" + ",".join(eligible)) if eligible else "NEGATIVE"
    both_fail_g0 = all(not recs[n]["G0"] for n in treat)

    results.update({"arms": recs, "G6": g6, "controls_passing_G1": ctrl_pass,
                    "all_treatment_fail_G0": both_fail_g0,
                    "mechanical_verdict": verdict})
    (WORK / "arm_results.json").write_text(json.dumps(results, indent=2))

    print(f"\nbaseline SR {base['SR']:.4f} CAGR {base['CAGR']:.4f} MDD {base['MDD']:.5f}")
    print("beta(S*):", beta)
    for n, rec in recs.items():
        line = (f"arm {n}: SR {rec['metrics']['SR']:.4f} dSR {rec['dSR']:+.4f} "
                f"CAGR {rec['metrics']['CAGR']:.4f} MDD {rec['metrics']['MDD']:.5f} "
                f"frac_derisked {rec['frac_derisked']:.3f} toggles {rec['toggles']} "
                f"G0 {rec['G0']} G1 {rec['G1']} G2 {rec['G2']} G3 {rec['G3']} "
                f"G4 {rec['G4']} G5 {rec['G5']} act {rec['activity_band_ok']}")
        if n in treat:
            line += f" collapse {rec['collapse_refuted']}"
        print(line)
    print("G0 window fracs:", {n: recs[n]["G0_windows_frac_derisked"] for n in treat})
    print("G6 (P and N both fail G1):", g6)
    print("VERDICT:", verdict)


if __name__ == "__main__":
    main()
