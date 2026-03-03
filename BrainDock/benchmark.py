"""BrainDock Benchmark Suite — reproducible performance metrics using mock LLMs.

Measures token usage, LLM call counts, execution speed, plan quality,
skill bank utilization, and failure/recovery behavior across scenarios.

Usage:
    python -m BrainDock.benchmark [output.json]
    python -m BrainDock.benchmark --save-baseline
    python -m BrainDock.benchmark --check-baseline
    python -m BrainDock.benchmark --history
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import shutil
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any


# ── Dataclasses ──────────────────────────────────────────────────────


@dataclass
class BenchmarkScenario:
    """Defines a single benchmark scenario."""
    name: str
    description: str
    problem: str
    responses: list[str]
    config_overrides: dict = field(default_factory=dict)
    expected_tasks: int = 1
    expected_success: bool = True


@dataclass
class BenchmarkResult:
    """Metrics collected from running one scenario."""
    scenario_name: str = ""
    success: bool = False
    wall_time_seconds: float = 0.0
    total_llm_calls: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens: int = 0
    per_agent_tokens: dict = field(default_factory=dict)
    per_agent_calls: dict = field(default_factory=dict)
    avg_call_duration_ms: float = 0.0
    task_count: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    step_completion_rate: float = 0.0
    plan_confidence: float = 0.0
    plan_entropy: float = 0.0
    reflection_count: int = 0
    debate_count: int = 0
    escalation_count: int = 0
    skills_learned: int = 0
    skills_matched: int = 0
    verification_pass_rate: float = 0.0
    generated_files: list = field(default_factory=list)
    errors: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BenchmarkReport:
    """Aggregated results from running multiple scenarios."""
    results: list[BenchmarkResult] = field(default_factory=list)
    timestamp: str = ""
    total_wall_time: float = 0.0
    summary: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "total_wall_time": self.total_wall_time,
            "summary": self.summary,
            "results": [r.to_dict() for r in self.results],
        }

    def to_text(self) -> str:
        lines = [
            "=" * 70,
            "BrainDock Benchmark Report",
            f"Timestamp: {self.timestamp}",
            f"Total wall time: {self.total_wall_time:.2f}s",
            "=" * 70,
            "",
            f"{'Scenario':<35} {'OK?':>4} {'Calls':>6} {'Tokens':>8} {'Time':>8}",
            "-" * 70,
        ]
        for r in self.results:
            ok = "PASS" if r.success else "FAIL"
            lines.append(
                f"{r.scenario_name:<35} {ok:>4} {r.total_llm_calls:>6} "
                f"{r.total_tokens:>8} {r.wall_time_seconds:>7.2f}s"
            )
        lines.append("-" * 70)
        s = self.summary
        lines.append(
            f"{'TOTALS':<35} {s.get('success_rate', 0)*100:>3.0f}% "
            f"{s.get('avg_calls', 0):>6.1f} {s.get('avg_tokens', 0):>8.0f} "
            f"{self.total_wall_time:>7.2f}s"
        )
        lines.append("")
        lines.append(f"Scenarios: {s.get('total_scenarios', 0)}")
        lines.append(f"Success rate: {s.get('success_rate', 0)*100:.0f}%")
        lines.append(f"Avg LLM calls: {s.get('avg_calls', 0):.1f}")
        lines.append(f"Avg tokens: {s.get('avg_tokens', 0):.0f}")
        lines.append(f"Avg reflections: {s.get('avg_reflections', 0):.1f}")
        lines.append(f"Avg debates: {s.get('avg_debates', 0):.1f}")
        lines.append("=" * 70)
        return "\n".join(lines)

    def compare_to_baseline(
        self, baseline: dict | None, threshold: float = 0.10
    ) -> list[dict]:
        """Compare current results against a baseline and return regression alerts.

        Args:
            baseline: Baseline dict (from load_baseline), or None.
            threshold: Fractional threshold (default 10%). Exceeding it is
                       "warning"; exceeding 2x is "critical".

        Returns:
            List of RegressionAlert dicts with keys: scenario, metric,
            baseline_value, current_value, pct_change, severity.
        """
        if baseline is None:
            return []

        baseline_scenarios = baseline.get("scenarios", {})
        tracked_metrics = [
            "total_tokens", "total_llm_calls", "reflection_count",
            "debate_count", "escalation_count",
        ]
        alerts: list[dict] = []

        for result in self.results:
            bl = baseline_scenarios.get(result.scenario_name)
            if bl is None:
                continue
            for metric in tracked_metrics:
                current_val = getattr(result, metric, 0)
                baseline_val = bl.get(metric, 0)
                if baseline_val == 0:
                    if current_val > 0:
                        pct = float("inf")
                    else:
                        continue
                else:
                    pct = (current_val - baseline_val) / baseline_val

                if pct > threshold:
                    severity = "critical" if pct > 2 * threshold else "warning"
                    alerts.append({
                        "scenario": result.scenario_name,
                        "metric": metric,
                        "baseline_value": baseline_val,
                        "current_value": current_val,
                        "pct_change": round(pct, 4),
                        "severity": severity,
                    })

        return alerts


# ── Baseline & History ──────────────────────────────────────────────

_BASELINE_METRICS = [
    "total_tokens", "total_llm_calls", "reflection_count",
    "debate_count", "escalation_count",
]


def save_baseline(report: BenchmarkReport, path: str) -> None:
    """Write the report's per-scenario metrics to a JSON baseline file."""
    scenarios: dict[str, dict] = {}
    for r in report.results:
        scenarios[r.scenario_name] = {m: getattr(r, m, 0) for m in _BASELINE_METRICS}
    data = {"timestamp": report.timestamp, "scenarios": scenarios}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_baseline(path: str) -> dict | None:
    """Load baseline from JSON. Returns None if file is missing."""
    if not os.path.isfile(path):
        return None
    with open(path, "r") as f:
        return json.load(f)


