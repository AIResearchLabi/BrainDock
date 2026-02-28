"""Tests for the LLM module."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from unittest.mock import patch, MagicMock

from BrainDock.llm import CallableBackend, ClaudeCLIBackend, LoggingBackend, extract_json


# ── Tests: extract_json ────────────────────────────────────────────────

class TestExtractJson(unittest.TestCase):
    def test_plain_json(self):
        result = extract_json('{"key": "value"}')
        self.assertEqual(result, {"key": "value"})

    def test_json_in_code_fence(self):
        text = '```json\n{"key": "value"}\n```'
        result = extract_json(text)
        self.assertEqual(result, {"key": "value"})

    def test_json_in_bare_fence(self):
        text = '```\n{"key": "value"}\n```'
        result = extract_json(text)
        self.assertEqual(result, {"key": "value"})

    def test_json_embedded_in_prose(self):
        text = 'Here is my answer:\n\n{"key": "value"}\n\nHope that helps!'
        result = extract_json(text)
        self.assertEqual(result, {"key": "value"})

    def test_nested_json(self):
        data = {"outer": {"inner": [1, 2, 3]}, "flag": True}
        result = extract_json(json.dumps(data))
        self.assertEqual(result, data)

    def test_empty_string_raises(self):
        with self.assertRaises(ValueError) as ctx:
            extract_json("")
        self.assertIn("empty", str(ctx.exception).lower())

    def test_whitespace_only_raises(self):
        with self.assertRaises(ValueError):
            extract_json("   \n  ")

    def test_no_json_raises(self):
        with self.assertRaises(ValueError):
            extract_json("This is just plain text with no JSON at all.")

    def test_malformed_json_raises(self):
        with self.assertRaises(ValueError):
            extract_json('{"key": "value"')  # missing closing brace

    def test_json_with_leading_whitespace(self):
        result = extract_json('  \n  {"key": "value"}  \n  ')
        self.assertEqual(result, {"key": "value"})

    def test_multiple_code_fences_picks_valid(self):
        text = '```\nnot json\n```\n\n```json\n{"valid": true}\n```'
        result = extract_json(text)
        self.assertEqual(result, {"valid": True})

    def test_json_with_array_values(self):
        text = '{"items": [1, 2, 3], "name": "test"}'
        result = extract_json(text)
        self.assertEqual(result["items"], [1, 2, 3])


# ── Tests: CallableBackend ────────────────────────────────────────────

class TestCallableBackend(unittest.TestCase):
    def test_basic_query(self):
        backend = CallableBackend(lambda s, u: f"echo: {u}")
        result = backend.query("sys", "hello")
        self.assertEqual(result, "echo: hello")

    def test_receives_both_prompts(self):
        captured = {}

        def fn(system_prompt, user_prompt):
            captured["system"] = system_prompt
            captured["user"] = user_prompt
            return "ok"

        backend = CallableBackend(fn)
        backend.query("sys_prompt", "user_prompt")
        self.assertEqual(captured["system"], "sys_prompt")
        self.assertEqual(captured["user"], "user_prompt")

    def test_exception_propagates(self):
        def failing_fn(s, u):
            raise ValueError("LLM error")

        backend = CallableBackend(failing_fn)
        with self.assertRaises(ValueError):
            backend.query("sys", "user")


# ── Tests: LoggingBackend ─────────────────────────────────────────────

class TestLoggingBackend(unittest.TestCase):
    def test_delegates_to_inner(self):
        inner = CallableBackend(lambda s, u: "inner_response")
        logging = LoggingBackend(inner)
        result = logging.query("sys", "user")
        self.assertEqual(result, "inner_response")

    def test_calls_on_log(self):
        logs = []
        inner = CallableBackend(lambda s, u: "response")
        logging = LoggingBackend(inner, on_log=logs.append)
        logging.set_agent_label("test_agent")
        logging.query("system prompt", "user prompt")

        self.assertEqual(len(logs), 1)
        entry = logs[0]
        self.assertEqual(entry["agent"], "test_agent")
        self.assertEqual(entry["system_prompt"], "system prompt")
        self.assertEqual(entry["user_prompt"], "user prompt")
        self.assertEqual(entry["response"], "response")
        self.assertIn("ts", entry)
        self.assertIn("duration", entry)
        self.assertIn("est_input_tokens", entry)
        self.assertIn("est_output_tokens", entry)

    def test_token_estimation(self):
        inner = CallableBackend(lambda s, u: "a" * 100)
        logs = []
        logging = LoggingBackend(inner, on_log=logs.append)
        logging.query("b" * 200, "c" * 200)

        entry = logs[0]
        # ~4 chars per token: (200+200)/4 = 100 input, 100/4 = 25 output
        self.assertEqual(entry["est_input_tokens"], 100)
        self.assertEqual(entry["est_output_tokens"], 25)

    def test_set_agent_label(self):
        inner = CallableBackend(lambda s, u: "ok")
        logs = []
        logging = LoggingBackend(inner, on_log=logs.append)

        logging.set_agent_label("agent_1")
        logging.query("s", "u")
        logging.set_agent_label("agent_2")
        logging.query("s", "u")

        self.assertEqual(logs[0]["agent"], "agent_1")
        self.assertEqual(logs[1]["agent"], "agent_2")

    def test_default_agent_label(self):
        inner = CallableBackend(lambda s, u: "ok")
        logs = []
        logging = LoggingBackend(inner, on_log=logs.append)
        logging.query("s", "u")
        self.assertEqual(logs[0]["agent"], "unknown")

    def test_no_on_log_callback(self):
        inner = CallableBackend(lambda s, u: "ok")
        logging = LoggingBackend(inner, on_log=None)
        # Should not raise
        result = logging.query("s", "u")
        self.assertEqual(result, "ok")

    def test_duration_is_positive(self):
        inner = CallableBackend(lambda s, u: "ok")
        logs = []
        logging = LoggingBackend(inner, on_log=logs.append)
        logging.query("s", "u")
        self.assertGreaterEqual(logs[0]["duration"], 0)

    def test_inner_exception_propagates(self):
        def failing(s, u):
            raise RuntimeError("boom")

        inner = CallableBackend(failing)
        logging = LoggingBackend(inner)
        with self.assertRaises(RuntimeError):
            logging.query("s", "u")


# ── Tests: ClaudeCLIBackend SDK mode ─────────────────────────────────

class TestClaudeCLIBackendSDK(unittest.TestCase):
    """Tests for ClaudeCLIBackend with --output-format json."""

    def _make_completed_process(self, stdout, returncode=0, stderr=""):
        proc = MagicMock()
        proc.stdout = stdout
        proc.stderr = stderr
        proc.returncode = returncode
        return proc

    @patch("BrainDock.llm.subprocess.run")
    def test_command_includes_output_format_json(self, mock_run):
        mock_run.return_value = self._make_completed_process(
            json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": "hello"})
        )
        backend = ClaudeCLIBackend()
        backend.query("system", "user")
        cmd = mock_run.call_args[0][0]
        self.assertIn("--output-format", cmd)
        self.assertIn("json", cmd)
        idx = cmd.index("--output-format")
        self.assertEqual(cmd[idx + 1], "json")

    @patch("BrainDock.llm.subprocess.run")
    def test_command_includes_system_prompt_flag(self, mock_run):
        mock_run.return_value = self._make_completed_process(
            json.dumps({"type": "result", "is_error": False, "result": "ok"})
        )
        backend = ClaudeCLIBackend()
        backend.query("my system prompt", "user msg")
        cmd = mock_run.call_args[0][0]
        self.assertIn("--system-prompt", cmd)
        idx = cmd.index("--system-prompt")
        self.assertEqual(cmd[idx + 1], "my system prompt")

    @patch("BrainDock.llm.subprocess.run")
    def test_no_system_prompt_flag_when_empty(self, mock_run):
        mock_run.return_value = self._make_completed_process(
            json.dumps({"type": "result", "is_error": False, "result": "ok"})
        )
        backend = ClaudeCLIBackend()
        backend.query("", "user msg")
        cmd = mock_run.call_args[0][0]
        self.assertNotIn("--system-prompt", cmd)

    @patch("BrainDock.llm.subprocess.run")
    def test_only_user_prompt_sent_as_stdin(self, mock_run):
        mock_run.return_value = self._make_completed_process(
            json.dumps({"type": "result", "is_error": False, "result": "ok"})
        )
        backend = ClaudeCLIBackend()
        backend.query("system prompt", "user prompt only")
        kwargs = mock_run.call_args[1]
        self.assertEqual(kwargs["input"], "user prompt only")

    @patch("BrainDock.llm.subprocess.run")
    def test_parses_result_field_from_json(self, mock_run):
        mock_run.return_value = self._make_completed_process(
            json.dumps({
                "type": "result",
                "subtype": "success",
                "cost_usd": 0.003,
                "is_error": False,
                "duration_ms": 1234,
                "result": "The assistant response",
                "session_id": "abc123",
            })
        )
        backend = ClaudeCLIBackend()
        result = backend.query("sys", "user")
        self.assertEqual(result, "The assistant response")

    @patch("BrainDock.llm.subprocess.run")
    def test_raises_on_is_error_true(self, mock_run):
        mock_run.return_value = self._make_completed_process(
            json.dumps({
                "type": "result",
                "subtype": "error_max_turns",
                "is_error": True,
                "result": "Max turns exceeded",
            })
        )
        backend = ClaudeCLIBackend()
        with self.assertRaises(RuntimeError) as ctx:
            backend.query("sys", "user")
        self.assertIn("Max turns exceeded", str(ctx.exception))

    @patch("BrainDock.llm.subprocess.run")
    def test_raises_on_nonzero_exit_code(self, mock_run):
        mock_run.return_value = self._make_completed_process(
            "", returncode=1, stderr="some error"
        )
        backend = ClaudeCLIBackend()
        with self.assertRaises(RuntimeError) as ctx:
            backend.query("sys", "user")
        self.assertIn("exit 1", str(ctx.exception))

    @patch("BrainDock.llm.subprocess.run")
    def test_fallback_on_non_json_output(self, mock_run):
        mock_run.return_value = self._make_completed_process("plain text response")
        backend = ClaudeCLIBackend()
        result = backend.query("sys", "user")
        self.assertEqual(result, "plain text response")

    @patch("BrainDock.llm.subprocess.run")
    def test_model_flag_included(self, mock_run):
        mock_run.return_value = self._make_completed_process(
            json.dumps({"type": "result", "is_error": False, "result": "ok"})
        )
        backend = ClaudeCLIBackend(model="claude-sonnet-4-6")
        backend.query("sys", "user")
        cmd = mock_run.call_args[0][0]
        self.assertIn("--model", cmd)
        idx = cmd.index("--model")
        self.assertEqual(cmd[idx + 1], "claude-sonnet-4-6")

    @patch("BrainDock.llm.subprocess.run")
    def test_missing_result_field_returns_empty(self, mock_run):
        mock_run.return_value = self._make_completed_process(
            json.dumps({"type": "result", "is_error": False})
        )
        backend = ClaudeCLIBackend()
        result = backend.query("sys", "user")
        self.assertEqual(result, "")


# ── Tests: SDK JSON round-trip with code generation ──────────────────

class TestSDKRoundTripWithCodeGeneration(unittest.TestCase):
    """Tests that the full pipeline works: SDK JSON → result extraction →
    extract_json → action dict with Python code content.

    This is the critical path for code generation: ClaudeCLIBackend returns
    the result string, then _llm_query_json / extract_json parses
    the embedded JSON action containing generated code.
    """

    def _sdk_wrap(self, llm_text, is_error=False):
        """Wrap LLM text in SDK JSON response envelope."""
        return json.dumps({
            "type": "result",
            "subtype": "error" if is_error else "success",
            "is_error": is_error,
            "cost_usd": 0.003,
            "duration_ms": 1500,
            "result": llm_text,
            "session_id": "test-session",
        })

    def _make_completed_process(self, stdout, returncode=0, stderr=""):
        proc = MagicMock()
        proc.stdout = stdout
        proc.stderr = stderr
        proc.returncode = returncode
        return proc

    @patch("BrainDock.llm.subprocess.run")
    def test_write_file_action_with_python_code(self, mock_run):
        """SDK JSON wrapping a write_file action with Python code."""
        from BrainDock.llm import extract_json

        action = {
            "action_type": "write_file",
            "path": "calculator.py",
            "content": (
                "def add(a: int, b: int) -> int:\n"
                "    return a + b\n\n"
                "def main():\n"
                "    print(add(2, 3))\n\n"
                "if __name__ == '__main__':\n"
                "    main()\n"
            ),
        }
        llm_text = json.dumps(action)
        mock_run.return_value = self._make_completed_process(self._sdk_wrap(llm_text))

        backend = ClaudeCLIBackend()
        result = backend.query("You are a coder", "Write calculator.py")

        # result is now the LLM text (the JSON action string)
        parsed = extract_json(result)
        self.assertEqual(parsed["action_type"], "write_file")
        self.assertEqual(parsed["path"], "calculator.py")
        self.assertIn("def add(a: int, b: int)", parsed["content"])
        self.assertIn("if __name__", parsed["content"])

    @patch("BrainDock.llm.subprocess.run")
    def test_action_with_code_in_markdown_fence(self, mock_run):
        """SDK JSON wrapping LLM response with JSON in markdown fences."""
        from BrainDock.llm import extract_json

        action = {
            "action_type": "write_file",
            "path": "app.py",
            "content": "import os\nprint(os.getcwd())\n",
        }
        llm_text = f"Here is the action:\n```json\n{json.dumps(action)}\n```"
        mock_run.return_value = self._make_completed_process(self._sdk_wrap(llm_text))

        backend = ClaudeCLIBackend()
        result = backend.query("sys", "user")
        parsed = extract_json(result)
        self.assertEqual(parsed["action_type"], "write_file")
        self.assertIn("import os", parsed["content"])

    @patch("BrainDock.llm.subprocess.run")
    def test_action_with_multiline_python_code(self, mock_run):
        """SDK JSON wrapping action with complex multiline Python code."""
        from BrainDock.llm import extract_json

        code = (
            "class Calculator:\n"
            "    def __init__(self):\n"
            "        self.history = []\n\n"
            "    def evaluate(self, expr: str) -> float:\n"
            '        """Evaluate a math expression."""\n'
            "        result = eval(expr)  # noqa: S307\n"
            "        self.history.append((expr, result))\n"
            "        return result\n"
        )
        action = {"action_type": "write_file", "path": "calc.py", "content": code}
        mock_run.return_value = self._make_completed_process(
            self._sdk_wrap(json.dumps(action))
        )

        backend = ClaudeCLIBackend()
        result = backend.query("sys", "user")
        parsed = extract_json(result)
        self.assertEqual(parsed["content"], code)

    @patch("BrainDock.llm.subprocess.run")
    def test_run_command_action_roundtrip(self, mock_run):
        """SDK JSON wrapping a run_command action."""
        from BrainDock.llm import extract_json

        action = {
            "action_type": "run_command",
            "command": "python -m pytest tests/ -v",
        }
        mock_run.return_value = self._make_completed_process(
            self._sdk_wrap(json.dumps(action))
        )

        backend = ClaudeCLIBackend()
        result = backend.query("sys", "user")
        parsed = extract_json(result)
        self.assertEqual(parsed["action_type"], "run_command")
        self.assertEqual(parsed["command"], "python -m pytest tests/ -v")

    @patch("BrainDock.llm.subprocess.run")
    def test_code_with_json_like_strings_inside(self, mock_run):
        """Python code containing JSON strings doesn't confuse extraction."""
        from BrainDock.llm import extract_json

        code = (
            "import json\n\n"
            "data = json.loads('{\"key\": \"value\"}')\n"
            "print(json.dumps(data, indent=2))\n"
        )
        action = {"action_type": "write_file", "path": "parse.py", "content": code}
        mock_run.return_value = self._make_completed_process(
            self._sdk_wrap(json.dumps(action))
        )

        backend = ClaudeCLIBackend()
        result = backend.query("sys", "user")
        parsed = extract_json(result)
        self.assertEqual(parsed["path"], "parse.py")
        self.assertIn("json.loads", parsed["content"])

    @patch("BrainDock.llm.subprocess.run")
    def test_base_agent_llm_query_json_with_sdk_backend(self, mock_run):
        """Full BaseAgent._llm_query_json() path using mocked ClaudeCLIBackend."""
        from BrainDock.base_agent import BaseAgent

        action = {
            "action_type": "write_file",
            "path": "hello.py",
            "content": "print('hello world')\n",
        }
        mock_run.return_value = self._make_completed_process(
            self._sdk_wrap(json.dumps(action))
        )

        agent = BaseAgent(llm=ClaudeCLIBackend())
        parsed = agent._llm_query_json("system prompt", "user prompt")
        self.assertEqual(parsed["action_type"], "write_file")
        self.assertEqual(parsed["path"], "hello.py")
        self.assertIn("hello world", parsed["content"])

    @patch("BrainDock.llm.subprocess.run")
    def test_base_agent_retries_on_sdk_error(self, mock_run):
        """BaseAgent retries when SDK returns is_error."""
        from BrainDock.base_agent import BaseAgent

        error_response = self._make_completed_process(
            self._sdk_wrap("Something went wrong", is_error=True)
        )
        success_response = self._make_completed_process(
            self._sdk_wrap(json.dumps({"action_type": "test", "command": "pytest"}))
        )
        mock_run.side_effect = [error_response, success_response]

        agent = BaseAgent(llm=ClaudeCLIBackend())
        parsed = agent._llm_query_json("sys", "user")
        self.assertEqual(parsed["action_type"], "test")
        self.assertEqual(mock_run.call_count, 2)

    @patch("BrainDock.llm.subprocess.run")
    def test_edit_file_action_with_code_roundtrip(self, mock_run):
        """SDK JSON wrapping an edit_file action with source content."""
        from BrainDock.llm import extract_json

        action = {
            "action_type": "edit_file",
            "path": "main.py",
            "search": "    return a + b",
            "replace": "    result = a + b\n    print(f'Result: {result}')\n    return result",
        }
        mock_run.return_value = self._make_completed_process(
            self._sdk_wrap(json.dumps(action))
        )

        backend = ClaudeCLIBackend()
        result = backend.query("sys", "user")
        parsed = extract_json(result)
        self.assertEqual(parsed["action_type"], "edit_file")
        self.assertIn("result = a + b", parsed["replace"])


if __name__ == "__main__":
    unittest.main()
