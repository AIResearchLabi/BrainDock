"""Tests for the Executor module."""

import json
import os
import sys
import tempfile
import shutil
import unittest
from pathlib import Path

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


# ── Batch / Session Tests ─────────────────────────────────────────────

from BrainDock.executor.agent import _ExecutionSession
from BrainDock.llm import extract_json_or_list
from BrainDock.base_agent import BaseAgent


class TestExecutionSession(unittest.TestCase):
    def test_empty_session(self):
        s = _ExecutionSession()
        self.assertTrue(s.is_empty)
        self.assertEqual(s.get_transcript(), "")

    def test_add_outcome(self):
        s = _ExecutionSession()
        s.add_outcome("s1", "write_file", True, "wrote file")
        self.assertFalse(s.is_empty)
        self.assertIn("s1", s.get_transcript())
        self.assertIn("OK", s.get_transcript())

    def test_add_failure_outcome(self):
        s = _ExecutionSession()
        s.add_outcome("s1", "run_command", False, "exit code 1")
        self.assertIn("FAIL", s.get_transcript())

    def test_needs_compression(self):
        s = _ExecutionSession(session_token_limit=50)
        s.add_outcome("s1", "write_file", True, "x" * 100)
        self.assertTrue(s.needs_compression())

    def test_no_compression_needed(self):
        s = _ExecutionSession(session_token_limit=8000)
        s.add_outcome("s1", "write_file", True, "ok")
        self.assertFalse(s.needs_compression())

    def test_compress_keeps_recent(self):
        s = _ExecutionSession(session_token_limit=10)
        for i in range(6):
            s.add_outcome(f"s{i}", "write_file", True, f"step {i}")
        s.compress()
        transcript = s.get_transcript()
        # Last 3 entries preserved verbatim
        self.assertIn("s3", transcript)
        self.assertIn("s4", transcript)
        self.assertIn("s5", transcript)
        # Older entries in summary
        self.assertIn("Completed 3 earlier steps", transcript)

    def test_compress_summarizes_old(self):
        s = _ExecutionSession(session_token_limit=10)
        for i in range(5):
            s.add_outcome(f"step{i}", "write_file", True, f"output {i}")
        s.compress()
        transcript = s.get_transcript()
        self.assertIn("step0", transcript)  # in summary
        self.assertIn("step1", transcript)  # in summary
        self.assertIn("step4", transcript)  # verbatim (last 3)

    def test_multiple_compressions(self):
        s = _ExecutionSession(session_token_limit=10)
        for i in range(5):
            s.add_outcome(f"s{i}", "write_file", True, "x" * 20)
        s.compress()
        # Add more entries and compress again
        for i in range(5, 10):
            s.add_outcome(f"s{i}", "write_file", True, "y" * 20)
        s.compress()
        transcript = s.get_transcript()
        # Should still have last 3 entries
        self.assertIn("s7", transcript)
        self.assertIn("s8", transcript)
        self.assertIn("s9", transcript)


class TestMakeBatches(unittest.TestCase):
    def setUp(self):
        self._agent = ExecutorAgent(
            llm=CallableBackend(lambda s, u: "{}"),
            stop_condition=StopCondition(batch_size=3),
        )

    def test_simple_batching(self):
        steps = [
            {"id": f"s{i}", "tool": "write_file"} for i in range(6)
        ]
        batches = self._agent._make_batches(steps, 3)
        self.assertEqual(len(batches), 2)
        self.assertEqual(len(batches[0]), 3)
        self.assertEqual(len(batches[1]), 3)

    def test_run_command_terminates_batch(self):
        steps = [
            {"id": "s1", "tool": "write_file"},
            {"id": "s2", "tool": "run_command"},
            {"id": "s3", "tool": "write_file"},
        ]
        batches = self._agent._make_batches(steps, 4)
        self.assertEqual(len(batches), 2)
        self.assertEqual(len(batches[0]), 2)  # s1, s2 (run_command terminates)
        self.assertEqual(len(batches[1]), 1)  # s3

    def test_test_terminates_batch(self):
        steps = [
            {"id": "s1", "tool": "write_file"},
            {"id": "s2", "tool": "test"},
            {"id": "s3", "tool": "write_file"},
        ]
        batches = self._agent._make_batches(steps, 4)
        self.assertEqual(len(batches), 2)
        self.assertEqual(len(batches[0]), 2)
        self.assertEqual(len(batches[1]), 1)

    def test_single_step_batch(self):
        steps = [{"id": "s1", "tool": "write_file"}]
        batches = self._agent._make_batches(steps, 4)
        self.assertEqual(len(batches), 1)
        self.assertEqual(len(batches[0]), 1)

    def test_empty_steps(self):
        batches = self._agent._make_batches([], 4)
        self.assertEqual(batches, [])


