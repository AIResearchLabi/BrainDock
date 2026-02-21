"""Core Spec Agent logic.

Orchestrates the analyze → ask → refine → generate flow.
The LLM self-decides routine questions and only asks the user critical ones.
Supports session persistence for resume-after-interrupt.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import sys

from .models import Question, Decision, ProjectSpec
from .prompts import SYSTEM_PROMPT, ANALYZE_PROMPT, REFINE_PROMPT, GENERATE_SPEC_PROMPT
from .llm import LLMBackend, ClaudeCLIBackend, extract_json
from BrainDock.preambles import build_system_prompt, BUSINESS_OPS, DEV_OPS

MAX_LLM_RETRIES = 2


class AnalyzeResult:
    """Result of an analyze/refine step."""

    def __init__(
        self,
        decisions: list[Decision],
        questions: list[Question],
        understanding: str,
        ready: bool = False,
    ):
        self.decisions = decisions
        self.questions = questions
        self.understanding = understanding
        self.ready = ready


class SpecAgent:
    """Interactive agent that turns a problem statement into a project spec.

    The LLM autonomously decides routine technical questions and only
    escalates critical/ambiguous ones to the user.

    Usage (with callback):
        agent = SpecAgent(problem="Build a todo app", llm=my_backend)
        spec = agent.run(ask_fn=my_question_handler)

    Resume after interrupt:
        agent = SpecAgent.load_session("session.json", llm=my_backend)
        spec = agent.run(ask_fn=my_question_handler)
    """

    MAX_ROUNDS = 3
    DEFAULT_SESSION_FILE = ".spec_agent_session.json"

    def __init__(
        self,
        problem: str,
        llm: LLMBackend | None = None,
        max_rounds: int | None = None,
        session_file: str | None = None,
    ):
        self.problem = problem
        self.llm = llm or ClaudeCLIBackend()
        self.max_rounds = max_rounds or self.MAX_ROUNDS
        self.conversation: list[dict] = []
        self.understanding: str = ""
        self._round = 0
        self._sys_prompt = build_system_prompt(SYSTEM_PROMPT, BUSINESS_OPS, DEV_OPS)
        self._pending_questions: list[Question] | None = None
        self._pending_decisions: list[Decision] | None = None
        self.session_file = session_file or self.DEFAULT_SESSION_FILE

    # ── Session persistence ──────────────────────────────────────────

    def _save_session(self):
        """Save current agent state to session file."""
        state = {
            "problem": self.problem,
            "conversation": self.conversation,
            "understanding": self.understanding,
            "round": self._round,
            "max_rounds": self.max_rounds,
            "pending_questions": (
                [q.to_dict() for q in self._pending_questions]
                if self._pending_questions else None
            ),
            "pending_decisions": (
                [d.to_dict() for d in self._pending_decisions]
                if self._pending_decisions else None
            ),
        }
        Path(self.session_file).write_text(json.dumps(state, indent=2))

    def _clear_session(self):
        """Remove session file after successful completion."""
        p = Path(self.session_file)
        if p.exists():
            p.unlink()

    @classmethod
    def load_session(
        cls,
        session_file: str | None = None,
        llm: LLMBackend | None = None,
    ) -> SpecAgent | None:
        """Load agent state from a session file.

        Returns None if no session file exists.
        """
        path = Path(session_file or cls.DEFAULT_SESSION_FILE)
        if not path.exists():
            return None

        state = json.loads(path.read_text())
        agent = cls(
            problem=state["problem"],
            llm=llm,
            max_rounds=state.get("max_rounds", cls.MAX_ROUNDS),
            session_file=str(path),
        )
        agent.conversation = state.get("conversation", [])
        agent.understanding = state.get("understanding", "")
        agent._round = state.get("round", 0)

        pending_q = state.get("pending_questions")
        if pending_q:
            agent._pending_questions = [
                Question(
                    id=q["id"],
                    question=q["question"],
                    why=q["why"],
                    options=q.get("options", []),
                )
                for q in pending_q
            ]

        pending_d = state.get("pending_decisions")
        if pending_d:
            agent._pending_decisions = [
                Decision(id=d["id"], topic=d["topic"], decision=d["decision"])
                for d in pending_d
            ]

        return agent

    # ── Conversation history ─────────────────────────────────────────

    def _build_history(self) -> str:
        """Format conversation history for prompts."""
        if not self.conversation:
            return "(No conversation yet)"

        parts = []
        for entry in self.conversation:
            if entry["role"] == "decisions":
                parts.append("AGENT DECIDED:")
                for d in entry["decisions"]:
                    parts.append(f"  - [{d['id']}] {d['topic']}: {d['decision']}")
            elif entry["role"] == "questions":
                parts.append("AGENT ASKED USER:")
                for q in entry["questions"]:
                    parts.append(f"  - [{q['id']}] {q['question']}")
                    parts.append(f"    Why: {q['why']}")
            elif entry["role"] == "answers":
                parts.append("USER ANSWERED:")
                for qid, answer in entry["answers"].items():
                    parts.append(f"  - [{qid}]: {answer}")
        return "\n".join(parts)

    # ── Core flow ────────────────────────────────────────────────────

    def _llm_query_json(self, system_prompt: str, user_prompt: str) -> dict:
        """Query the LLM and parse JSON response, with retry on parse failure."""
        last_error = None
        for attempt in range(MAX_LLM_RETRIES):
            response = self.llm.query(system_prompt, user_prompt)
            try:
                return extract_json(response)
            except (ValueError, json.JSONDecodeError) as e:
                last_error = e
                print(
                    f"  [Retry {attempt + 1}/{MAX_LLM_RETRIES}] "
                    f"LLM response was not valid JSON, retrying...",
                    file=sys.stderr,
                )
        raise RuntimeError(
            f"LLM failed to return valid JSON after {MAX_LLM_RETRIES} attempts: {last_error}"
        )

    @staticmethod
    def _parse_decisions(data: dict) -> list[Decision]:
        return [
            Decision(id=d["id"], topic=d["topic"], decision=d["decision"])
            for d in data.get("self_decided", [])
        ]

    @staticmethod
    def _parse_questions(data: dict) -> list[Question]:
        return [
            Question(
                id=q["id"],
                question=q["question"],
                why=q["why"],
                options=q.get("options", []),
            )
            for q in data.get("user_questions", [])
        ]

    def analyze(self) -> AnalyzeResult:
        """Analyze the problem statement. LLM self-decides what it can."""
        prompt = ANALYZE_PROMPT.format(problem_statement=self.problem)
        data = self._llm_query_json(self._sys_prompt, prompt)

        self.understanding = data.get("understanding", "")
        decisions = self._parse_decisions(data)
        questions = self._parse_questions(data)

        # Record decisions in conversation
        if decisions:
            self.conversation.append({
                "role": "decisions",
                "decisions": [d.to_dict() for d in decisions],
            })

        # Record questions in conversation (if any)
        if questions:
            self.conversation.append({
                "role": "questions",
                "questions": [q.to_dict() for q in questions],
            })

        self._round = 1
        self._pending_questions = questions if questions else None
        self._pending_decisions = decisions if decisions else None
        self._save_session()

        return AnalyzeResult(
            decisions=decisions,
            questions=questions,
            understanding=self.understanding,
        )

    def refine(self, answers: dict[str, str]) -> AnalyzeResult:
        """Process user answers and either ask follow-ups or signal readiness.

        Returns an AnalyzeResult. Check result.ready to know if spec
        generation can proceed, and result.questions for any new user questions.
        """
        self.conversation.append({"role": "answers", "answers": answers})
        self._round += 1
        self._pending_questions = None
        self._pending_decisions = None
        self._save_session()

        # Force spec generation after max rounds
        if self._round > self.max_rounds:
            return AnalyzeResult(
                decisions=[], questions=[],
                understanding=self.understanding, ready=True,
            )

        prompt = REFINE_PROMPT.format(
            problem_statement=self.problem,
            conversation_history=self._build_history(),
        )
        data = self._llm_query_json(self._sys_prompt, prompt)

        self.understanding = data.get("understanding", self.understanding)
        decisions = self._parse_decisions(data)
        questions = self._parse_questions(data)
        ready = data.get("ready", False)

        if decisions:
            self.conversation.append({
                "role": "decisions",
                "decisions": [d.to_dict() for d in decisions],
            })

        if questions and not ready:
            self.conversation.append({
                "role": "questions",
                "questions": [q.to_dict() for q in questions],
            })
            self._pending_questions = questions
            self._pending_decisions = decisions if decisions else None
            self._save_session()
        else:
            questions = []

        return AnalyzeResult(
            decisions=decisions,
            questions=questions,
            understanding=self.understanding,
            ready=ready or not questions,
        )

    def generate_spec(self) -> ProjectSpec:
        """Generate the final project specification."""
        prompt = GENERATE_SPEC_PROMPT.format(
            problem_statement=self.problem,
            conversation_history=self._build_history(),
        )
        data = self._llm_query_json(self._sys_prompt, prompt)

        return ProjectSpec.from_dict(data)

    def run(
        self,
        ask_fn: Callable[[list[Question], list[Decision], str], dict[str, str]],
    ) -> ProjectSpec:
        """Run the full interactive loop.

        The ask_fn callback signature is:
            ask_fn(questions, decisions, understanding) -> {question_id: answer}

        It receives the LLM's autonomous decisions (for display) and only
        the critical questions that need user input. Return answers keyed
        by question id. If questions is empty, the callback is still called
        so it can display the decisions, but the returned dict is ignored.

        Returns:
            The generated ProjectSpec.
        """
        # Resume: if we have pending questions from a saved session
        if self._pending_questions is not None or self._pending_decisions is not None:
            questions = self._pending_questions or []
            decisions = self._pending_decisions or []
            if questions:
                answers = ask_fn(questions, decisions, self.understanding)
                result = self.refine(answers)
            else:
                # Only decisions pending, show them and move on
                ask_fn([], decisions, self.understanding)
                result = AnalyzeResult(
                    decisions=decisions, questions=[],
                    understanding=self.understanding, ready=True,
                )
        else:
            result = self.analyze()
            if result.questions:
                answers = ask_fn(result.questions, result.decisions, self.understanding)
                result = self.refine(answers)
            else:
                # No user questions needed — show decisions only
                ask_fn([], result.decisions, self.understanding)

        # Continue refinement rounds if needed
        while not result.ready:
            answers = ask_fn(result.questions, result.decisions, self.understanding)
            result = self.refine(answers)

        spec = self.generate_spec()
        self._clear_session()
        return spec
