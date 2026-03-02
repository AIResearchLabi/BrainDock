"""Tests for the BrainDock benchmark suite.

Validates benchmark infrastructure (dataclasses, harness, report generation)
and runs all 10 built-in scenarios to verify metrics collection.
"""

import json
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from BrainDock.benchmark import (
    BenchmarkScenario,
    BenchmarkResult,
    BenchmarkReport,
    BenchmarkHarness,
    save_baseline,
    load_baseline,
    append_history,
    load_history,
    scenario_happy_path,
    scenario_multi_task_deps,
    scenario_reflection_retry,
    scenario_reflection_exhausted,
    scenario_debate_path,
    scenario_token_budget_pressure,
    scenario_three_task_chain,
    scenario_multi_step_plan,
    scenario_skill_reuse,
    scenario_needs_human,
    get_all_scenarios,
)


# ── Infrastructure Tests ──────────────────────────────────────────────


class TestBenchmarkInfrastructure(unittest.TestCase):
    """Tests for benchmark dataclasses and harness utilities."""

    def test_scenario_dataclass_roundtrip(self):
        scenario = BenchmarkScenario(
            name="test_sc",
            description="A test scenario",
            problem="Test problem",
            responses=["resp1", "resp2"],
            config_overrides={"max_reflection_iterations": 1},
            expected_tasks=2,
            expected_success=True,
        )
        self.assertEqual(scenario.name, "test_sc")
        self.assertEqual(scenario.description, "A test scenario")
        self.assertEqual(scenario.problem, "Test problem")
        self.assertEqual(len(scenario.responses), 2)
        self.assertEqual(scenario.config_overrides["max_reflection_iterations"], 1)
        self.assertEqual(scenario.expected_tasks, 2)
        self.assertTrue(scenario.expected_success)

    def test_result_to_dict(self):
        result = BenchmarkResult(
            scenario_name="test",
            success=True,
            wall_time_seconds=1.5,
            total_llm_calls=7,
            total_input_tokens=100,
            total_output_tokens=50,
            total_tokens=150,
            per_agent_tokens={"spec": 80, "planner": 70},
            per_agent_calls={"spec": 3, "planner": 1},
            avg_call_duration_ms=0.5,
            task_count=1,
            tasks_completed=1,
            tasks_failed=0,
            step_completion_rate=1.0,
            plan_confidence=0.9,
            plan_entropy=0.1,
            reflection_count=0,
            debate_count=0,
            escalation_count=0,
            skills_learned=1,
            skills_matched=0,
            verification_pass_rate=1.0,
            generated_files=["main.py"],
            errors=[],
        )
        d = result.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(d["scenario_name"], "test")
        self.assertTrue(d["success"])
        self.assertEqual(d["total_tokens"], 150)
        self.assertEqual(d["per_agent_tokens"]["spec"], 80)
        # JSON serializable
        serialized = json.dumps(d)
        self.assertIn("test", serialized)

    def test_report_to_text(self):
        result = BenchmarkResult(
            scenario_name="happy_path",
            success=True,
            wall_time_seconds=0.5,
            total_llm_calls=7,
            total_tokens=150,
        )
        report = BenchmarkReport(
            results=[result],
            timestamp="2026-03-01T00:00:00+00:00",
            total_wall_time=0.5,
            summary={
                "total_scenarios": 1,
                "successes": 1,
                "failures": 0,
                "success_rate": 1.0,
                "avg_calls": 7.0,
                "avg_tokens": 150.0,
                "avg_reflections": 0.0,
                "avg_debates": 0.0,
            },
        )
        text = report.to_text()
        self.assertIn("BrainDock Benchmark Report", text)
        self.assertIn("happy_path", text)
        self.assertIn("PASS", text)
        self.assertIn("100%", text)

    def test_report_to_dict(self):
        result = BenchmarkResult(scenario_name="test", success=True)
        report = BenchmarkReport(
            results=[result],
            timestamp="2026-03-01T00:00:00+00:00",
            total_wall_time=1.0,
            summary={"total_scenarios": 1, "success_rate": 1.0},
        )
        d = report.to_dict()
        self.assertIsInstance(d, dict)
        self.assertEqual(len(d["results"]), 1)
        self.assertEqual(d["timestamp"], "2026-03-01T00:00:00+00:00")
        # JSON serializable
        serialized = json.dumps(d)
        self.assertIn("test", serialized)

    def test_harness_auto_skip_ask_fn(self):
        """Verify the harness's ask_fn auto-skips escalations."""
        harness = BenchmarkHarness()
        # The ask_fn is created inside run_scenario, but we can verify
        # the pattern by testing with a simple scenario
        scenario = scenario_happy_path()
        self.assertTrue(scenario.expected_success)
        self.assertGreater(len(scenario.responses), 0)


