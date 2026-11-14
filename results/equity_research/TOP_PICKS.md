# Top picks — synthesis (agent debate equity research)

*18 names with a positive expected-return signal, assembled deterministically from the per-name report JSONs. Research only; not investment advice.*

## How these were picked

- Universe: top names by 12-mo Sharpe on the repo's US price panel (momentum is the best-documented cross-sectional expected-return anomaly), diversified across sectors.
- Signal: each name got a full agent debate (bull/bear with rebuttals, evidence-graded against real data) plus a deterministic Python valuation. Names below only appear here when the effective base-case 12-mo PT (risk-team deterministic override when the judge was vetoed, else the judge's target) is above the price AND a forward-consensus EPS anchor existed (no anchor -> the valuation abstains and no signal is claimed).

| Sym | Rating | Conv | Current price | Predicted 1-yr price | Expected return |
|---|---|---|---|---|---|
| **SNDK** | BUY | 0.7 | 886.51 | 2,204.24 | **+148.6%** |
| **PSX** | BUY | 0.65 | 253.02 | 508.11 | **+100.8%** |
| **LITE** | BUY | 0.6 | 596.16 | 1,154.65 | **+93.7%** |
| **VLO** | HOLD | 0.5 | 356.75 | 663.41 | **+86.0%** |
| **MPC** | BUY | 0.65 | 389.88 | 699.43 | **+79.4%** |
| **AMD** | HOLD | 0.5 | 508.58 | 851.46 | **+67.4%** |
| **CNC** | HOLD | 0.5 | 68.54 | 109.41 | **+59.6%** |
| **MU** | BUY | 0.75 | 733.15 | 1,147.24 | **+56.5%** |
| **DELL** | BUY | 0.65 | 346.31 | 500.52 | **+44.5%** |
| **RDDT** | HOLD | 0.5 | 100.79 | 134.00 | **+32.9%** |
| **EXE** | BUY | 0.6 | 85.96 | 113.80 | **+32.4%** |
| **NUE** | HOLD | 0.4 | 249.24 | 309.93 | **+24.4%** |
| **TXN** | HOLD | 0.5 | 295.73 | 343.02 | **+16.0%** |
| **APA** | HOLD | 0.5 | 44.55 | 49.97 | **+12.2%** |
| **ADI** | HOLD | 0.5 | 394.66 | 440.98 | **+11.7%** |
| **HPE** | HOLD | 0.5 | 47.54 | 52.66 | **+10.8%** |
| **CSGP** | HOLD | 0.4 | 31.24 | 32.78 | **+4.9%** |
| **PODD** | HOLD | 0.5 | 149.81 | 153.51 | **+2.5%** |

## SNDK — BUY (conviction 0.7, expected +148.6% to base PT 2,204.24)

**Judge's rationale:** The bull case is strongly supported by exceptional profitability, robust growth, and a low forward P/E, while the bear case highlights cyclical risks that are inherent to the memory industry. The deterministic valuation's base case of $2,204.24 implies substantial upside, and the analyst consensus target of $2,047.38 corroborates this. Although the debate is unresolved due to cyclicality concerns, the fundamental strength and valuation support a BUY rating with moderate conviction.

**Catalysts:** Next earnings report; AI product reveal and stock surge; Analyst price target updates

**Key risks:**
- Cyclical downturn in memory prices
- Earnings growth fails to meet forward estimates
- Momentum reversal after recent surge

Full report: `SNDK_2026-11-12.md` (JSON alongside).

## PSX — BUY (conviction 0.65, expected +100.8% to base PT 508.11)

**Judge's rationale:** The deterministic valuation indicates significant upside even in the bear case, with a base fair value of $508.11 versus the current price of $253.02. The bull case is supported by strong fundamentals (P/E 8.3, PEG 0.14, FCF yield 12.27%, ROE 39.84%) and analyst consensus, while the bear case highlights cyclical risks and leverage but does not negate the valuation gap. Given the unresolved debate on sustainability of earnings, conviction is moderate, but the risk-reward remains favorable, warranting a BUY.

**Catalysts:** Next earnings report showing continued EPS growth and margin strength; Resolution of strike risks and supply deals; Analyst price target revisions upward

**Key risks:**
- Refining margins weaken due to commodity price volatility
- Operational disruptions from strikes or supply issues
- Higher capex needs for maintenance or environmental compliance reduce FCF

Full report: `PSX_2026-11-12.md` (JSON alongside).

## LITE — BUY (conviction 0.6, expected +93.7% to base PT 1,154.65)

**Judge's rationale:** The bull case is compelling: Lumentum's core operations are profitable (operating income $874M, 23.35% operating margin), the balance sheet is solid (net cash $549M), and the forward P/E of 22.18x is reasonable for 86% EPS growth, supported by a DCF-lite fair value of $1,057. The bear case relies heavily on a one-time $6.58B impairment and trailing metrics that obscure the AI-driven growth story. However, the debate is unresolved due to extreme valuation multiples and execution risks, so conviction is moderate. With the base case target of $1,154.65 (94% upside) and a favorable risk/reward, we rate LITE a BUY.

**Catalysts:** Next earnings report (expected to show strong AI optics demand and forward guidance); Resolution of production bottlenecks to meet AI optics demand; Completion or announcement of M&A activity (Form 425 filings)

**Key risks:**
- AI optics demand slows or production bottlenecks persist, limiting revenue growth
- Valuation remains elevated (P/S 15.7x, P/FCF 164.9x) and could compress if growth disappoints
- High beta (1.65) and short interest (8.58%) could lead to sharp downside in a market correction

Full report: `LITE_2026-11-12.md` (JSON alongside).

## VLO — HOLD (conviction 0.5, expected +86.0% to base PT 663.41)

**Judge's rationale:** The bull and bear cases present a fundamental disagreement on the sustainability of Valero's current earnings power, with the bull citing exceptional profitability and the bear warning of cyclical peak margins. The deterministic valuation, which uses a base EPS of 43.73 and a P/E of 8.3, yields a base fair value of $663.41, implying significant upside from the current price of $356.75. However, given the unresolved debate on cyclicality and the wide range of possible outcomes, a HOLD rating with moderate conviction is appropriate, as the stock appears undervalued but carries meaningful cyclical risk.

**Catalysts:** Next quarterly earnings report; Refining margin trends and crack spreads; Potential dividend increase or share buyback announcements

**Key risks:**
- Cyclical downturn in refining margins
- Higher-than-expected debt or leverage concerns
- Revenue growth stagnation

Full report: `VLO_2026-11-12.md` (JSON alongside).

## MPC — BUY (conviction 0.65, expected +79.4% to base PT 699.43)

**Judge's rationale:** The deterministic valuation indicates a base fair value of $699.43, implying 79% upside, with bull and bear scenarios both positive, but the debate on cyclicality and leverage remains unresolved. Given the deep value, strong cash flow, and analyst targets, a BUY rating is warranted with moderate conviction, as the bear case's risks are real but not sufficient to offset the valuation cushion.

**Catalysts:** Next earnings report; Refining margin sustainability; Debt reduction progress

**Key risks:**
- Refining margin compression
- High leverage and negative net cash
- Cyclical earnings peak
- Insider selling signals

Full report: `MPC_2026-11-12.md` (JSON alongside).

## AMD — HOLD (conviction 0.5, expected +67.4% to base PT 851.46)

**Judge's rationale:** The bull and bear cases are sharply divided on whether AMD's growth justifies its premium valuation, with the bull citing strong momentum and the bear pointing to extreme multiples and volatility. The deterministic valuation's base case of $851 implies significant upside, but the wide scenario range (from $432 to $1175) and unresolved debate warrant a cautious stance. Given the high uncertainty and lack of convergence, a HOLD rating with moderate conviction is appropriate.

**Catalysts:** Next earnings report (date not specified in data); Google Cloud deal and Wall Street upgrade (news[2]); Insider selling via Form 144 filings (filings[4])

**Key risks:**
- High valuation (trailing P/E 119.84, P/FCF 130.32) leaves no room for error
- High beta (2.54) amplifies downside in market downturns
- Competition from NVIDIA in AI chips could pressure growth and margins
- Analyst EPS estimates may be overly optimistic, leading to earnings misses

Full report: `AMD_2026-11-12.md` (JSON alongside).

## CNC — HOLD (conviction 0.5, expected +59.6% to base PT 109.41)

**Judge's rationale:** The bull case highlights a compelling valuation (PEG 0.35, FCF yield 11.3%) and strong EPS growth, while the bear case correctly points to razor-thin margins and high leverage that make the forward estimates fragile. The deterministic valuation suggests a base fair value of $109.41, implying significant upside, but the unresolved debate over margin sustainability and execution risk warrants a cautious stance. With a wide range of outcomes and no clear convergence, a HOLD rating with moderate conviction is appropriate.

**Catalysts:** Quarterly earnings updates (10-Q filings); 8-K filings including insider Form 4 stock sales

**Key risks:**
- Medical cost inflation or pricing resets in government-sponsored plans
- Regulatory changes affecting managed care operations
- High leverage (debt-to-equity 0.7) straining cash flows if interest rates remain elevated
- Failure to meet aggressive forward EPS expectations

Full report: `CNC_2026-11-12.md` (JSON alongside).

## MU — BUY (conviction 0.75, expected +56.5% to base PT 1,147.24)

**Judge's rationale:** The deterministic valuation indicates a base fair value of $1,147, offering 56% upside, while the bull case at $1,654 and bear case at $817 bracket the range. Despite the bear's valid cyclicality concerns, the company's strong balance sheet, exceptional profitability, and deeply discounted forward multiples tilt the risk/reward favorably. The debate remains unresolved on sustainability of peak earnings, but the margin of safety supports a BUY with moderate conviction.

**Catalysts:** Next earnings report; Memory price trends and AI demand updates; Analyst price target revisions

**Key risks:**
- Memory price normalization or downturn
- High beta amplifies market volatility
- Insider selling signals potential overvaluation

Full report: `MU_2026-11-12.md` (JSON alongside).

## DELL — BUY (conviction 0.65, expected +44.5% to base PT 500.52)

**Judge's rationale:** The bull case is compelling with strong growth, low forward P/E, and high ROIC, but the bear's concerns about leverage and margin quality are valid and unresolved. The deterministic valuation shows significant upside to base fair value of $500.52, supporting a BUY, but the lack of convergence and balance sheet risks warrant a moderate conviction.

**Catalysts:** CoreWeave increased spending plan (AI server demand); Next earnings report; Insider selling activity

**Key risks:**
- High leverage and negative book value
- Low margins in AI server business
- High beta amplifies market downturns

Full report: `DELL_2026-11-12.md` (JSON alongside).

## RDDT — HOLD (conviction 0.5, expected +32.9% to base PT 134.00)

**Judge's rationale:** The bull case is well-supported by strong fundamentals and a discounted valuation (PEG 0.52, forward P/E 16.83), while the bear case relies on recent negative news and high volatility, but with weaker evidence grounding. The deterministic base fair value is $134, implying 33% upside, but the unresolved debate over growth sustainability and traffic headwinds warrants a cautious stance. Hence, a HOLD rating with moderate conviction is appropriate, as the risk-reward is balanced until catalysts clarify the trajectory.

**Catalysts:** Next earnings report (guidance and revenue growth update); OpenAI partnership revenue contribution; Google search traffic trends; Login requirement test outcome

**Key risks:**
- High beta (2.27) amplifies market downturns
- Declining Google search traffic reduces user acquisition
- Insider selling signals potential lack of confidence
- High short interest (15.28% of float) could lead to volatility

Full report: `RDDT_2026-11-12.md` (JSON alongside).

## EXE — BUY (conviction 0.6, expected +32.4% to base PT 113.80)

**Judge's rationale:** The deterministic valuation indicates a base fair value of $113.8, offering 32% upside from the current price, with bull and bear scenarios spanning from -2% to +79%. Despite bear concerns about earnings decline and debt, the company's strong FCF yield, low leverage, and attractive valuation support a positive outlook. The debate is unresolved given the forward earnings decline risk, so conviction is moderate.

**Catalysts:** Next earnings report; CEO appointment strategic changes; Insider selling activity

**Key risks:**
- Commodity price downturn
- Earnings decline as implied by forward P/E
- High debt burden limiting financial flexibility

Full report: `EXE_2026-11-12.md` (JSON alongside).

## NUE — HOLD (conviction 0.4, expected +24.4% to base PT 309.93)

**Judge's rationale:** The bull and bear cases present conflicting views on valuation sustainability, with the bull citing low forward P/E and strong growth while the bear highlights cyclical peak earnings and net debt. The deterministic valuation's base fair value of $309.93 is within 25% of the current price, suggesting limited upside. Given the unresolved debate and moderate conviction, a HOLD rating is appropriate.

**Catalysts:** Next earnings report; Steel price movements; Insider selling activity

**Key risks:**
- Cyclical downturn in steel prices
- High beta amplifies market volatility
- Net debt position may constrain flexibility

Full report: `NUE_2026-11-12.md` (JSON alongside).

## TXN — HOLD (conviction 0.5, expected +16.0% to base PT 343.02)

**Judge's rationale:** The bull and bear cases present a balanced debate: bull highlights strong growth, margins, and reasonable PEG, while bear points to high trailing P/E, payout ratio, and net debt. The deterministic valuation suggests a base fair value of $343, implying ~16% upside, but the wide scenario range (220-530) and unresolved valuation debate lower conviction. With no clear directional edge, a HOLD rating with moderate conviction is appropriate.

**Catalysts:** Next earnings report; AI-driven tech rebound continues; Insider selling activity

**Key risks:**
- Valuation multiple compression
- Dividend sustainability if earnings decline
- Higher volatility due to beta

Full report: `TXN_2026-11-12.md` (JSON alongside).

## APA — HOLD (conviction 0.5, expected +12.2% to base PT 49.97)

**Judge's rationale:** The bull and bear cases present valid but opposing views: the stock is cheap on earnings and cash flow with strong profitability, yet revenue growth is flat and net cash is negative. The deterministic valuation places base fair value at $49.97, implying 12% upside, but the unresolved debate and modest analyst target suggest limited near-term re-rating. Thus, a HOLD with moderate conviction is appropriate, with catalysts centered on Suriname and earnings.

**Catalysts:** Suriname FCF inflection progress; Next earnings report

**Key risks:**
- Commodity price decline
- Suriname project delays or cost overruns
- Negative net cash position strains finances

Full report: `APA_2026-11-12.md` (JSON alongside).

## ADI — HOLD (conviction 0.5, expected +11.7% to base PT 440.98)

**Judge's rationale:** The bull and bear cases present a genuine disagreement on whether the premium valuation is justified by growth or leaves the stock vulnerable to a pullback. The deterministic valuation's base fair value of $440.98 is within 12% of the current price, suggesting limited upside from here. Given the unresolved debate and the balanced risk-reward, a HOLD rating with moderate conviction is appropriate.

**Catalysts:** Next earnings report; Analyst price target revisions; Insider selling activity

**Key risks:**
- Valuation compression due to high trailing P/E and P/S
- Leverage and negative net cash position
- Growth deceleration from cyclical downturn

Full report: `ADI_2026-11-12.md` (JSON alongside).

## HPE — HOLD (conviction 0.5, expected +10.8% to base PT 52.66)

**Judge's rationale:** The deterministic valuation's base fair value of $52.66 is only 10.8% above the current price, and the bull and bear cases diverge sharply on growth sustainability and debt impact, leaving the debate unresolved. With a base-case target within the required range and balanced risks, a HOLD rating with moderate conviction is appropriate.

**Catalysts:** Next earnings report; Analyst price target revisions; Debt reduction or refinancing announcements

**Key risks:**
- High debt load and negative net cash
- Thin operating margins in competitive hardware market
- Insider selling activity

Full report: `HPE_2026-11-12.md` (JSON alongside).

## CSGP — HOLD (conviction 0.4, expected +4.9% to base PT 32.78)

**Judge's rationale:** The bull case highlights strong growth metrics and a low PEG, but the bear case correctly points out that the trailing P/E is elevated and margins are thin. The deterministic valuation places fair value at $32.78, only 4.9% above the current price, suggesting limited upside. With unresolved debate and a wide scenario range, a HOLD rating with moderate conviction is appropriate.

**Catalysts:** Next earnings report; Analyst price target revisions; Short interest dynamics

**Key risks:**
- Earnings growth fails to meet forward estimates
- Negative net cash position limits financial flexibility
- High trailing P/E leaves little room for disappointment

Full report: `CSGP_2026-11-12.md` (JSON alongside).

## PODD — HOLD (conviction 0.5, expected +2.5% to base PT 153.51)

**Judge's rationale:** The bull and bear cases present a balanced debate: the company shows strong growth and profitability, but the balance sheet and cash flow metrics raise valid concerns. The deterministic valuation's base fair value of $153.51 is close to the current price, suggesting limited upside or downside in the base case. Given the unresolved debate and the modest base-case upside, a HOLD rating with moderate conviction is appropriate.

**Catalysts:** Next earnings report; Execution of $1 billion buyback; Interest rate changes affecting debt costs

**Key risks:**
- Negative net cash position and $1.04B debt could increase interest expenses and refinancing risk
- High P/FCF of 40x implies aggressive cash flow growth expectations that may not materialize
- Short interest of 8.15% of float could pressure the stock if earnings disappoint

Full report: `PODD_2026-11-12.md` (JSON alongside).

## Caveats

- Single-run LLM ratings vary between runs (e.g. MU was BUY then HOLD on two runs the same day); treat ratings as directional, not precise. The evidence-graded debate is the stable output.
- Forward EPS is annualized from one consensus quarter (crude; disclosed per report). Valuation bands are mechanistic (P/E x 0.8/1.0/1.25), no sector judgment.
- Prices are the last close at report time; verify live quotes before any decision.