class TestBatchExecution(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_execute_batch_first_call(self):
        """First batch uses full project context (EXECUTE_BATCH_PROMPT)."""
        batch_response = json.dumps([
            {"step_id": "s1", "action_type": "write_file",
             "file_path": "a.py", "content": "# file a", "verification": ""},
            {"step_id": "s2", "action_type": "write_file",
             "file_path": "b.py", "content": "# file b", "verification": ""},
        ])
        prompts_seen = []

        def mock_fn(system_prompt, user_prompt):
            prompts_seen.append(user_prompt)
            return batch_response

        agent = ExecutorAgent(llm=CallableBackend(mock_fn))
        session = _ExecutionSession()
        steps = [
            {"id": "s1", "tool": "write_file"},
            {"id": "s2", "tool": "write_file"},
        ]
        outcomes = agent._execute_batch(steps, self._tmpdir, session, "project files here")
        self.assertEqual(len(outcomes), 2)
        self.assertTrue(outcomes[0].success)
        self.assertTrue(outcomes[1].success)
        # First call should use full project context
        self.assertIn("project files here", prompts_seen[0])

    def test_execute_batch_continuation(self):
        """Subsequent batches use transcript (EXECUTE_CONTINUATION_PROMPT)."""
        batch_response = json.dumps([
            {"step_id": "s3", "action_type": "write_file",
             "file_path": "c.py", "content": "# file c", "verification": ""},
        ])
        prompts_seen = []

        def mock_fn(system_prompt, user_prompt):
            prompts_seen.append(user_prompt)
            return batch_response

        agent = ExecutorAgent(llm=CallableBackend(mock_fn))
        session = _ExecutionSession()
        # Simulate prior batch by adding an outcome
        session.add_outcome("s1", "write_file", True, "wrote a.py")
        steps = [{"id": "s3", "tool": "write_file"}]
        outcomes = agent._execute_batch(steps, self._tmpdir, session, "project files here")
        self.assertEqual(len(outcomes), 1)
        self.assertTrue(outcomes[0].success)
        # Continuation should include transcript, not full project context
        self.assertIn("Session transcript", prompts_seen[0])
        self.assertNotIn("Current project files", prompts_seen[0])

    def test_execute_with_batching(self):
        """Full execute() with batch_size=2."""
        call_count = {"n": 0}

        def mock_fn(system_prompt, user_prompt):
            call_count["n"] += 1
            return json.dumps([
                {"step_id": "sx", "action_type": "write_file",
                 "file_path": f"f{call_count['n']}.py", "content": "# ok",
                 "verification": ""},
                {"step_id": "sy", "action_type": "write_file",
                 "file_path": f"g{call_count['n']}.py", "content": "# ok",
                 "verification": ""},
            ])

        agent = ExecutorAgent(
            llm=CallableBackend(mock_fn),
            stop_condition=StopCondition(batch_size=2),
        )
        plan = {
            "task_id": "t1",
            "steps": [
                {"id": "s1", "tool": "write_file"},
                {"id": "s2", "tool": "write_file"},
                {"id": "s3", "tool": "write_file"},
                {"id": "s4", "tool": "write_file"},
            ],
        }
        result = agent.execute(plan, project_dir=self._tmpdir)
        self.assertTrue(result.success)
        self.assertEqual(result.steps_completed, 4)
        # Should have made 2 LLM calls (2 batches of 2)
        self.assertEqual(call_count["n"], 2)

    def test_execute_batch_handles_fewer_actions(self):
        """Graceful handling when LLM returns fewer actions than steps."""
        # Only return 1 action for 2 steps
        batch_response = json.dumps([
            {"step_id": "s1", "action_type": "write_file",
             "file_path": "a.py", "content": "# a", "verification": ""},
        ])
        agent = ExecutorAgent(llm=CallableBackend(lambda s, u: batch_response))
        session = _ExecutionSession()
        steps = [
            {"id": "s1", "tool": "write_file"},
            {"id": "s2", "tool": "write_file"},
        ]
        outcomes = agent._execute_batch(steps, self._tmpdir, session, "ctx")
        self.assertEqual(len(outcomes), 2)
        self.assertTrue(outcomes[0].success)
        # Second step gets skip fallback — still succeeds
        self.assertTrue(outcomes[1].success)


class TestExtractJsonList(unittest.TestCase):
    def test_extract_json_array(self):
        text = '[{"a": 1}, {"b": 2}]'
        result = extract_json_or_list(text)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)

    def test_extract_json_array_in_markdown(self):
        text = '```json\n[{"a": 1}]\n```'
        result = extract_json_or_list(text)
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)

    def test_extract_json_dict_still_works(self):
        text = '{"key": "value"}'
        result = extract_json_or_list(text)
        self.assertIsInstance(result, dict)
        self.assertEqual(result["key"], "value")

    def test_extract_json_array_in_prose(self):
        text = 'Here is the result:\n[{"x": 1}]\nDone.'
        result = extract_json_or_list(text)
        self.assertIsInstance(result, list)

    def test_extract_json_or_list_empty(self):
        with self.assertRaises(ValueError):
            extract_json_or_list("")


