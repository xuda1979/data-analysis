"""M6 unit tests: deterministic valuation + risk-team gate + shared read layer.

Targets the pure-Python contract of the agent-debate equity research
pipeline -- no LLM, no network:

  * equity_fundamentals._num / _pct parsing (incl. the -$76.56 sign case)
  * research_report._valuation (CAGR conversion, clamps, beta-tilted
    discount, scenario grid, abstention)
  * research_report._risk_checks / _run_risk_manager (approve / veto /
    deterministic override, fail-closed)
  * report_view.effective_scenarios / latest_json_per_sym (verdict-aware
    ranking base used by index/top-picks/portfolios)

Run from repo root:  python3 -m pytest tools/tests/test_agent_research.py -q
"""
from __future__ import annotations

import json
import os
import tempfile

import pytest

from wt.agent import research_report as rr
from wt.agent import report_view as rv
from wt.agent.equity_fundamentals import _num, _pct

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))  # repo root


# ---------------------------------------------------------------------------
# _num / _pct parsing
# ---------------------------------------------------------------------------
class TestNumParsing:
    def test_plain_decimal(self):
        assert _num("1.23") == 1.23

    def test_negative_with_currency_between_sign_and_digits(self):
        # "-$76.56" -- currency strip must run BEFORE sign capture
        assert _num("-$76.56") == -76.56

    def test_negative_with_trailing_currency(self):
        assert _num("-54.10$") == -54.10

    def test_magnitude_suffixes(self):
        assert _num("1.23B") == 1.23e9
        assert _num("450M") == 450e6
        assert _num("12.5K") == 12.5e3
        assert _num("2T") == 2e12

    def test_percent_returns_fraction(self):
        assert _num("-4.5%") == pytest.approx(-0.045)
        assert _pct("12.3%") == pytest.approx(0.123)

    def test_pct_without_sign_is_not_divided(self):
        # _pct only divides when the string carried a % sign
        assert _pct("0.5") == 0.5

    def test_none_and_garbage(self):
        assert _num(None) is None
        assert _num("n/a") is None
        assert _pct(None) is None

    def test_commas_in_numbers(self):
        assert _num("1,234,567") == 1234567.0


# ---------------------------------------------------------------------------
# _valuation
# ---------------------------------------------------------------------------
def _fund(**kw):
    """Fundamentals dict with a sane default profile."""
    base = dict(eps_ttm=5.0, pe_ttm=15.0, beta=1.0, eps_growth_yoy=0.30,
                net_cash_per_share=2.0, roe=0.20, roic=0.15, debt_eq=0.5,
                fcf_margin=0.15)
    base.update(kw)
    return base


