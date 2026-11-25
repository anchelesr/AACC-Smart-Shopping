import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import carbon_experiment as ce   # noqa: E402


def test_experiment_runs_is_deterministic_and_never_misses_a_deadline():
    a = ce.run_once(7, 3, 600.0, False, (0, 5))
    assert a == ce.run_once(7, 3, 600.0, False, (0, 5))
    imm = ce.run_once(7, 3, 600.0, True, (0, 5))
    assert a["late"] == 0 and imm["late"] == 0 and a["jobs"] > 0
    per_job = lambda r: r["kwh"] / r["jobs"] * 3_600_000 / 600.0                 # average power in W
    assert 45.0 - 1e-6 <= per_job(a) <= 65.0 + 1e-6 and 45.0 - 1e-6 <= per_job(imm) <= 65.0 + 1e-6
    assert imm["max_wait_h"] <= 0.5                                              # immediate: first step after arrival


def test_report_states_the_assumptions_and_both_scenarios(tmp_path):
    res = {k: [{"seed": 7, "immediate": ce.run_once(7, 3, 600.0, True, h), "adaptive": ce.run_once(7, 3, 600.0, False, h)}] for k, _, h in ce.SCENARIOS}
    text = ce.report(res, 3, 600.0, [7])
    assert "Scenario A" in text and "Scenario B" in text and "assumed" in text.lower() and "No measurement" in text
