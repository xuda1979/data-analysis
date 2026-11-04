"""Verify the unlevered_v1 protocol freeze: hashes, required keys, gate consistency.

Run: python research/protocols/verify_freeze.py
Exit 0 = freeze intact; nonzero = do not score anything until resolved.
"""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_PLAN_SHA = "4a4125d46362a067b2d564b8062ba9f348f8fde8dc1969f24454bc819d69414e"
FAILURES = []


def check(condition, message):
    if not condition:
        FAILURES.append(message)


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    protocol = json.loads((ROOT / "research/protocols/unlevered_v1.json").read_text())
    check(protocol["protocol_id"] == "unlevered_v1", "protocol_id mismatch")

    plan = ROOT / "docs/research-plan-unlevered.md"
    check(plan.exists(), "governing plan missing")
    check(sha256(plan) == EXPECTED_PLAN_SHA,
          f"plan sha256 drifted: expected {EXPECTED_PLAN_SHA}, got {sha256(plan)}")
    check(protocol["governing_document"]["sha256"] == EXPECTED_PLAN_SHA,
          "protocol no longer pins the plan hash it froze")

    for manifest in ("sources_v1.json",):
        p = ROOT / "research/manifests" / manifest
        check(p.exists(), f"manifest missing: {manifest}")
        if p.exists():
            json.loads(p.read_text())

    gates = protocol["acceptance_gates"]
    check(gates["net_nominal_cagr"]["minimum"] == 0.10, "CAGR minimum gate must stay 0.10")
    check(gates["annualized_daily_excess_sharpe"]["minimum"] == 1.00, "Sharpe minimum gate must stay 1.00")
    check(gates["daily_max_drawdown"]["maximum"] == 0.15, "MaxDD maximum gate must stay 0.15")
    check(gates["annualized_half_turn_turnover"]["maximum"] == 1.00,
          "annualized half-turn turnover maximum must stay 1.00")
    check(gates["gross_exposure_instrument_level"]["maximum"] == 1.00,
          "gross exposure cap must stay 1.00")
    check(protocol["trial_budget"]["max_development_configs"] == 24, "trial budget must stay 24")

    wf = protocol["chronological_design"]
    check((wf["initial_train_months"], wf["inner_validation_months"], wf["outer_evaluation_months"])
          == (36, 12, 12), "walk-forward structure must stay 36/12/12")

    registry = ROOT / "research/registries/data_exposure_v1.md"
    check(registry.exists(), "data-exposure registry missing")
    if registry.exists():
        text = registry.read_text()
        check("Max 24 development configurations" in text, "registry must restate the trial budget")
        check("| 9 | A4 |" in text, "registry must list the A4 combined controller")

    seal = ROOT / "research/protocols/unlevered_v1.seal.json"
    if seal.exists():
        sealed = json.loads(seal.read_text())
        for name, expected in sealed["hashes"].items():
            p = ROOT / name
            check(p.exists(), f"sealed file missing: {name}")
            if p.exists():
                actual = sha256(p)
                check(actual == expected, f"sealed file drifted: {name} {actual} != {expected}")
        check(sealed["t0"] == "2026-11-04", "T0 must stay 2026-11-04")
    else:
        print("NOTE: no seal file yet (first run). Seal after freezing.")

    if FAILURES:
        print("FREEZE VERIFY: RED")
        for f in FAILURES:
            print(f"  FAIL: {f}")
        return 1
    print("FREEZE VERIFY: GREEN")
    return 0


if __name__ == "__main__":
    sys.exit(main())
