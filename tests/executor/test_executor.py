"""Tests for the Executor module."""

import json
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from BrainDock.executor.models import TaskOutcome, StopCondition, ExecutionResult
from BrainDock.executor.agent import ExecutorAgent
from BrainDock.executor.sandbox import run_sandboxed, write_file_safe
from BrainDock.llm import CallableBackend


# ── Mock Responses ─────────────────────────────────────────────────────

WRITE_FILE_RESPONSE = json.dumps({
    "step_id": "s1",
    "action_type": "write_file",
    "file_path": "src/models.py",
    "content": "class User:\n    pass\n",
    "verification": "File exists with User class",
})

RUN_COMMAND_RESPONSE = json.dumps({
    "step_id": "s2",
    "action_type": "run_command",
    "file_path": "",
    "content": "echo 'hello world'",
    "verification": "Output contains hello",
})


def make_executor_llm():
    call_count = {"n": 0}
    responses = [WRITE_FILE_RESPONSE, RUN_COMMAND_RESPONSE]

    def mock_fn(system_prompt, user_prompt):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]

    return CallableBackend(mock_fn)


def make_failing_llm():
    """LLM that returns a command that will fail."""
    return CallableBackend(lambda s, u: json.dumps({
        "step_id": "s_fail",
        "action_type": "run_command",
        "file_path": "",
        "content": "exit 1",
        "verification": "",
    }))


# ── Tests ──────────────────────────────────────────────────────────────

class TestTaskOutcome(unittest.TestCase):
    def test_roundtrip(self):
        o = TaskOutcome(step_id="s1", success=True, output="OK")
        d = o.to_dict()
        restored = TaskOutcome.from_dict(d)
        self.assertEqual(restored.step_id, "s1")
        self.assertTrue(restored.success)

    def test_failure(self):
        o = TaskOutcome(step_id="s1", success=False, error="Crash")
        self.assertFalse(o.success)
        self.assertEqual(o.error, "Crash")


class TestStopCondition(unittest.TestCase):
    def test_defaults(self):
        s = StopCondition()
        self.assertEqual(s.max_steps, 50)
        self.assertEqual(s.max_failures, 3)

    def test_roundtrip(self):
        s = StopCondition(max_steps=10, max_failures=1)
        d = s.to_dict()
        restored = StopCondition.from_dict(d)
        self.assertEqual(restored.max_steps, 10)


class TestExecutionResult(unittest.TestCase):
    def test_roundtrip(self):
        r = ExecutionResult(
            task_id="t1",
            success=True,
            outcomes=[TaskOutcome(step_id="s1", success=True, output="OK")],
            steps_completed=1,
            steps_total=1,
        )
        d = r.to_dict()
        restored = ExecutionResult.from_dict(d)
        self.assertEqual(restored.task_id, "t1")
        self.assertTrue(restored.success)
        self.assertEqual(len(restored.outcomes), 1)


class TestSandbox(unittest.TestCase):
    def test_run_sandboxed_success(self):
        success, output = run_sandboxed("echo hello", cwd="/tmp")
        self.assertTrue(success)
        self.assertIn("hello", output)

    def test_run_sandboxed_failure(self):
        success, output = run_sandboxed("exit 1", cwd="/tmp")
        self.assertFalse(success)

    def test_write_file_safe(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            success, msg = write_file_safe("test.txt", "content", tmpdir)
            self.assertTrue(success)
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "test.txt")))

    def test_write_file_safe_nested(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            success, msg = write_file_safe("a/b/c.txt", "content", tmpdir)
            self.assertTrue(success)
            self.assertTrue(os.path.exists(os.path.join(tmpdir, "a", "b", "c.txt")))

    def test_write_file_safe_escape(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            success, msg = write_file_safe("../../etc/passwd", "hack", tmpdir)
            self.assertFalse(success)
            self.assertIn("escapes", msg)


class TestExecutorAgent(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_execute_step_write_file(self):
        agent = ExecutorAgent(llm=CallableBackend(lambda s, u: WRITE_FILE_RESPONSE))
        step = {"id": "s1", "action": "Create models", "description": "Write models", "tool": "write_file"}
        outcome = agent.execute_step(step, self._tmpdir, [])
        self.assertTrue(outcome.success)
        self.assertTrue(os.path.exists(os.path.join(self._tmpdir, "src", "models.py")))

    def test_execute_step_run_command(self):
        agent = ExecutorAgent(llm=CallableBackend(lambda s, u: RUN_COMMAND_RESPONSE))
        step = {"id": "s2", "action": "Run test", "description": "Run", "tool": "run_command"}
        outcome = agent.execute_step(step, self._tmpdir, [])
        self.assertTrue(outcome.success)
        self.assertIn("hello", outcome.output)

    def test_execute_full_plan(self):
        agent = ExecutorAgent(llm=make_executor_llm())
        plan = {
            "task_id": "t2",
            "task_title": "Database setup",
            "steps": [
                {"id": "s1", "action": "Write models", "description": "Models", "tool": "write_file"},
                {"id": "s2", "action": "Run migration", "description": "Migrate", "tool": "run_command"},
            ],
        }
        result = agent.execute(plan, project_dir=self._tmpdir)
        self.assertIsInstance(result, ExecutionResult)
        self.assertTrue(result.success)
        self.assertEqual(result.steps_completed, 2)
        self.assertEqual(result.failure_count, 0)

    def test_execute_stops_on_max_failures(self):
        agent = ExecutorAgent(
            llm=make_failing_llm(),
            stop_condition=StopCondition(max_failures=2),
        )
        plan = {
            "task_id": "t1",
            "task_title": "Failing task",
            "steps": [
                {"id": "s1", "action": "Fail 1", "description": "Fail", "tool": "run_command"},
                {"id": "s2", "action": "Fail 2", "description": "Fail", "tool": "run_command"},
                {"id": "s3", "action": "Never reached", "description": "Nope", "tool": "run_command"},
            ],
        }
        result = agent.execute(plan, project_dir=self._tmpdir)
        self.assertFalse(result.success)
        self.assertEqual(result.failure_count, 2)
        self.assertIn("Max failures", result.stop_reason)

    def test_execute_stops_on_max_steps(self):
        agent = ExecutorAgent(
            llm=CallableBackend(lambda s, u: RUN_COMMAND_RESPONSE),
            stop_condition=StopCondition(max_steps=1),
        )
        plan = {
            "task_id": "t1",
            "task_title": "Many steps",
            "steps": [
                {"id": "s1", "action": "Step 1", "description": "1", "tool": "run_command"},
                {"id": "s2", "action": "Step 2", "description": "2", "tool": "run_command"},
            ],
        }
        result = agent.execute(plan, project_dir=self._tmpdir)
        self.assertFalse(result.success)
        self.assertIn("Max steps", result.stop_reason)


if __name__ == "__main__":
    unittest.main()
