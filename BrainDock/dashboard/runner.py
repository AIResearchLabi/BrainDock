"""Pipeline thread manager for the BrainDock dashboard.

Bridges the synchronous blocking orchestrator with the async web server
using threading primitives. All access to shared state is thread-safe.

Chat, activity, and LLM log history is persisted to disk alongside
pipeline_state.json so that resumed runs restore their full history.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

from BrainDock.orchestrator.agent import OrchestratorAgent
from BrainDock.orchestrator.models import PipelineState, RunConfig, slugify
from BrainDock.spec_agent.models import Question, Decision

logger = logging.getLogger("braindock.runner")

# Filenames for persisted history (stored next to pipeline_state.json)
_CHAT_FILE = "dashboard_chat.json"
_ACTIVITIES_FILE = "dashboard_activities.json"
_LLM_LOGS_FILE = "dashboard_llm_logs.json"


class PipelineRunner:
    """Manages a pipeline run in a daemon thread with thread-safe state access."""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        self._lock = threading.Lock()
        self._state: PipelineState | None = None
        self._running = False
        self._error: str = ""
        self._thread: threading.Thread | None = None

        # Per-run output directory (set on start/resume for persistence)
        self._run_dir: str | None = None

        # Activity log: list of {ts, agent, action, detail, status}
        self._activities: list[dict] = []

        # Chat messages: list of {ts, role, text, questions?, answers?}
        self._chat: list[dict] = []

        # LLM call logs: list of {ts, agent, duration, system_prompt, user_prompt, response, est_*}
        self._llm_logs: list[dict] = []

        # Question/answer synchronization
        self._pending_questions: list[dict] | None = None
        self._pending_decisions: list[dict] | None = None
        self._pending_understanding: str = ""
        self._answers: dict[str, str] = {}
        self._answer_event = threading.Event()

    # ── Persistence helpers ────────────────────────────────────────

    def _persist_chat(self) -> None:
        """Write chat history to disk (must hold self._lock)."""
        if not self._run_dir:
            return
        path = os.path.join(self._run_dir, _CHAT_FILE)
        try:
            with open(path, "w") as f:
                json.dump(self._chat, f, default=str)
        except OSError as e:
            logger.warning("Failed to persist chat: %s", e)

    def _persist_activities(self) -> None:
        """Write activity log to disk (must hold self._lock)."""
        if not self._run_dir:
            return
        path = os.path.join(self._run_dir, _ACTIVITIES_FILE)
        try:
            with open(path, "w") as f:
                json.dump(self._activities, f, default=str)
        except OSError as e:
            logger.warning("Failed to persist activities: %s", e)

    def _persist_llm_logs(self) -> None:
        """Write LLM logs to disk (must hold self._lock)."""
        if not self._run_dir:
            return
        path = os.path.join(self._run_dir, _LLM_LOGS_FILE)
        try:
            with open(path, "w") as f:
                json.dump(self._llm_logs, f, default=str)
        except OSError as e:
            logger.warning("Failed to persist LLM logs: %s", e)

    def _load_history(self, run_dir: str) -> None:
        """Load persisted chat, activities, and LLM logs from a run directory."""
        for attr, filename in [
            ("_chat", _CHAT_FILE),
            ("_activities", _ACTIVITIES_FILE),
            ("_llm_logs", _LLM_LOGS_FILE),
        ]:
            path = os.path.join(run_dir, filename)
            if os.path.isfile(path):
                try:
                    with open(path) as f:
                        data = json.load(f)
                    if isinstance(data, list):
                        setattr(self, attr, data)
                        logger.info("Loaded %d %s entries from %s", len(data), attr, filename)
                    else:
                        logger.warning("Unexpected format in %s, ignoring", filename)
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning("Failed to load %s: %s", filename, e)
            else:
                logger.debug("No %s found in %s", filename, run_dir)

    # ── Start / Resume ────────────────────────────────────────────

    def start(self, title: str, problem: str) -> bool:
        """Spawn a daemon thread running the orchestrator pipeline."""
        with self._lock:
            if self._running:
                return False
            self._running = True
            self._error = ""
            self._state = None
            self._pending_questions = None
            self._answer_event.clear()

        # Resolve and store the run directory
        slug = slugify(title)
        run_dir = os.path.join(self.output_dir, slug)
        Path(run_dir).mkdir(parents=True, exist_ok=True)
        self._run_dir = run_dir
        logger.info("Starting pipeline: title=%r, run_dir=%s", title, run_dir)

        self._thread = threading.Thread(
            target=self._run_pipeline,
            args=(title, problem),
            daemon=True,
        )
        self._thread.start()
        self._add_chat("system", f"Pipeline started: {title}")
        return True

    def resume(self, title: str) -> bool:
        """Resume an existing run by title, restoring chat/activity/log history."""
        slug = slugify(title)
        run_dir = os.path.join(self.output_dir, slug)
        state_path = os.path.join(run_dir, "pipeline_state.json")
        if not os.path.isfile(state_path):
            logger.warning("Cannot resume %r: %s not found", title, state_path)
            return False

        try:
            with open(state_path) as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Cannot resume %r: failed to read state: %s", title, e)
            return False

        problem = data.get("problem", "")
        if not problem:
            logger.warning("Cannot resume %r: no problem statement in state", title)
            return False

        # Load old history BEFORE starting (so it's available immediately)
        logger.info("Resuming pipeline: title=%r, run_dir=%s", title, run_dir)
        with self._lock:
            self._chat = []
            self._activities = []
            self._llm_logs = []
        self._load_history(run_dir)

        return self.start(title, problem)

    def _run_pipeline(self, title: str, problem: str) -> None:
        """Target for the daemon thread — runs the orchestrator."""
        try:
            config = RunConfig(output_dir=self.output_dir)
            orchestrator = OrchestratorAgent(config=config)
            logger.info("Orchestrator.run() starting for %r", title)
            state = orchestrator.run(
                problem=problem,
                ask_fn=self._web_ask_fn,
                title=title,
                on_activity=self._on_activity,
                on_state=self._on_state_change,
                on_llm_log=self._on_llm_log,
            )
            with self._lock:
                self._state = state
            logger.info("Pipeline completed for %r", title)
        except Exception as e:
            with self._lock:
                self._error = str(e)
            logger.exception("Pipeline failed for %r: %s", title, e)
            self._on_activity("orchestrator", "error", str(e), "error")
        finally:
            with self._lock:
                self._running = False

    # ── State change callback ─────────────────────────────────────

    def _on_state_change(self, state: PipelineState) -> None:
        """Called by the orchestrator after every _save_state().

        Updates runner's live state so the dashboard can poll it in real-time.
        """
        with self._lock:
            self._state = state

    # ── Ask function (blocks pipeline thread) ─────────────────────

    def _web_ask_fn(
        self,
        questions: list[Question],
        decisions: list[Decision],
        understanding: str,
    ) -> dict[str, str]:
        """Called by the orchestrator in the pipeline thread.

        Stores the questions, posts them to chat, then blocks until
        the web UI submits answers via submit_answers().
        """
        q_dicts = [
            {
                "id": q.id,
                "question": q.question,
                "why": q.why,
                "options": q.options,
            }
            for q in questions
        ]
        d_dicts = [
            {"id": d.id, "topic": d.topic, "decision": d.decision}
            for d in decisions
        ]

        with self._lock:
            self._pending_questions = q_dicts
            self._pending_decisions = d_dicts
            self._pending_understanding = understanding
            self._answer_event.clear()

        # Add to chat
        if decisions:
            for d in d_dicts:
                self._add_chat("system", f"Decision: {d['topic']} — {d['decision']}")
        if understanding:
            self._add_chat("system", f"Understanding: {understanding}")
        if q_dicts:
            self._add_chat("question", "", questions=q_dicts)
        else:
            # No questions — auto-proceed
            with self._lock:
                self._pending_questions = None
                self._pending_decisions = None
            return {}

        logger.info("Waiting for user answers (%d questions)", len(q_dicts))
        # Block until web UI submits answers
        self._answer_event.wait()

        with self._lock:
            answers = dict(self._answers)
            self._pending_questions = None
            self._pending_decisions = None
            self._answers = {}

        logger.info("Received answers: %s", list(answers.keys()))
        return answers

    # ── Activity callback ─────────────────────────────────────────

    def _on_activity(self, agent: str, action: str, detail: str = "", status: str = "info") -> None:
        """Called by the orchestrator via on_activity."""
        entry = {
            "ts": time.time(),
            "agent": agent,
            "action": action,
            "detail": detail,
            "status": status,
        }
        with self._lock:
            self._activities.append(entry)
            self._persist_activities()

        logger.info("[Activity] %s | %s | %s | %s", agent, action, status, detail[:120] if detail else "")

        # Surface errors to chat so the user sees them immediately
        if status == "error":
            self._add_chat("system", f"[Error] {agent}: {detail or action}")

    # ── LLM log callback ───────────────────────────────────────────

    def _on_llm_log(self, entry: dict) -> None:
        """Called by the LoggingBackend after every LLM call."""
        with self._lock:
            self._llm_logs.append(entry)
            self._persist_llm_logs()

        logger.info(
            "[LLM] agent=%s duration=%.1fs est_tokens=%d+%d",
            entry.get("agent", "?"),
            entry.get("duration", 0),
            entry.get("est_input_tokens", 0),
            entry.get("est_output_tokens", 0),
        )

    # ── Thread-safe getters ───────────────────────────────────────

    def get_state(self) -> dict:
        """Return current pipeline state + runner metadata."""
        with self._lock:
            state_dict = self._state.to_dict() if self._state else {}
            return {
                **state_dict,
                "_running": self._running,
                "_error": self._error,
                "_pending_questions": self._pending_questions,
                "_pending_decisions": self._pending_decisions,
                "_pending_understanding": self._pending_understanding if self._pending_questions else "",
            }

    def get_activities(self, since: int = 0) -> dict:
        """Return activity log entries since index `since`."""
        with self._lock:
            entries = self._activities[since:]
            return {"entries": entries, "cursor": len(self._activities)}

    def get_chat(self, since: int = 0) -> dict:
        """Return chat messages since index `since`."""
        with self._lock:
            entries = self._chat[since:]
            return {"entries": entries, "cursor": len(self._chat)}

    def get_logs(self, since: int = 0) -> dict:
        """Return LLM call logs since index `since`."""
        with self._lock:
            entries = self._llm_logs[since:]
            return {"entries": entries, "cursor": len(self._llm_logs)}

    # ── Mutations ─────────────────────────────────────────────────

    def submit_answers(self, answers: dict[str, str]) -> bool:
        """Submit answers from the web UI, unblocking the pipeline thread."""
        with self._lock:
            if self._pending_questions is None:
                return False
            self._answers = answers

        # Add user answers to chat
        for qid, val in answers.items():
            self._add_chat("user", f"Answer ({qid}): {val}")

        self._answer_event.set()
        return True

    def send_chat(self, message: str) -> None:
        """Add a user message to the chat log."""
        self._add_chat("user", message)

    def _add_chat(self, role: str, text: str, questions: list[dict] | None = None) -> None:
        entry: dict[str, Any] = {"ts": time.time(), "role": role, "text": text}
        if questions is not None:
            entry["questions"] = questions
        with self._lock:
            self._chat.append(entry)
            self._persist_chat()

        logger.debug("[Chat] role=%s text=%s", role, text[:80] if text else "(empty)")

    def list_runs(self) -> list[dict]:
        """Delegate to OrchestratorAgent.list_runs()."""
        return OrchestratorAgent.list_runs(self.output_dir)