def append_history(report: BenchmarkReport, path: str) -> None:
    """Append one JSONL line with timestamp + per-scenario summary metrics."""
    scenarios: dict[str, dict] = {}
    for r in report.results:
        scenarios[r.scenario_name] = {m: getattr(r, m, 0) for m in _BASELINE_METRICS}
    entry = {"timestamp": report.timestamp, "scenarios": scenarios}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


def load_history(path: str) -> list[dict]:
    """Read all history entries from a JSONL file. Returns [] if missing."""
    if not os.path.isfile(path):
        return []
    entries: list[dict] = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


# ── BenchmarkHarness ────────────────────────────────────────────────


class BenchmarkHarness:
    """Runs benchmark scenarios and collects metrics."""

    def __init__(self, output_dir: str | None = None):
        self._output_dir = output_dir
        self._own_tmpdir = False

    def run_scenario(self, scenario: BenchmarkScenario) -> BenchmarkResult:
        """Run a single scenario and return metrics."""
        # Lazy imports to avoid circular deps at module level
        from tests.e2e.mock_responses import SequencedLLM
        from BrainDock.llm import LoggingBackend
        from BrainDock.orchestrator.agent import OrchestratorAgent
        from BrainDock.orchestrator.models import RunConfig

        # Setup output directory
        if self._output_dir:
            run_dir = self._output_dir
        else:
            run_dir = tempfile.mkdtemp(prefix="benchmark_")
            self._own_tmpdir = True

        scenario_dir = os.path.join(run_dir, scenario.name)
        os.makedirs(scenario_dir, exist_ok=True)

        # Build mock LLM
        seq = SequencedLLM(scenario.responses)

        # Collect logs
        llm_logs: list[dict] = []

        def on_llm_log(entry: dict) -> None:
            llm_logs.append(entry)

        # Build config
        config_kwargs: dict[str, Any] = {"output_dir": scenario_dir}
        config_kwargs.update(scenario.config_overrides)
        config = RunConfig(**config_kwargs)

        # Auto-skip escalation ask_fn
        def ask_fn(questions, decisions, understanding):
            return {"escalation_action": "skip", "escalation_hint": ""}

        # Run pipeline
        errors: list[str] = []
        start = time.monotonic()
        try:
            orchestrator = OrchestratorAgent(llm=seq.backend, config=config)
            state = orchestrator.run(
                problem=scenario.problem,
                ask_fn=ask_fn,
                on_llm_log=on_llm_log,
            )
        except Exception as e:
            errors.append(str(e))
            elapsed = time.monotonic() - start
            return BenchmarkResult(
                scenario_name=scenario.name,
                success=False,
                wall_time_seconds=elapsed,
                errors=errors,
            )
        elapsed = time.monotonic() - start

        # Extract metrics
        result = self._extract_metrics(state, llm_logs, elapsed, scenario)
        result.errors = errors

        # Cleanup temp dir if we created it
        if self._own_tmpdir and not self._output_dir:
            shutil.rmtree(run_dir, ignore_errors=True)
            self._own_tmpdir = False

        return result

    def run_all(self, scenarios: list[BenchmarkScenario]) -> BenchmarkReport:
        """Run all scenarios and produce an aggregated report."""
        results = []
        total_start = time.monotonic()
        for scenario in scenarios:
            result = self.run_scenario(scenario)
            results.append(result)
        total_elapsed = time.monotonic() - total_start

        report = BenchmarkReport(
            results=results,
            timestamp=datetime.now(timezone.utc).isoformat(),
            total_wall_time=total_elapsed,
        )

        # Compute summary
        n = len(results) or 1
        successes = sum(1 for r in results if r.success)
        report.summary = {
            "total_scenarios": len(results),
            "successes": successes,
            "failures": len(results) - successes,
            "success_rate": successes / n,
            "avg_calls": sum(r.total_llm_calls for r in results) / n,
            "avg_tokens": sum(r.total_tokens for r in results) / n,
            "avg_reflections": sum(r.reflection_count for r in results) / n,
            "avg_debates": sum(r.debate_count for r in results) / n,
            "avg_wall_time": sum(r.wall_time_seconds for r in results) / n,
        }

        return report

    def _extract_metrics(
        self,
        state: Any,
        llm_logs: list[dict],
        wall_time: float,
        scenario: BenchmarkScenario,
    ) -> BenchmarkResult:
        """Extract BenchmarkResult from pipeline state and logs."""
        # Token metrics from llm_logs
        total_input = sum(e.get("est_input_tokens", 0) for e in llm_logs)
        total_output = sum(e.get("est_output_tokens", 0) for e in llm_logs)
        total_calls = len(llm_logs)

        # Per-agent breakdown
        per_agent_tokens: dict[str, int] = {}
        per_agent_calls: dict[str, int] = {}
        total_duration_ms = 0.0
        for entry in llm_logs:
            agent = entry.get("agent", "unknown")
            tokens = entry.get("est_input_tokens", 0) + entry.get("est_output_tokens", 0)
            per_agent_tokens[agent] = per_agent_tokens.get(agent, 0) + tokens
            per_agent_calls[agent] = per_agent_calls.get(agent, 0) + 1
            total_duration_ms += entry.get("duration", 0) * 1000

        avg_duration = total_duration_ms / total_calls if total_calls > 0 else 0.0

        # Task metrics
        task_count = len(state.task_graph.get("tasks", []))
        tasks_completed = len(state.completed_tasks)
        tasks_failed = len(state.failed_tasks)

        # Step completion rate
        steps_completed_total = 0
        steps_total_total = 0
        for er in state.execution_results:
            steps_completed_total += er.get("steps_completed", 0)
            steps_total_total += er.get("steps_total", 0)
        step_rate = steps_completed_total / steps_total_total if steps_total_total > 0 else 0.0

        # Plan metrics
        confidences = []
        entropies = []
        for plan in state.plans:
            metrics = plan.get("metrics", {})
            if "confidence" in metrics:
                confidences.append(metrics["confidence"])
            if "entropy" in metrics:
                entropies.append(metrics["entropy"])
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0
        avg_entropy = sum(entropies) / len(entropies) if entropies else 0.0

        # Reflection / debate / escalation
        reflection_count = len(state.reflections)
        debate_count = len(state.debates)
        escalation_count = len(state.escalations)

        # Skill metrics
        skills_learned = len(state.learned_skills)
        # Count skills_matched from plans' relevant_skills
        skills_matched = 0
        for plan in state.plans:
            skills_matched += len(plan.get("relevant_skills", []))

        # Verification
        v_total = len(state.verification_results)
        v_pass = sum(1 for v in state.verification_results if v.get("success"))
        v_rate = v_pass / v_total if v_total > 0 else 0.0

        # Generated files
        gen_files: list[str] = []
        for er in state.execution_results:
            gen_files.extend(er.get("generated_files", []))

        # Determine overall success
        pipeline_ok = (
            len(state.completed_tasks) > 0
            and len(state.failed_tasks) == 0
            and not state.error
        )
        # For scenarios that expect failure, invert
        if not scenario.expected_success:
            pipeline_ok = len(state.failed_tasks) > 0 or len(state.escalations) > 0

        return BenchmarkResult(
            scenario_name=scenario.name,
            success=pipeline_ok,
            wall_time_seconds=wall_time,
            total_llm_calls=total_calls,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
            total_tokens=total_input + total_output,
            per_agent_tokens=per_agent_tokens,
            per_agent_calls=per_agent_calls,
            avg_call_duration_ms=avg_duration,
            task_count=task_count,
            tasks_completed=tasks_completed,
            tasks_failed=tasks_failed,
            step_completion_rate=step_rate,
            plan_confidence=avg_confidence,
            plan_entropy=avg_entropy,
            reflection_count=reflection_count,
            debate_count=debate_count,
            escalation_count=escalation_count,
            skills_learned=skills_learned,
            skills_matched=skills_matched,
            verification_pass_rate=v_rate,
            generated_files=gen_files,
        )


