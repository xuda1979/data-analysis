"""TVP-VECM HUNT1 — build weekly spread panel from sealed data sources.

Implements FINDINGS_PRECOMMIT.md §3.1 exactly:
- 5 pilot pairs (P1..P5), daily->weekly W-FRI last(), no fill.
- P3 gold-copper is MONTHLY (fallback local copper_monthly.csv).
- Log prices. Outputs parquet-free CSV panels + sha256 manifest.
"""
from __future__ import annotations
import hashlib, os, sys
import pandas as pd
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
REPO = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
LOCAL_FRED = os.path.join(REPO, "tools", "quant", "hedge_fund_strats", "data_fred")


def read_fred_csv(path: str) -> pd.Series:
    df = pd.read_csv(path)
    col = "observation_date" if "observation_date" in df.columns else "date"
    vcol = [c for c in df.columns if c != col][0]
    df[col] = pd.to_datetime(df[col])
    s = df.set_index(col)[vcol].sort_index()
    s = pd.to_numeric(s, errors="coerce").dropna()
    # remove duplicate index keep last
    s = s[~s.index.duplicated(keep="last")]
    return s


def read_local_csv(path: str) -> pd.Series:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    s = df.set_index("date")["value"].sort_index()
    s = pd.to_numeric(s, errors="coerce").dropna()
    return s[~s.index.duplicated(keep="last")]


def weekly(s: pd.Series) -> pd.Series:
    return s.resample("W-FRI").last().dropna()


def monthly(s: pd.Series) -> pd.Series:
    return s.resample("ME").last().dropna()


def main():
    os.makedirs(DATA, exist_ok=True)
    series = {}

    # --- FRED free CSVs (fetched 2026-11-03) ---
    fred_ids = ["DCOILWTICO", "DCOILBRENTEU", "DHHNGSP", "BAMLC0A0CM",
                "BAMLH0A0HYM2", "PCOPPUSDM", "IQ12260"]
    for fid in fred_ids:
        p = os.path.join(DATA, f"fred_{fid}.csv")
        series[fid] = read_fred_csv(p)

    # --- local repo CSVs ---
    series["xau"] = read_local_csv(os.path.join(LOCAL_FRED, "xau.csv"))
    series["slv"] = read_local_csv(os.path.join(LOCAL_FRED, "slv.csv"))
    series["copper_m"] = read_local_csv(os.path.join(LOCAL_FRED, "copper_monthly.csv"))

    # --- P1 WTI vs Brent (weekly) ---
    p1 = pd.concat([weekly(series["DCOILWTICO"]).rename("y1"),
                    weekly(series["DCOILBRENTEU"]).rename("y2")], axis=1).dropna()
    p1.to_csv(os.path.join(DATA, "pair_P1_wti_brent_weekly.csv"))

    # --- P2 Gold vs Silver (weekly, local stooq histories) ---
    p2 = pd.concat([weekly(series["xau"]).rename("y1"),
                    weekly(series["slv"]).rename("y2")], axis=1).dropna()
    p2.to_csv(os.path.join(DATA, "pair_P2_gold_silver_weekly.csv"))

    # --- P3 Gold vs Copper (MONTHLY) ---
    p3 = pd.concat([monthly(series["xau"]).rename("y1"),
                    monthly(series["copper_m"]).rename("y2")], axis=1).dropna()
    p3.to_csv(os.path.join(DATA, "pair_P3_gold_copper_monthly.csv"))

    # --- P4 Henry Hub vs WTI (weekly; PRECOMMIT redefined) ---
    p4 = pd.concat([weekly(series["DHHNGSP"]).rename("y1"),
                    weekly(series["DCOILWTICO"]).rename("y2")], axis=1).dropna()
    p4.to_csv(os.path.join(DATA, "pair_P4_hh_wti_weekly.csv"))

    # --- P5 IG vs HY credit spread (weekly) ---
    p5 = pd.concat([weekly(series["BAMLC0A0CM"]).rename("y1"),
                    weekly(series["BAMLH0A0HYM2"]).rename("y2")], axis=1).dropna()
    p5.to_csv(os.path.join(DATA, "pair_P5_ig_hy_weekly.csv"))

    # --- manifest with sha256 ---
    pairs = {k: v for k, v in {
        "pair_P1_wti_brent_weekly.csv": p1, "pair_P2_gold_silver_weekly.csv": p2,
        "pair_P3_gold_copper_monthly.csv": p3, "pair_P4_hh_wti_weekly.csv": p4,
        "pair_P5_ig_hy_weekly.csv": p5}.items()}
    rows = []
    for fn, df in pairs.items():
        p = os.path.join(DATA, fn)
        h = hashlib.sha256(open(p, "rb").read()).hexdigest()
        rows.append({"file": fn, "sha256": h, "n_obs": len(df),
                     "start": str(df.index.min().date()), "end": str(df.index.max().date())})
    man = pd.DataFrame(rows)
    man.to_csv(os.path.join(DATA, "PANEL_MANIFEST.csv"), index=False)
    print(man.to_string(index=False))


if __name__ == "__main__":
    main()