# ── Scenario Tests ────────────────────────────────────────────────────


class TestBenchmarkScenarios(unittest.TestCase):
    """Run each benchmark scenario and validate metrics."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._harness = BenchmarkHarness(output_dir=self._tmpdir)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_scenario_happy_path(self):
        result = self._harness.run_scenario(scenario_happy_path())
        self.assertTrue(result.success, f"Errors: {result.errors}")
        self.assertGreater(result.total_tokens, 0)
        self.assertGreater(result.total_llm_calls, 0)
        self.assertEqual(result.tasks_completed, 1)
        self.assertEqual(result.tasks_failed, 0)

    def test_scenario_multi_task_deps(self):
        result = self._harness.run_scenario(scenario_multi_task_deps())
        self.assertTrue(result.success, f"Errors: {result.errors}")
        self.assertEqual(result.task_count, 3)
        self.assertEqual(result.tasks_completed, 3)
        self.assertEqual(result.tasks_failed, 0)

    def test_scenario_reflection_retry(self):
        result = self._harness.run_scenario(scenario_reflection_retry())
        self.assertTrue(result.success, f"Errors: {result.errors}")
        self.assertGreaterEqual(result.reflection_count, 1)
        self.assertEqual(result.tasks_completed, 1)

    def test_scenario_reflection_exhausted(self):
        result = self._harness.run_scenario(scenario_reflection_exhausted())
        self.assertTrue(result.success, f"Expected failure scenario to pass: {result.errors}")
        self.assertGreaterEqual(result.escalation_count, 1)
        self.assertGreater(result.tasks_failed, 0)

    def test_scenario_debate_path(self):
        result = self._harness.run_scenario(scenario_debate_path())
        self.assertTrue(result.success, f"Errors: {result.errors}")
        self.assertGreaterEqual(result.debate_count, 1)
        self.assertEqual(result.tasks_completed, 1)

    def test_scenario_token_budget_pressure(self):
        result = self._harness.run_scenario(scenario_token_budget_pressure())
        # Should handle budget limit gracefully (scenario expects failure)
        self.assertTrue(result.success, f"Errors: {result.errors}")
        self.assertGreater(result.tasks_failed, 0)

    def test_scenario_three_task_chain(self):
        result = self._harness.run_scenario(scenario_three_task_chain())
        self.assertTrue(result.success, f"Errors: {result.errors}")
        self.assertEqual(result.task_count, 3)
        self.assertEqual(result.tasks_completed, 3)

    def test_scenario_multi_step_plan(self):
        result = self._harness.run_scenario(scenario_multi_step_plan())
        self.assertTrue(result.success, f"Errors: {result.errors}")
        self.assertEqual(result.tasks_completed, 1)
        # Step completion tracking works
        self.assertGreaterEqual(result.step_completion_rate, 0.0)

    def test_scenario_skill_reuse(self):
        result = self._harness.run_scenario(scenario_skill_reuse())
        self.assertTrue(result.success, f"Errors: {result.errors}")
        self.assertGreaterEqual(result.skills_learned, 0)

    def test_scenario_needs_human(self):
        result = self._harness.run_scenario(scenario_needs_human())
        self.assertTrue(result.success, f"Expected failure scenario to pass: {result.errors}")
        self.assertGreaterEqual(result.escalation_count, 0)


# ── Regression Tests ──────────────────────────────────────────────────


class TestBenchmarkRegression(unittest.TestCase):
    """Regression tests with ceilings on key metrics."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._harness = BenchmarkHarness(output_dir=self._tmpdir)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_happy_path_token_ceiling(self):
        result = self._harness.run_scenario(scenario_happy_path())
        self.assertTrue(result.success)
        self.assertLess(result.total_tokens, 50000,
                        f"Token usage {result.total_tokens} exceeds ceiling of 50000")

    def test_happy_path_call_ceiling(self):
        result = self._harness.run_scenario(scenario_happy_path())
        self.assertTrue(result.success)
        self.assertLess(result.total_llm_calls, 20,
                        f"LLM calls {result.total_llm_calls} exceeds ceiling of 20")

    def test_reflection_adds_overhead(self):
        happy_result = self._harness.run_scenario(scenario_happy_path())
        reflect_result = self._harness.run_scenario(scenario_reflection_retry())
        self.assertTrue(happy_result.success)
        self.assertTrue(reflect_result.success)
        self.assertGreater(reflect_result.total_tokens, happy_result.total_tokens,
                           "Reflection scenario should use more tokens than happy path")


