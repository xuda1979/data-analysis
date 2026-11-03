"""TVP-VECM HUNT1 — run sealed arms A/B/C per FINDINGS_PRECOMMIT.md.

Weekly event loop per pair:
  t-1 info -> position at week t -> return = position * d(spread log value)
Arms:
  A: static-rolling-beta (156w), banded z 2.0/0.5, hard stop |z|>=4, no gate.
  B: TVP beta (frozen q from init window), same z rules + credibility gate.
  C: TVP beta, no gate (ablation).
P3 monthly variant run separately (excluded from weekly sleeve aggregation).
P5 has 157 obs < 156+1 estimation window: run from obs 100 with reduced window
  (documented deviation), flagged separately in FINDINGS.
Sleeve: equal-weight active pairs, per-pair 10% vol target, 10 bps/unit turnover cost.
"""
from __future__ import annotations
import os, sys, json
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from tvp_estimator import (fit_tvp_first_window, kalman_tvp, johansen_trace,
                           gh_minadf, gate_value, halflife_from_rho)

DATA = os.path.join(HERE, "data")
WEEKS_YEAR = 52
VOL_TARGET = 0.10
COST_PER_UNIT = 0.0010  # 10 bps per unit turnover
Z_ENTRY, Z_EXIT, Z_STOP = 2.0, 0.5, 4.0
GATE_ON, GATE_HALF, GATE_OFF = 0.50, 0.30, 0.15
COOLDOWN = 8
REARM = 8
VOL_WIN = 26


def load_pair(fn):
    df = pd.read_csv(os.path.join(DATA, fn), parse_dates=[0], index_col=0)
    return np.log(df["y1"].values), np.log(df["y2"].values), df.index


def rolling_ols_beta(y1, y2, win):
    """Anchored-at-window-end rolling OLS beta using data up to t (inclusive)."""
    n = len(y1)
    beta = np.full(n, np.nan)
    alpha = np.full(n, np.nan)
    for t in range(win - 1, n):
        X = np.column_stack([y2[t - win + 1:t + 1], np.ones(win)])
        c, *_ = np.linalg.lstsq(X, y1[t - win + 1:t + 1], rcond=None)
        beta[t], alpha[t] = c
    return beta, alpha


def ewma_sigma(x, span):
    """EWMA std of the LAST span obs ending at t (inclusive), returned as array."""
    n = len(x)
    out = np.full(n, np.nan)
    lam = 1.0 - 2.0 / (span + 1)
    for t in range(span, n):
        w = lam ** np.arange(span)[::-1]
        w = w / w.sum()
        seg = x[t - span + 1:t + 1]
        m = (w * seg).sum()
        out[t] = np.sqrt((w * (seg - m) ** 2).sum())
    return out