# ── Built-in Scenarios ──────────────────────────────────────────────

# Lazy imports for scenario factories (avoids import-time dependency issues)

class _MockFactories:
    """Namespace for lazily-imported mock response factories."""
    __slots__ = ("spec", "tg", "plan", "exec_batch", "exec_fail",
                 "reflection", "debate", "skill", "skill_match")


def _mock() -> _MockFactories:
    """Lazy import of mock_responses factories."""
    from tests.e2e.mock_responses import (
        make_spec_responses,
        make_task_graph,
        make_plan,
        make_exec_batch,
        make_exec_fail,
        make_reflection,
        make_debate_responses,
        make_skill,
        make_skill_match,
    )
    m = _MockFactories()
    m.spec = make_spec_responses
    m.tg = make_task_graph
    m.plan = make_plan
    m.exec_batch = make_exec_batch
    m.exec_fail = make_exec_fail
    m.reflection = make_reflection
    m.debate = make_debate_responses
    m.skill = make_skill
    m.skill_match = make_skill_match
    return m


def scenario_happy_path() -> BenchmarkScenario:
    """Single task, no failures. Baseline for token/call metrics."""
    m = _mock()
    return BenchmarkScenario(
        name="happy_path",
        description="Single task, all gates pass, skill learned",
        problem="Build a CLI calculator",
        responses=[
            *m.spec(),
            m.tg(),
            m.plan(),
            m.exec_batch(),
            m.skill(),
        ],
        expected_tasks=1,
        expected_success=True,
    )


