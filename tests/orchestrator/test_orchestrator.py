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
            "tags": [],
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

        # Output files should exist (under slugified project dir)
        project_dir = os.path.join(self._tmpdir, "build-a-cli-calculator")
        self.assertTrue(os.path.exists(os.path.join(project_dir, "spec_agent", "spec.json")))
        self.assertTrue(os.path.exists(os.path.join(project_dir, "task_graph", "task_graph.json")))


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


class TestProjectMemory(unittest.TestCase):
    """Test the project_memory module."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_scan_empty_dir(self):
        from BrainDock.project_memory import scan_project
        snapshot = scan_project(self._tmpdir)
        self.assertEqual(snapshot.total_files, 0)
        self.assertEqual(snapshot.key_file_contents, {})
        self.assertIn("empty", snapshot.to_context_string())

    def test_scan_with_files(self):
        from BrainDock.project_memory import scan_project
        # Create some files
        with open(os.path.join(self._tmpdir, "main.py"), "w") as f:
            f.write("print('hello')\n")
        with open(os.path.join(self._tmpdir, "utils.py"), "w") as f:
            f.write("def helper(): pass\n")

        snapshot = scan_project(self._tmpdir)
        self.assertEqual(snapshot.total_files, 2)
        self.assertIn("main.py", snapshot.key_file_contents)
        ctx = snapshot.to_context_string()
        self.assertIn("main.py", ctx)
        self.assertIn("print('hello')", ctx)

    def test_scan_skips_binary(self):
        from BrainDock.project_memory import scan_project
        with open(os.path.join(self._tmpdir, "image.png"), "wb") as f:
            f.write(b"\x89PNG\r\n")
        with open(os.path.join(self._tmpdir, "main.py"), "w") as f:
            f.write("x = 1\n")

        snapshot = scan_project(self._tmpdir)
        self.assertNotIn("image.png", snapshot.key_file_contents)
        self.assertIn("main.py", snapshot.key_file_contents)

    def test_scan_prioritizes_key_files(self):
        from BrainDock.project_memory import scan_project
        # main.py should come before random files
        with open(os.path.join(self._tmpdir, "main.py"), "w") as f:
            f.write("entry\n")
        with open(os.path.join(self._tmpdir, "zzz_other.py"), "w") as f:
            f.write("other\n")

        snapshot = scan_project(self._tmpdir)
        keys = list(snapshot.key_file_contents.keys())
        self.assertEqual(keys[0], "main.py")


class TestVerifyProject(unittest.TestCase):
    """Test the verify_project function."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_verify_success(self):
        from BrainDock.executor.sandbox import verify_project
        with open(os.path.join(self._tmpdir, "main.py"), "w") as f:
            f.write("print('hello')\n")
        result = verify_project(self._tmpdir, timeout=10)
        self.assertTrue(result.success)
        self.assertEqual(result.detection_method, "main.py")

    def test_verify_failure(self):
        from BrainDock.executor.sandbox import verify_project
        with open(os.path.join(self._tmpdir, "main.py"), "w") as f:
            f.write("raise Exception('boom')\n")
        result = verify_project(self._tmpdir, timeout=10)
        self.assertFalse(result.success)
        self.assertIn("boom", result.error_summary + result.stderr)

    def test_verify_no_entry_point(self):
        from BrainDock.executor.sandbox import verify_project
        result = verify_project(self._tmpdir, timeout=10)
        self.assertTrue(result.success)  # No entry point → skip → success
        self.assertEqual(result.detection_method, "none")

    def test_verify_syntax_error(self):
        from BrainDock.executor.sandbox import verify_project
        with open(os.path.join(self._tmpdir, "main.py"), "w") as f:
            f.write("def foo(\n")  # SyntaxError
        result = verify_project(self._tmpdir, timeout=10)
        self.assertFalse(result.success)


class TestVerifyResult(unittest.TestCase):
    """Test the VerifyResult model."""

    def test_to_dict(self):
        from BrainDock.executor.models import VerifyResult
        vr = VerifyResult(success=True, command="python main.py", exit_code=0)
        d = vr.to_dict()
        self.assertTrue(d["success"])
        self.assertEqual(d["command"], "python main.py")


class TestTaskOutcomeAffectedFile(unittest.TestCase):
    """Test the affected_file field on TaskOutcome."""

    def test_affected_file_roundtrip(self):
        from BrainDock.executor.models import TaskOutcome
        o = TaskOutcome(step_id="s1", success=True, affected_file="calc.py")
        d = o.to_dict()
        self.assertEqual(d["affected_file"], "calc.py")
        restored = TaskOutcome.from_dict(d)
        self.assertEqual(restored.affected_file, "calc.py")