def run_arm(y1, y2, arm, init_win=156, gh_every=0):
    """Event-loop backtest for one pair. arm in {'A','B','C'}.

    Returns dict of arrays: position, spread_ret, sleeve_ret (after vol target
    and costs), gate (if B), diagnostics.
    """
    n = len(y1)
    pos = np.zeros(n)            # position applied to week t+1 return
    z_hist = np.full(n, np.nan)
    gate_hist = np.full(n, np.nan)
    beta_hist = np.full(n, np.nan)
    gh_hist = np.full(n, np.nan)
    q_frozen = s2_frozen = None
    alpha_frozen = beta0 = None
    state = 0                    # 0 flat, +1/-1 in
    cooldown = 0
    rearm_cnt = 0
    stop_exits = 0
    gate_exits = 0
    z_entries = 0

    # static beta paths (arms A) and TVP params (B, C)
    if arm == "A":
        beta_s, alpha_s = rolling_ols_beta(y1, y2, init_win)
    else:
        fit = fit_tvp_first_window(y1[:init_win], y2[:init_win])
        q_frozen, s2_frozen = fit["q_beta"], fit["s2_eps"]
        alpha_frozen, beta0 = fit["alpha"], fit["beta_ols"]

    # TVP filtered beta, computed causally: beta_t from data up to t
    beta_tvp = np.full(n, np.nan)
    if arm in ("B", "C"):
        # run filter once over the full sample but READ ONLY the filtered (past) value
        # filter is causal by construction: beta_tvp[t] uses y[0..t] only.
        beta_f, _, _ = kalman_tvp(y1, y2, q_frozen, alpha_frozen, beta0, s2_frozen)
        beta_tvp = beta_f

    # spread construction + z with lag discipline:
    # eps_t = y1_t - beta_t*y2_t - alpha_t (info at t)
    # z_t = eps_t / sigma_eps(26w up to t)
    eps = np.full(n, np.nan)
    sigma_eps = np.full(n, np.nan)
    for t in range(init_win, n):
        if arm == "A":
            b, a = beta_s[t], alpha_s[t]
        else:
            b, a = beta_tvp[t], alpha_frozen
        eps[t] = y1[t] - b * y2[t] - a
    sigma_eps = ewma_sigma(eps, VOL_WIN)

    # spread return for week t: d(y1 - beta*y2) approximated by d(eps) is wrong
    # for PnL; use position * (d y1 - beta * d y2) with beta at t-1 (held).
    dy1 = np.diff(y1, prepend=np.nan)
    dy2 = np.diff(y2, prepend=np.nan)

    for t in range(init_win + 1, n):
        # ---- gate (arm B)
        gate = np.nan
        if arm == "B":
            tr, cv = johansen_trace(y1[t - init_win + 1:t + 1], y2[t - init_win + 1:t + 1])
            # rho on residual AR(1) over trailing window
            e = eps[t - VOL_WIN + 1:t + 1]
            if np.isfinite(e).all() and len(e) == VOL_WIN:
                rho = np.polyfit(e[:-1], e[1:], 1)[0]
                gate = gate_value(tr, cv, rho)
            else:
                gate = 0.0
        gate_hist[t] = gate

        z = eps[t] / sigma_eps[t] if np.isfinite(eps[t]) and sigma_eps[t] > 0 else np.nan
        z_hist[t] = z

        # ---- state machine, decide position for week t (return over t->t+1)
        if cooldown > 0:
            cooldown -= 1
            state = 0
        else:
            if state == 0:
                if arm == "B":
                    if rearm_cnt >= REARM and gate is not None and gate >= GATE_ON and np.isfinite(z) and abs(z) >= Z_ENTRY:
                        state = -1 if z > 0 else 1
                        z_entries += 1
                    if gate is not None and gate >= GATE_ON:
                        rearm_cnt += 1
                    else:
                        rearm_cnt = 0
                else:
                    if np.isfinite(z) and abs(z) >= Z_ENTRY:
                        state = -1 if z > 0 else 1
                        z_entries += 1
            else:
                # hard stop
                if np.isfinite(z) and abs(z) >= Z_STOP:
                    state = 0; cooldown = COOLDOWN; stop_exits += 1
                # z exit
                elif np.isfinite(z) and abs(z) <= Z_EXIT:
                    state = 0
                # gate de-risk (arm B)
                elif arm == "B" and gate is not None:
                    if gate < GATE_OFF:
                        state = 0; cooldown = COOLDOWN; gate_exits += 1
                    elif gate < GATE_HALF:
                        state = np.sign(state) * 0.5
        pos[t] = state

    # ---- returns: position formed at t (info through t) applies to return t->t+1.
    # NO LOOKAHEAD: spread_ret[t] = pos[t-1] * (dy1[t] - beta_lag[t] * dy2[t]),
    # where beta_lag[t] is the beta HELD during week t (decided at t-1).
    beta_hold = np.full(n, np.nan)
    beta_hold[1:] = (beta_tvp[:-1] if arm in ("B", "C") else beta_s[:-1])

    spread_ret = np.full(n, np.nan)
    for t in range(init_win + 2, n):
        spread_ret[t] = pos[t - 1] * (dy1[t] - beta_hold[t] * dy2[t])

    # ---- vol target 10%: leverage for week t set from sigma known at t-1 (no lookahead)
    sig = ewma_sigma(spread_ret, VOL_WIN)
    lev = np.full(n, np.nan)
    lev[0] = 0.0
    for t in range(init_win + 2, n):
        s = sig[t - 1]
        if not np.isfinite(s) or s <= 0:
            lev[t] = 1.0 if pos[t - 1] != 0 else 0.0
        else:
            lev[t] = (VOL_TARGET / WEEKS_YEAR**0.5) / s
        lev[t] = min(lev[t], 3.0)
    strat_ret = spread_ret * lev

    # ---- costs on position changes (in levered units)
    turn = np.abs(np.diff(np.where(np.isnan(lev * pos), 0, lev * pos), prepend=0))
    cost = np.full(n, np.nan)
    for t in range(init_win + 2, n):
        cost[t] = COST_PER_UNIT * turn[t]
    net_ret = strat_ret - cost

    return {"pos": pos, "net_ret": net_ret, "gross_ret": strat_ret, "z": z_hist,
            "gate": gate_hist, "beta": beta_tvp if arm in ("B", "C") else beta_s,
            "stop_exits": stop_exits, "gate_exits": gate_exits, "z_entries": z_entries,
            "eps": eps, "sigma_eps": sigma_eps}


