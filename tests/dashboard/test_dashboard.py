"""Tests for the Dashboard module (runner + server helpers)."""

import json
import os
import sys
import tempfile
import shutil
import threading
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from BrainDock.dashboard.runner import PipelineRunner
from BrainDock.dashboard.server import DashboardHandler


# ── Tests: DashboardHandler._extract_api_path ──────────────────────────

class TestExtractApiPath(unittest.TestCase):
    """Test the static _extract_api_path method."""

    def test_simple_api_path(self):
        self.assertEqual(DashboardHandler._extract_api_path("/api/state"), "/api/state")

    def test_api_with_proxy_prefix(self):
        self.assertEqual(
            DashboardHandler._extract_api_path("/proxy/3000/api/state"),
            "/api/state",
        )

    def test_api_runs(self):
        self.assertEqual(DashboardHandler._extract_api_path("/api/runs"), "/api/runs")

    def test_api_activities_with_query(self):
        # Query strings are parsed separately, so path won't include them
        self.assertEqual(
            DashboardHandler._extract_api_path("/api/activities"),
            "/api/activities",
        )

    def test_non_api_path(self):
        self.assertIsNone(DashboardHandler._extract_api_path("/"))
        self.assertIsNone(DashboardHandler._extract_api_path("/index.html"))

    def test_bare_api(self):
        result = DashboardHandler._extract_api_path("/api")
        self.assertEqual(result, "/api")

    def test_deep_proxy_prefix(self):
        self.assertEqual(
            DashboardHandler._extract_api_path("/some/deep/proxy/api/logs"),
            "/api/logs",
        )

    def test_trailing_slash_stripped(self):
        result = DashboardHandler._extract_api_path("/api/state/")
        self.assertEqual(result, "/api/state")


# ── Tests: PipelineRunner state management ────────────────────────────

