"""Champion reconstruction check (M3 prerequisite) — CANONICAL builder import.

Two paths, one discriminating question: is this Linux machine able to reproduce
the champion of record exactly?

  Path A (diagnostic only): full canonical build() INCLUDING the IS max-Sharpe
    fit. The SLSQP convergence path is scipy-version-dependent, so a refit on
    this machine may differ from the Mac-emitted champion by ~1e-9 in weights
    even with byte-identical inputs. Recorded, NOT part of the verdict.

  Path B (OPERATIVE): the committed weights (RAWEW13v2_IS_SR_weights.csv,
    sha16 2b0f5fbc43113149) are PINNED and only the NAV-drift mechanics are
    replicated (same math as rawew13v2_build.build() static-fit branch). If the
    12 sleeve files are byte-identical on this machine, this path must match
    the committed daily CSV to the --verify standard max|new-old| < 1e-12.

  VERDICT = GREEN iff Path B matches the committed CSV < 1e-12 AND PIN stats
  (KW-sealed conventions) match to 1e-9:
    SR 3.7844894672049048  ann 0.23860978396835986  mdd -0.03304849169440516

Hunt implication: META_LABEL_HUNT1 pins the committed weights (never refits) —
the bet-sizing rule acts on relw * b_t with the champion's own weight vector,
so the b==1 identity reproduces the champion of record exactly.

Run: .venv/bin/python campaign/hunts/META_LABEL_HUNT1/work/recon_check.py
"""
import importlib.util
import sys

import numpy as np
import pandas as pd

ROOT = "/home/david/software/world-trader"
BUILDER = f"{ROOT}/campaign/scripts/rawew13v2_build.py"
CHAMP_CSV = f"{ROOT}/campaign/results/GOAL100_RAWEW13v2_WEIGHTED_GEAR16_daily.csv"
WGT_CSV = f"{ROOT}/campaign/results/RAWEW13v2_IS_SR_weights.csv"

PIN_SR = 3.7844894672049048
PIN_ANN = 0.23860978396835986
PIN_MDD = -0.03304849169440516


def load_builder():
    spec = importlib.util.spec_from_file_location("rawew13v2_build", BUILDER)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["rawew13v2_build"] = mod
    spec.loader.exec_module(mod)
    mod.ROOT = ROOT  # the ONLY patch (Mac path -> this machine)
    return mod


def pinned_build(B, relw_pinned):
    """rawew13v2_build.build() static-fit branch with relw SUPPLIED (not fitted).
    Lines 317-360 replicated exactly: window pins, C5ngsum truncation, NAV-drift
    T+1 causal weighting, full-|dW| turnover, margin (0 at gear 1.0)."""
    parts = {}
    for n in B.NAMES:
        s = B.load(B.PATHS[n])
        if n == "C5ngsum":
            s = s[s.index <= B.C5NGSUM_TRUNC]  # ITER61 sealed vintage
        parts[n] = s.dropna()
    df = pd.DataFrame(parts)
    df = df[df.index >= "2008-03-31"]
    df = df[df.index <= B.VINTAGE_END]
    relw = relw_pinned.reindex(B.NAMES).fillna(0.0)
    nav = (1 + df.fillna(0)).cumprod().shift(1).fillna(1.0)
    d2 = nav.div(nav.mean(axis=1), axis=0).mul(relw, axis=1)
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


def main():
    B = load_builder()

    # ---- Path A: full canonical build() with local refit (diagnostic) ----
    net_a, relw_a, gross_a, to_a, _ = B.build()
    print("[Path A: local refit — diagnostic only, solver path is "
          "scipy-version-dependent]")

    # ---- committed artifacts ----
    champ = pd.read_csv(CHAMP_CSV, index_col=0, parse_dates=True).iloc[:, 0]
    oldw = pd.read_csv(WGT_CSV, index_col=0).iloc[:, 0]
    oldw.index = oldw.index.astype(str)

    # ---- Path B: pinned committed weights, mechanics only (operative) ----
    net_b, relw_b, Wg, to_b, df = pinned_build(B, oldw)

    for tag, net, relw in (("A(local refit)", net_a, relw_a),
                           ("B(pinned wts )", net_b, relw_b)):
        j = pd.concat([champ.rename("old"), net.rename("new")],
                      axis=1, join="inner").dropna()
        md = float((j.old - j.new).abs().max())
        wr = float((oldw.reindex(B.NAMES).fillna(0.0) - relw).abs().max())
        print(f"{tag}: n={len(net)} inner={len(j)} "
              f"max|new-old|={md:.3e} {'IDENTICAL' if md < 1e-12 else 'DIFF'} "
              f"| weights max|committed-built|={wr:.3e}")

    sr, ann, mdd = sr_ann_mdd(net_b)
    print(f"[Path B] gross mean {Wg.abs().sum(axis=1).mean():.6f} "
          f"max {Wg.abs().sum(axis=1).max():.12f} "
          f"days>1.6 {int((Wg.abs().sum(axis=1) > 1.6 + 1e-9).sum())} "
          f"turnover {to_b.mean() * 252 * B.BPS:.4f} bp/yr")
    print(f"rebuilt  SR {sr:.16f}  ann {ann:.16f}  mdd {mdd:.16f}")
    print(f"PIN      SR {PIN_SR:.16f}  ann {PIN_ANN:.16f}  mdd {PIN_MDD:.16f}")
    print(f"PIN match: SR {abs(sr - PIN_SR) < 1e-9}  "
          f"ann {abs(ann - PIN_ANN) < 1e-9}  mdd {abs(mdd - PIN_MDD) < 1e-9}")

    jb = pd.concat([champ.rename("old"), net_b.rename("new")],
                   axis=1, join="inner").dropna()
    mdb = float((jb.old - jb.new).abs().max())
    ok = (mdb < 1e-12
          and abs(sr - PIN_SR) < 1e-9
          and abs(ann - PIN_ANN) < 1e-9
          and abs(mdd - PIN_MDD) < 1e-9)
    print("RECON VERDICT (Path B, pinned weights):",
          "GREEN" if ok else "RED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