class TestValuation:
    def test_headline_fair_value_is_base_cell(self):
        out = rr._valuation("X", {"fundamentals": _fund()}, price=50.0)
        fv = out["outputs"]["fair_value"]
        assert fv["base"] == out["outputs"]["scenario_grid"]["base"]["value"]
        assert 0 < fv["bear"] < fv["base"] < fv["bull"]

    def test_cagr_conversion_of_cumulative_3y_growth(self):
        # 3Y cumulative 30% -> per-year CAGR (1.30)^(1/3)-1 ~= 0.0914
        out = rr._valuation("X", {"fundamentals": _fund(eps_growth_yoy=0.30)},
                            price=50.0)
        g = out["outputs"]["dcf_lite"]["growth_5y"]
        assert 0.0913 < g < 0.0915  # 4-dp rounding of (1.30)^(1/3)-1

    def test_growth_clamped_to_25pct(self):
        for raw in (0.99, 2.0, 5.0):
            out = rr._valuation("X", {"fundamentals": _fund(eps_growth_yoy=raw)},
                                price=50.0)
            assert out["outputs"]["dcf_lite"]["growth_5y"] <= 0.25

    def test_growth_clamped_at_zero_for_negative(self):
        out = rr._valuation("X", {"fundamentals": _fund(eps_growth_yoy=-0.5)},
                            price=50.0)
        assert out["outputs"]["dcf_lite"]["growth_5y"] == 0.0

    def test_missing_growth_holds_eps_flat(self):
        out = rr._valuation("X", {"fundamentals": _fund(eps_growth_yoy=None,
                                                        revenue_growth_yoy=None)},
                            price=50.0)
        assert out["outputs"]["dcf_lite"]["growth_5y"] == 0.0

    def test_beta_tilted_discount(self):
        out = rr._valuation("X", {"fundamentals": _fund(beta=1.5)}, price=50.0)
        assert out["outputs"]["dcf_lite"]["discount_rate"] == pytest.approx(0.11)
        out = rr._valuation("X", {"fundamentals": _fund(beta=0.5)}, price=50.0)
        assert out["outputs"]["dcf_lite"]["discount_rate"] == pytest.approx(0.09)

    def test_discount_clamped_upper_lower(self):
        # formula: clamp(0.10 + (beta-1)*0.02, [0.07, 0.14]); note beta=0 is
        # 0.08, NOT the lower clamp -- only beta <= -0.5 hits 0.07.
        out = rr._valuation("X", {"fundamentals": _fund(beta=5.0)}, price=50.0)
        assert out["outputs"]["dcf_lite"]["discount_rate"] == 0.14
        out = rr._valuation("X", {"fundamentals": _fund(beta=0.0)}, price=50.0)
        assert out["outputs"]["dcf_lite"]["discount_rate"] == pytest.approx(0.08)
        out = rr._valuation("X", {"fundamentals": _fund(beta=-0.5)}, price=50.0)
        assert out["outputs"]["dcf_lite"]["discount_rate"] == 0.07

    def test_peg_uses_annualized_growth(self):
        out = rr._valuation("X", {"fundamentals": _fund(eps_growth_yoy=0.30,
                                                        pe_ttm=15.0)}, price=50.0)
        g = out["outputs"]["dcf_lite"]["growth_5y"]
        assert out["outputs"]["peg"] == round(15.0 / (g * 100), 2)

    def test_abstains_without_eps_or_pe(self):
        out = rr._valuation("X", {"fundamentals": _fund(eps_ttm=None, pe_ttm=None,
                                                        eps_forward=None,
                                                        forward_pe=None)},
                            price=50.0)
        assert out["outputs"]["fair_value"] is None
        assert any("NOT computed" in n for n in out["notes"])

    def test_forward_eps_fallback_when_no_ttm(self):
        out = rr._valuation("X", {"fundamentals": _fund(eps_ttm=None,
                                                        forward_pe=10.0)},
                            price=50.0)
        assert out["inputs"]["base EPS used"] > 0

    def test_upside_computed_vs_price(self):
        out = rr._valuation("X", {"fundamentals": _fund()}, price=50.0)
        fv = out["outputs"]["fair_value"]["base"]
        assert out["outputs"]["upside_base"] == round(fv / 50.0 - 1.0, 3)

    def test_deterministic_flag_and_sym(self):
        out = rr._valuation("X", {"fundamentals": _fund()}, price=50.0)
        assert out["deterministic"] is True
        assert out["sym"] == "X"


# ---------------------------------------------------------------------------
# _fmt_input: markdown input-table display (JSON keeps verbatim precision)
# ---------------------------------------------------------------------------
class TestFmtInput:
    def test_float_blob_rounded_to_2dp(self):
        # binary-repr noise must never leak into the markdown table
        assert rr._fmt_input("eps_forward (consensus-derived)",
                             3.051194539249147) == "3.05"

    def test_growth_and_rate_fractions_show_as_percent(self):
        assert rr._fmt_input("revenue_growth_3y_fcst",
                             0.030699999999999998) == "3.07%"
        assert rr._fmt_input("eps_growth_3y_fcst", 0.0319) == "3.19%"
        assert rr._fmt_input("DCF discount rate", 0.0918) == "9.18%"
        assert rr._fmt_input("DCF growth (5y)", 0.0105) == "1.05%"

    def test_plain_floats_keep_2dp(self):
        assert rr._fmt_input("eps_ttm", 2.37) == "2.37"
        assert rr._fmt_input("beta", 0.59) == "0.59"
        assert rr._fmt_input("net_cash_per_share", -7.83) == "-7.83"

    def test_non_float_values_pass_through(self):
        assert rr._fmt_input("P/E band (bear/base/bull)",
                             "15.2 / 19.1 / 23.8") == "15.2 / 19.1 / 23.8"
        assert rr._fmt_input("pe_ttm", None) == "n/a"
        assert rr._fmt_input("forward_pe", "n/a") == "n/a"


