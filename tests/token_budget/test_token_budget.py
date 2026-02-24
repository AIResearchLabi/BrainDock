"""Tests for the token_budget module."""

import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from BrainDock.token_budget import TokenBudgetConfig, TokenBudgetTracker


class TestTokenBudgetConfig(unittest.TestCase):
    """Test TokenBudgetConfig defaults and serialization."""

    def test_defaults(self):
        config = TokenBudgetConfig()
        self.assertEqual(config.global_token_budget, 500_000)
        self.assertEqual(config.per_task_token_budget, 80_000)
        self.assertEqual(config.pre_step_reserve, 15_000)
        self.assertAlmostEqual(config.warn_pct, 0.8)
        self.assertAlmostEqual(config.pause_pct, 0.95)

    def test_roundtrip(self):
        config = TokenBudgetConfig(global_token_budget=100_000, per_task_token_budget=20_000)
        d = config.to_dict()
        restored = TokenBudgetConfig.from_dict(d)
        self.assertEqual(restored.global_token_budget, 100_000)
        self.assertEqual(restored.per_task_token_budget, 20_000)

    def test_custom_values(self):
        config = TokenBudgetConfig(
            global_token_budget=1_000_000,
            per_task_token_budget=200_000,
            pre_step_reserve=30_000,
            warn_pct=0.7,
            pause_pct=0.9,
        )
        self.assertEqual(config.global_token_budget, 1_000_000)
        self.assertAlmostEqual(config.warn_pct, 0.7)

    def test_from_dict_missing_fields(self):
        restored = TokenBudgetConfig.from_dict({})
        self.assertEqual(restored.global_token_budget, 500_000)
        self.assertEqual(restored.per_task_token_budget, 80_000)


