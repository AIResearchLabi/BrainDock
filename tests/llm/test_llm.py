"""Tests for the LLM module."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from BrainDock.llm import CallableBackend, LoggingBackend, extract_json


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


if __name__ == "__main__":
    unittest.main()