def scenario_multi_task_deps() -> BenchmarkScenario:
    """3 tasks with dependency chain (t1->t2->t3)."""
    m = _mock()
    import json
    tasks = [
        {"id": "t1", "title": "Core module", "description": "Core logic",
         "depends_on": [], "estimated_effort": "small", "tags": [], "risks": []},
        {"id": "t2", "title": "API layer", "description": "Wrap core in API",
         "depends_on": ["t1"], "estimated_effort": "small", "tags": [], "risks": []},
        {"id": "t3", "title": "CLI wrapper", "description": "CLI for API",
         "depends_on": ["t2"], "estimated_effort": "small", "tags": [], "risks": []},
    ]
    return BenchmarkScenario(
        name="multi_task_deps",
        description="3 tasks with dependency chain t1->t2->t3",
        problem="Build a CLI calculator",
        responses=[
            *m.spec(),
            m.tg(tasks=tasks),
            # t1
            m.plan(task_id="t1", task_title="Core module"),
            m.exec_batch([{"step_id": "s1", "action_type": "write_file",
                           "file_path": "core.py", "content": "def calc(x): return x\n",
                           "verification": ""}]),
            m.skill("skill_core"),
            # t2 (skill matching is heuristic, no LLM call)
            m.plan(task_id="t2", task_title="API layer"),
            m.exec_batch([{"step_id": "s1", "action_type": "write_file",
                           "file_path": "api.py", "content": "from core import calc\n",
                           "verification": ""}]),
            m.skill("skill_api"),
            # t3
            m.plan(task_id="t3", task_title="CLI wrapper"),
            m.exec_batch([{"step_id": "s1", "action_type": "write_file",
                           "file_path": "main.py", "content": "from api import *\n",
                           "verification": ""}]),
            m.skill("skill_cli"),
        ],
        expected_tasks=3,
        expected_success=True,
    )


