"""Pipeline thread manager for the BrainDock dashboard.

Bridges the synchronous blocking orchestrator with the async web server
using threading primitives. All access to shared state is thread-safe.
"""

from __future__ import annotations

import threading
import time
from typing import Any

from BrainDock.orchestrator.agent import OrchestratorAgent
from BrainDock.orchestrator.models import PipelineState, RunConfig
from BrainDock.spec_agent.models import Question, Decision


class PipelineRunner:
    """Manages a pipeline run in a daemon thread with thread-safe state access."""

    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        self._lock = threading.Lock()
        self._state: PipelineState | None = None
        self._running = False
        self._error: str = ""
        self._thread: threading.Thread | None = None

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

        self._thread = threading.Thread(
            target=self._run_pipeline,
            args=(title, problem),
            daemon=True,
        )
        self._thread.start()
        self._add_chat("system", f"Pipeline started: {title}")
        return True

    def resume(self, title: str) -> bool:
        """Resume an existing run by title."""
        import json
        import os
        from BrainDock.orchestrator.models import slugify

        slug = slugify(title)
        state_path = os.path.join(self.output_dir, slug, "pipeline_state.json")
        if not os.path.isfile(state_path):
            return False

        with open(state_path) as f:
            data = json.load(f)
        problem = data.get("problem", "")
        if not problem:
            return False

        return self.start(title, problem)

    def _run_pipeline(self, title: str, problem: str) -> None:
        """Target for the daemon thread — runs the orchestrator."""
        try:
            config = RunConfig(output_dir=self.output_dir)
            orchestrator = OrchestratorAgent(config=config)
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
        except Exception as e:
            with self._lock:
                self._error = str(e)
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

        # Block until web UI submits answers
        self._answer_event.wait()

        with self._lock:
            answers = dict(self._answers)
            self._pending_questions = None
            self._pending_decisions = None
            self._answers = {}

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

        # Surface errors to chat so the user sees them immediately
        if status == "error":
            self._add_chat("system", f"[Error] {agent}: {detail or action}")

    # ── LLM log callback ───────────────────────────────────────────

    def _on_llm_log(self, entry: dict) -> None:
        """Called by the LoggingBackend after every LLM call."""
        with self._lock:
            self._llm_logs.append(entry)

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

    def list_runs(self) -> list[dict]:
        """Delegate to OrchestratorAgent.list_runs()."""
        return OrchestratorAgent.list_runs(self.output_dir)
