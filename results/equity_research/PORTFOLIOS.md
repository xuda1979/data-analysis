# Portfolios — built from the agent-debate equity research

*Deterministic assembly from the 60 report JSONs (no LLM). Long book = WATCHLIST top-30 names with positive expected return to the effective base PT. Short book = WATCHLIST bottom-30 names with negative expected return. Weights are equal-weight within each book; target horizon 12-mo. Research only; not investment advice.*

## Long-only conviction book

| Sym | Rating | Conv | Last px | Base PT | ExpReturn | Verdict |
|---|---|---|---|---|---|---|
| **SNDK** | BUY | 0.7 | $886.51 | $2,204.24 | **+148.6%** | APPROVED |
| **PSX** | BUY | 0.65 | $253.02 | $508.11 | **+100.8%** | APPROVED |
| **LITE** | BUY | 0.6 | $596.16 | $1,154.65 | **+93.7%** | APPROVED |
| **VLO** | HOLD | 0.5 | $356.75 | $663.41 | **+86.0%** | APPROVED |
| **MPC** | BUY | 0.65 | $389.88 | $699.43 | **+79.4%** | APPROVED |
| **AMD** | HOLD | 0.5 | $508.58 | $851.46 | **+67.4%** | APPROVED |
| **CNC** | HOLD | 0.5 | $68.54 | $109.41 | **+59.6%** | APPROVED |
| **MU** | BUY | 0.75 | $733.15 | $1,147.24 | **+56.5%** | APPROVED |
| **DELL** | BUY | 0.65 | $346.31 | $500.52 | **+44.5%** | APPROVED |
| **NUE** | HOLD | 0.4 | $249.24 | $309.93 | **+24.4%** | APPROVED |
| **TXN** | HOLD | 0.5 | $295.73 | $343.02 | **+16.0%** | APPROVED |
| **APA** | HOLD | 0.5 | $44.55 | $49.97 | **+12.2%** | APPROVED |
| **ADI** | HOLD | 0.5 | $394.66 | $440.98 | **+11.7%** | APPROVED |
| **HPE** | HOLD | 0.5 | $47.54 | $52.66 | **+10.8%** | APPROVED |

_Equal weight: 7.1% of the long book per name._

## Long/short book (bottom-30 shorts)

Long leg: the conviction book above. Short leg:

| Sym | Rating | Conv | Last px | Base PT | ExpReturn | Verdict |
|---|---|---|---|---|---|---|
| **FIS** | HOLD | 0.35 | $28.34 | $6.09 | **-78.5%** | VETOED (override) |
| **APTV** | UNDERWEIGHT | 0.55 | $39.91 | $12.64 | **-68.3%** | APPROVED |
| **LVS** | UNDERWEIGHT | 0.6 | $40.18 | $17.14 | **-57.3%** | APPROVED |
| **TSCO** | UNDERWEIGHT | 0.55 | $37.40 | $20.24 | **-45.9%** | APPROVED |
| **COIN** | UNDERWEIGHT | 0.6 | $136.10 | $80.51 | **-40.8%** | APPROVED |
| **FICO** | UNDERWEIGHT | 0.55 | $723.76 | $435.04 | **-39.9%** | APPROVED |
| **LDOS** | HOLD | 0.5 | $135.76 | $86.48 | **-36.3%** | APPROVED |
| **ZTS** | HOLD | 0.4 | $82.32 | $58.81 | **-28.6%** | APPROVED |
| **LII** | HOLD | 0.5 | $349.47 | $252.12 | **-27.9%** | APPROVED |
| **BSX** | HOLD | 0.4 | $44.02 | $32.37 | **-26.5%** | APPROVED |
| **PNR** | UNDERWEIGHT | 0.6 | $70.20 | $52.27 | **-25.5%** | APPROVED |
| **WYNN** | UNDERWEIGHT | 0.6 | $86.70 | $65.00 | **-25.0%** | APPROVED |
| **ROL** | UNDERWEIGHT | 0.6 | $38.74 | $29.68 | **-23.4%** | APPROVED |
| **XYL** | UNDERWEIGHT | 0.6 | $99.26 | $76.49 | **-22.9%** | APPROVED |
| **MKC** | UNDERWEIGHT | 0.6 | $47.88 | $37.59 | **-21.5%** | APPROVED |
| **ORCL** | HOLD | 0.45 | $119.79 | $99.46 | **-17.0%** | APPROVED |
| **NKE** | UNDERWEIGHT | 0.6 | $39.88 | $33.20 | **-16.8%** | APPROVED |
| **AXON** | HOLD | 0.4 | $303.18 | $260.00 | **-14.2%** | APPROVED |
| **NOW** | HOLD | 0.4 | $102.76 | $89.98 | **-12.4%** | APPROVED |
| **INTU** | HOLD | 0.35 | $338.23 | $305.04 | **-9.8%** | APPROVED |
| **LULU** | HOLD | 0.4 | $112.53 | $107.67 | **-4.3%** | APPROVED |
| **TRMB** | HOLD | 0.5 | $54.68 | $52.36 | **-4.2%** | APPROVED |

_Equal-weight dollar short: 4.5% of short book per name_

## Coverage & method

- 60 names covered; 14 long candidates, 22 short candidates.
- Expected return = effective base PT / last close − 1 (effective = risk-team override when the judge was vetoed).
- Evidence gate: `errors == 0` on the report; conviction bar is a positive expected return (≈2% floor), not a rating filter.
- Equal-weight sizing; no position-sizing or portfolio optimization — the debate reports are security selection input, not a full allocator.