class TestLlmQueryJsonList(unittest.TestCase):
    def test_returns_list(self):
        backend = CallableBackend(lambda s, u: '[{"a": 1}, {"b": 2}]')
        agent = BaseAgent(llm=backend)
        result = agent._llm_query_json_list("sys", "user")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)

    def test_wraps_dict_in_list(self):
        backend = CallableBackend(lambda s, u: '{"a": 1}')
        agent = BaseAgent(llm=backend)
        result = agent._llm_query_json_list("sys", "user")
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["a"], 1)


class TestStopConditionBatchFields(unittest.TestCase):
    def test_defaults(self):
        s = StopCondition()
        self.assertEqual(s.batch_size, 4)
        self.assertEqual(s.session_token_limit, 8000)

    def test_roundtrip(self):
        s = StopCondition(batch_size=2, session_token_limit=4000)
        d = s.to_dict()
        restored = StopCondition.from_dict(d)
        self.assertEqual(restored.batch_size, 2)
        self.assertEqual(restored.session_token_limit, 4000)

    def test_from_dict_defaults(self):
        """from_dict with missing batch fields uses defaults."""
        s = StopCondition.from_dict({"max_steps": 10})
        self.assertEqual(s.max_steps, 10)
        self.assertEqual(s.batch_size, 4)
        self.assertEqual(s.session_token_limit, 8000)


# ── Guidance Integration Tests ─────────────────────────────────────────

