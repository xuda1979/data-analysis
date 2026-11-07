#!/usr/bin/env python3
"""Pre-seal prerequisite verification for ICP_CAUSAL_HUNT1.

Verification only — no z construction, no ICP, no overlay measurement.
  1. Champion pin (file sha256, 4806 rows, metrics, IS/OOS split, 4 IS blocks).
  2. Drawdown episodes via clean single-pass scanner (E1/E2/E3 decline windows).
  3. KW dead-arm g-series pins (sha16 + de-risked counts) for the collapse branch.
  4. FRED candidate coverage on the champion window (sha256, rows, coverage, max staleness).
  5. scipy availability (needed for the ICP invariance tests).
"""
import hashlib
import json

import numpy as np
import pandas as pd
from scipy import stats  # noqa: F401  (availability check)

ROOT = "/home/david/software/world-trader"
CHAMP_CSV = f"{ROOT}/campaign/results/GOAL100_RAWEW13v2_WEIGHTED_GEAR16_daily.csv"
KW_WORK = f"{ROOT}/campaign/hunts/KW_TERMPREMIA_HUNT1/work"
DATA = f"{ROOT}/campaign/hunts/ICP_CAUSAL_HUNT1/data"
SERIES = ["DTWEXBGS", "T10YIE", "DGS3MO"]

out = {}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_fred(path):
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    s = df.iloc[:, 0].apply(pd.to_numeric, errors="coerce")
    s = s.replace([np.inf, -np.inf], np.nan).dropna()
    return s.sort_index()


# ---- 1. champion pin ----
champ_sha = sha256_file(CHAMP_CSV)
s = pd.read_csv(CHAMP_CSV, index_col=0, parse_dates=True)["ret"].sort_index()
assert len(s) == 4806, f"champion rows {len(s)} != 4806"
sr = s.mean() / s.std(ddof=1) * np.sqrt(252)
cagr = np.exp(252 * np.log1p(s).mean()) - 1
nav = (1 + s).cumprod()
dd = nav / nav.cummax() - 1
mdd = dd.min()
yrs = (1 + s).groupby(s.index.year).prod() - 1
out["champion"] = {
    "file_sha256": champ_sha,
    "sha16": champ_sha[:16],
    "rows": int(len(s)),
    "first": str(s.index[0].date()),
    "last": str(s.index[-1].date()),
    "SR": float(sr),
    "CAGR": float(cagr),
    "MDD": float(mdd),
    "neg_years": int((yrs < 0).sum()),
    "worst_year": float(yrs.min()),
}

is_mask = s.index < pd.Timestamp("2017-01-01")
out["split"] = {
    "IS_rows": int(is_mask.sum()),
    "OOS_rows": int((~is_mask).sum()),
    "IS_first": str(s.index[is_mask][0].date()),
    "IS_last": str(s.index[is_mask][-1].date()),
    "OOS_first": str(s.index[~is_mask][0].date()),
    "OOS_last": str(s.index[~is_mask][-1].date()),
}
is_s = s[is_mask]
blocks = []
for k, idx in enumerate(np.array_split(np.arange(len(is_s)), 4), 1):
    blk = is_s.iloc[idx]
    blocks.append({"block": f"b{k}", "n": int(len(blk)),
                   "first": str(blk.index[0].date()),
                   "last": str(blk.index[-1].date())})
out["blocks"] = blocks

# ---- 2. drawdown episodes (clean single-pass scanner) ----
# Convention: episode opens at the first session with dd < 0 after high water;
# decline window = episode start .. trough session (inclusive); closes at the
# first session with dd >= 0 (new high water).
eps = []
in_ep = False
start = trough_date = None
trough = 0.0
n_under = n_at_trough = 0
for dt, v in dd.items():
    if not in_ep:
        if v < -1e-12:
            in_ep = True
            start, trough, trough_date = dt, v, dt
            n_under = 1
            n_at_trough = 1
    else:
        if v < -1e-12:
            n_under += 1
            if v < trough:
                trough, trough_date = v, dt
                n_at_trough = n_under
        else:
            eps.append({"start": str(start.date()),
                        "trough_date": str(trough_date.date()),
                        "end": str(dt.date()),
                        "depth": float(trough),
                        "n_decline_sessions": int(n_at_trough),
                        "n_underwater_sessions": int(n_under)})
            in_ep = False
if in_ep:
    eps.append({"start": str(start.date()),
                "trough_date": str(trough_date.date()),
                "end": None,
                "depth": float(trough),
                "n_decline_sessions": int(n_at_trough),
                "n_underwater_sessions": int(n_under)})
eps.sort(key=lambda e: e["depth"])
out["episodes_top6"] = eps[:6]

# ---- 3. KW dead-arm g-series pins (collapse-branch comparators) ----
kw_pins = {}
for arm in ["A", "B", "C"]:
    p = f"{KW_WORK}/g_{arm}.csv"
    digest = sha256_file(p)
    g = pd.read_csv(p, index_col=0, parse_dates=True).iloc[:, 0]
    kw_pins[arm] = {
        "sha16": digest[:16],
        "rows": int(len(g)),
        "derisked_sessions": int((g < 1.0).sum()),
        "g_levels": sorted(set(np.round(g.values, 6).tolist())),
    }
out["kw_g_pins"] = kw_pins


# ---- 4. FRED candidate coverage ----
def staleness_bdays(z, champ):
    """Business-day staleness per champion session (numpy-safe, KW pattern)."""
    z = z.dropna()
    z = z[~z.index.duplicated(keep="last")]
    pos = z.index.searchsorted(champ.index, side="right") - 1
    ok = pos >= 0
    safe = np.where(ok, pos, 0)
    src = z.index.values[safe].astype("datetime64[D]")
    dst = champ.index.values.astype("datetime64[D]")
    gaps = np.busday_count(src, dst).astype(float)
    gaps[~ok] = np.nan
    return gaps


fred = {}
for sid in SERIES:
    p = f"{DATA}/fred_{sid}.csv"
    digest = sha256_file(p)
    z = load_fred(p)
    gaps = staleness_bdays(z, s)
    covered = ~np.isnan(gaps)
    fred[sid] = {
        "file": f"fred_{sid}.csv",
        "sha256": digest,
        "sha16": digest[:16],
        "rows": int(len(z)),
        "first": str(z.index[0].date()),
        "last": str(z.index[-1].date()),
        "champ_window_coverage": float(covered.mean()),
        "max_staleness_bdays": float(np.nanmax(gaps)) if covered.any() else None,
        "within_ffill5_limit": bool(np.nanmax(gaps) <= 5) if covered.any() else False,
    }
out["fred"] = fred
out["scipy_available"] = True

print(json.dumps(out, indent=2))