class TestTokenBudgetTracker(unittest.TestCase):
    """Test TokenBudgetTracker recording and budget checks."""

    def test_record_updates_counters(self):
        tracker = TokenBudgetTracker()
        tracker.record("planner", 1000, 500)
        snap = tracker.get_snapshot()
        self.assertEqual(snap["global_used"], 1500)
        self.assertEqual(snap["global_input"], 1000)
        self.assertEqual(snap["global_output"], 500)

    def test_record_accumulates(self):
        tracker = TokenBudgetTracker()
        tracker.record("planner", 1000, 500)
        tracker.record("executor", 2000, 1000)
        snap = tracker.get_snapshot()
        self.assertEqual(snap["global_used"], 4500)

    def test_start_task_resets_task_counters(self):
        tracker = TokenBudgetTracker()
        tracker.start_task("t1")
        tracker.record("planner", 1000, 500)
        tracker.start_task("t2")
        snap = tracker.get_snapshot()
        # Task counters reset
        self.assertEqual(snap["task_used"], 0)
        self.assertEqual(snap["task_id"], "t2")
        # Global counters preserved
        self.assertEqual(snap["global_used"], 1500)

    def test_check_pre_step_allowed(self):
        config = TokenBudgetConfig(global_token_budget=100_000, per_task_token_budget=50_000)
        tracker = TokenBudgetTracker(config=config)
        tracker.start_task("t1")
        allowed, reason = tracker.check_pre_step()
        self.assertTrue(allowed)
        self.assertEqual(reason, "")

    def test_check_pre_step_blocked_global(self):
        config = TokenBudgetConfig(global_token_budget=1000, per_task_token_budget=100_000, pre_step_reserve=100)
        tracker = TokenBudgetTracker(config=config)
        tracker.start_task("t1")
        tracker.record("planner", 500, 450)  # 950 of 1000 used
        allowed, reason = tracker.check_pre_step()
        self.assertFalse(allowed)
        self.assertIn("Global token budget", reason)

    def test_check_pre_step_blocked_task(self):
        config = TokenBudgetConfig(global_token_budget=1_000_000, per_task_token_budget=1000, pre_step_reserve=100)
        tracker = TokenBudgetTracker(config=config)
        tracker.start_task("t1")
        tracker.record("planner", 500, 450)  # 950 of 1000 task budget used
        allowed, reason = tracker.check_pre_step()
        self.assertFalse(allowed)
        self.assertIn("Task 't1'", reason)

    def test_agent_totals_tracking(self):
        tracker = TokenBudgetTracker()
        tracker.record("planner", 1000, 500)
        tracker.record("executor", 2000, 800)
        tracker.record("planner", 500, 200)
        snap = tracker.get_snapshot()
        self.assertEqual(snap["agent_totals"]["planner"]["input"], 1500)
        self.assertEqual(snap["agent_totals"]["planner"]["output"], 700)
        self.assertEqual(snap["agent_totals"]["executor"]["input"], 2000)
        self.assertEqual(snap["agent_totals"]["executor"]["output"], 800)

    def test_snapshot_percentages(self):
        config = TokenBudgetConfig(global_token_budget=10_000, per_task_token_budget=5_000)
        tracker = TokenBudgetTracker(config=config)
        tracker.start_task("t1")
        tracker.record("planner", 2500, 2500)  # 5000/10000 global, 5000/5000 task
        snap = tracker.get_snapshot()
        self.assertAlmostEqual(snap["global_pct"], 0.5)
        self.assertAlmostEqual(snap["task_pct"], 1.0)

    def test_threshold_callbacks_warn(self):
        events = []
        def on_threshold(level, scope, used, budget):
            events.append((level, scope, used, budget))

        config = TokenBudgetConfig(global_token_budget=1000, per_task_token_budget=100_000, warn_pct=0.5)
        tracker = TokenBudgetTracker(config=config, on_threshold=on_threshold)
        tracker.start_task("t1")

        tracker.record("planner", 250, 250)  # 500/1000 = 50% → warn
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "warn")
        self.assertEqual(events[0][1], "global")

    def test_threshold_callbacks_pause(self):
        events = []
        def on_threshold(level, scope, used, budget):
            events.append((level, scope, used, budget))

        config = TokenBudgetConfig(global_token_budget=1000, per_task_token_budget=100_000, warn_pct=0.8, pause_pct=0.95)
        tracker = TokenBudgetTracker(config=config, on_threshold=on_threshold)
        tracker.start_task("t1")

        tracker.record("planner", 480, 480)  # 960/1000 = 96% → both warn and pause
        # pause fires but warn doesn't because pause check comes first
        self.assertTrue(any(e[0] == "pause" for e in events))

    def test_threshold_fires_only_once(self):
        events = []
        def on_threshold(level, scope, used, budget):
            events.append((level, scope))

        config = TokenBudgetConfig(global_token_budget=1000, per_task_token_budget=100_000, warn_pct=0.5)
        tracker = TokenBudgetTracker(config=config, on_threshold=on_threshold)
        tracker.start_task("t1")

        tracker.record("planner", 300, 300)  # 600/1000 = 60% → warn
        tracker.record("planner", 50, 50)    # 700/1000 = 70% → no re-fire
        warn_count = sum(1 for e in events if e[0] == "warn" and e[1] == "global")
        self.assertEqual(warn_count, 1)

    def test_task_threshold_resets_on_new_task(self):
        events = []
        def on_threshold(level, scope, used, budget):
            events.append((level, scope))

        config = TokenBudgetConfig(
            global_token_budget=1_000_000,
            per_task_token_budget=1000,
            warn_pct=0.5,
        )
        tracker = TokenBudgetTracker(config=config, on_threshold=on_threshold)

        tracker.start_task("t1")
        tracker.record("planner", 300, 300)  # 600/1000 → task warn
        task_warns_t1 = sum(1 for e in events if e[1] == "task")
        self.assertEqual(task_warns_t1, 1)

        tracker.start_task("t2")
        tracker.record("planner", 300, 300)  # 600/1000 → task warn again for t2
        task_warns_total = sum(1 for e in events if e[1] == "task")
        self.assertEqual(task_warns_total, 2)

    def test_check_pre_step_with_est_tokens(self):
        config = TokenBudgetConfig(global_token_budget=10_000, per_task_token_budget=50_000, pre_step_reserve=100)
        tracker = TokenBudgetTracker(config=config)
        tracker.start_task("t1")
        tracker.record("planner", 4000, 4000)  # 8000 used, 2000 remaining
        # Without est_tokens: 2000 > 100 → allowed
        allowed, _ = tracker.check_pre_step()
        self.assertTrue(allowed)
        # With est_tokens: reserve = 100 + 2000 = 2100 > 2000 → blocked
        allowed, reason = tracker.check_pre_step(est_tokens=2000)
        self.assertFalse(allowed)
        self.assertIn("Global", reason)

    def test_snapshot_empty_tracker(self):
        tracker = TokenBudgetTracker()
        snap = tracker.get_snapshot()
        self.assertEqual(snap["global_used"], 0)
        self.assertEqual(snap["task_used"], 0)
        self.assertEqual(snap["agent_totals"], {})
        self.assertAlmostEqual(snap["global_pct"], 0)


