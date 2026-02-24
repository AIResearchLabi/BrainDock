"""Live end-to-end tests that make real LLM calls via ``claude`` CLI.

These tests are **opt-in** because real LLM calls are slow (~500s for
the full suite), cost tokens, and are inherently non-deterministic.

Run explicitly::

    RUN_LIVE_TESTS=1 python -m unittest tests.e2e.test_e2e_live -v

Optionally specify a model::

    BRAINDOCK_TEST_MODEL=haiku RUN_LIVE_TESTS=1 python -m unittest tests.e2e.test_e2e_live -v

Each test uses the simplest possible prompts to minimise token usage.
Assertions are structural (field existence, types) rather than exact
value matches, since LLM output is non-deterministic.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))


# ── Skip guard ────────────────────────────────────────────────────────

def _claude_available() -> bool:
    """Check whether ``claude`` CLI is reachable."""
    try:
        r = subprocess.run(
            ["claude", "--version"],
            capture_output=True, text=True, timeout=10,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


_RUN_LIVE = os.environ.get("RUN_LIVE_TESTS", "0") == "1"
_SKIP_LIVE = not _RUN_LIVE or not _claude_available()
_SKIP_REASON = (
    "Set RUN_LIVE_TESTS=1 to enable live LLM tests"
    if not _RUN_LIVE
    else "claude CLI not available"
)


# ── Imports (deferred after skip check) ───────────────────────────────

from BrainDock.llm import ClaudeCLIBackend
from BrainDock.spec_agent.agent import SpecAgent
from BrainDock.task_graph.agent import TaskGraphAgent
from BrainDock.planner.agent import PlannerAgent
from BrainDock.executor.agent import ExecutorAgent
from BrainDock.executor.models import StopCondition
from BrainDock.reflection.agent import ReflectionAgent
from BrainDock.skill_bank.agent import SkillLearningAgent
from BrainDock.orchestrator.agent import OrchestratorAgent
from BrainDock.orchestrator.models import RunConfig

# Use the configured model, defaulting to claude CLI's default (most reliable
# for JSON output).  Set BRAINDOCK_TEST_MODEL=haiku to use a faster/cheaper model.
_TEST_MODEL = os.environ.get("BRAINDOCK_TEST_MODEL") or None
_LLM = ClaudeCLIBackend(model=_TEST_MODEL)

# A deliberately trivial project spec used by several tests.
_MINI_SPEC = {
    "title": "hello",
    "summary": "Print hello world",
    "problem_statement": "Print hello world to stdout",
    "goals": ["Print hello world"],
    "target_users": "Developers",
    "user_stories": [],
    "functional_requirements": [
        {"feature": "Print", "description": "Print hello world",
         "acceptance_criteria": ["Prints hello world"], "priority": "must-have"},
    ],
    "non_functional_requirements": [],
    "tech_stack": {"language": "Python"},
    "architecture_overview": "Single file",
    "data_models": [],
    "api_endpoints": [],
    "milestones": [{"name": "v1", "description": "Done", "deliverables": ["Script"]}],
    "constraints": [],
    "assumptions": [],
    "open_questions": [],
}

# A trivial task used by planner / executor tests.
_MINI_TASK = {
    "id": "t1",
    "title": "Create hello world script",
    "description": "Create a Python script that prints 'hello world'",
    "depends_on": [],
    "estimated_effort": "small",
    "tags": [],
    "risks": [],
}


# ── Individual Agent Tests ────────────────────────────────────────────

@unittest.skipIf(_SKIP_LIVE, _SKIP_REASON)
class TestLiveSpecAnalyze(unittest.TestCase):
    """SpecAgent.analyze() returns well-structured JSON from real LLM."""

    def test_analyze_returns_understanding(self):
        agent = SpecAgent(problem="Print hello world", llm=_LLM)
        result = agent.analyze()

        self.assertIsInstance(result.understanding, str)
        self.assertGreater(len(result.understanding), 0)
        # Decisions or questions may or may not be present — both valid
        self.assertIsInstance(result.decisions, list)
        self.assertIsInstance(result.questions, list)


@unittest.skipIf(_SKIP_LIVE, _SKIP_REASON)
class TestLiveTaskGraph(unittest.TestCase):
    """TaskGraphAgent.decompose() returns a valid task graph."""

    def test_decompose_returns_tasks(self):
        agent = TaskGraphAgent(llm=_LLM)
        graph = agent.decompose(_MINI_SPEC)

        self.assertGreater(len(graph.tasks), 0)
        for task in graph.tasks:
            self.assertTrue(task.id, "Task must have an id")
            self.assertTrue(task.title, "Task must have a title")
            self.assertIsInstance(task.depends_on, list)


@unittest.skipIf(_SKIP_LIVE, _SKIP_REASON)
class TestLivePlanner(unittest.TestCase):
    """PlannerAgent.plan_task() returns a valid action plan."""

    def test_plan_has_steps_and_metrics(self):
        agent = PlannerAgent(llm=_LLM)
        plan = agent.plan_task(_MINI_TASK, context="Project: hello world printer")

        self.assertEqual(plan.task_id, "t1")
        self.assertGreater(len(plan.steps), 0)
        for step in plan.steps:
            self.assertTrue(step.id)
            self.assertIsInstance(step.tool, str)
        self.assertGreaterEqual(plan.metrics.confidence, 0.0)
        self.assertLessEqual(plan.metrics.confidence, 1.0)
        self.assertGreaterEqual(plan.metrics.entropy, 0.0)
        self.assertLessEqual(plan.metrics.entropy, 1.0)


@unittest.skipIf(_SKIP_LIVE, _SKIP_REASON)
class TestLiveExecutorStep(unittest.TestCase):
    """ExecutorAgent.execute_step() returns a valid TaskOutcome and writes a file."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_execute_write_file_step(self):
        agent = ExecutorAgent(llm=_LLM)
        step = {
            "id": "s1",
            "action": "Write hello.py",
            "description": "Create hello.py that prints 'hello world'",
            "tool": "write_file",
            "expected_output": "hello.py",
        }
        outcome = agent.execute_step(step, self._tmpdir, [])

        self.assertIsInstance(outcome.success, bool)
        self.assertTrue(outcome.step_id)
        # If it succeeded, a file should exist
        if outcome.success and outcome.affected_file:
            self.assertTrue(
                os.path.exists(os.path.join(self._tmpdir, outcome.affected_file)),
            )


