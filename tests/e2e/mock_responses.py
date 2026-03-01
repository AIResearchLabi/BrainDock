"""Shared mock LLM response factories for E2E tests.

Each factory returns a JSON string matching the exact format expected by
the corresponding agent.  The `make_sequenced_llm()` builder returns a
CallableBackend that cycles through a response list and captures every
prompt it sees (for assertion in tests).
"""

from __future__ import annotations

import json

from BrainDock.llm import CallableBackend


# ── Spec Agent responses ──────────────────────────────────────────────

def make_spec_analyze(*, questions: list[dict] | None = None) -> str:
    return json.dumps({
        "understanding": "Building a CLI calculator",
        "self_decided": [
            {"id": "d1", "topic": "Language", "decision": "Python 3.11+"},
        ],
        "user_questions": questions or [],
    })


def make_spec_refine(*, ready: bool = True) -> str:
    return json.dumps({
        "ready": ready,
        "understanding": "Building a CLI calculator — clear requirements",
        "self_decided": [],
        "user_questions": [],
    })


def make_spec_generate() -> str:
    return json.dumps({
        "title": "PyCalc",
        "summary": "A CLI calculator",
        "problem_statement": "Need a calculator",
        "goals": ["Fast arithmetic"],
        "target_users": "Developers",
        "user_stories": ["As a user, I want to calculate"],
        "functional_requirements": [
            {"feature": "Eval", "description": "Evaluate expressions",
             "acceptance_criteria": ["Works"], "priority": "must-have"}
        ],
        "non_functional_requirements": ["Fast"],
        "tech_stack": {"language": "Python"},
        "architecture_overview": "Single file",
        "data_models": [],
        "api_endpoints": [],
        "milestones": [
            {"name": "v1", "description": "Done", "deliverables": ["Calculator"]}
        ],
        "constraints": [],
        "assumptions": [],
        "open_questions": [],
    })


def make_spec_responses() -> list[str]:
    """Return the standard 3-call spec sequence: analyze → refine → generate."""
    return [make_spec_analyze(), make_spec_refine(), make_spec_generate()]


# ── Task Graph response ───────────────────────────────────────────────

def make_task_graph(
    tasks: list[dict] | None = None,
    project_title: str = "PyCalc",
) -> str:
    if tasks is None:
        tasks = [{
            "id": "t1",
            "title": "Create calculator module",
            "description": "Write the main calculator with eval support",
            "depends_on": [],
            "estimated_effort": "small",
            "tags": [],
            "risks": [],
        }]
    return json.dumps({"project_title": project_title, "tasks": tasks})


# ── Planner response ─────────────────────────────────────────────────

def make_plan(
    task_id: str = "t1",
    task_title: str = "Create calculator module",
    confidence: float = 0.9,
    entropy: float = 0.1,
    steps: list[dict] | None = None,
) -> str:
    if steps is None:
        steps = [{
            "id": "s1",
            "action": "Write calculator",
            "description": "Create calc.py with eval function",
            "tool": "write_file",
            "expected_output": "calc.py file",
        }]
    return json.dumps({
        "task_id": task_id,
        "task_title": task_title,
        "steps": steps,
        "metrics": {
            "confidence": confidence,
            "entropy": entropy,
            "estimated_steps": len(steps),
            "complexity": "low",
        },
        "relevant_skills": [],
        "assumptions": [],
    })


# ── Executor responses ────────────────────────────────────────────────

def make_exec_write(
    step_id: str = "s1",
    file_path: str = "main.py",
    content: str = "print('hello')\n",
) -> str:
    """Single write_file action (for single-step batches)."""
    return json.dumps({
        "step_id": step_id,
        "action_type": "write_file",
        "file_path": file_path,
        "content": content,
        "verification": "File exists",
    })


def make_exec_batch(actions: list[dict] | None = None) -> str:
    """Array of action objects for a batch."""
    if actions is None:
        actions = [{
            "step_id": "s1",
            "action_type": "write_file",
            "file_path": "main.py",
            "content": "print('hello')\n",
            "verification": "File exists",
        }]
    return json.dumps(actions)


def make_exec_fail(step_id: str = "s1") -> str:
    """Executor action that runs a failing command."""
    return json.dumps({
        "step_id": step_id,
        "action_type": "run_command",
        "file_path": "",
        "content": "exit 1",
        "verification": "",
    })


# ── Reflection response ──────────────────────────────────────────────