class TestPipelineStateVerificationResults(unittest.TestCase):
    """Test that verification_results is included in PipelineState."""

    def test_verification_results_default(self):
        state = PipelineState()
        self.assertEqual(state.verification_results, [])

    def test_verification_results_roundtrip(self):
        state = PipelineState()
        state.verification_results = [{"success": True, "command": "python main.py"}]
        d = state.to_dict()
        restored = PipelineState.from_dict(d)
        self.assertEqual(len(restored.verification_results), 1)
        self.assertTrue(restored.verification_results[0]["success"])


class TestReadFileSafe(unittest.TestCase):
    """Test the read_file_safe function."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_read_existing_file(self):
        from BrainDock.executor.sandbox import read_file_safe
        with open(os.path.join(self._tmpdir, "test.py"), "w") as f:
            f.write("content\n")
        result = read_file_safe("test.py", self._tmpdir)
        self.assertEqual(result, "content\n")

    def test_read_nonexistent_file(self):
        from BrainDock.executor.sandbox import read_file_safe
        result = read_file_safe("nonexistent.py", self._tmpdir)
        self.assertIsNone(result)

    def test_read_path_traversal(self):
        from BrainDock.executor.sandbox import read_file_safe
        result = read_file_safe("../../etc/passwd", self._tmpdir)
        self.assertIsNone(result)


class TestPipelineStateMarketStudies(unittest.TestCase):
    """Test that market_studies is included in PipelineState."""

    def test_market_studies_default(self):
        state = PipelineState()
        self.assertEqual(state.market_studies, [])

    def test_market_studies_roundtrip(self):
        state = PipelineState()
        state.market_studies = [{"task_id": "t1", "competitors": ["Acme"]}]
        d = state.to_dict()
        restored = PipelineState.from_dict(d)
        self.assertEqual(len(restored.market_studies), 1)
        self.assertEqual(restored.market_studies[0]["task_id"], "t1")


class TestTaskNodeTags(unittest.TestCase):
    """Test that tags field works on TaskNode."""

    def test_tags_default(self):
        from BrainDock.task_graph.models import TaskNode
        node = TaskNode(id="t1", title="Test", description="Desc")
        self.assertEqual(node.tags, [])

    def test_tags_roundtrip(self):
        from BrainDock.task_graph.models import TaskNode
        node = TaskNode(id="t1", title="Test", description="Desc", tags=["needs_market_study"])
        d = node.to_dict()
        self.assertEqual(d["tags"], ["needs_market_study"])
        restored = TaskNode.from_dict(d)
        self.assertEqual(restored.tags, ["needs_market_study"])


class TestMarketStudyResult(unittest.TestCase):
    """Test the MarketStudyResult model."""

    def test_roundtrip(self):
        from BrainDock.market_study.models import MarketStudyResult
        result = MarketStudyResult(
            task_id="t1",
            competitors=["Acme", "Corp"],
            recommendations=["Focus on UX"],
            risks=["Market saturation"],
            target_audience="Developers",
            positioning="Best-in-class CLI tool",
        )
        d = result.to_dict()
        self.assertEqual(d["task_id"], "t1")
        self.assertEqual(d["competitors"], ["Acme", "Corp"])

        restored = MarketStudyResult.from_dict(d)
        self.assertEqual(restored.task_id, "t1")
        self.assertEqual(restored.positioning, "Best-in-class CLI tool")

    def test_to_context_string(self):
        from BrainDock.market_study.models import MarketStudyResult
        result = MarketStudyResult(
            task_id="t1",
            competitors=["Acme"],
            target_audience="Devs",
            positioning="Leader",
        )
        ctx = result.to_context_string()
        self.assertIn("t1", ctx)
        self.assertIn("Acme", ctx)
        self.assertIn("Devs", ctx)


class TestBaseAgentRetry(unittest.TestCase):
    """Test that BaseAgent retries on transient failures."""

    def test_retry_on_runtime_error(self):
        from BrainDock.base_agent import BaseAgent, MAX_LLM_RETRIES
        call_count = {"n": 0}

        class FailOnceBackend:
            def query(self, system_prompt, user_prompt):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise RuntimeError("Transient failure")
                return '{"result": "ok"}'

        agent = BaseAgent(llm=FailOnceBackend())
        result = agent._llm_query_json("sys", "user")
        self.assertEqual(result, {"result": "ok"})
        self.assertEqual(call_count["n"], 2)

    def test_persistent_failure_raises(self):
        from BrainDock.base_agent import BaseAgent, MAX_LLM_RETRIES

        class AlwaysFailBackend:
            def query(self, system_prompt, user_prompt):
                raise RuntimeError("Always fails")

        agent = BaseAgent(llm=AlwaysFailBackend())
        with self.assertRaises(RuntimeError):
            agent._llm_query_json("sys", "user")


if __name__ == "__main__":
    unittest.main()