class TestGuidanceIntegration(unittest.TestCase):
    """Test that check_guidance callback injects guidance into executor prompts."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_execute_with_guidance_callback(self):
        """Guidance from callback is injected into the LLM prompt."""
        prompts_seen = []
        batch_response = json.dumps([
            {"step_id": "s1", "action_type": "write_file",
             "file_path": "a.py", "content": "# guided", "verification": ""},
        ])

        def mock_fn(system_prompt, user_prompt):
            prompts_seen.append(user_prompt)
            return batch_response

        guidance_calls = {"n": 0}

        def mock_guidance():
            guidance_calls["n"] += 1
            if guidance_calls["n"] == 1:
                return ["Use TypeScript instead of JavaScript"]
            return []

        agent = ExecutorAgent(llm=CallableBackend(mock_fn))
        plan = {
            "task_id": "t1",
            "steps": [{"id": "s1", "tool": "write_file"}],
        }
        result = agent.execute(plan, project_dir=self._tmpdir, check_guidance=mock_guidance)
        self.assertTrue(result.success)
        # Guidance should appear in the prompt
        self.assertTrue(any("TypeScript" in p for p in prompts_seen))

    def test_execute_no_guidance_callback(self):
        """execute() works fine with check_guidance=None (backward compat)."""
        batch_response = json.dumps([
            {"step_id": "s1", "action_type": "write_file",
             "file_path": "a.py", "content": "# ok", "verification": ""},
        ])
        agent = ExecutorAgent(llm=CallableBackend(lambda s, u: batch_response))
        plan = {
            "task_id": "t1",
            "steps": [{"id": "s1", "tool": "write_file"}],
        }
        result = agent.execute(plan, project_dir=self._tmpdir, check_guidance=None)
        self.assertTrue(result.success)

    def test_guidance_appears_in_continuation(self):
        """Guidance text appears in continuation prompt (non-empty session)."""
        prompts_seen = []
        call_count = {"n": 0}

        def mock_fn(system_prompt, user_prompt):
            call_count["n"] += 1
            prompts_seen.append(user_prompt)
            return json.dumps([
                {"step_id": "sx", "action_type": "write_file",
                 "file_path": f"f{call_count['n']}.py", "content": "# ok",
                 "verification": ""},
            ])

        guidance_calls = {"n": 0}

        def mock_guidance():
            guidance_calls["n"] += 1
            if guidance_calls["n"] == 2:
                return ["Add error handling"]
            return []

        agent = ExecutorAgent(
            llm=CallableBackend(mock_fn),
            stop_condition=StopCondition(batch_size=1),
        )
        plan = {
            "task_id": "t1",
            "steps": [
                {"id": "s1", "tool": "write_file"},
                {"id": "s2", "tool": "write_file"},
            ],
        }
        agent.execute(plan, project_dir=self._tmpdir, check_guidance=mock_guidance)
        # Second prompt (continuation) should contain guidance
        self.assertTrue(len(prompts_seen) >= 2)
        self.assertIn("Add error handling", prompts_seen[1])

    def test_guidance_recorded_in_session(self):
        """Guidance is recorded in the session transcript for subsequent batches."""
        prompts_seen = []
        call_count = {"n": 0}

        def mock_fn(system_prompt, user_prompt):
            call_count["n"] += 1
            prompts_seen.append(user_prompt)
            return json.dumps([
                {"step_id": "sx", "action_type": "write_file",
                 "file_path": f"f{call_count['n']}.py", "content": "# ok",
                 "verification": ""},
            ])

        guidance_calls = {"n": 0}

        def mock_guidance():
            guidance_calls["n"] += 1
            if guidance_calls["n"] == 1:
                return ["Use dataclasses"]
            return []

        agent = ExecutorAgent(
            llm=CallableBackend(mock_fn),
            stop_condition=StopCondition(batch_size=1),
        )
        plan = {
            "task_id": "t1",
            "steps": [
                {"id": "s1", "tool": "write_file"},
                {"id": "s2", "tool": "write_file"},
                {"id": "s3", "tool": "write_file"},
            ],
        }
        agent.execute(plan, project_dir=self._tmpdir, check_guidance=mock_guidance)
        # Third prompt should contain the transcript which includes guidance
        self.assertTrue(len(prompts_seen) >= 3)
        # The continuation prompt includes session transcript with guidance entry
        self.assertIn("user_message", prompts_seen[2])


# ── Pre-write Validation Tests ────────────────────────────────────────

from BrainDock.executor.sandbox import (
    _looks_like_description,
    _looks_like_shell_command,
    _validate_source_content,
    scan_for_corrupted_files,
)


class TestLooksLikeDescription(unittest.TestCase):
    def test_normal_code_is_not_description(self):
        self.assertFalse(_looks_like_description("class User:\n    pass\n"))

    def test_empty_is_not_description(self):
        self.assertFalse(_looks_like_description(""))

    def test_wrote_prefix_is_description(self):
        self.assertTrue(_looks_like_description(
            "Wrote complete Python module with ConfigError exception and load_config function."
        ))

    def test_updated_prefix_is_description(self):
        self.assertTrue(_looks_like_description(
            "Updated load_config() to accept optional config_path parameter."
        ))

    def test_already_exists_is_description(self):
        self.assertTrue(_looks_like_description(
            "Already exists with 11 test methods across 6 test classes."
        ))

    def test_wrapped_prefix_is_description(self):
        self.assertTrue(_looks_like_description(
            "Wrapped from playwright.sync_api import sync_playwright in try/except."
        ))

    def test_single_line_prose_is_description(self):
        self.assertTrue(_looks_like_description(
            "This module handles configuration loading and validation for the application"
        ))

    def test_short_content_is_not_description(self):
        self.assertFalse(_looks_like_description("pass"))

    def test_comment_only_file_is_not_description(self):
        self.assertFalse(_looks_like_description("# This is a comment\n"))

    def test_init_py_empty_not_description(self):
        self.assertFalse(_looks_like_description(""))


class TestLooksLikeShellCommand(unittest.TestCase):
    def test_cd_and_python(self):
        self.assertTrue(_looks_like_shell_command(
            "cd /some/path && python -m mypackage"
        ))

    def test_python_m(self):
        self.assertTrue(_looks_like_shell_command("python -m unittest discover -s tests -v"))

    def test_npm_install(self):
        self.assertTrue(_looks_like_shell_command("npm install && npm run build"))

    def test_pip_install(self):
        self.assertTrue(_looks_like_shell_command("pip install -r requirements.txt"))

    def test_make(self):
        self.assertTrue(_looks_like_shell_command("make test"))

    def test_description_not_shell(self):
        self.assertFalse(_looks_like_shell_command(
            "Wrote a shell script that checks the database connection."
        ))

    def test_created_prefix_not_shell(self):
        self.assertFalse(_looks_like_shell_command(
            "Created the main.py file with the calculator implementation"
        ))

    def test_empty(self):
        self.assertFalse(_looks_like_shell_command(""))

    def test_shell_command_not_blocked_by_combined_guard(self):
        """Shell commands should not be blocked even if they look like descriptions."""
        cmd = "cd /home/user/project && python -m mypackage.module"
        # The old guard would block this; combined guard should not
        self.assertTrue(
            _looks_like_shell_command(cmd) or not _looks_like_description(cmd)
        )


class TestValidateSourceContent(unittest.TestCase):
    def test_valid_python(self):
        ok, err = _validate_source_content("app.py", "print('hello')\n")
        self.assertTrue(ok)
        self.assertEqual(err, "")

    def test_description_rejected(self):
        ok, err = _validate_source_content(
            "config.py",
            "Wrote a complete Python module with dataclass definitions."
        )
        self.assertFalse(ok)
        self.assertIn("description", err.lower())

    def test_syntax_error_detected(self):
        ok, err = _validate_source_content("bad.py", "def foo(:\n    pass\n")
        self.assertFalse(ok)
        self.assertIn("syntax", err.lower())

    def test_non_code_files_pass(self):
        ok, _ = _validate_source_content("readme.md", "Wrote a description")
        self.assertTrue(ok)

    def test_valid_empty_init(self):
        ok, _ = _validate_source_content("__init__.py", "")
        self.assertTrue(ok)

    def test_json_file_not_validated(self):
        ok, _ = _validate_source_content("data.json", '{"key": "value"}')
        self.assertTrue(ok)


class TestWriteFileSafeValidation(unittest.TestCase):
    def test_rejects_description_content(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            success, msg = write_file_safe(
                "config.py",
                "Wrote complete Python module with ConfigError exception.",
                tmpdir,
            )
            self.assertFalse(success)
            self.assertIn("description", msg.lower())
            # File should NOT be created
            self.assertFalse(os.path.exists(os.path.join(tmpdir, "config.py")))

    def test_accepts_valid_code(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            success, msg = write_file_safe(
                "app.py",
                "import sys\n\ndef main():\n    print('hello')\n",
                tmpdir,
            )
            self.assertTrue(success)

    def test_rejects_python_syntax_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            success, msg = write_file_safe(
                "bad.py",
                "def foo(:\n    pass\n",
                tmpdir,
            )
            self.assertFalse(success)
            self.assertIn("syntax", msg.lower())


class TestScanForCorruptedFiles(unittest.TestCase):
    def test_finds_corrupted_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a corrupted file
            bad = Path(tmpdir) / "config.py"
            bad.write_text("Wrote complete Python module with dataclasses.")
            # Create a good file
            good = Path(tmpdir) / "app.py"
            good.write_text("import sys\nprint('hello')\n")

            corrupted = scan_for_corrupted_files(tmpdir)
            self.assertEqual(len(corrupted), 1)
            self.assertEqual(corrupted[0]["path"], "config.py")

    def test_empty_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            corrupted = scan_for_corrupted_files(tmpdir)
            self.assertEqual(corrupted, [])

    def test_skips_empty_init_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            init = Path(tmpdir) / "__init__.py"
            init.write_text("")
            corrupted = scan_for_corrupted_files(tmpdir)
            self.assertEqual(corrupted, [])

    def test_skips_pycache(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir) / "__pycache__"
            cache_dir.mkdir()
            bad = cache_dir / "module.cpython-311.pyc"
            bad.write_text("Updated the module to use new API.")
            # .pyc not in code_extensions so it's skipped
            corrupted = scan_for_corrupted_files(tmpdir)
            self.assertEqual(corrupted, [])


# ── Step-Level Validation Retry Tests ─────────────────────────────────

class TestValidationRetry(unittest.TestCase):
    """Test that validation failures trigger a step-level LLM retry."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_retry_on_description_content(self):
        """When LLM returns a description, executor retries and uses the good response."""
        call_count = {"n": 0}

        def mock_fn(system_prompt, user_prompt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                # First call: returns description instead of code (in a batch)
                return json.dumps([{
                    "step_id": "s1",
                    "action_type": "write_file",
                    "file_path": "config.py",
                    "content": "Wrote complete Python module with ConfigError exception.",
                    "verification": "",
                }])
            else:
                # Retry call: returns actual code
                return json.dumps({
                    "step_id": "s1",
                    "action_type": "write_file",
                    "file_path": "config.py",
                    "content": "class ConfigError(Exception):\n    pass\n",
                    "verification": "",
                })

        agent = ExecutorAgent(llm=CallableBackend(mock_fn))
        plan = {
            "task_id": "t1",
            "steps": [{"id": "s1", "tool": "write_file"}],
        }
        result = agent.execute(plan, project_dir=self._tmpdir)
        self.assertTrue(result.success)
        # File should contain actual code
        content = (Path(self._tmpdir) / "config.py").read_text()
        self.assertIn("class ConfigError", content)
        # Should have made 2 LLM calls (initial batch + retry)
        self.assertEqual(call_count["n"], 2)

    def test_no_retry_on_normal_failure(self):
        """Normal failures (e.g. command exit code 1) should NOT trigger retry."""
        call_count = {"n": 0}

        def mock_fn(system_prompt, user_prompt):
            call_count["n"] += 1
            return json.dumps([{
                "step_id": "s1",
                "action_type": "run_command",
                "file_path": "",
                "content": "exit 1",
                "verification": "",
            }])

        agent = ExecutorAgent(llm=CallableBackend(mock_fn))
        plan = {
            "task_id": "t1",
            "steps": [{"id": "s1", "tool": "run_command"}],
        }
        result = agent.execute(plan, project_dir=self._tmpdir)
        self.assertFalse(result.success)
        # Should NOT retry — only 1 LLM call
        self.assertEqual(call_count["n"], 1)

    def test_retry_fails_both_times(self):
        """If retry also returns a description, step fails."""
        def mock_fn(system_prompt, user_prompt):
            return json.dumps([{
                "step_id": "s1",
                "action_type": "write_file",
                "file_path": "bad.py",
                "content": "Updated the module to handle errors gracefully.",
                "verification": "",
            }])

        agent = ExecutorAgent(llm=CallableBackend(mock_fn))
        plan = {
            "task_id": "t1",
            "steps": [{"id": "s1", "tool": "write_file"}],
        }
        result = agent.execute(plan, project_dir=self._tmpdir)
        self.assertFalse(result.success)
        # File should NOT exist
        self.assertFalse(os.path.exists(os.path.join(self._tmpdir, "bad.py")))

    def test_description_in_run_command_detected(self):
        """Description content in run_command action should be caught."""
        def mock_fn(system_prompt, user_prompt):
            return json.dumps([{
                "step_id": "s1",
                "action_type": "run_command",
                "file_path": "",
                "content": "Wrote a shell script that checks the database connection.",
                "verification": "",
            }])

        agent = ExecutorAgent(llm=CallableBackend(mock_fn))
        plan = {
            "task_id": "t1",
            "steps": [{"id": "s1", "tool": "run_command"}],
        }
        result = agent.execute(plan, project_dir=self._tmpdir)
        self.assertFalse(result.success)
        self.assertIn("description", result.outcomes[0].error.lower())

    def test_is_validation_error(self):
        """_is_validation_error detects validation-specific error messages."""
        self.assertTrue(ExecutorAgent._is_validation_error(
            "Content for config.py appears to be a natural-language description"
        ))
        self.assertTrue(ExecutorAgent._is_validation_error(
            "Python syntax error in config.py: invalid syntax (line 1)"
        ))
        self.assertFalse(ExecutorAgent._is_validation_error(
            "Command failed: exit code 1"
        ))
        self.assertFalse(ExecutorAgent._is_validation_error(""))


# ── Controller Reset Per Task Tests ──────────────────────────────────

from BrainDock.controller.agent import ControllerAgent
from BrainDock.controller.models import ControllerState, GateThresholds


class TestControllerResetForTask(unittest.TestCase):
    """Test that controller failure counters reset per task."""

    def test_reset_clears_counters(self):
        state = ControllerState(failure_count=5, reflection_count=3, debate_count=2)
        state.reset_for_task()
        self.assertEqual(state.failure_count, 0)
        self.assertEqual(state.reflection_count, 0)
        self.assertEqual(state.debate_count, 0)

    def test_reset_preserves_gate_history(self):
        state = ControllerState()
        from BrainDock.controller.models import GateResult
        state.record_gate(GateResult(gate_name="test", passed=False, action="reflect"))
        self.assertEqual(len(state.gate_history), 1)
        state.reset_for_task()
        # History preserved
        self.assertEqual(len(state.gate_history), 1)
        # But counter reset
        self.assertEqual(state.failure_count, 0)

    def test_controller_reset_for_task(self):
        controller = ControllerAgent(thresholds=GateThresholds(max_failures=2))
        # Simulate a failed task
        controller.check_execution_gate({"success": False})
        controller.check_execution_gate({"success": False})
        self.assertEqual(controller.state.failure_count, 2)
        # Reset for new task
        controller.reset_for_task()
        self.assertEqual(controller.state.failure_count, 0)
        # New task should be able to fail again without aborting
        result = controller.check_execution_gate({"success": False})
        self.assertEqual(result.action, "reflect")
        self.assertNotEqual(result.action, "abort")

    def test_no_cascade_across_tasks(self):
        """After reset, a new task gets a fresh failure budget."""
        controller = ControllerAgent(thresholds=GateThresholds(max_failures=2))
        # Task 1: 3 failures — first 2 return reflect, 3rd returns abort
        controller.check_execution_gate({"success": False})  # reflect, count→1
        controller.check_execution_gate({"success": False})  # reflect, count→2
        result = controller.check_execution_gate({"success": False})  # abort, count=2 >= 2
        self.assertEqual(result.action, "abort")

        # Task 2: reset and try again
        controller.reset_for_task()
        result = controller.check_execution_gate({"success": False})
        # Should be "reflect", not "abort" — counter was reset
        self.assertEqual(result.action, "reflect")


class TestExecutorJsonParseFailureGraceful(unittest.TestCase):
    """Test that executor handles LLM JSON parse failures gracefully."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_batch_already_done_response_handled_as_skip(self):
        """When LLM returns 'already done' prose, executor treats it as a skip
        (success) instead of a hard failure."""
        def already_done_llm(system_prompt, user_prompt):
            return "All steps are completed successfully. No JSON here."

        executor = ExecutorAgent(llm=CallableBackend(already_done_llm))
        plan = {
            "task_id": "t1",
            "steps": [
                {"id": "s1", "action": "Write file", "tool": "write_file"},
                {"id": "s2", "action": "Write file", "tool": "write_file"},
            ],
        }
        # Should NOT raise — auto-skip detects "completed" in response
        result = executor.execute(plan, project_dir=self._tmpdir)
        self.assertTrue(result.success)

    def test_batch_truly_bad_json_returns_failed_outcomes(self):
        """When LLM returns genuinely unparseable non-JSON with no 'already done'
        markers, returns failed outcomes."""
        def bad_llm(system_prompt, user_prompt):
            return "xyz random gibberish with no recognizable pattern 12345"

        executor = ExecutorAgent(llm=CallableBackend(bad_llm))
        plan = {
            "task_id": "t1",
            "steps": [
                {"id": "s1", "action": "Write file", "tool": "write_file"},
            ],
        }
        result = executor.execute(plan, project_dir=self._tmpdir)
        self.assertFalse(result.success)

    def test_single_step_already_done_handled_as_skip(self):
        """When LLM returns 'already done' prose for execute_step, treats as skip."""
        def already_done_llm(system_prompt, user_prompt):
            return "I completed the step. Everything is done."

        executor = ExecutorAgent(llm=CallableBackend(already_done_llm))
        step = {"id": "s1", "action": "Write file", "tool": "write_file"}
        # Should NOT raise — auto-skip detects "complete" in response
        outcome = executor.execute_step(step, self._tmpdir, [])
        self.assertTrue(outcome.success)


if __name__ == "__main__":
    unittest.main()
