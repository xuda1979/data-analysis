#!/usr/bin/env python3
"""F13F_CROWDING_HUNT1 — frozen measurement artifact (SINGLE RUN, precommit §4-§6).

Implements FINDINGS_PRECOMMIT.md EXACTLY: §4.1 holdings panel (units-era rule,
cont-row cusip forward-fill within filing, per-filing cusip-level HHI/TOP10,
amendment rule (report_date, acceptance) last-wins); §4.2 composite step series
on bdate_range 2006-01-02..2026-12-31 (acceptance <= d, NaN if <3 managers
active) + 1260/252 rolling z of LEVEL, as-of reindex to champion grid; §4.3
first-stage environment-stability gate (IS OLS champion ~ 1 + zA_{t-1};
Alexander-Govern + Brown-Forsythe across 4 pinned IS blocks; p_first =
max(p_AG, p_BF) >= 0.05 else NEGATIVE, fail-closed, NO overlay measured);
§4.4 arms A/C/P/N (HIGH-side hysteresis: de-risk z_{t-1} > +1.0 -> g=0.7,
re-risk z_{t-1} <= +0.7 -> g=1.0; P time-reversed zA; N iid N(0,1) seed
20261108; 6.4 bps full |dg|, T+1, NaN -> HOLD); §4.5 collapse branch vs dead
KW g-series (>=95% match at 1e-6 -> refuted); §5 gates G0-G6 + adoption extras
(report-only) + report-only sections; §6 activity band 2%-60%. One frozen run,
no re-runs, no re-tuning after unblinding (TVPVECM_HUNT1 precedent;
KW_TERMPREMIA_HUNT1 / ICP_CAUSAL_HUNT1 patterns).
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
WORK = HERE / "work"
CHAMP_CSV = HERE.parent.parent / "results" / "GOAL100_RAWEW13v2_WEIGHTED_GEAR16_daily.csv"
KW_WORK = HERE.parent / "KW_TERMPREMIA_HUNT1" / "work"

COST_BPS = 6.4            # one-side, full |dg| (§3)
N_SEED = 20261108         # arm N seed (§4.4; KW 20261106, ICP 20261107)
Z_WIN, Z_MINP = 1260, 252
HI, RE_LO, G_CUT = 1.0, 0.7, 0.7     # HIGH-side rule (§4.2)
ACT_MIN, ACT_MAX = 0.02, 0.60        # §6 activity band
ALPHA = 0.05                         # §4.3 first-stage level
MANAGERS = ["appaloosa", "berkshire", "bridgewater", "paulson",
            "renaissance", "southeastern"]
STEP_START, STEP_END = "2006-01-02", "2026-12-31"

CHAMP_SHA = "a8ed233bd0f6fd5dad4056fda8fbd4cdde10d87ca4886c104c25b93c8014fbf4"
HOLD_SHA = {
    "berkshire": "2a2c15902adbf519e287eb0b838371d17f2516b05db19120cd0714ced50c4007",
    "bridgewater": "52260cb344cf884d200a2589dc7ea047e19eba12a4be4b397efb92433c79160e",
    "paulson": "f809d2d46de50f7e9d983255af5c213902881cd6006530e5ad62cb1e4b9eb9d6",
    "renaissance": "0479a3f421f13bd0aa57a6d6491f27b2a54ae770e24630064cb4560d9624be9c",
    "southeastern": "525227641ead1538e00c43016ffaf2dfd3a475caeb5e7cd4f74aae73f12a0d39",
    "appaloosa": "59118438797d1c90915286d1f6f748fffc0015812dbb6182aa01970434ee7e77",
}
PIN = {"SR": 3.7844894672049048, "CAGR": 0.23860978396835986,
       "MDD": -0.03304849169440516}
BLOCK_END = ["2010-06-07", "2012-08-15", "2014-10-23", "2016-12-30"]  # b1..b4 (§4.3)
G0_WINDOWS = [("E1", "2023-12-28", "2024-01-11", 11),
              ("E2", "2018-06-20", "2018-06-25", 4),
              ("E3", "2026-03-10", "2026-03-17", 6)]
KW_ARMS = ["A", "B", "C"]
KW_G_SHA16 = {"A": "cc49cfba4664cef5", "B": "1f9d77019459089c",
              "C": "b4fa8aefde66d8be"}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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


def run_arm(champ, z, hi, re_lo, g_cut):
    """HIGH-side hysteresis de-risk on champion-grid z. T+1 (z at t-1); NaN -> HOLD.

    De-risk when z_{t-1} > hi (crowding extreme); re-risk when z_{t-1} <= re_lo.
    """
    n = len(champ)
    g = np.ones(n)
    state, toggles = 1.0, 0
    for i in range(1, n):
        zi = z.iloc[i - 1]
        if not np.isnan(zi):
            if state == 1.0 and zi > hi:
                state, toggles = g_cut, toggles + 1
            elif state == g_cut and zi <= re_lo:
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


def sr_of(r):
    return float(r.mean() / r.std(ddof=1) * np.sqrt(252))


def build_filing_features():
    """§4.1 holdings panel -> per-(manager, accession) HHI/TOP10.

    Units-era rule (value x1000 if units=='K', frozen per row); cont-row cusip
    forward-fill within filing (row_idx order); still-null-cusip rows dropped
    (counted, not fixed); cusip-level value aggregate per filing (sub-accounts
    merged, instrument-blind — putCall/PRN included per §8.7).
    """
    feats, dropped, zero_tot, n_acc = {}, {}, {}, {}
    for mgr in MANAGERS:
        path = DATA / f"holdings_{mgr}.csv.gz"
        if sha256_file(path) != HOLD_SHA[mgr]:
            raise SystemExit(f"holdings sha256 pin broken: {mgr}")
        df = pd.read_csv(path, dtype={"cik": str, "accession": str, "cusip": str},
                         low_memory=False)
        df["acceptance"] = pd.to_datetime(df["acceptance_dt"]).dt.tz_localize(
            None).dt.normalize()
        df["value_dollars"] = df["value"].astype(float) * np.where(
            df["units"] == "K", 1000.0, 1.0)
        df = df.sort_values(["accession", "row_idx"], kind="mergesort")
        df["cusip"] = df.groupby("accession", sort=False)["cusip"].ffill()
        n0 = len(df)
        df = df[df["cusip"].notna() & df["value_dollars"].notna()]
        dropped[mgr] = int(n0 - len(df))
        n_acc[mgr] = int(df["accession"].nunique())
        zf = 0
        for acc, sub in df.groupby("accession", sort=False):
            v = sub.groupby("cusip")["value_dollars"].sum()
            tot = float(v.sum())
            if tot <= 0:
                zf += 1
                continue
            w = v / tot
            first = sub.iloc[0]
            feats[(mgr, acc)] = {
                "acceptance": first["acceptance"],
                "report_date": str(first["report_date"]),
                "HHI": float((w ** 2).sum()),
                "TOP10": float(w.nlargest(10).sum()),
            }
        zero_tot[mgr] = zf
    diag = {"dropped_no_cusip": dropped, "zero_total_filings": zero_tot,
            "unique_accessions": n_acc}
    return feats, diag


def build_composite(feats, champ):
    """§4.2 composite step series + traded states.

    Step grid: bdate_range 2006-01-02..2026-12-31. Per manager: filings sorted
    by (report_date, acceptance); slice-assign HHI/TOP10 to all step days >=
    acceptance, later filing overwrites earlier (most-recent-quarter,
    amended-version-wins). Composite = equal-weight mean over managers with an
    active filing; NaN if < 3 active. z = 1260/252 rolling z of LEVEL on the
    full step series (KW convention), as-of reindex to champion grid.
    """
    step = pd.bdate_range(STEP_START, STEP_END)
    per_mgr = {}
    for mgr in MANAGERS:
        rows = [(v["report_date"], v["acceptance"], v["HHI"], v["TOP10"])
                for (m, _a), v in feats.items() if m == mgr]
        rows.sort(key=lambda r: (r[0], r[1]))
        hhi = np.full(len(step), np.nan)
        top10 = np.full(len(step), np.nan)
        for rep, acc, h, t10 in rows:
            start = step.searchsorted(acc, side="left")
            if start < len(step):
                hhi[start:] = h
                top10[start:] = t10
        per_mgr[mgr] = (pd.Series(hhi, index=step),
                        pd.Series(top10, index=step))
    H = pd.concat({m: per_mgr[m][0] for m in MANAGERS}, axis=1)
    T = pd.concat({m: per_mgr[m][1] for m in MANAGERS}, axis=1)
    nact = H.notna().sum(axis=1)
    comp_hhi = H.mean(axis=1).where(nact >= 3)
    comp_top10 = T.mean(axis=1).where(nact >= 3)
    zA = reindex_to_champ(zscore_full(comp_hhi), champ)
    zC = reindex_to_champ(zscore_full(comp_top10), champ)
    diag = {
        "step_days": int(len(step)),
        "composite_first_valid": str(comp_hhi.dropna().index[0].date()),
        "managers_active_first": int(nact.iloc[0]),
        "per_mgr_mean_HHI": {m: float(per_mgr[m][0].mean()) for m in MANAGERS},
        "per_mgr_mean_TOP10": {m: float(per_mgr[m][1].mean()) for m in MANAGERS},
        "per_mgr_active_days": {m: int(per_mgr[m][0].notna().sum())
                                for m in MANAGERS},
        "zA_nan_on_champ": int(zA.isna().sum()),
        "zC_nan_on_champ": int(zC.isna().sum()),
    }
    return zA, zC, diag


def first_stage(champ, zA, is_m):
    """§4.3 environment-stability gate: IS OLS champion ~ 1 + zA_{t-1};
    Alexander-Govern + Brown-Forsythe across 4 pinned IS blocks.
    p_first = max(p_AG, p_BF) >= 0.05 else NEGATIVE (fail-closed, row-78 wall).
    """
    y = champ[is_m]
    x = zA[is_m].shift(1)
    ok = x.notna()
    yv, xv = y[ok].values, x[ok].values
    beta, resid = ols_fit(yv, [xv])
    b_arr = np.array([np.datetime64(d) for d in BLOCK_END])
    dates = y.index[ok].values.astype("datetime64[D]")
    blk = np.searchsorted(b_arr, dates, side="left")
    groups = [resid[blk == b] for b in range(4)]
    p_ag = float(stats.alexandergovern(*groups).pvalue)
    p_bf = float(stats.levene(*groups, center="median").pvalue)
    p_first = max(p_ag, p_bf)
    return {
        "reg_rows": int(ok.sum()),
        "first_stage_dropped_shift": int((~ok).sum()),
        "block_ns": [int(len(gg)) for gg in groups],
        "beta": [float(b) for b in beta],
        "p_alexandergovern": p_ag,
        "p_brownforsythe": p_bf,
        "p_first": p_first,
        "pass": bool(p_first >= ALPHA),
    }


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

    feats, hold_diag = build_filing_features()
    zA, zC, comp_diag = build_composite(feats, champ)
    fs = first_stage(champ, zA, is_m)
    (WORK / "first_stage.json").write_text(json.dumps(fs, indent=2) + "\n")
    print(f"[first-stage] reg_rows={fs['reg_rows']} block_ns={fs['block_ns']} "
          f"p_AG={fs['p_alexandergovern']:.6g} p_BF={fs['p_brownforsythe']:.6g} "
          f"p_first={fs['p_first']:.6g} pass={fs['pass']}")
    if not fs["pass"]:
        rec = {"first_stage": fs, "holdings": hold_diag, "composite": comp_diag,
               "arms": None,
               "mechanical_verdict": "NEGATIVE_FIRST_STAGE_FAIL (row-78 wall; "
                                     "no overlay measured, §4.3 fail-closed)"}
        (WORK / "arm_results.json").write_text(json.dumps(rec, indent=2) + "\n")
        print("[verdict] NEGATIVE_FIRST_STAGE_FAIL — no overlay measured")
        return

    # §4.4 arms (single frozen run)
    rng = np.random.default_rng(N_SEED)
    zN = pd.Series(rng.standard_normal(len(champ)), index=champ.index)
    zP = pd.Series(zA.values[::-1], index=champ.index)
    arms = {"A": (zA, "composite_HHI z-state"),
            "C": (zC, "composite_TOP10 z-state"),
            "P": (zP, "time-reversed control (zA reversed)"),
            "N": (zN, "iid N(0,1) control")}
    for name in ("P", "N"):
        assert arms[name][0].isna().sum() == 0, f"control {name} has NaN"

    # §4.5 KW comparators (axis-closure guard)
    kw_g = {}
    for a in KW_ARMS:
        p = KW_WORK / f"g_{a}.csv"
        if sha256_file(p)[:16] != KW_G_SHA16[a]:
            raise SystemExit(f"KW g_{a} sha16 pin broken")
        kw_g[a] = pd.read_csv(p, index_col=0, parse_dates=True).iloc[:, 0]
        if len(kw_g[a]) != 4806:
            raise SystemExit(f"KW g_{a} rows {len(kw_g[a])} != 4806")

    treat = ("A", "C")
    recs = {}
    for name, (z, _desc) in arms.items():
        arm = run_arm(champ, z, HI, RE_LO, G_CUT)
        g, m = arm["g"], metrics(arm["ret"])
        frac_derisk = float((g < 1.0).mean())
        # G0 drawdown-overlap pre-screen
        g0w = {}
        for tag, d0, d1, nn in G0_WINDOWS:
            msk = (g.index >= pd.Timestamp(d0)) & (g.index <= pd.Timestamp(d1))
            if int(msk.sum()) != nn:
                raise SystemExit(f"G0 window {tag} sessions {int(msk.sum())} != {nn}")
            g0w[tag] = float((g[msk] < 1.0).mean())
        # §4.5 collapse + correlations (report-only)
        match = {a: float(((g - kw_g[a]).abs() < 1e-6).mean()) for a in KW_ARMS}
        collapse_refuted = any(v >= 0.95 for v in match.values())
        kw_corr = {a: {"pearson": float(stats.pearsonr(g, kw_g[a]).statistic),
                       "spearman": float(stats.spearmanr(g, kw_g[a]).statistic)}
                   for a in KW_ARMS}
        recs[name] = {
            "desc": arms[name][1],
            "toggles": arm["toggles"],
            "frac_sessions_derisked": frac_derisk,
            "activity_band_ok": bool(ACT_MIN <= frac_derisk <= ACT_MAX),
            "g0_windows": g0w,
            "G0": any(v >= 0.5 for v in g0w.values()),
            "metrics": m,
            "dSR": float(m["SR"] - base["SR"]),
            "dCAGR_pp": float((m["CAGR"] - base["CAGR"]) * 100.0),
            "ann_half_turn": arm["ann_half_turn"],
            "roll252_half_turn": arm["roll252_half_turn"],
            "G1": bool(m["SR"] - base["SR"] >= 0.15),
            "G2": bool((base["CAGR"] - m["CAGR"]) <= 0.005),
            "G3": bool(abs(m["MDD"]) <= abs(PIN["MDD"]) + 0.01),
            "G4": bool(arm["ann_half_turn"] <= 1.0),
            "G5": bool(arm["roll252_half_turn"] <= 1.5),
            "kw_match_frac": match,
            "collapse_refuted": bool(collapse_refuted),
            "kw_corr": kw_corr,
            "A_R1_mdd_strictly_shallower": bool(m["MDD"] > PIN["MDD"]),
            "A_R2_zero_neg_years": bool(m["neg_years"] == 0),
        }
        # report-only: IS/OOS dSR split, decade bins, cost stress 8/10 bps
        r = arm["ret"]
        recs[name]["report_is_oos_dSR"] = {
            "IS": sr_of(r[is_m]) - sr_of(champ[is_m]),
            "OOS": sr_of(r[~is_m]) - sr_of(champ[~is_m]),
        }
        dec = np.asarray(champ.index.year) // 10 * 10
        dec_out = {}
        for d in np.unique(dec):
            msk = dec == d
            if int(msk.sum()) < 252:
                continue
            dec_out[f"{d}s"] = {"SR": sr_of(r[msk]), "champ_SR": sr_of(champ[msk])}
        recs[name]["report_decades"] = dec_out
        dg = g.diff().fillna(0.0)
        recs[name]["report_cost_stress"] = {}
        for bps in (8.0, 10.0):
            rs = g * champ - dg.abs() * (bps / 10000.0)
            recs[name]["report_cost_stress"][f"{int(bps)}bps"] = {
                "SR": sr_of(rs), "dSR": sr_of(rs) - base["SR"]}
        g.rename("g").to_csv(WORK / f"g_{name}.csv")
        arm["ret"].rename("ret").to_csv(WORK / f"ret_{name}.csv")

    # §5 G6 machinery validity + sealed decision rule
    ctrl_pass = [n for n in ("P", "N") if recs[n]["G1"]]
    g6 = len(ctrl_pass) == 0
    if not g6:
        verdict = ("MACHINERY_INVALID_VOID (control passed G1: "
                   + ",".join(ctrl_pass) + ")")
    else:
        eligible = [n for n in treat if recs[n]["activity_band_ok"]
                    and not recs[n]["collapse_refuted"]
                    and all(recs[n][gk] for gk in ("G0", "G1", "G2",
                                                   "G3", "G4", "G5"))]
        verdict = ("PROMOTION_CANDIDATE:" + ",".join(eligible)) if eligible \
            else "NEGATIVE"
    out = {"champion": {k: base[k] for k in ("SR", "CAGR", "MDD", "neg_years",
                                             "worst_year")},
           "first_stage": fs, "holdings": hold_diag, "composite": comp_diag,
           "G6": g6, "arms": recs, "verdict": verdict}
    (WORK / "arm_results.json").write_text(json.dumps(out, indent=2) + "\n")
    for name in ("A", "C", "P", "N"):
        r = recs[name]
        print(f"[arm {name}] frac_derisk={r['frac_sessions_derisked']:.4f} "
              f"toggles={r['toggles']} G0={r['G0']} ("
              + " ".join(f"{t}={v:.2f}" for t, v in r["g0_windows"].items())
              + f") G1={r['G1']} G2={r['G2']} G3={r['G3']} G4={r['G4']} "
              f"G5={r['G5']} dSR={r['dSR']:+.4f} dCAGR_pp={r['dCAGR_pp']:+.3f} "
              f"annHT={r['ann_half_turn']:.4f} rollHT={r['roll252_half_turn']:.4f} "
              f"collapse={r['collapse_refuted']}")
    print(f"[G6] {g6}")
    print(f"[verdict] {verdict}")


if __name__ == "__main__":
    main()
