"""META_LABEL_HUNT1 frozen measurement run (single run, sealed spec).

Implements FINDINGS_PRECOMMIT.md §4 EXACTLY (seal 2026-11-13, commit 5a38038).
No hyperparameter may change post-seal: c=2.5, band [0.5,1.5], halflife 5,
ridge 1e-6, max 50 IRLS iterations, gradient tol 1e-10, N seed 20261113,
identity threshold 1e-12 (fail-closed), IS < 2017-01-01,
window 2008-03-31..2026-08-28, C5ngsum <= 2026-08-24, CFX4 relw 0.

Order of operations (§4.5 + §5): G-1 identity FIRST (abort if RED before any
arm is built) -> arms M/V/P/N -> gates G0-G7 -> work/arm_results.json +
work/run_stdout.txt.

Run: .venv/bin/python campaign/hunts/META_LABEL_HUNT1/work/run_hunt.py
"""
import hashlib
import importlib.util
import json
import sys

import numpy as np
import pandas as pd

ROOT = "/home/david/software/world-trader"
BUILDER = f"{ROOT}/campaign/scripts/rawew13v2_build.py"
CHAMP_CSV = f"{ROOT}/campaign/results/GOAL100_RAWEW13v2_WEIGHTED_GEAR16_daily.csv"
WGT_CSV = f"{ROOT}/campaign/results/RAWEW13v2_IS_SR_weights.csv"
OUT_JSON = f"{ROOT}/campaign/hunts/META_LABEL_HUNT1/work/arm_results.json"
OUT_STDOUT = f"{ROOT}/campaign/hunts/META_LABEL_HUNT1/work/run_stdout.txt"

PIN_SR = 3.7844894672049048
PIN_ANN = 0.23860978396835986
PIN_MDD = -0.03304849169440516

# ---- sealed constants (FINDINGS_PRECOMMIT §4; frozen at seal) ----
C_MULT = 2.5                 # §4.4: b = clip(1 + 2.5*zema, 0.5, 1.5)
B_LO, B_HI = 0.5, 1.5        # §4.4 band
HALFLIFE = 5                 # §4.4 zema EMA halflife (bdays)
RIDGE = 1e-6                 # §4.3 IRLS ridge
MAX_ITER = 50                # §4.3
GRAD_TOL = 1e-10             # §4.3 gradient tol
N_SEED = 20261113            # §4.4 arm N seed (history: 20261106/07/08)
IDENTITY_TOL = 1e-12         # §4.5 G-1 fail-closed threshold
WIN_START = "2008-03-31"
IS_END = pd.Timestamp("2017-01-01")

# §5 G0 drawdown windows
DD_WINDOWS = {
    "E1": ("2023-12-28", "2024-01-11"),
    "E2": ("2018-06-20", "2018-06-25"),
    "E3": ("2026-03-10", "2026-03-17"),
}

# §2/§3 run-time sha16 pins (first 16 hex of sha256)
SHA16 = {
    "campaign/results/GOAL100_RAWEW13v2_WEIGHTED_GEAR16_daily.csv":
        "a8ed233bd0f6fd5d",
    "campaign/results/RAWEW13v2_IS_SR_weights.csv":
        "2b0f5fbc43113149",
    "campaign/agents/chief/coord/CAMP_COST/sleeves/brwt10_2000__costfix.csv":
        "b0a0bd99338e2bb4",
    "campaign/agents/chief/coord/CAMP_COST/sleeves/brwt7__costfix.csv":
        "680c5468856361c8",
    "campaign/agents/chief/coord/CAMP_COST/sleeves/brwt5__costfix.csv":
        "ca5151f346524469",
    "campaign/agents/E1_20yspan/sleeves/E1_C5ng_weekday_prem.csv":
        "3d2b80691ef7a448",
    "campaign/agents/E1_20yspan/sleeves/E1_C5ng_summer_weekday.csv":
        "0f572f6f8fea2c0d",
    "campaign/agents/A5_vol_cond/sleeves/A5_r2_contango_rateshock__vt024.csv":
        "7ec85336e7f7d00f",
    "campaign/agents/E1_20yspan/sleeves/E1_a6r7_bond2y_trend_1990.csv":
        "e281e8c4cc5682fb",
    "campaign/agents/E1_20yspan/sleeves/E1_QAxasts_tsmom189__vt015.csv":
        "c40d008ddbf7c579",
    "campaign/agents/E1_20yspan/sleeves/E1_carryv2_GLD_2006.csv":
        "03f4d0e099da9759",
    "campaign/agents/A3_xs_quality/sleeves/QA_dualmom_band121.csv":
        "7462a8dfa391b18f",
    "campaign/agents/loop_team/HUNT_BASIS2/sleeves/diescrack_L40Z20_net.csv":
        "1b07ad09049b0b11",
    "campaign/agents/loop_team/HUNT_CARRYFX/sleeves/CFX4_DTF21_63_raw_daily.csv":
        "0e448b301fba08c7",
}


