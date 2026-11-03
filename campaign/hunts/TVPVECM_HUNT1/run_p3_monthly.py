"""TVP-VECM HUNT1 — P3 gold-copper MONTHLY variant (per PRECOMMIT §2: monthly only).

Uses the same sealed logic at monthly frequency: 36m init window (156w/4.33≈36),
z 2.0/0.5/4.0, gate with half-life in months (hl_max 12m, target 2m).
Reported separately, NOT in weekly sleeve.
"""
from __future__ import annotations
import os, sys, json
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tvp_estimator import fit_tvp_first_window, kalman_tvp, johansen_trace, gate_value

DATA = os.path.join(HERE, "data")
M_YEAR = 12
VOL_TARGET = 0.10
COST = 0.0010
Z_E, Z_X, Z_S = 2.0, 0.5, 4.0
G_ON, G_HALF, G_OFF = 0.50, 0.30, 0.15
INIT = 36
COOL = 2   # months (8w ≈ 2m)
VOL_WIN = 6  # 26w ≈ 6m


def ewma_sigma(x, span):
    n = len(x); out = np.full(n, np.nan)
    lam = 1 - 2 / (span + 1)
    for t in range(span, n):
        w = lam ** np.arange(span)[::-1]; w /= w.sum()
        seg = x[t - span + 1:t + 1]; m = (w * seg).sum()
        out[t] = np.sqrt((w * (seg - m) ** 2).sum())
    return out


def main():
    df = pd.read_csv(os.path.join(DATA, "pair_P3_gold_copper_monthly.csv"),
                     parse_dates=[0], index_col=0)
    y1 = np.log(df["y1"].values); y2 = np.log(df["y2"].values)
    n = len(y1)
    for arm in ["A", "B", "C"]:
        if arm == "A":
            b = np.full(n, np.nan); a = np.full(n, np.nan)
            for t in range(INIT, n):
                X = np.column_stack([y2[t - INIT + 1:t + 1], np.ones(INIT)])
                c, *_ = np.linalg.lstsq(X, y1[t - INIT + 1:t + 1], rcond=None)
                b[t], a[t] = c
        else:
            fit = fit_tvp_first_window(y1[:INIT], y2[:INIT])
            bf, _, _ = kalman_tvp(y1, y2, fit["q_beta"], fit["alpha"], fit["beta_ols"], fit["s2_eps"])
            b = bf; a = np.full(n, fit["alpha"])
        eps = np.full(n, np.nan)
        for t in range(INIT, n):
            eps[t] = y1[t] - b[t] * y2[t] - a[t]
        sig = ewma_sigma(eps, VOL_WIN)
        z = eps / sig
        pos = np.zeros(n); state = 0; cool = 0; rearm = 0
        gate_h = np.full(n, np.nan)
        for t in range(INIT + 1, n):
            gate = np.nan
            if arm == "B":
                tr, cv = johansen_trace(y1[t - INIT + 1:t + 1], y2[t - INIT + 1:t + 1])
                e = eps[t - VOL_WIN + 1:t + 1]
                rho = np.polyfit(e[:-1], e[1:], 1)[0] if np.isfinite(e).all() else np.nan
                gate = gate_value(tr, cv, rho, hl_max_w=12, hl_target_w=2)
            gate_h[t] = gate
            if cool > 0:
                cool -= 1; state = 0
            else:
                if state == 0:
                    ok = np.isfinite(z[t]) and abs(z[t]) >= Z_E
                    if arm == "B":
                        ok = ok and rearm >= 2 and gate is not None and gate >= G_ON
                    if ok:
                        state = -1 if z[t] > 0 else 1
                    if arm == "B":
                        rearm = rearm + 1 if (gate is not None and gate >= G_ON) else 0
                else:
                    if np.isfinite(z[t]) and abs(z[t]) >= Z_S:
                        state = 0; cool = COOL
                    elif np.isfinite(z[t]) and abs(z[t]) <= Z_X:
                        state = 0
                    elif arm == "B" and gate is not None:
                        if gate < G_OFF: state = 0; cool = COOL
                        elif gate < G_HALF: state = np.sign(state) * 0.5
            pos[t] = state
        dy1 = np.diff(y1, prepend=np.nan); dy2 = np.diff(y2, prepend=np.nan)
        bl = np.full(n, np.nan); bl[1:] = b[:-1]
        sr_ret = pos * (dy1 - bl * dy2)
        s = ewma_sigma(sr_ret, VOL_WIN)
        lev = np.where(np.isfinite(s) & (s > 0), (VOL_TARGET / M_YEAR**0.5) / s, np.nan)
        lev = np.where(pos != 0, np.minimum(lev, 3.0), 0.0)
        turn = np.abs(np.diff(np.nan_to_num(lev), prepend=0))
        net = lev * sr_ret - COST * turn
        r = pd.Series(net[INIT + 1:], index=df.index[INIT + 1:]).dropna()
        if len(r) > 20:
            ann = r.mean() * M_YEAR; vol = r.std() * np.sqrt(M_YEAR)
            print(f"P3 monthly {arm}: ann={ann*100:.2f}% vol={vol*100:.2f}% SR={ann/vol if vol>0 else float('nan'):.2f} n={len(r)}")
        else:
            print(f"P3 monthly {arm}: insufficient obs n={len(r)}")


if __name__ == "__main__":
    main()