class TestContextProfile(unittest.TestCase):
    """Test context profiles produce different snapshot sizes."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        # Create enough files to fill a full-size snapshot
        for i in range(50):
            with open(os.path.join(self._tmpdir, f"file_{i:03d}.py"), "w") as f:
                f.write(f"# File {i}\n" + "x = 1\n" * 200)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_profile_budgets_exist(self):
        from BrainDock.project_memory import ContextProfile, PROFILE_BUDGETS
        self.assertIn(ContextProfile.FULL, PROFILE_BUDGETS)
        self.assertIn(ContextProfile.MEDIUM, PROFILE_BUDGETS)
        self.assertIn(ContextProfile.LIGHT, PROFILE_BUDGETS)
        self.assertIn(ContextProfile.MINIMAL, PROFILE_BUDGETS)

    def test_profiles_produce_different_sizes(self):
        from BrainDock.project_memory import scan_project
        full = scan_project(self._tmpdir, profile="full")
        medium = scan_project(self._tmpdir, profile="medium")
        light = scan_project(self._tmpdir, profile="light")
        minimal = scan_project(self._tmpdir, profile="minimal")

        full_size = len(full.to_context_string())
        medium_size = len(medium.to_context_string())
        light_size = len(light.to_context_string())
        minimal_size = len(minimal.to_context_string())

        # Each profile should produce smaller or equal output
        self.assertGreaterEqual(full_size, medium_size)
        self.assertGreaterEqual(medium_size, light_size)
        self.assertGreaterEqual(light_size, minimal_size)

    def test_default_profile_is_full(self):
        from BrainDock.project_memory import scan_project
        default = scan_project(self._tmpdir)
        full = scan_project(self._tmpdir, profile="full")
        # Same number of key files
        self.assertEqual(len(default.key_file_contents), len(full.key_file_contents))


class TestAdaptiveProfile(unittest.TestCase):
    """Test the _adaptive_profile function for dynamic context compression."""

    def test_no_downgrade_below_50pct(self):
        from BrainDock.orchestrator.agent import _adaptive_profile
        from BrainDock.project_memory import ContextProfile
        self.assertEqual(_adaptive_profile(ContextProfile.FULL, 0.0), ContextProfile.FULL)
        self.assertEqual(_adaptive_profile(ContextProfile.FULL, 0.3), ContextProfile.FULL)
        self.assertEqual(_adaptive_profile(ContextProfile.FULL, 0.49), ContextProfile.FULL)
        self.assertEqual(_adaptive_profile(ContextProfile.MEDIUM, 0.3), ContextProfile.MEDIUM)

    def test_one_level_downgrade_at_50pct(self):
        from BrainDock.orchestrator.agent import _adaptive_profile
        from BrainDock.project_memory import ContextProfile
        self.assertEqual(_adaptive_profile(ContextProfile.FULL, 0.5), ContextProfile.MEDIUM)
        self.assertEqual(_adaptive_profile(ContextProfile.MEDIUM, 0.6), ContextProfile.LIGHT)
        self.assertEqual(_adaptive_profile(ContextProfile.LIGHT, 0.7), ContextProfile.MINIMAL)

    def test_two_level_downgrade_at_80pct(self):
        from BrainDock.orchestrator.agent import _adaptive_profile
        from BrainDock.project_memory import ContextProfile
        self.assertEqual(_adaptive_profile(ContextProfile.FULL, 0.8), ContextProfile.LIGHT)
        self.assertEqual(_adaptive_profile(ContextProfile.FULL, 0.95), ContextProfile.LIGHT)
        self.assertEqual(_adaptive_profile(ContextProfile.MEDIUM, 0.85), ContextProfile.MINIMAL)

    def test_clamps_at_minimal(self):
        from BrainDock.orchestrator.agent import _adaptive_profile
        from BrainDock.project_memory import ContextProfile
        # Already minimal — can't go lower
        self.assertEqual(_adaptive_profile(ContextProfile.MINIMAL, 0.5), ContextProfile.MINIMAL)
        self.assertEqual(_adaptive_profile(ContextProfile.MINIMAL, 0.9), ContextProfile.MINIMAL)
        # Light at 80%+ → minimal (clamped)
        self.assertEqual(_adaptive_profile(ContextProfile.LIGHT, 0.85), ContextProfile.MINIMAL)

    def test_unknown_profile_passthrough(self):
        from BrainDock.orchestrator.agent import _adaptive_profile
        self.assertEqual(_adaptive_profile("custom", 0.9), "custom")


if __name__ == "__main__":
    unittest.main()