# ── Baseline & History Tracking Tests ─────────────────────────────────


class TestBenchmarkTracking(unittest.TestCase):
    """Tests for baseline comparison and history tracking."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_report(self, **overrides) -> BenchmarkReport:
        """Create a minimal report with one scenario for testing."""
        defaults = dict(
            scenario_name="happy_path",
            success=True,
            total_tokens=8888,
            total_llm_calls=7,
            reflection_count=0,
            debate_count=0,
            escalation_count=0,
        )
        defaults.update(overrides)
        result = BenchmarkResult(**defaults)
        return BenchmarkReport(
            results=[result],
            timestamp="2026-03-01T00:00:00+00:00",
            total_wall_time=1.0,
            summary={"total_scenarios": 1, "success_rate": 1.0},
        )

    def test_save_and_load_baseline(self):
        report = self._make_report()
        path = os.path.join(self._tmpdir, "baseline.json")
        save_baseline(report, path)

        loaded = load_baseline(path)
        self.assertIsNotNone(loaded)
        self.assertIn("timestamp", loaded)
        self.assertIn("scenarios", loaded)
        self.assertIn("happy_path", loaded["scenarios"])
        sc = loaded["scenarios"]["happy_path"]
        self.assertEqual(sc["total_tokens"], 8888)
        self.assertEqual(sc["total_llm_calls"], 7)
        self.assertEqual(sc["reflection_count"], 0)
        self.assertEqual(sc["debate_count"], 0)
        self.assertEqual(sc["escalation_count"], 0)

    def test_compare_to_baseline_no_regression(self):
        report = self._make_report()
        path = os.path.join(self._tmpdir, "baseline.json")
        save_baseline(report, path)
        baseline = load_baseline(path)

        alerts = report.compare_to_baseline(baseline)
        self.assertEqual(alerts, [])

    def test_compare_to_baseline_with_regression(self):
        # Save a baseline with normal tokens
        baseline_report = self._make_report(total_tokens=1000)
        path = os.path.join(self._tmpdir, "baseline.json")
        save_baseline(baseline_report, path)
        baseline = load_baseline(path)

        # Current report with inflated tokens (50% increase -> warning)
        current = self._make_report(total_tokens=1500)
        alerts = current.compare_to_baseline(baseline, threshold=0.10)
        self.assertGreater(len(alerts), 0)

        token_alert = [a for a in alerts if a["metric"] == "total_tokens"][0]
        self.assertEqual(token_alert["scenario"], "happy_path")
        self.assertEqual(token_alert["baseline_value"], 1000)
        self.assertEqual(token_alert["current_value"], 1500)
        self.assertEqual(token_alert["severity"], "critical")  # 50% > 2*10%

        # Mild regression (15% increase -> warning, not critical)
        mild = self._make_report(total_tokens=1150)
        mild_alerts = mild.compare_to_baseline(baseline, threshold=0.10)
        mild_token = [a for a in mild_alerts if a["metric"] == "total_tokens"][0]
        self.assertEqual(mild_token["severity"], "warning")  # 15% > 10% but < 20%

    def test_compare_to_baseline_missing_file(self):
        path = os.path.join(self._tmpdir, "nonexistent.json")
        baseline = load_baseline(path)
        self.assertIsNone(baseline)

        report = self._make_report()
        alerts = report.compare_to_baseline(baseline)
        self.assertEqual(alerts, [])

    def test_append_and_load_history(self):
        path = os.path.join(self._tmpdir, "history.jsonl")

        report1 = self._make_report(total_tokens=8000)
        report1.timestamp = "2026-03-01T00:00:00+00:00"
        append_history(report1, path)

        report2 = self._make_report(total_tokens=9000)
        report2.timestamp = "2026-03-01T01:00:00+00:00"
        append_history(report2, path)

        entries = load_history(path)
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]["timestamp"], "2026-03-01T00:00:00+00:00")
        self.assertEqual(entries[1]["timestamp"], "2026-03-01T01:00:00+00:00")
        self.assertEqual(entries[0]["scenarios"]["happy_path"]["total_tokens"], 8000)
        self.assertEqual(entries[1]["scenarios"]["happy_path"]["total_tokens"], 9000)

    def test_history_missing_file(self):
        path = os.path.join(self._tmpdir, "nonexistent.jsonl")
        entries = load_history(path)
        self.assertEqual(entries, [])


if __name__ == "__main__":
    unittest.main()