def make_reflection(
    should_retry: bool = True,
    needs_human: bool = False,
    escalation_reason: str = "",
    modified_plan: dict | None = None,
) -> str:
    if modified_plan is None and should_retry:
        modified_plan = {
            "task_id": "t1",
            "task_title": "Create calculator module",
            "steps": [{
                "id": "s1_fix",
                "action": "Write calculator (fixed)",
                "description": "Create main.py that works",
                "tool": "write_file",
                "expected_output": "main.py",
            }],
            "metrics": {"confidence": 0.9, "entropy": 0.1,
                        "estimated_steps": 1, "complexity": "low"},
            "relevant_skills": [],
            "assumptions": [],
        }
    return json.dumps({
        "root_causes": [
            {"description": "Command failed", "category": "wrong_approach",
             "confidence": 0.9},
        ],
        "modifications": [
            {"action": "modify_step", "target_step_id": "s1",
             "description": "Fix the failing step"},
        ],
        "summary": "Execution failed, proposing fix",
        "should_retry": should_retry,
        "modified_plan": modified_plan or {},
        "needs_human": needs_human,
        "escalation_reason": escalation_reason,
    })


# ── Debate responses ─────────────────────────────────────────────────

def make_debate_propose() -> str:
    return json.dumps({
        "proposals": [
            {
                "perspective": "pragmatist",
                "approach": "Use simple eval",
                "strengths": ["Fast to implement"],
                "weaknesses": ["Security risk"],
                "confidence": 0.8,
            },
            {
                "perspective": "security-focused",
                "approach": "Use ast.literal_eval",
                "strengths": ["Safe"],
                "weaknesses": ["Limited operations"],
                "confidence": 0.7,
            },
        ],
    })


def make_debate_critique(converged: bool = True) -> str:
    return json.dumps({
        "critiques": [
            {
                "target_perspective": "pragmatist",
                "issues": ["eval is unsafe"],
                "suggestions": ["Add input validation"],
            },
        ],
        "converged": converged,
        "winning_approach": "security-focused",
        "synthesis": "Use ast.literal_eval with extended operator support",
    })


def make_debate_synthesize(plan: dict | None = None) -> str:
    if plan is None:
        plan = {
            "task_id": "t1",
            "task_title": "Create calculator module",
            "steps": [{
                "id": "s1_debated",
                "action": "Write safe calculator",
                "description": "Create main.py using ast.literal_eval",
                "tool": "write_file",
                "expected_output": "main.py",
            }],
            "metrics": {"confidence": 0.95, "entropy": 0.05,
                        "estimated_steps": 1, "complexity": "low"},
            "relevant_skills": [],
            "assumptions": [],
        }
    return json.dumps({
        "improved_plan": plan,
        "synthesis": "Settled on ast.literal_eval for safety",
    })


def make_debate_responses(plan: dict | None = None) -> list[str]:
    """Return the 3-call debate sequence: propose → critique → synthesize."""
    return [
        make_debate_propose(),
        make_debate_critique(converged=True),
        make_debate_synthesize(plan),
    ]


# ── Market Study response ────────────────────────────────────────────

def make_market_study(task_id: str = "t1") -> str:
    return json.dumps({
        "task_id": task_id,
        "competitors": ["bc", "dc"],
        "recommendations": ["Focus on ease of use"],
        "risks": ["Crowded market"],
        "target_audience": "Developers",
        "positioning": "Simplest CLI calculator",
    })


# ── Skill Learning response ──────────────────────────────────────────

def make_skill(skill_id: str = "skill_eval", category: str = "code/evaluation") -> str:
    return json.dumps({
        "id": skill_id,
        "name": "Expression Evaluation",
        "description": "Evaluate user expressions safely",
        "tags": ["parsing", "evaluation"],
        "category": category,
        "pattern": "eval with validation",
        "example_code": "def calc(expr): return eval(expr)",
    })


def make_skill_match(matches: list[dict] | None = None) -> str:
    """Return a match_skills response. Empty matches by default."""
    return json.dumps({"matches": matches or []})


# ── Sequenced LLM builder ────────────────────────────────────────────

class SequencedLLM:
    """A CallableBackend wrapper that captures prompts and cycles responses."""

    def __init__(self, responses: list[str]):
        self.responses = responses
        self.prompts: list[tuple[str, str]] = []  # (system, user)
        self.call_count = 0

        def mock_fn(system_prompt: str, user_prompt: str) -> str:
            self.prompts.append((system_prompt, user_prompt))
            idx = min(self.call_count, len(self.responses) - 1)
            self.call_count += 1
            return self.responses[idx]

        self.backend = CallableBackend(mock_fn)

    @property
    def user_prompts(self) -> list[str]:
        """Convenience: just the user prompts."""
        return [p[1] for p in self.prompts]


def make_sequenced_llm(responses: list[str]) -> SequencedLLM:
    """Build a SequencedLLM with the given response list.

    Usage:
        llm = make_sequenced_llm([resp1, resp2, ...])
        orchestrator = OrchestratorAgent(llm=llm.backend, ...)
        # after run:
        assert "keyword" in llm.user_prompts[5]
    """
    return SequencedLLM(responses)