@unittest.skipIf(_SKIP_LIVE, _SKIP_REASON)
class TestLiveReflection(unittest.TestCase):
    """ReflectionAgent.reflect() returns structured analysis."""

    def test_reflect_on_failure(self):
        agent = ReflectionAgent(llm=_LLM, max_iterations=1)
        fake_exec = {
            "task_id": "t1",
            "success": False,
            "outcomes": [
                {"step_id": "s1", "success": False,
                 "output": "exit code 1", "error": "Command failed"},
            ],
            "steps_completed": 1,
            "steps_total": 1,
            "failure_count": 1,
            "stop_reason": "Some steps failed",
        }
        fake_plan = {
            "task_id": "t1",
            "task_title": "Create hello script",
            "steps": [
                {"id": "s1", "action": "Run failing", "description": "exit 1",
                 "tool": "run_command"},
            ],
            "metrics": {"confidence": 0.9, "entropy": 0.1},
        }

        result = agent.reflect(fake_exec, fake_plan, context="Simple hello project")

        self.assertIsInstance(result.summary, str)
        self.assertIsInstance(result.should_retry, bool)
        self.assertIsInstance(result.root_causes, list)
        self.assertIsInstance(result.needs_human, bool)


@unittest.skipIf(_SKIP_LIVE, _SKIP_REASON)
class TestLiveSkillExtraction(unittest.TestCase):
    """SkillLearningAgent.extract_skill() returns a valid Skill."""

    def test_extract_produces_skill(self):
        agent = SkillLearningAgent(llm=_LLM)
        skill = agent.extract_skill(
            task_description="Print hello world",
            solution_code="print('hello world')",
            outcome="Task completed successfully",
        )

        self.assertTrue(skill.id)
        self.assertTrue(skill.name)
        self.assertIsInstance(skill.tags, list)
        self.assertIsInstance(skill.description, str)


