"""TVP-VECM HUNT1 — TVP Kalman estimator + Gregory-Hansen diagnostic.

Implements FINDINGS_PRECOMMIT.md §3.2:
- Local-level state space for time-varying cointegrating beta (filter, not smoother).
- q_beta ML estimation on first 156w only, floor 1e-8 / cap 1e-2, then frozen.
- Gregory-Hansen rolling scan (diagnostic only).
- Johansen trace credibility + AR(1) half-life -> Gate.

Pure numpy/scipy (no statsmodels dependency for the filter itself — deterministic,
auditable, no hidden defaults).
"""
from __future__ import annotations
import numpy as np
from scipy import optimize, stats
from dataclasses import dataclass


# ---------------------------------------------------------------- Kalman filter
def kalman_tvp(y1: np.ndarray, y2: np.ndarray, q_beta: float, alpha0: float,
               beta0: float, s2_eps: float, P0: float = 10.0):
    """Local-level TVP: y1_t = beta_t*y2_t + alpha + eps_t; beta_t = beta_{t-1} + eta_t.

    Returns filtered beta, one-step-ahead prediction errors (v_t), their variances (F_t).
    alpha fixed at OLS value. s2_eps fixed (EWMA-residual variance passed in).
    """
    n = len(y1)
    beta_f = np.empty(n)
    v = np.empty(n)
    F = np.empty(n)
    b = beta0
    P = P0
    for t in range(n):
        # predict
        # (state already stepped: b unchanged; P = P + q_beta)
        P = P + q_beta
        # observation
        H = np.array([y2[t], 1.0])          # [beta, alpha] row
        v_t = y1[t] - (H @ np.array([b, alpha0]))
        F_t = (H @ H.T * P if False else y2[t] * P * y2[t]) + s2_eps
        K = P * y2[t] / F_t
        b = b + K * v_t
        P = (1.0 - K * y2[t]) * P
        beta_f[t] = b
        v[t] = v_t
        F[t] = F_t
    return beta_f, v, F


def loglik_tvp(params, y1, y2, alpha0, beta0):
    q_beta = np.exp(params[0])
    s2_eps = np.exp(params[1])
    _, v, F = kalman_tvp(y1, y2, q_beta, alpha0, beta0, s2_eps)
    ll = -0.5 * np.sum(np.log(F) + v * v / F)
    return ll


def fit_tvp_first_window(y1: np.ndarray, y2: np.ndarray):
    """OLS init + ML for (q_beta, s2_eps) on the INIT window (first 156 obs).
    Returns dict with q_beta (floored/capped), s2_eps, alpha, beta_ols.
    """
    X = np.column_stack([y2, np.ones(len(y2))])
    coef, *_ = np.linalg.lstsq(X, y1, rcond=None)
    beta_ols, alpha = coef
    resid = y1 - X @ coef
    s2 = max(resid.var(ddof=2), 1e-10)
    # grid+local ML
    best = (np.inf, None)
    for q0 in np.logspace(-8, -2, 25):
        for s0 in [s2]:
            try:
                res = optimize.minimize(lambda p: -loglik_tvp(p, y1, y2, alpha, beta_ols),
                                        x0=[np.log(q0), np.log(s0)],
                                        method="Nelder-Mead",
                                        options={"maxiter": 400, "xatol": 1e-6, "fatol": 1e-8})
                if res.fun < best[0]:
                    best = (res.fun, res.x)
            except Exception:
                continue
    if best[1] is None:
        q_beta, s2_eps = 1e-6, s2
    else:
        q_beta = float(np.exp(best[1][0]))
        s2_eps = float(np.exp(best[1][1]))
    s2_eps = float(np.exp(best[1][1]))
    q_beta = float(np.clip(q_beta, 1e-8, 1e-2))
    return {"q_beta": q_beta, "s2_eps": s2_eps, "alpha": float(alpha),
            "beta_ols": float(beta_ols), "hit_bound": q_beta in (1e-8, 1e-2)}


# ---------------------------------------------------------------- Johansen trace (r=1, bivariate)
def johansen_trace(y1w: np.ndarray, y2w: np.ndarray):
    """Bivariate Johansen trace stat for r=0 vs r>=1 via statsmodels coint_johansen.

    det_order=0 (constant in CE), k_ar_diff=1. Returns (trace_stat, cv5) where
    cv5 is the Mackinnon-Haug-Michelis 5% critical value for r=0 (n-r=2): 15.4943.
    """
    n = len(y1w)
    if n < 40:
        return np.nan, 15.4943
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from statsmodels.tsa.vector_ar.vecm import coint_johansen
        jr = coint_johansen(np.column_stack([y1w, y2w]), det_order=0, k_ar_diff=1)
    return float(jr.lr1[0]), float(jr.cvt[0, 1])


# ---------------------------------------------------------------- Gregory-Hansen (diagnostic)
def gh_minadf(y1w: np.ndarray, y2w: np.ndarray, tau_lo=0.15, tau_hi=0.85):
    """Gregory-Hansen (1996) model C (level shift) min-ADF scan.

    Returns (min_adf, argmin_tau_fraction, gh_cv5). GH1996 model C 5% cv = -4.61.
    Diagnostic only per PRECOMMIT.
    """
    n = len(y1w)
    lo, hi = int(tau_lo * n), int(tau_hi * n)
    if hi - lo < 20:
        return np.nan, np.nan, -4.61
    best = (np.inf, np.nan)
    for k in range(lo, hi):
        D = np.zeros(n); D[k:] = 1.0
        X = np.column_stack([y2w, D, np.ones(n)])
        coef, *_ = np.linalg.lstsq(X, y1w, rcond=None)
        e = y1w - X @ coef
        # ADF(1) on e: de[t] = g*e[t-1] + d*de[t-1] + c
        de = np.diff(e)          # len n-1
        lag = e[:-1]             # e[0..n-2], len n-1
        M = np.column_stack([lag[1:], de[:-1], np.ones(len(de) - 1)])
        try:
            c, *_ = np.linalg.lstsq(M, de[1:], rcond=None)
            r = de[1:] - M @ c
            T = len(r); kk = M.shape[1]
            s2 = np.sum(r ** 2) / (T - kk)
            XtX_inv = np.linalg.inv(M.T @ M)
            se_gamma = np.sqrt(s2 * XtX_inv[0, 0])
            adf = c[0] / se_gamma
        except Exception:
            continue
        if adf < best[0]:
            best = (adf, k / n)
    return best[0], best[1], -4.61


# ---------------------------------------------------------------- Half-life / gate
def halflife_from_rho(rho: float, periods_per_year: int = 52) -> float:
    """h (weeks) from AR(1) rho on the spread residual."""
    if rho is None or not np.isfinite(rho):
        return np.inf
    if rho <= 0 or rho >= 1:
        return np.inf
    return float(np.log(0.5) / np.log(rho))


def gate_value(trace: float, cv: float, rho: float, se_trace: float = 3.0,
               hl_max_w: int = 52, hl_target_w: int = 8):
    """PRECOMMIT §3.3: Gate = C_rank * C_halflife."""
    if not np.isfinite(trace) or not np.isfinite(rho):
        return 0.0
    c_rank = stats.norm.cdf((trace - cv) / se_trace)
    c_rank = float(min(max(c_rank, 0.0), 1.0))
    h = halflife_from_rho(rho)
    if not np.isfinite(h) or h > hl_max_w:
        c_hl = 0.0
    elif h <= hl_target_w:
        c_hl = 1.0
    else:
        c_hl = hl_target_w / h
    return float(c_rank * c_hl)