def summarize(rets, idx, start_t):
    r = pd.Series(rets[start_t:], index=idx[start_t:]).dropna()
    if len(r) < 30:
        return {"n": len(r), "ann": np.nan, "sr": np.nan, "mdd": np.nan}
    ann = r.mean() * WEEKS_YEAR
    vol = r.std(ddof=1) * np.sqrt(WEEKS_YEAR)
    sr = ann / vol if vol > 0 else np.nan
    cum = r.cumsum()
    mdd = (cum - cum.cummax()).min()
    return {"n": int(len(r)), "ann": float(ann), "vol": float(vol), "sr": float(sr),
            "mdd": float(mdd)}


def main():
    pairs = {
        "P1_wti_brent": ("pair_P1_wti_brent_weekly.csv", 156),
        "P2_gold_silver": ("pair_P2_gold_silver_weekly.csv", 156),
        "P4_hh_wti": ("pair_P4_hh_wti_weekly.csv", 156),
        "P5_ig_hy": ("pair_P5_ig_hy_weekly.csv", 100),   # documented deviation
    }
    results = {}
    for pname, (fn, init) in pairs.items():
        y1, y2, idx = load_pair(fn)
        for arm in ["A", "B", "C"]:
            res = run_arm(y1, y2, arm, init_win=init)
            res["summary"] = summarize(res["net_ret"], idx, init + 1)
            results[f"{pname}_{arm}"] = res
            s = res["summary"]
            print(f"{pname:14s} {arm}: ann={s['ann']*100 if np.isfinite(s['ann']) else float('nan'):.2f}% "
                  f"sr={s['sr']:.2f} mdd={s['mdd']*100 if np.isfinite(s['mdd']) else float('nan'):.2f}% "
                  f"n={s['n']} stops={res['stop_exits']} gateExits={res['gate_exits']} entries={res['z_entries']}",
                  flush=True)

    # ---- sleeve aggregation (P1, P2, P4, P5 weekly; equal weight of active pairs)
    sleeve = {}
    for arm in ["A", "B", "C"]:
        rets, idxs = [], []
        for pname in pairs:
            res = results[f"{pname}_{arm}"]
            r = pd.Series(res["net_ret"], index=load_pair(pairs[pname][0])[2]).dropna()
            rets.append(r)
        df = pd.concat(rets, axis=1)
        active = df.notna().sum(axis=1)
        sleeve_r = df.mean(axis=1, skipna=True)
        sleeve_r[active == 0] = 0.0
        sleeve[arm] = sleeve_r.dropna()
        sr = sleeve[arm]
        print(f"SLEEVE {arm}: ann={sr.mean()*52*100:.2f}% vol={sr.std()*np.sqrt(52)*100:.2f}% "
              f"SR={sr.mean()*52/(sr.std()*np.sqrt(52)):.2f}", flush=True)

    # save
    out = os.path.join(HERE, "arm_results.json")
    payload = {}
    for k, v in results.items():
        payload[k] = {kk: (vv if not isinstance(vv, np.ndarray) else vv.tolist())
                      for kk, vv in v.items()}
    for arm in ["A", "B", "C"]:
        payload[f"sleeve_{arm}"] = {"rets": sleeve[arm].tolist(),
                                    "index": [str(d.date()) for d in sleeve[arm].index]}
    json.dump(payload, open(out, "w"))
    print("saved", out)


if __name__ == "__main__":
    main()