# ---------------------------------------------------------------------------
# _risk_checks / _run_risk_manager
# ---------------------------------------------------------------------------
def _judge(base_pt=100.0, probs=(0.3, 0.4, 0.3), rating="BUY", conviction=0.7):
    return {
        "rating": rating, "conviction": conviction,
        "scenarios": {
            "bull": {"pt": base_pt * 1.2, "prob": probs[0]},
            "base": {"pt": base_pt, "prob": probs[1]},
            "bear": {"pt": base_pt * 0.8, "prob": probs[2]},
        },
    }


def _val(fv_base=100.0, g=0.10):
    """Valuation-shaped result dict the risk manager reads."""
    bear, base, bull = fv_base * 0.75, fv_base, fv_base * 1.25
    return {"outputs": {
        "fair_value": {"bear": bear, "base": base, "bull": bull},
        "scenario_grid": {
            "bear": {"growth": g * 0.5, "exit_pe": 10.0, "value": bear},
            "base": {"growth": g, "exit_pe": 12.0, "value": base},
            "bull": {"growth": g * 1.5, "exit_pe": 16.0, "value": bull},
        },
    }}


class TestRiskChecks:
    def test_approves_when_aligned(self):
        j = _judge(base_pt=100.0)
        chk = rr._risk_checks(j, _val(fv_base=100.0), price=90.0)
        assert chk["passed"] is True
        assert all(c["ok"] for c in chk["checks"].values())

    def test_vetoes_when_base_pt_drifts_25pct(self):
        j = _judge(base_pt=150.0)  # +50% vs deterministic 100
        chk = rr._risk_checks(j, _val(fv_base=100.0), price=90.0)
        assert chk["passed"] is False
        assert chk["checks"]["base_pt_within_25pct"]["ok"] is False

    def test_vetoes_bad_rating(self):
        j = _judge(rating="BANANA")
        chk = rr._risk_checks(j, _val(), price=90.0)
        assert chk["passed"] is False
        assert chk["checks"]["rating_in_scale"]["ok"] is False

    def test_vetoes_conviction_out_of_range(self):
        j = _judge(conviction=3.5)
        chk = rr._risk_checks(j, _val(), price=90.0)
        assert chk["passed"] is False

    def test_probs_must_sum_to_one(self):
        j = _judge(probs=(0.1, 0.1, 0.1))
        chk = rr._risk_checks(j, _val(), price=90.0)
        assert chk["checks"]["probs_sum_1"]["ok"] is False

    def test_missing_fair_value_makes_constraint_not_applicable(self):
        j = _judge(base_pt=300.0)
        chk = rr._risk_checks(j, {"outputs": {"fair_value": None}}, price=90.0)
        assert chk["checks"]["base_pt_within_25pct"]["ok"] is True


class TestRunRiskManager:
    def test_approved_path_keeps_judge_scenarios(self):
        j = _judge(base_pt=100.0)
        out = rr._run_risk_manager("X", j, _val(fv_base=100.0), price=90.0,
                                   errors=[])
        assert out["verdict"] == "approved"
        assert out["override_applied"] is False
        assert "override" not in out

    def test_veto_overrides_with_deterministic_grid(self):
        j = _judge(base_pt=250.0)  # way off deterministic 100
        out = rr._run_risk_manager("X", j, _val(fv_base=100.0), price=90.0,
                                   errors=[])
        assert out["verdict"] == "vetoed"
        assert out["override_applied"] is True
        ov = out["override"]["scenarios"]
        # deterministic numbers replace the judge's -- from scenario_grid values
        assert ov["base"]["pt"] == rr._round2(100.0)
        assert ov["bull"]["pt"] == rr._round2(125.0)
        assert ov["bear"]["pt"] == rr._round2(75.0)
        # probs fall back to judge's (or 1/3)
        assert ov["base"]["prob"] == j["scenarios"]["base"]["prob"]

    def test_fail_closed_on_none_judge(self):
        out = rr._run_risk_manager("X", None, _val(), price=90.0, errors=[])
        assert out["verdict"] == "vetoed"
        assert out["reason"].startswith("judge produced no verdict")

    def test_n_checks_bookkeeping(self):
        j = _judge(base_pt=250.0)
        out = rr._run_risk_manager("X", j, _val(fv_base=100.0), price=90.0,
                                   errors=[])
        assert out["n_checks"] == 4
        assert out["n_checks_passed"] < out["n_checks"]