# ── Pipeline-Level Live Tests ─────────────────────────────────────────

@unittest.skipIf(_SKIP_LIVE, _SKIP_REASON)
class TestLivePlanOnlyPipeline(unittest.TestCase):
    """Orchestrator with skip_execution=True: spec → task_graph only."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_plan_only_produces_spec_and_graph(self):
        config = RunConfig(output_dir=self._tmpdir, skip_execution=True)
        orchestrator = OrchestratorAgent(llm=_LLM, config=config)

        def ask_fn(questions, decisions, understanding):
            return {}

        state = orchestrator.run(
            problem="Create a Python script that prints hello world",
            ask_fn=ask_fn,
        )

        # Spec generated with real LLM
        self.assertIn("title", state.spec)
        self.assertTrue(state.spec["title"])

        # Task graph generated
        self.assertIn("tasks", state.task_graph)
        self.assertGreater(len(state.task_graph["tasks"]), 0)

        # No execution (plan only)
        self.assertEqual(len(state.execution_results), 0)

        # State file persisted
        slug_candidates = os.listdir(self._tmpdir)
        self.assertGreater(len(slug_candidates), 0)
        run_dir = os.path.join(self._tmpdir, slug_candidates[0])
        self.assertTrue(os.path.isfile(os.path.join(run_dir, "pipeline_state.json")))


@unittest.skipIf(_SKIP_LIVE, _SKIP_REASON)
class TestLiveFullPipeline(unittest.TestCase):
    """Full pipeline: spec → task_graph → plan → execute → verify → skill.

    Uses the simplest possible problem ("print hello world") to minimise
    token usage and execution time.
    """

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_full_pipeline_completes(self):
        config = RunConfig(output_dir=self._tmpdir)
        orchestrator = OrchestratorAgent(llm=_LLM, config=config)

        activities = []

        def ask_fn(questions, decisions, understanding):
            return {}

        def on_activity(agent, action, detail="", status="info"):
            activities.append({"agent": agent, "action": action, "status": status})

        state = orchestrator.run(
            problem="Create a Python script that prints hello world",
            ask_fn=ask_fn,
            on_activity=on_activity,
        )

        # Spec generated
        self.assertIn("title", state.spec)
        self.assertTrue(state.spec["title"])

        # Task graph generated
        self.assertIn("tasks", state.task_graph)
        self.assertGreater(len(state.task_graph["tasks"]), 0)

        # At least one plan was created
        self.assertGreater(len(state.plans), 0)

        # Execution attempted
        self.assertGreater(len(state.execution_results), 0)

        # At least one task completed or failed (pipeline didn't hang)
        total_tasks = len(state.completed_tasks) + len(state.failed_tasks)
        self.assertGreater(total_tasks, 0)

        # Activities were logged throughout
        agents_seen = {a["agent"] for a in activities}
        self.assertIn("spec", agents_seen)
        self.assertIn("task_graph", agents_seen)
        self.assertIn("planner", agents_seen)
        self.assertIn("executor", agents_seen)

        # Pipeline state persisted
        slug_candidates = os.listdir(self._tmpdir)
        self.assertGreater(len(slug_candidates), 0)
        run_dir = os.path.join(self._tmpdir, slug_candidates[0])
        state_path = os.path.join(run_dir, "pipeline_state.json")
        self.assertTrue(os.path.isfile(state_path))

        # State file is valid JSON and round-trips
        with open(state_path) as f:
            data = json.load(f)
        from BrainDock.orchestrator.models import PipelineState
        restored = PipelineState.from_dict(data)
        self.assertEqual(restored.spec["title"], state.spec["title"])


if __name__ == "__main__":
    unittest.main()
