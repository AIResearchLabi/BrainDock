"""Tests for the Orchestrator module."""

import json
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from BrainDock.orchestrator.models import Mode, PipelineState, RunConfig
from BrainDock.orchestrator.agent import OrchestratorAgent
from BrainDock.llm import CallableBackend


# ── Mock Responses ─────────────────────────────────────────────────────

# Spec agent responses (analyze, refine, generate)
SPEC_ANALYZE = json.dumps({
    "understanding": "Building a CLI calculator",
    "self_decided": [
        {"id": "d1", "topic": "Language", "decision": "Python 3.11+"},
    ],
    "user_questions": [],
})

# Refine response (needed because run() calls refine even with 0 questions)
SPEC_REFINE = json.dumps({
    "ready": True,
    "understanding": "Building a CLI calculator — clear requirements",
    "self_decided": [],
    "user_questions": [],
})

SPEC_GENERATE = json.dumps({
    "title": "PyCalc",
    "summary": "A CLI calculator",
    "problem_statement": "Need a calculator",
    "goals": ["Fast arithmetic"],
    "target_users": "Developers",
    "user_stories": ["As a user, I want to calculate"],
    "functional_requirements": [
        {"feature": "Eval", "description": "Evaluate expressions", "acceptance_criteria": ["Works"], "priority": "must-have"}
    ],
    "non_functional_requirements": ["Fast"],
    "tech_stack": {"language": "Python"},
    "architecture_overview": "Single file",
    "data_models": [],
    "api_endpoints": [],
    "milestones": [{"name": "v1", "description": "Done", "deliverables": ["Calculator"]}],
    "constraints": [],
    "assumptions": [],
    "open_questions": [],
})

# Task graph response
TASK_GRAPH = json.dumps({
    "project_title": "PyCalc",
    "tasks": [
        {
            "id": "t1",
            "title": "Create calculator module",
            "description": "Write the main calculator with eval support",
            "depends_on": [],
            "estimated_effort": "small",
            "risks": [],
        }
    ],
})

# Plan response
PLAN = json.dumps({
    "task_id": "t1",
    "task_title": "Create calculator module",
    "steps": [
        {
            "id": "s1",
            "action": "Write calculator",
            "description": "Create calc.py with eval function",
            "tool": "write_file",
            "expected_output": "calc.py file",
        }
    ],
    "metrics": {
        "confidence": 0.9,
        "entropy": 0.1,
        "estimated_steps": 1,
        "complexity": "low",
    },
    "relevant_skills": [],
    "assumptions": [],
})

# Executor response
EXEC_WRITE = json.dumps({
    "step_id": "s1",
    "action_type": "write_file",
    "file_path": "calc.py",
    "content": "def calc(expr): return eval(expr)\n",
    "verification": "File exists",
})

# Skill extraction response
SKILL_EXTRACT = json.dumps({
    "id": "skill_eval_pattern",
    "name": "Expression Evaluation",
    "description": "Evaluate user expressions safely",
    "tags": ["parsing", "evaluation"],
    "pattern": "eval with validation",
    "example_code": "def calc(expr): return eval(expr)",
})


def make_pipeline_llm():
    """Mock LLM that returns responses for the full pipeline."""
    call_count = {"n": 0}
    responses = [
        SPEC_ANALYZE,    # spec analyze
        SPEC_REFINE,     # spec refine (run() calls refine even with 0 questions)
        SPEC_GENERATE,   # spec generate
        TASK_GRAPH,      # task graph decompose
        PLAN,            # planner plan_task
        EXEC_WRITE,      # executor execute_step
        SKILL_EXTRACT,   # skill extraction
    ]

    def mock_fn(system_prompt, user_prompt):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]

    return CallableBackend(mock_fn)


def make_plan_only_llm():
    """Mock LLM for plan-only mode (spec + task_graph + plan only)."""
    call_count = {"n": 0}
    responses = [SPEC_ANALYZE, SPEC_REFINE, SPEC_GENERATE, TASK_GRAPH]

    def mock_fn(system_prompt, user_prompt):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]

    return CallableBackend(mock_fn)