# ---------------------------------------------------------------------------
# _render_markdown: the page must show the EFFECTIVE scenarios
# (vetoed judge PTs never reach section 1; same contract the portfolio
# builders rank on via report_view.effective_scenarios)
# ---------------------------------------------------------------------------
def _res(judge, risk_manager, price=50.0):
    return rr.ReportResult(sym="X", price=price, judge=judge,
                           valuation=_val(fv_base=100.0),
                           risk_manager=risk_manager)


class TestRenderMarkdownEffectiveScenarios:
    def test_vetoed_headline_shows_override_not_judge_pt(self):
        j = _judge(base_pt=150.0)  # +50% vs deterministic 100 -> vetoed
        rm = rr._run_risk_manager("X", j, _val(fv_base=100.0), price=50.0,
                                  errors=[])
        assert rm["override_applied"] is True
        md = rr._render_markdown(_res(j, rm, price=50.0))
        # headline row: current 50.00, predicted = override base 100.0 (+100%)
        assert "| 50.00 | 100.0 | **100.0%** |" in md
        # the vetoed judge number must NOT be the headline predicted price
        assert "| 50.00 | 150.0 |" not in md
        # the scenario table also carries the override grid (75/100/125)
        assert "| bear | 30.0% | 75.0 |" in md
        assert "| bull | 30.0% | 125.0 |" in md

    def test_approved_headline_keeps_judge_pt(self):
        j = _judge(base_pt=100.0)
        rm = rr._run_risk_manager("X", j, _val(fv_base=100.0), price=50.0,
                                  errors=[])
        assert rm["override_applied"] is False
        md = rr._render_markdown(_res(j, rm, price=50.0))
        assert "| 50.00 | 100.0 | **100.0%** |" in md


# ---------------------------------------------------------------------------
# _evidence_grounded: citation grammar incl. numbered list rows
# ---------------------------------------------------------------------------
class TestEvidenceGrading:
    DATA = {
        "fundamentals": {"roe": 0.20, "price_target": 49.60},
        "news": [
            {"headline": "WATCHMAN trial results", "pub_date": "2026-11-10"},
            {"headline": "Q3 earnings beat", "pub_date": "2026-10-22"},
        ],
        "filings": [{"form": "8-K", "date": "2026-11-01"},
                    {"form": "4", "date": "2026-10-28"}],
    }

    def test_indexed_list_row_grounds(self):
        ok, why = rr._evidence_grounded("news[1].headline", self.DATA)
        assert ok and why == "ok"
        ok, why = rr._evidence_grounded("news[2].headline", self.DATA)
        assert ok and why == "ok"
        ok, why = rr._evidence_grounded("filings[2].form", self.DATA)
        assert ok and why == "ok"

    def test_index_out_of_range_rejects_with_reason(self):
        ok, why = rr._evidence_grounded("news[3].headline", self.DATA)
        assert not ok and "out of range" in why and "'news[3]'" in why
        ok, why = rr._evidence_grounded("news[0].headline", self.DATA)
        assert not ok

    def test_indexed_unknown_field_rejects(self):
        ok, why = rr._evidence_grounded("news[1].nonexistent", self.DATA)
        assert not ok and "field 'nonexistent' not found in news[1]" in why

    def test_indexed_unknown_section_rejects(self):
        ok, why = rr._evidence_grounded("bogus[1].x", self.DATA)
        assert not ok and "section 'bogus' not present" in why

    def test_plain_sections_still_work(self):
        assert rr._evidence_grounded("fundamentals.roe", self.DATA) == (True, "ok")
        assert rr._evidence_grounded("news.headline", self.DATA) == (True, "ok")
        assert rr._evidence_grounded("news", self.DATA) == (True, "ok")

    def test_dot_index_form_0based_is_tolerated(self):
        ok, why = rr._evidence_grounded("news.0.headline", self.DATA)
        assert ok and why == "ok"
        ok, why = rr._evidence_grounded("filings.1.form", self.DATA)
        assert ok and why == "ok"

    def test_dot_index_out_of_range_rejects(self):
        ok, why = rr._evidence_grounded("news.9.headline", self.DATA)
        assert not ok and "out of range" in why
        assert rr._evidence_grounded("news.0.nope", self.DATA) == \
            (False, "field 'nope' not found in news.0")

    def test_grade_evidence_counts_indexed_claim_grounded(self):
        claims = [{"claim": "Q3 beat was strong",
                   "evidence": "news[2].headline"},
                  {"claim": "ROE is decent",
                   "evidence": "fundamentals.roe"},
                  {"claim": "bad row",
                   "evidence": "news[9].headline"}]
        out = rr._grade_evidence("bull", claims, self.DATA)
        assert out["grounded"] == 2
        assert out["ungrounded"] == 1
        assert out["claims"][2]["grounded"] is False