def scenario_reflection_retry() -> BenchmarkScenario:
    """Execution fails once, reflection produces fix, retry succeeds."""
    m = _mock()
    fixed_plan = {
        "task_id": "t1", "task_title": "Create calculator module",
        "steps": [{"id": "s1_fix", "action": "Write calculator (fixed)",
                   "description": "Create main.py that works",
                   "tool": "write_file", "expected_output": "main.py"}],
        "metrics": {"confidence": 0.9, "entropy": 0.1,
                    "estimated_steps": 1, "complexity": "low"},
        "relevant_skills": [], "assumptions": [],
    }
    return BenchmarkScenario(
        name="reflection_retry",
        description="Execution fails once, reflection fixes, retry succeeds",
        problem="Build a CLI calculator",
        responses=[
            *m.spec(),
            m.tg(),
            m.plan(),
            m.exec_fail(),
            m.reflection(should_retry=True, modified_plan=fixed_plan),
            m.exec_batch([{"step_id": "s1_fix", "action_type": "write_file",
                           "file_path": "main.py", "content": "print('hello')\n",
                           "verification": "File exists"}]),
            m.skill(),
        ],
        expected_tasks=1,
        expected_success=True,
    )


def scenario_reflection_exhausted() -> BenchmarkScenario:
    """All reflection retries exhausted, escalates to human."""
    m = _mock()
    failing_plan = {
        "task_id": "t1", "task_title": "Create calculator module",
        "steps": [{"id": "s1_retry", "action": "Still fails",
                   "description": "Run a failing command",
                   "tool": "run_command", "expected_output": ""}],
        "metrics": {"confidence": 0.9, "entropy": 0.1,
                    "estimated_steps": 1, "complexity": "low"},
        "relevant_skills": [], "assumptions": [],
    }
    return BenchmarkScenario(
        name="reflection_exhausted",
        description="All reflection retries fail, escalation triggered",
        problem="Build a CLI calculator",
        responses=[
            *m.spec(),
            m.tg(),
            m.plan(steps=[{"id": "s1", "action": "Run failing",
                           "description": "Fail", "tool": "run_command",
                           "expected_output": ""}]),
            m.exec_fail("s1"),
            m.reflection(should_retry=True, modified_plan=failing_plan),
            m.exec_fail("s1_retry"),
            m.reflection(should_retry=True, modified_plan=failing_plan),
            m.exec_fail("s1_retry"),
        ],
        config_overrides={
            "max_reflection_iterations": 2,
            "enable_human_escalation": True,
        },
        expected_tasks=1,
        expected_success=False,
    )


def scenario_debate_path() -> BenchmarkScenario:
    """Low confidence plan triggers debate, then succeeds."""
    m = _mock()
    return BenchmarkScenario(
        name="debate_path",
        description="High-entropy plan triggers debate, improved plan executes",
        problem="Build a CLI calculator",
        responses=[
            *m.spec(),
            m.tg(),
            m.plan(confidence=0.9, entropy=0.9),
            *m.debate(),
            m.exec_batch([{"step_id": "s1_debated", "action_type": "write_file",
                           "file_path": "main.py", "content": "print('safe')\n",
                           "verification": "File exists"}]),
            m.skill("skill_debated"),
        ],
        expected_tasks=1,
        expected_success=True,
    )