class TestPipelineRunnerState(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.runner = PipelineRunner(output_dir=self._tmpdir)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_initial_state(self):
        state = self.runner.get_state()
        self.assertFalse(state["_running"])
        self.assertEqual(state["_error"], "")
        self.assertIsNone(state["_pending_questions"])

    def test_get_activities_empty(self):
        data = self.runner.get_activities()
        self.assertEqual(data["entries"], [])
        self.assertEqual(data["cursor"], 0)

    def test_get_chat_empty(self):
        data = self.runner.get_chat()
        self.assertEqual(data["entries"], [])
        self.assertEqual(data["cursor"], 0)

    def test_get_logs_empty(self):
        data = self.runner.get_logs()
        self.assertEqual(data["entries"], [])
        self.assertEqual(data["cursor"], 0)

    def test_submit_answers_no_pending(self):
        result = self.runner.submit_answers({"q1": "answer"})
        self.assertFalse(result)


class TestPipelineRunnerChat(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.runner = PipelineRunner(output_dir=self._tmpdir)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_send_chat(self):
        self.runner.send_chat("Hello!")
        data = self.runner.get_chat()
        self.assertEqual(len(data["entries"]), 1)
        self.assertEqual(data["entries"][0]["role"], "user")
        self.assertEqual(data["entries"][0]["text"], "Hello!")
        self.assertIn("ts", data["entries"][0])

    def test_send_multiple_chats(self):
        self.runner.send_chat("msg1")
        self.runner.send_chat("msg2")
        data = self.runner.get_chat()
        self.assertEqual(len(data["entries"]), 2)
        self.assertEqual(data["cursor"], 2)

    def test_chat_cursor_pagination(self):
        self.runner.send_chat("msg1")
        self.runner.send_chat("msg2")
        self.runner.send_chat("msg3")

        data = self.runner.get_chat(since=1)
        self.assertEqual(len(data["entries"]), 2)
        self.assertEqual(data["entries"][0]["text"], "msg2")
        self.assertEqual(data["cursor"], 3)


class TestPipelineRunnerActivities(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.runner = PipelineRunner(output_dir=self._tmpdir)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_on_activity(self):
        self.runner._on_activity("executor", "completed", "Task done", "success")
        data = self.runner.get_activities()
        self.assertEqual(len(data["entries"]), 1)
        entry = data["entries"][0]
        self.assertEqual(entry["agent"], "executor")
        self.assertEqual(entry["action"], "completed")
        self.assertEqual(entry["detail"], "Task done")
        self.assertEqual(entry["status"], "success")

    def test_activity_cursor_pagination(self):
        self.runner._on_activity("a", "x", "")
        self.runner._on_activity("b", "y", "")
        self.runner._on_activity("c", "z", "")

        data = self.runner.get_activities(since=2)
        self.assertEqual(len(data["entries"]), 1)
        self.assertEqual(data["entries"][0]["agent"], "c")

    def test_error_activity_adds_chat(self):
        self.runner._on_activity("executor", "error", "Something failed", "error")
        chat = self.runner.get_chat()
        # Error activities should surface as chat messages
        self.assertTrue(any("Something failed" in e["text"] for e in chat["entries"]))


class TestPipelineRunnerLogs(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.runner = PipelineRunner(output_dir=self._tmpdir)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_on_llm_log(self):
        entry = {
            "ts": time.time(),
            "agent": "planner",
            "duration": 1.5,
            "system_prompt": "sys",
            "user_prompt": "user",
            "response": "resp",
            "est_input_tokens": 100,
            "est_output_tokens": 50,
        }
        self.runner._on_llm_log(entry)
        data = self.runner.get_logs()
        self.assertEqual(len(data["entries"]), 1)
        self.assertEqual(data["entries"][0]["agent"], "planner")

    def test_log_cursor_pagination(self):
        for i in range(3):
            self.runner._on_llm_log({"ts": time.time(), "agent": f"a{i}", "duration": 0,
                                      "est_input_tokens": 0, "est_output_tokens": 0})
        data = self.runner.get_logs(since=1)
        self.assertEqual(len(data["entries"]), 2)


class TestPipelineRunnerPersistence(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.runner = PipelineRunner(output_dir=self._tmpdir)
        # Set up a run directory for persistence
        self.runner._run_dir = os.path.join(self._tmpdir, "test-run")
        os.makedirs(self.runner._run_dir, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_persist_and_load_chat(self):
        self.runner.send_chat("hello")
        self.runner.send_chat("world")

        # Create a new runner and load history
        runner2 = PipelineRunner(output_dir=self._tmpdir)
        runner2._load_history(self.runner._run_dir)
        data = runner2.get_chat()
        self.assertEqual(len(data["entries"]), 2)
        self.assertEqual(data["entries"][0]["text"], "hello")

    def test_persist_and_load_activities(self):
        self.runner._on_activity("spec", "started", "Begin")

        runner2 = PipelineRunner(output_dir=self._tmpdir)
        runner2._load_history(self.runner._run_dir)
        data = runner2.get_activities()
        self.assertEqual(len(data["entries"]), 1)

    def test_persist_and_load_llm_logs(self):
        self.runner._on_llm_log({"ts": 0, "agent": "test", "duration": 0,
                                  "est_input_tokens": 0, "est_output_tokens": 0})

        runner2 = PipelineRunner(output_dir=self._tmpdir)
        runner2._load_history(self.runner._run_dir)
        data = runner2.get_logs()
        self.assertEqual(len(data["entries"]), 1)

    def test_load_history_missing_dir(self):
        runner2 = PipelineRunner(output_dir=self._tmpdir)
        # Should not raise
        runner2._load_history(os.path.join(self._tmpdir, "nonexistent"))
        self.assertEqual(runner2.get_chat()["entries"], [])


class TestPipelineRunnerWebAskFn(unittest.TestCase):
    """Test the _web_ask_fn question/answer mechanism."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.runner = PipelineRunner(output_dir=self._tmpdir)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_zero_questions_auto_proceeds(self):
        from BrainDock.spec_agent.models import Question, Decision

        decisions = [Decision(id="d1", topic="Lang", decision="Python")]
        result = self.runner._web_ask_fn([], decisions, "Understanding text")
        self.assertEqual(result, {})
        # No pending questions should be set
        state = self.runner.get_state()
        self.assertIsNone(state["_pending_questions"])

    def test_questions_block_and_unblock(self):
        from BrainDock.spec_agent.models import Question, Decision

        questions = [Question(id="q1", question="What?", why="Need to know")]
        result_holder = {}

        def ask_in_thread():
            result_holder["answers"] = self.runner._web_ask_fn(
                questions, [], "context"
            )

        t = threading.Thread(target=ask_in_thread)
        t.start()

        # Wait a moment for the thread to set pending questions
        time.sleep(0.1)

        # Verify questions are pending
        state = self.runner.get_state()
        self.assertIsNotNone(state["_pending_questions"])
        self.assertEqual(len(state["_pending_questions"]), 1)

        # Submit answers
        ok = self.runner.submit_answers({"q1": "My answer"})
        self.assertTrue(ok)

        t.join(timeout=2)
        self.assertEqual(result_holder["answers"], {"q1": "My answer"})

        # Questions should be cleared
        state = self.runner.get_state()
        self.assertIsNone(state["_pending_questions"])


class TestPipelineRunnerStartGuard(unittest.TestCase):
    """Test that double-start is prevented."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.runner = PipelineRunner(output_dir=self._tmpdir)

    def tearDown(self):
        # Force runner to stop so daemon thread doesn't linger
        with self.runner._lock:
            self.runner._running = False
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_cannot_start_while_running(self):
        with self.runner._lock:
            self.runner._running = True
        result = self.runner.start("test", "problem")
        self.assertFalse(result)


class TestPipelineRunnerListRuns(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self.runner = PipelineRunner(output_dir=self._tmpdir)

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_list_runs_empty(self):
        runs = self.runner.list_runs()
        self.assertEqual(runs, [])

    def test_list_runs_with_state_file(self):
        run_dir = os.path.join(self._tmpdir, "my-project")
        os.makedirs(run_dir)
        with open(os.path.join(run_dir, "pipeline_state.json"), "w") as f:
            json.dump({
                "title": "My Project",
                "problem": "Build something",
                "current_mode": "execution",
                "completed_tasks": ["t1"],
                "failed_tasks": [],
                "task_graph": {"tasks": [{"id": "t1"}, {"id": "t2"}]},
            }, f)
        runs = self.runner.list_runs()
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["title"], "My Project")
        self.assertEqual(runs[0]["completed"], 1)
        self.assertEqual(runs[0]["total"], 2)


if __name__ == "__main__":
    unittest.main()
