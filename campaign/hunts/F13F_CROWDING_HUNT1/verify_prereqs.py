#!/usr/bin/env python3
"""F13F_CROWDING_HUNT1 — pre-seal prerequisite verification (verification-only).

One run -> work/prereqs_verified.json. Contract: FINDINGS_PRECOMMIT.md §9
(champion pin, manifest pins, KW comparator pins, environment versions).

  1. Champion pin: campaign/results/GOAL100_RAWEW13v2_WEIGHTED_GEAR16_daily.csv
     sha <=> sha16 a8ed233bd0f6fd5d; 4806 rows; SR/CAGR/MDD; zero neg years;
     IS/OOS split at 2017-01-01 (2286/2520); authoritative 4 IS blocks.
  2. Frozen holdings pins: data/holdings_{mgr}.csv.gz sha16 vs §2 AND row count
     vs work/fetch_manifest.json (manifest-authoritative census).
  3. KW g-series comparator pins: g_A/g_B/g_C sha16 + derisked-session counts
     (collapse branch, §4.5).
  4. G0 decline-window census: E1/E2/E3 pinned windows' champion session counts
     (11/4/6) — the kill-switch pre-screen inputs.
  5. Environment versions (.venv): Python 3.12.16, scipy 1.18.1, numpy 2.5.4,
     pandas 3.1.0 (precommit §9); scipy alexandergovern/levene availability.

Every pin is asserted (fail fast, exit non-zero). Nothing computed on the
champion grid, no holdings aggregation, no features, no measurement.
"""
import csv
import gzip
import hashlib
import io
import json
import platform

import numpy as np
import pandas as pd
import scipy
from scipy import stats  # noqa: F401  (availability check)

ROOT = "/home/david/software/world-trader"
HUNT = f"{ROOT}/campaign/hunts/F13F_CROWDING_HUNT1"
CHAMP_CSV = f"{ROOT}/campaign/results/GOAL100_RAWEW13v2_WEIGHTED_GEAR16_daily.csv"
KW_WORK = f"{ROOT}/campaign/hunts/KW_TERMPREMIA_HUNT1/work"
MANIFEST_JSON = f"{HUNT}/work/fetch_manifest.json"

# ---- §2 frozen sha16 pins ----
PINS = {
    "champion": "a8ed233bd0f6fd5d",
    "berkshire": "2a2c15902adbf519",
    "bridgewater": "52260cb344cf884d",
    "paulson": "f809d2d46de50f7e",
    "renaissance": "0479a3f421f13bd0",
    "southeastern": "525227641ead1538",
    "appaloosa": "59118438797d1c90",
    "g_A": "cc49cfba4664cef5",
    "g_B": "1f9d77019459089c",
    "g_C": "b4fa8aefde66d8be",
}
MANAGERS = ["berkshire", "bridgewater", "paulson", "renaissance",
            "southeastern", "appaloosa"]
KW_ARMS = ["A", "B", "C"]
# §5 G0 pinned decline windows: (name, start, end, expected champion sessions)
G0_WINDOWS = [
    ("E1", "2023-12-28", "2024-01-11", 11),
    ("E2", "2018-06-20", "2018-06-25", 4),
    ("E3", "2026-03-10", "2026-03-17", 6),
]
EXPECT_ENV = {"python": "3.12.16", "scipy": "1.18.1",
              "numpy": "2.5.4", "pandas": "3.1.0"}

out = {}


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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
assert champ_sha[:16] == PINS["champion"], "champion sha16 mismatch"

is_mask = s.index < pd.Timestamp("2017-01-01")
out["split"] = {
    "IS_rows": int(is_mask.sum()),
    "OOS_rows": int((~is_mask).sum()),
    "IS_first": str(s.index[is_mask][0].date()),
    "IS_last": str(s.index[is_mask][-1].date()),
    "OOS_first": str(s.index[~is_mask][0].date()),
    "OOS_last": str(s.index[~is_mask][-1].date()),
}
assert int(is_mask.sum()) == 2286, f"IS rows {is_mask.sum()} != 2286"
assert int((~is_mask).sum()) == 2520, f"OOS rows {(~is_mask).sum()} != 2520"