# ── Tests ──────────────────────────────────────────────────────────────

class TestMode(unittest.TestCase):
    def test_values(self):
        self.assertEqual(Mode.SPECIFICATION.value, "specification")
        self.assertEqual(Mode.DEBATE.value, "debate")
        self.assertEqual(len(Mode), 8)


class TestRunConfig(unittest.TestCase):
    def test_defaults(self):
        config = RunConfig()
        self.assertEqual(config.output_dir, "output")
        self.assertFalse(config.skip_execution)
        self.assertAlmostEqual(config.min_confidence, 0.6)

    def test_roundtrip(self):
        config = RunConfig(output_dir="/tmp/test", skip_execution=True)
        d = config.to_dict()
        restored = RunConfig.from_dict(d)
        self.assertEqual(restored.output_dir, "/tmp/test")
        self.assertTrue(restored.skip_execution)


class TestPipelineState(unittest.TestCase):
    def test_defaults(self):
        state = PipelineState()
        self.assertEqual(state.current_mode, Mode.SPECIFICATION.value)
        self.assertEqual(state.spec, {})
        self.assertEqual(state.completed_tasks, [])

    def test_roundtrip(self):
        state = PipelineState()
        state.spec = {"title": "Test"}
        state.completed_tasks = ["t1"]
        d = state.to_dict()
        restored = PipelineState.from_dict(d)
        self.assertEqual(restored.spec["title"], "Test")
        self.assertEqual(restored.completed_tasks, ["t1"])


class TestOrchestratorPlanOnly(unittest.TestCase):
    """Test orchestrator in plan-only mode (no execution)."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_plan_only_produces_spec_and_graph(self):
        config = RunConfig(output_dir=self._tmpdir, skip_execution=True)
        orchestrator = OrchestratorAgent(llm=make_plan_only_llm(), config=config)

        def ask_fn(questions, decisions, understanding):
            return {}

        state = orchestrator.run(problem="Build a CLI calculator", ask_fn=ask_fn)

        # Should have spec
        self.assertEqual(state.spec["title"], "PyCalc")

        # Should have task graph
        self.assertEqual(state.task_graph["project_title"], "PyCalc")
        self.assertEqual(len(state.task_graph["tasks"]), 1)

        # Should NOT have execution results (plan-only)
        self.assertEqual(len(state.execution_results), 0)

        # Output files should exist
        self.assertTrue(os.path.exists(os.path.join(self._tmpdir, "spec_agent", "spec.json")))
        self.assertTrue(os.path.exists(os.path.join(self._tmpdir, "task_graph", "task_graph.json")))


class TestOrchestratorFullPipeline(unittest.TestCase):
    """Test orchestrator with full pipeline execution."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_full_pipeline(self):
        config = RunConfig(output_dir=self._tmpdir)
        orchestrator = OrchestratorAgent(llm=make_pipeline_llm(), config=config)

        def ask_fn(questions, decisions, understanding):
            return {}

        state = orchestrator.run(problem="Build a CLI calculator", ask_fn=ask_fn)

        # Should have completed all stages
        self.assertEqual(state.spec["title"], "PyCalc")
        self.assertEqual(len(state.plans), 1)
        self.assertGreater(len(state.execution_results), 0)
        self.assertEqual(state.completed_tasks, ["t1"])
        self.assertEqual(len(state.failed_tasks), 0)

        # Skill should have been learned
        self.assertEqual(len(state.learned_skills), 1)
        self.assertEqual(state.learned_skills[0]["id"], "skill_eval_pattern")

    def test_full_pipeline_no_skill_learning(self):
        config = RunConfig(output_dir=self._tmpdir, skip_skill_learning=True)
        orchestrator = OrchestratorAgent(llm=make_pipeline_llm(), config=config)

        def ask_fn(questions, decisions, understanding):
            return {}

        state = orchestrator.run(problem="Build a CLI calculator", ask_fn=ask_fn)

        self.assertEqual(state.completed_tasks, ["t1"])
        self.assertEqual(len(state.learned_skills), 0)


if __name__ == "__main__":
    unittest.main()