# ---------------------------------------------------------------------------
# report_view: verdict-aware effective scenarios + newest-date selection
# ---------------------------------------------------------------------------
class TestReportView:
    def test_effective_scenarios_uses_judge_when_approved(self):
        d = {"judge": {"scenarios": {"base": {"pt": 100}}},
             "risk_manager": {"verdict": "approved", "override_applied": False}}
        sc = rv.effective_scenarios(d)
        assert sc["base"]["pt"] == 100

    def test_effective_scenarios_uses_override_when_vetoed(self):
        d = {"judge": {"scenarios": {"base": {"pt": 100}}},
             "risk_manager": {"verdict": "vetoed", "override_applied": True,
                              "override": {"scenarios": {"base": {"pt": 1503.72}}}}}
        sc = rv.effective_scenarios(d)
        assert sc["base"]["pt"] == 1503.72

    def test_expected_return(self):
        sc = {"base": {"pt": 120.0}}
        pt, exp = rv.expected_return(sc, 100.0)
        assert pt == 120.0 and abs(exp - 0.2) < 1e-9
        assert rv.expected_return({}, None) == (None, None)

    def test_latest_json_per_sym_keeps_newest_only(self):
        with tempfile.TemporaryDirectory() as td:
            old = os.path.join(td, "AAPL_2026-11-01.json")
            new = os.path.join(td, "AAPL_2026-11-10.json")
            other = os.path.join(td, "MSFT_2026-11-08.json")
            for p in (old, new, other):
                with open(p, "w") as f:
                    json.dump({"sym": os.path.basename(p)}, f)
            got = [os.path.basename(p) for p in rv.latest_json_per_sym(td)]
            assert got == ["AAPL_2026-11-10.json", "MSFT_2026-11-08.json"]

    def test_latest_json_per_sym_skips_index_top_names(self):
        with tempfile.TemporaryDirectory() as td:
            for name in ("INDEX_2026-11-10.json", "TOP_PICKS_2026-11-10.json",
                         "PORTFOLIOS_2026-11-10.json", "AAPL_2026-11-10.json"):
                with open(os.path.join(td, name), "w") as f:
                    json.dump({"x": 1}, f)
            got = [os.path.basename(p) for p in rv.latest_json_per_sym(td)]
            assert got == ["AAPL_2026-11-10.json"]

    def test_builders_import_same_read_layer(self):
        from wt.agent.build_index import effective_scenarios as bi_es
        from wt.agent.build_top_picks import effective_scenarios as bp_es
        assert bi_es is rv.effective_scenarios
        assert bp_es is rv.effective_scenarios