def sha256_16(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def verify_pins():
    """§2: pins 'verified at run time'. Fail-closed before anything loads."""
    bad = []
    for rel, pin in SHA16.items():
        got = sha256_16(f"{ROOT}/{rel}")
        if got != pin:
            bad.append(f"{rel}: got {got} pin {pin}")
    return bad


def load_builder():
    spec = importlib.util.spec_from_file_location("rawew13v2_build", BUILDER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rawew13v2_build"] = mod
    spec.loader.exec_module(mod)
    mod.ROOT = ROOT  # the ONLY patch (Mac path -> this machine)
    return mod


def pinned_build_with_b(B, relw_pinned, b_matrix=None):
    """rawew13v2_build.build() static-fit branch; relw SUPPLIED (never fitted).

    b_matrix None  -> exact champion identity (recon Path B mechanics).
    b_matrix given -> time-varying relw_i * b_{i,t} (elementwise), then the
    IDENTICAL row-normalization, cost, and margin steps (§4.4: 'Book
    mechanics: identical to champion but relw becomes time-varying
    relw_i · b_{i,t} (elementwise); row-normalization, cost, margin
    unchanged.'). b_matrix: DataFrame indexed like df, columns B.NAMES,
    values = b_{i,t} (1.0 = champion weight).
    """
    parts = {}
    for n in B.NAMES:
        s = B.load(B.PATHS[n])
        if n == "C5ngsum":
            s = s[s.index <= B.C5NGSUM_TRUNC]  # ITER61 sealed vintage
        parts[n] = s.dropna()
    df = pd.DataFrame(parts)
    df = df[df.index >= WIN_START]
    df = df[df.index <= B.VINTAGE_END]
    relw = relw_pinned.reindex(B.NAMES).fillna(0.0)
    nav = (1 + df.fillna(0)).cumprod().shift(1).fillna(1.0)
    d2 = nav.div(nav.mean(axis=1), axis=0)
    if b_matrix is None:
        d2 = d2.mul(relw, axis=1)                      # champion identity
    else:
        bm = b_matrix.reindex(index=df.index, columns=B.NAMES).fillna(1.0)
        d2 = d2.mul(relw * bm, axis=1)                 # relw_i * b_{i,t}
    d2 = d2.div(d2.sum(axis=1), axis=0) * len(B.NAMES)
    Wg = d2 * (B.GEAR / len(B.NAMES))
    port = (df.fillna(0).values * Wg.values).sum(axis=1)
    to = (Wg.diff().abs().sum(axis=1)).fillna(0.0)
    net = (pd.Series(port, index=df.index)
           - to * B.BPS / 1e4
           - np.maximum(B.GEAR - 1, 0) * B.RATE / 252)
    return net, relw, Wg, to, df


def sr_ann_mdd(r):
    """KW-sealed metric conventions (KW_TERMPREMIA_HUNT1 precommit S3)."""
    sr = r.mean() / r.std(ddof=1) * np.sqrt(252)
    ann = np.exp(252 * np.log1p(r).mean()) - 1
    nav = (1 + r).cumprod()
    mdd = (nav / nav.cummax() - 1).min()
    return sr, ann, mdd


# ------------------------------------------------------------- §4.2 / §4.3
FEATURES = ["vol63", "sharpe126", "dd252", "win21", "mom21"]


def load_sleeves(B):
    """§4.1: 12 sleeves via canonical builder PATHS, C5ngsum truncated
    <= 2026-08-24 (ITER61 sealed vintage), dropna. Returns {name: Series}."""
    out = {}
    for n in B.NAMES:
        s = B.load(B.PATHS[n])
        if n == "C5ngsum":
            s = s[s.index <= B.C5NGSUM_TRUNC]
        out[n] = s.dropna()
    return out


def sleeve_features(r):
    """§4.2: features on a sleeve's own FULL return series (files predate
    the window, so trailing windows are full at window start). All rolling,
    min_periods = window."""
    x = pd.DataFrame(index=r.index)
    x["vol63"] = r.rolling(63, min_periods=63).std() * np.sqrt(252)
    x["sharpe126"] = (r.rolling(126, min_periods=126).mean()
                      / r.rolling(126, min_periods=126).std() * np.sqrt(252))
    nav = (1.0 + r).cumprod()
    x["dd252"] = nav / nav.rolling(252, min_periods=252).max() - 1.0
    x["win21"] = (r > 0).astype(float).rolling(21, min_periods=21).mean()
    x["mom21"] = r.rolling(21, min_periods=21).mean()
    return x[FEATURES]


def sigmoid(v):
    out = np.empty_like(v)
    m = v >= 0
    out[m] = 1.0 / (1.0 + np.exp(-v[m]))
    ev = np.exp(v[~m])
    out[~m] = ev / (1.0 + ev)
    return out


def fit_logistic_irls(X, y):
    """§4.3: pooled logistic regression, intercept included, Newton-IRLS,
    ridge 1e-6 on the 5 feature coefficients (intercept unpenalized),
    beta init 0, max 50 iterations, gradient tol 1e-10 (inf-norm).
    Deterministic (no sklearn on this machine)."""
    n, k = X.shape
    Xd = np.column_stack([np.ones(n), X])
    beta = np.zeros(k + 1)
    pen = np.ones(k + 1)
    pen[0] = 0.0
    gin, n_iter = np.inf, 0
    for _ in range(MAX_ITER):
        p = sigmoid(Xd @ beta)
        g = Xd.T @ (p - y) + RIDGE * (pen * beta)
        gin = float(np.max(np.abs(g)))
        if gin < GRAD_TOL:
            break
        w = np.clip(p * (1.0 - p), 1e-12, None)
        H = Xd.T @ (Xd * w[:, None]) + RIDGE * np.diag(pen)
        beta = beta - np.linalg.solve(H, g)
        n_iter += 1
    return {"beta": beta, "n_iter": n_iter,
            "final_grad_inf": gin, "converged": bool(gin < GRAD_TOL)}


def place_on_grid(b_sleeve, grid):
    """Grid placement: b stays at prior value through gaps (ffill); b = 1
    before first availability (§4.2 'no bet update ... b=1 before first
    availability')."""
    return b_sleeve.reindex(grid).ffill().fillna(1.0)


def build_bM(B, grid, feats, beta, mu, sd, live):
    """§4.4 arm M: z = 2p-1 from standardized features (frozen IS mu/sd);
    zema = EMA(z, halflife=5 bdays) on the sleeve's own series; causal
    b_t = clip(1 + 2.5*zema_{t-1}, 0.5, 1.5) (shift(1); b=1 warmup/NaN);
    CFX4 (not live) b == 1. Missing feature at s -> z NaN -> zema carries
    prior state (ewm) -> b stays at prior value."""
    bM = pd.DataFrame(1.0, index=grid, columns=B.NAMES)
    for n in B.NAMES:
        if n not in live:
            continue
        X = feats[n]
        Xs = (X - mu) / sd
        p = sigmoid(Xs.to_numpy() @ beta[1:] + beta[0])
        z = pd.Series(2.0 * p - 1.0, index=X.index)
        zema = z.ewm(halflife=HALFLIFE).mean()
        b = (1.0 + C_MULT * zema.shift(1)).clip(B_LO, B_HI)
        bM[n] = place_on_grid(b.fillna(1.0), grid)
    return bM


def build_bV(B, grid, feats, live, vbar):
    """§4.4 arm V (vol-target twin): b^V_t = clip(vbar_i / vol63_{t-1},
    0.5, 1.5), vbar_i = frozen IS mean of F1 per sleeve, shift(1),
    b=1 warmup."""
    bV = pd.DataFrame(1.0, index=grid, columns=B.NAMES)
    for n in B.NAMES:
        if n not in live:
            continue
        b = (vbar[n] / feats[n]["vol63"].shift(1)).clip(B_LO, B_HI)
        bV[n] = place_on_grid(b.fillna(1.0), grid)
    return bV


def build_bN(B, grid, live, rng):
    """§4.4 arm N (iid control): b ~ U(0.5, 1.5) per live sleeve-day,
    seed 20261113, draw order = live sleeves in B.NAMES order, grid order
    within sleeve."""
    bN = pd.DataFrame(1.0, index=grid, columns=B.NAMES)
    for n in B.NAMES:
        if n in live:
            bN[n] = rng.uniform(B_LO, B_HI, len(grid))
    return bN


def build_bP(B, grid, bM, live):
    """§4.4 arm P (time-reversed control): b^P_{i,t} = b^M_{i,T+1-t} per live
    sleeve — full value reversal over the champion grid; CFX4 (not live)
    b == 1."""
    bP = pd.DataFrame(1.0, index=grid, columns=B.NAMES)
    for n in B.NAMES:
        if n in live:
            bP[n] = bM[n].to_numpy()[::-1]
    return bP


def auc_rank(y, p):
    """Average-rank Mann-Whitney AUC (tie-safe, pure numpy)."""
    y = np.asarray(y, dtype=float)
    p = np.asarray(p, dtype=float)
    order = np.argsort(p, kind="mergesort")
    ps = p[order]
    ranks = np.empty(len(p), dtype=float)
    i = 0
    while i < len(p):
        j = i
        while j + 1 < len(p) and ps[j + 1] == ps[i]:
            j += 1
        ranks[order[i:j + 1]] = 0.5 * (i + j) + 1.0
        i = j + 1
    n1 = float(y.sum())
    n0 = float(len(y) - n1)
    if n1 == 0 or n0 == 0:
        return float("nan")
    return float((ranks[y == 1.0].sum() - n1 * (n1 + 1.0) / 2.0) / (n1 * n0))


def main():
    # ---- §2 run-time pin verification (fail-closed before anything loads) ----
    bad = verify_pins()
    if bad:
        for m in bad:
            print("PIN MISMATCH:", m)
        print("VERDICT: RED — run-time pin verification failed; "
              "nothing measured.")
        sys.exit(1)
    print(f"pins: {len(SHA16)}/{len(SHA16)} GREEN (run-time sha16 "
          "verification)")

    self_sha = sha256_16(__file__)
    print(f"run_hunt.py sha256[:16] = {self_sha} (recorded at execution, §7)")

    B = load_builder()
    champ = pd.read_csv(CHAMP_CSV, index_col=0, parse_dates=True).iloc[:, 0]
    oldw = pd.read_csv(WGT_CSV, index_col=0).iloc[:, 0]
    oldw.index = oldw.index.astype(str)

    # ---- §4.5 G-1 identity FIRST (fail-closed before any arm is built) ----
    net_id, relw, Wg_id, to_id, df = pinned_build_with_b(B, oldw, None)
    jj = pd.concat([champ.rename("old"), net_id.rename("new")],
                   axis=1, join="inner").dropna()
    g1_diff = float((jj["old"] - jj["new"]).abs().max())
    print(f"G-1 identity: max|b==1 book - champion CSV| = {g1_diff:.3e} "
          f"(threshold {IDENTITY_TOL:.0e}) -> "
          f"{'GREEN' if g1_diff < IDENTITY_TOL else 'RED'}")
    if g1_diff >= IDENTITY_TOL:
        print("VERDICT: INVALID — G-1 identity failed before any arm was "
              "built; no measurement recorded (fail-closed, §4.5).")
        sys.exit(1)

    grid = df.index
    is_mask = np.asarray(grid < IS_END)
    oos_mask = ~is_mask
    is_dates = set(grid[is_mask])
    oos_dates = set(grid[oos_mask])
    print(f"grid: {len(grid)} rows {grid[0].date()}..{grid[-1].date()} | "
          f"IS {int(is_mask.sum())} | OOS {int(oos_mask.sum())}")

    # ---- §4.2 sleeves + features (each on the sleeve's own FULL series) ----
    sleeves = load_sleeves(B)
    feats = {n: sleeve_features(sleeves[n]) for n in B.NAMES}
    live = [n for n in B.NAMES if float(relw[n]) > 0.0]
    print(f"live sleeves: {len(live)}/{len(B.NAMES)} "
          f"(CFX4 relw pinned 0 -> b == 1 by construction)")

    # ---- §4.3 pooled IS training rows: label date t in the champion IS grid
    # AND in the sleeve index; features as-of s = t-1 (shift(1) on the
    # sleeve's own index); all 5 features non-NaN ----
    X_parts, y_parts = [], []
    for n in live:
        r = sleeves[n]
        Xf = feats[n].shift(1)
        lab = Xf.copy()
        lab["y"] = (r > 0).astype(float)
        lab = lab[lab.index.isin(is_dates)].dropna()
        X_parts.append(lab[FEATURES])
        y_parts.append(lab["y"])
    X_tr = pd.concat(X_parts)
    y_tr = pd.concat(y_parts)

    # ---- frozen pooled IS standardization (pandas default ddof=1) ----
    mu = X_tr.mean()
    sd = X_tr.std()
    fit = fit_logistic_irls(((X_tr - mu) / sd).to_numpy(), y_tr.to_numpy())
    print(f"IRLS: n_train={len(y_tr)} n_iter={fit['n_iter']} "
          f"final_grad_inf={fit['final_grad_inf']:.3e} "
          f"converged={fit['converged']}")
    for fname, bval in zip(["intercept"] + FEATURES, fit["beta"]):
        print(f"  beta[{fname}] = {bval:+.6f}")

    # ---- §4.4 arm V input: vbar_i = frozen IS mean of F1 per live sleeve
    # (grid IS dates with available values) ----
    vbar = {}
    for n in live:
        v = feats[n]["vol63"]
        vbar[n] = float(v[v.index.isin(is_dates)].dropna().mean())

    # ---- arms (single frozen run; N seed 20261113) ----
    rng = np.random.default_rng(N_SEED)
    bM = build_bM(B, grid, feats, fit["beta"], mu, sd, live)
    bV = build_bV(B, grid, feats, live, vbar)
    bP = build_bP(B, grid, bM, live)
    bN = build_bN(B, grid, live, rng)
    print("arms built: M (treatment), V (vol-target twin), "
          "P (time-reversed control), N (iid control, seed 20261113)")

    # ---- §4.4 arm books: identical mechanics, relw_i * b_{i,t} ----
    arm_out = {}
    for tag, bm in (("M", bM), ("V", bV), ("P", bP), ("N", bN)):
        net, _, _, to, _ = pinned_build_with_b(B, oldw, bm)
        arm_out[tag] = (net, to)
    net_M, to_M = arm_out["M"]
    net_V, to_V = arm_out["V"]
    net_P, to_P = arm_out["P"]
    net_N, to_N = arm_out["N"]

    def arm_stats(net, to):
        fsr, fann, fmdd = sr_ann_mdd(net)
        osr, oann, omdd = sr_ann_mdd(net[oos_mask])
        isr, _, _ = sr_ann_mdd(net[is_mask])
        return {"full": {"sr": float(fsr), "ann": float(fann),
                         "mdd": float(fmdd)},
                "oos": {"sr": float(osr), "ann": float(oann),
                        "mdd": float(omdd)},
                "is_sr": float(isr),
                "to_bp_yr": float(to.mean() * 252 * 6.4)}

    champ_stats = arm_stats(net_id, to_id)
    stats_by_arm = {tag: arm_stats(net, to)
                    for tag, (net, to) in arm_out.items()}
    oos_dsr = {t: stats_by_arm[t]["oos"]["sr"] - champ_stats["oos"]["sr"]
               for t in stats_by_arm}

    # ---- §5 gates ----
    # G0: drawdown-window pre-screen; "cum" = sum of daily net returns in
    # window; strict >; >= 1 of 3 (implementation note, recorded in JSON).
    g0 = {"windows": {}, "n_better": 0, "pass": False}
    for k, (a, bnd) in DD_WINDOWS.items():
        wm = (grid >= pd.Timestamp(a)) & (grid <= pd.Timestamp(bnd))
        mc = float(net_M[wm].sum())
        cc = float(net_id[wm].sum())
        g0["windows"][k] = {"start": a, "end": bnd, "M_cum": mc,
                            "champ_cum": cc, "M_better": bool(mc > cc)}
        g0["n_better"] += int(mc > cc)
    g0["pass"] = g0["n_better"] >= 1

    g1 = {"oos_dSR_M": float(oos_dsr["M"]),
          "pass": bool(oos_dsr["M"] >= 0.15)}
    g2_val = champ_stats["full"]["ann"] - stats_by_arm["M"]["full"]["ann"]
    g2 = {"cagr_sacrifice_pp": float(g2_val * 100.0),
          "pass": bool(g2_val <= 0.005)}
    g3_val = stats_by_arm["M"]["full"]["mdd"]
    g3 = {"mdd_M": g3_val,
          "pass": bool(g3_val >= champ_stats["full"]["mdd"] - 0.01)}
    g4_val = float((to_M.mean() - to_id.mean()) * 252 * 6.4)
    g4 = {"incr_cost_bp_yr": g4_val, "pass": bool(g4_val <= 50.0)}
    g5_val = float(((to_M - to_id) * 6.4)
                   .rolling(252, min_periods=1).sum().max())
    g5 = {"max_roll252_incr_cost_bp": g5_val, "pass": bool(g5_val <= 75.0)}
    g6 = {"oos_dSR_P": float(oos_dsr["P"]), "oos_dSR_N": float(oos_dsr["N"]),
          "pass": bool(oos_dsr["P"] < 0.15 and oos_dsr["N"] < 0.15)}
    g7_val = float(oos_dsr["M"] - oos_dsr["V"])
    g7 = {"oos_dSR_M_minus_V": g7_val, "pass": bool(g7_val >= 0.05)}
    gates_pass = {"G0": g0["pass"], "G1": g1["pass"], "G2": g2["pass"],
                  "G3": g3["pass"], "G4": g4["pass"], "G5": g5["pass"],
                  "G6": g6["pass"], "G7": g7["pass"]}

    # activity band (report-only): live sleeve-days with |b-1| > 0.01
    activity = float((bM[live].sub(1.0).abs() > 0.01).to_numpy().mean())

    # ---- report-only: classifier in-sample quality (§5 report-only list)
    p_tr = sigmoid(((X_tr - mu) / sd).to_numpy() @ fit["beta"][1:]
                   + fit["beta"][0])
    is_accuracy = float(((p_tr >= 0.5).astype(float)
                         == y_tr.to_numpy()).mean())
    is_auc = float(auc_rank(y_tr.to_numpy(), p_tr))
    print(f"IS classifier: accuracy {is_accuracy:.4f} AUC {is_auc:.4f} "
          f"(n_train={len(y_tr)}, in-sample by design)")

    # ---- report-only: OOS calibration deciles (pooled live sleeves) ----
    Xo_parts, yo_parts = [], []
    for n in live:
        r = sleeves[n]
        Xf = feats[n].shift(1)
        lab = Xf.copy()
        lab["y"] = (r > 0).astype(float)
        lab = lab[lab.index.isin(oos_dates)].dropna()
        Xo_parts.append(lab[FEATURES])
        yo_parts.append(lab["y"])
    X_oos = pd.concat(Xo_parts)
    y_oos = pd.concat(yo_parts)
    p_oos = pd.Series(sigmoid(((X_oos - mu) / sd).to_numpy()
                              @ fit["beta"][1:] + fit["beta"][0]),
                      index=X_oos.index)
    calib = []
    if len(p_oos) > 0:
        # positional (array) construction: the pooled index carries
        # duplicate date labels across sleeves; Series-based alignment
        # would raise on duplicate-axis reindex. Values identical.
        caldf = pd.DataFrame({"p": p_oos.to_numpy(), "y": y_oos.to_numpy()})
        caldf["decile"] = pd.qcut(p_oos.to_numpy(), 10, duplicates="drop")
        for dl, gr in caldf.groupby("decile", observed=True):
            calib.append({"decile_lo": float(dl.left),
                          "decile_hi": float(dl.right),
                          "mean_p": float(gr["p"].mean()),
                          "realized_win": float(gr["y"].mean()),
                          "n": int(len(gr))})

    # ---- report-only: yearly returns (champion vs arm M) ----
    def yearly(net):
        return {int(k): float(v) for k, v in
                ((1.0 + net).groupby(net.index.year).prod() - 1.0).items()}

    yearly_champ = yearly(net_id)
    yearly_M = yearly(net_M)

    # ---- report-only: per-sleeve mean b + bound-hit fraction (M and V) ----
    per_sleeve = {}
    for n in live:
        bm_s = bM[n]
        bv_s = bV[n]
        per_sleeve[n] = {
            "mean_b_M": float(bm_s.mean()),
            "frac_at_bound_M": float(((bm_s <= B_LO + 1e-12)
                                      | (bm_s >= B_HI - 1e-12)).mean()),
            "mean_b_V": float(bv_s.mean()),
            "frac_at_bound_V": float(((bv_s <= B_LO + 1e-12)
                                      | (bv_s >= B_HI - 1e-12)).mean()),
        }

    # ---- report-only: IS dSR (in-sample, inflated by design) ----
    is_dsr = {t: float(stats_by_arm[t]["is_sr"] - champ_stats["is_sr"])
              for t in stats_by_arm}

    # ---- V own-pass check: vol-targeting follow-up note (NOT promotion) ----
    vg = {
        "v_g1_oos_dsr_V": float(oos_dsr["V"]),
        "v_g1_pass": bool(oos_dsr["V"] >= 0.15),
        "v_g2_cagr_sacrifice_pp": float(
            (champ_stats["full"]["ann"]
             - stats_by_arm["V"]["full"]["ann"]) * 100.0),
        "v_g2_pass": bool(champ_stats["full"]["ann"]
                          - stats_by_arm["V"]["full"]["ann"] <= 0.005),
        "v_g3_mdd_V": float(stats_by_arm["V"]["full"]["mdd"]),
        "v_g3_pass": bool(stats_by_arm["V"]["full"]["mdd"]
                          >= champ_stats["full"]["mdd"] - 0.01),
        "v_g4_incr_cost_bp_yr": float((to_V.mean() - to_id.mean())
                                      * 252 * 6.4),
        "v_g5_max_roll252_incr_cost_bp": float(
            ((to_V - to_id) * 6.4)
            .rolling(252, min_periods=1).sum().max()),
    }
    vg["v_g4_pass"] = bool(vg["v_g4_incr_cost_bp_yr"] <= 50.0)
    vg["v_g5_pass"] = bool(vg["v_g5_max_roll252_incr_cost_bp"] <= 75.0)
    vg["vol_target_followup"] = bool(vg["v_g1_pass"] and vg["v_g2_pass"]
                                     and vg["v_g3_pass"] and vg["v_g4_pass"]
                                     and vg["v_g5_pass"])

    # ---- §5 sealed decision rule ----
    p_or_n_g1 = bool(oos_dsr["P"] >= 0.15 or oos_dsr["N"] >= 0.15)
    if p_or_n_g1:
        verdict = ("INVALID (P or N passes G1 -> gates not discriminating); "
                   "recorded NEGATIVE, no promotion")
    elif all(gates_pass.values()):
        verdict = ("POSITIVE candidate -> promotion memo (adoption is its "
                   "own operator round)")
    else:
        verdict = "NEGATIVE -> campaign/results/DEAD_IDEAS.csv row 80"

    # ---- §7 outputs: arm_results.json (deterministic; no timestamp) ----
    results = {
        "hunt": "META_LABEL_HUNT1",
        "run_hunt_sha256_16": self_sha,
        "pins": f"{len(SHA16)}/{len(SHA16)} verified at run time",
        "champion": champ_stats,
        "arms": stats_by_arm,
        "oos_dsr": {t: float(v) for t, v in oos_dsr.items()},
        "is_dsr": is_dsr,
        "gates": {"G0": g0, "G1": g1, "G2": g2, "G3": g3,
                  "G4": g4, "G5": g5, "G6": g6, "G7": g7},
        "gates_pass": gates_pass,
        "activity_band": {"frac_live_sleeve_days_b_off_1": activity,
                          "band": [0.02, 0.60], "report_only": True},
        "verdict": verdict,
        "vol_target_followup_V": vg,
        "classifier": {
            "feature_names": ["intercept"] + FEATURES,
            "beta": [float(bv) for bv in fit["beta"]],
            "n_train": int(len(y_tr)),
            "n_iter": int(fit["n_iter"]),
            "converged": bool(fit["converged"]),
            "is_accuracy": is_accuracy,
            "is_auc": is_auc,
        },
        "report_only": {
            "yearly_champ": yearly_champ,
            "yearly_M": yearly_M,
            "per_sleeve": per_sleeve,
            "oos_calibration_deciles": calib,
        },
        "implementation_notes": [
            "G0 'cum' = sum of daily net returns in window; strict >; "
            "pass requires >= 1 of 3 windows strictly better.",
            "G5 rolling-252 uses min_periods=1 (partial windows included "
            "in the max — conservative toward tripping).",
            "activity = live sleeve-days with |b-1|>0.01 over the full "
            "grid, including warmup (b=1 days count as inactive).",
            "calibration deciles pooled across live sleeves, positional "
            "construction (duplicate date labels across sleeves).",
            "yearly returns = calendar-year (1+r).prod()-1; 2008 partial "
            "from 2008-03-31.",
            "to_bp_yr hardcodes 6.4 = B.BPS (champion convention).",
            "no timestamp in this JSON by design (deterministic); the "
            "execution date is carried by run_stdout.txt and FINDINGS.md.",
        ],
    }
    with open(OUT_JSON, "w") as fh:
        json.dump(results, fh, indent=2)

    # ---- printed report (run_stdout.txt via tee) ----
    print()
    print("=" * 72)
    print("META_LABEL_HUNT1 — frozen single run (FINDINGS_PRECOMMIT sealed "
          "2026-11-13)")
    print("=" * 72)
    print(f"champion : SR {champ_stats['full']['sr']:.6f} "
          f"CAGR {champ_stats['full']['ann']*100:.4f}% "
          f"MDD {champ_stats['full']['mdd']*100:.4f}% "
          f"to {champ_stats['to_bp_yr']:.4f} bp/yr")
    for tag in ("M", "V", "P", "N"):
        s = stats_by_arm[tag]
        print(f"arm {tag}   : SR {s['full']['sr']:.6f} "
              f"CAGR {s['full']['ann']*100:.4f}% "
              f"MDD {s['full']['mdd']*100:.4f}% "
              f"to {s['to_bp_yr']:.4f} bp/yr | "
              f"OOS SR {s['oos']['sr']:.6f} (dSR {oos_dsr[tag]:+.6f})")
    print(f"G-1 identity max|diff| = {g1_diff:.3e} (< {IDENTITY_TOL:.0e}) "
          "PASS" if g1_diff < IDENTITY_TOL else "FAIL")
    print(f"G0 drawdown pre-screen: n_better = {g0['n_better']}/3 -> "
          f"{'PASS' if gates_pass['G0'] else 'FAIL'}")
    print(f"G1 OOS dSR(M) = {oos_dsr['M']:+.6f} (>= +0.15) -> "
          f"{'PASS' if gates_pass['G1'] else 'FAIL'}")
    print(f"G2 CAGR sacrifice = {g2['cagr_sacrifice_pp']:+.4f} pp "
          f"(<= 0.5) -> {'PASS' if gates_pass['G2'] else 'FAIL'}")
    print(f"G3 MDD(M) = {g3['mdd_M']*100:.4f}% (<= champ+1pp) -> "
          f"{'PASS' if gates_pass['G3'] else 'FAIL'}")
    print(f"G4 incr cost = {g4['incr_cost_bp_yr']:.4f} bp/yr (<= 50) -> "
          f"{'PASS' if gates_pass['G4'] else 'FAIL'}")
    print(f"G5 max roll-252 incr cost = {g5['max_roll252_incr_cost_bp']:.4f} "
          f"bp (<= 75) -> {'PASS' if gates_pass['G5'] else 'FAIL'}")
    print(f"G6 controls OOS dSR: P {oos_dsr['P']:+.6f} "
          f"N {oos_dsr['N']:+.6f} (both < +0.15) -> "
          f"{'PASS' if gates_pass['G6'] else 'FAIL'}")
    print(f"G7 OOS dSR(M-V) = {g7['oos_dSR_M_minus_V']:+.6f} (>= +0.05) -> "
          f"{'PASS' if gates_pass['G7'] else 'FAIL'}")
    print(f"activity band (report-only): {activity*100:.2f}% "
          f"(band [2%, 60%])")
    print(f"V vol-target follow-up (report-only): "
          f"{'FLAGGED' if vg['vol_target_followup'] else 'no'} "
          f"(V OOS dSR {oos_dsr['V']:+.6f})")
    print("-" * 72)
    print(f"VERDICT: {verdict}")


if __name__ == "__main__":
    main()