def scenario_token_budget_pressure() -> BenchmarkScenario:
    """Config with very low budget. Tests graceful budget exhaustion."""
    m = _mock()
    return BenchmarkScenario(
        name="token_budget_pressure",
        description="Very low token budget causes graceful exhaustion",
        problem="Build a CLI calculator",
        responses=[
            *m.spec(),
            m.tg(),
            m.plan(),
            m.exec_batch(),
            m.skill(),
        ],
        config_overrides={
            "global_token_budget": 1,
            "per_task_token_budget": 1,
            "enable_human_escalation": False,
        },
        expected_tasks=1,
        expected_success=False,
    )


def scenario_three_task_chain() -> BenchmarkScenario:
    """3 independent tasks (no deps). Tests parallel execution."""
    m = _mock()
    tasks = [
        {"id": "t1", "title": "Module A", "description": "A",
         "depends_on": [], "estimated_effort": "small", "tags": [], "risks": []},
        {"id": "t2", "title": "Module B", "description": "B",
         "depends_on": [], "estimated_effort": "small", "tags": [], "risks": []},
        {"id": "t3", "title": "Module C", "description": "C",
         "depends_on": [], "estimated_effort": "small", "tags": [], "risks": []},
    ]
    return BenchmarkScenario(
        name="three_task_chain",
        description="3 independent tasks, no dependencies",
        problem="Build a CLI calculator",
        responses=[
            *m.spec(),
            m.tg(tasks=tasks),
            # t1
            m.plan(task_id="t1", task_title="Module A"),
            m.exec_batch([{"step_id": "s1", "action_type": "write_file",
                           "file_path": "a.py", "content": "# A\n", "verification": ""}]),
            m.skill("skill_a"),
            # t2 (skill matching is heuristic, no LLM call)
            m.plan(task_id="t2", task_title="Module B"),
            m.exec_batch([{"step_id": "s1", "action_type": "write_file",
                           "file_path": "b.py", "content": "# B\n", "verification": ""}]),
            m.skill("skill_b"),
            # t3
            m.plan(task_id="t3", task_title="Module C"),
            m.exec_batch([{"step_id": "s1", "action_type": "write_file",
                           "file_path": "c.py", "content": "# C\n", "verification": ""}]),
            m.skill("skill_c"),
        ],
        expected_tasks=3,
        expected_success=True,
    )


def scenario_multi_step_plan() -> BenchmarkScenario:
    """Single task with 3 execution steps. Tests step completion tracking."""
    m = _mock()
    steps = [
        {"id": "s1", "action": "Create config", "description": "Write config",
         "tool": "write_file", "expected_output": "config.py"},
        {"id": "s2", "action": "Create core", "description": "Write core",
         "tool": "write_file", "expected_output": "core.py"},
        {"id": "s3", "action": "Create main", "description": "Write main",
         "tool": "write_file", "expected_output": "main.py"},
    ]
    return BenchmarkScenario(
        name="multi_step_plan",
        description="Single task with 3 execution steps",
        problem="Build a CLI calculator",
        responses=[
            *m.spec(),
            m.tg(),
            m.plan(steps=steps),
            m.exec_batch([
                {"step_id": "s1", "action_type": "write_file",
                 "file_path": "config.py", "content": "# config\n", "verification": ""},
                {"step_id": "s2", "action_type": "write_file",
                 "file_path": "core.py", "content": "# core\n", "verification": ""},
                {"step_id": "s3", "action_type": "write_file",
                 "file_path": "main.py", "content": "# main\n", "verification": ""},
            ]),
            m.skill(),
        ],
        expected_tasks=1,
        expected_success=True,
    )


def scenario_skill_reuse() -> BenchmarkScenario:
    """Two tasks; second uses skills from first. Tests skill matching."""
    m = _mock()
    import json
    tasks = [
        {"id": "t1", "title": "Core module", "description": "Core logic",
         "depends_on": [], "estimated_effort": "small", "tags": [], "risks": []},
        {"id": "t2", "title": "CLI wrapper", "description": "Wraps core",
         "depends_on": ["t1"], "estimated_effort": "small", "tags": [], "risks": []},
    ]
    return BenchmarkScenario(
        name="skill_reuse",
        description="Second task reuses skills from first",
        problem="Build a CLI calculator",
        responses=[
            *m.spec(),
            m.tg(tasks=tasks),
            # t1
            m.plan(task_id="t1", task_title="Core module"),
            m.exec_batch([{"step_id": "s1", "action_type": "write_file",
                           "file_path": "core.py", "content": "def calc(x): return x\n",
                           "verification": ""}]),
            m.skill("skill_core"),
            # t2 (skill matching is heuristic, no LLM call)
            m.plan(task_id="t2", task_title="CLI wrapper"),
            m.exec_batch([{"step_id": "s1", "action_type": "write_file",
                           "file_path": "main.py", "content": "from core import calc\n",
                           "verification": ""}]),
            m.skill("skill_cli"),
        ],
        expected_tasks=2,
        expected_success=True,
    )