is_s = s[is_mask]
# authoritative np.array_split blocks (precommit §4.3, ICP-identical)
blk_n = [int(len(b)) for _, b in
         [blk for blk in [("b", i) for i in np.array_split(np.arange(len(is_s)), 4)]]]
EXP_BLK = [572, 572, 571, 571]
blocks = []
for k, idx in enumerate(np.array_split(np.arange(len(is_s)), 4), 1):
    blk = is_s.iloc[idx]
    blocks.append({"block": f"b{k}", "n": int(len(blk)),
                   "first": str(blk.index[0].date()),
                   "last": str(blk.index[-1].date())})
    assert int(len(blk)) == EXP_BLK[k - 1], f"b{k} n != {EXP_BLK[k-1]}"
out["blocks"] = blocks

# ---- 4. G0 decline-window census ----
g0 = []
for name, lo, hi, exp_n in G0_WINDOWS:
    w = s.loc[pd.Timestamp(lo):pd.Timestamp(hi)]
    g0.append({"window": name, "start": lo, "end": hi,
               "champion_sessions": int(len(w))})
    assert int(len(w)) == exp_n, f"{name}: {len(w)} sessions != {exp_n}"
out["g0_windows"] = g0

# ---- 2. holdings manifest pins (sha16 + row count) ----
manifest = json.load(open(MANIFEST_JSON))
hold = {}
for mgr in MANAGERS:
    p = f"{HUNT}/data/holdings_{mgr}.csv.gz"
    digest = sha256_file(p)
    with gzip.open(p, "rt") as fh:
        n = sum(1 for _ in csv.reader(fh)) - 1  # minus header
    mrows = int(manifest["managers"][mgr]["n_rows"])
    assert digest[:16] == PINS[mgr], f"holdings_{mgr} sha16 mismatch"
    assert n == mrows, f"holdings_{mgr} rows {n} != manifest {mrows}"
    hold[mgr] = {"file": f"data/holdings_{mgr}.csv.gz", "sha256": digest,
                 "sha16": digest[:16], "rows": n,
                 "manifest_rows": mrows,
                 "manifest_sha16": manifest["managers"][mgr]["sha256"][:16],
                 "n_filings": int(manifest["managers"][mgr]["n_filings"]),
                 "is_report_periods": int(
                     manifest["managers"][mgr]["is_report_periods"]),
                 "is_first": manifest["managers"][mgr]["is_first"],
                 "is_last": manifest["managers"][mgr]["is_last"]}
    assert digest[:16] == manifest["managers"][mgr]["sha256"][:16], \
        f"holdings_{mgr} manifest sha16 mismatch"
out["holdings"] = hold
out["holdings_total_filings"] = int(manifest["total_filings_fetched"])

# ---- 3. KW g-series comparator pins ----
kw_pins = {}
for arm in KW_ARMS:
    p = f"{KW_WORK}/g_{arm}.csv"
    digest = sha256_file(p)
    g = pd.read_csv(p, index_col=0, parse_dates=True).iloc[:, 0]
    assert digest[:16] == PINS[f"g_{arm}"], f"g_{arm} sha16 mismatch"
    kw_pins[arm] = {"sha16": digest[:16], "rows": int(len(g)),
                    "derisked_sessions": int((g < 1.0).sum()),
                    "g_levels": sorted(set(np.round(g.values, 6).tolist()))}
out["kw_g_pins"] = kw_pins

# ---- 5. environment versions ----
env = {"python": platform.python_version(),
       "scipy": scipy.__version__,
       "numpy": np.__version__,
       "pandas": pd.__version__}
for k, v in EXPECT_ENV.items():
    assert env[k] == v, f"env {k} {env[k]} != expected {v}"
out["environment"] = env
out["scipy_available"] = {
    "alexandergovern": hasattr(stats, "alexandergovern"),
    "levene": hasattr(stats, "levene"),
}
assert out["scipy_available"]["alexandergovern"]
assert out["scipy_available"]["levene"]

out["prereqs_green"] = True  # reached => every assertion above passed

with open(f"{HUNT}/work/prereqs_verified.json", "w") as fh:
    json.dump(out, fh, indent=2)
print(json.dumps(out, indent=2))
print("\nPREREQS GREEN" if out["prereqs_green"] else "\nPREREQS FAIL")