def scenario_needs_human() -> BenchmarkScenario:
    """Reflection returns needs_human=True. Tests human escalation."""
    m = _mock()
    return BenchmarkScenario(
        name="needs_human",
        description="Reflection identifies human-required cause, escalation triggered",
        problem="Build a CLI calculator",
        responses=[
            *m.spec(),
            m.tg(),
            m.plan(),
            m.exec_fail(),
            m.reflection(
                should_retry=False,
                needs_human=True,
                escalation_reason="Needs API credentials",
                modified_plan=None,
            ),
        ],
        config_overrides={
            "enable_human_escalation": True,
        },
        expected_tasks=1,
        expected_success=False,
    )


def get_all_scenarios() -> list[BenchmarkScenario]:
    """Return all 10 built-in benchmark scenarios."""
    return [
        scenario_happy_path(),
        scenario_multi_task_deps(),
        scenario_reflection_retry(),
        scenario_reflection_exhausted(),
        scenario_debate_path(),
        scenario_token_budget_pressure(),
        scenario_three_task_chain(),
        scenario_multi_step_plan(),
        scenario_skill_reuse(),
        scenario_needs_human(),
    ]


# ── CLI Runner ──────────────────────────────────────────────────────

_DEFAULT_BASELINE_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "benchmark_baseline.json"
)
_DEFAULT_HISTORY_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data", "benchmark_history.jsonl"
)


def main():
    """Run all benchmark scenarios and print report."""
    import argparse

    parser = argparse.ArgumentParser(description="BrainDock Benchmark Suite")
    parser.add_argument("output", nargs="?", default=None,
                        help="Path to save JSON report")
    parser.add_argument("--save-baseline", action="store_true",
                        help="Save results as the new baseline")
    parser.add_argument("--check-baseline", action="store_true",
                        help="Compare results against saved baseline")
    parser.add_argument("--history", action="store_true",
                        help="Append results to history log")
    parser.add_argument("--baseline-path", default=_DEFAULT_BASELINE_PATH,
                        help="Path to baseline JSON file")
    parser.add_argument("--history-path", default=_DEFAULT_HISTORY_PATH,
                        help="Path to history JSONL file")
    args = parser.parse_args()

    harness = BenchmarkHarness()
    scenarios = get_all_scenarios()

    print(f"Running {len(scenarios)} benchmark scenarios...")
    print()

    report = harness.run_all(scenarios)

    print(report.to_text())

    if args.output:
        with open(args.output, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        print(f"\nJSON report saved to: {args.output}")

    if args.save_baseline:
        save_baseline(report, args.baseline_path)
        print(f"\nBaseline saved to: {args.baseline_path}")

    if args.check_baseline:
        baseline = load_baseline(args.baseline_path)
        if baseline is None:
            print(f"\nNo baseline found at {args.baseline_path}. "
                  "Run with --save-baseline first.")
        else:
            alerts = report.compare_to_baseline(baseline)
            if alerts:
                print(f"\n{len(alerts)} regression(s) detected:")
                for a in alerts:
                    print(f"  [{a['severity'].upper()}] {a['scenario']}.{a['metric']}: "
                          f"{a['baseline_value']} -> {a['current_value']} "
                          f"({a['pct_change']*100:+.1f}%)")
                sys.exit(1)
            else:
                print("\nNo regressions detected vs baseline.")

    if args.history:
        append_history(report, args.history_path)
        print(f"\nHistory appended to: {args.history_path}")


if __name__ == "__main__":
    main()
