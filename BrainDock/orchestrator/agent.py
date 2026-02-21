"""Orchestrator Agent — coordinates the 8-mode pipeline."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

from BrainDock.llm import LLMBackend, ClaudeCLIBackend, LoggingBackend
from BrainDock.project_memory import scan_project
from BrainDock.spec_agent.agent import SpecAgent
from BrainDock.spec_agent.models import Question, Decision
from BrainDock.spec_agent.output import save_spec as save_spec_output
from BrainDock.task_graph.agent import TaskGraphAgent
from BrainDock.task_graph.models import TaskGraph
from BrainDock.task_graph.output import save_task_graph
from BrainDock.planner.agent import PlannerAgent
from BrainDock.planner.models import ActionPlan
from BrainDock.controller.agent import ControllerAgent
from BrainDock.controller.models import GateThresholds
from BrainDock.executor.agent import ExecutorAgent
from BrainDock.executor.models import StopCondition, VerifyResult
from BrainDock.executor.sandbox import verify_project
from BrainDock.skill_bank.agent import SkillLearningAgent
from BrainDock.skill_bank.storage import load_skill_bank, save_skill_bank
from BrainDock.reflection.agent import ReflectionAgent
from BrainDock.debate.agent import DebateAgent
from BrainDock.market_study.agent import MarketStudyAgent
from .models import Mode, PipelineState, RunConfig, slugify


def _emit(on_activity, agent: str, action: str, detail: str = "", status: str = "info"):
    """Fire an activity event if callback is provided."""
    if on_activity:
        on_activity(agent, action, detail, status)


def _build_project_context(
    spec: dict,
    project_dir: str,
    completed_tasks: list[str] | None = None,
) -> str:
    """Build enriched project context including file snapshot.

    Args:
        spec: Project specification dict.
        project_dir: Path to the project output directory.
        completed_tasks: List of completed task IDs.

    Returns:
        Context string for LLM prompts.
    """
    base = f"Project: {spec.get('title', '')}\nSummary: {spec.get('summary', '')}\n"
    if completed_tasks:
        base += f"Completed tasks: {', '.join(completed_tasks)}\n"
    snapshot = scan_project(project_dir)
    base += "\n" + snapshot.to_context_string()
    return base


class OrchestratorAgent:
    """Main orchestrator that coordinates all 8 modes.

    Pipeline: SPEC -> TASK_GRAPH -> (for each task: PLAN -> CONTROLLER ->
    EXECUTE -> VERIFY -> SKILL_LEARN) with REFLECT on failure and DEBATE
    on uncertainty.

    Usage:
        orchestrator = OrchestratorAgent(config=RunConfig())
        state = orchestrator.run(problem="Build a todo app", ask_fn=callback)
    """

    def __init__(
        self,
        llm: LLMBackend | None = None,
        config: RunConfig | None = None,
    ):
        self.llm = llm or ClaudeCLIBackend()
        self.config = config or RunConfig()

    @staticmethod
    def _escalate_to_human(ask_fn, task_node, reason, context, reflection_result=None):
        """Present an escalation question to the human via ask_fn.

        Creates Questions with Skip/Retry/Abort options plus a hint text field,
        then calls ask_fn() which blocks the pipeline thread (same mechanism as
        spec questions).

        Returns:
            dict of answers from the human.
        """
        summary = f"Task '{task_node.id}' needs human help: {reason}"
        if reflection_result and reflection_result.escalation_reason:
            summary += f"\n\nDetails: {reflection_result.escalation_reason}"
        if context:
            # Truncate context to keep the question manageable
            ctx_preview = context[:300] + "..." if len(context) > 300 else context
            summary += f"\n\nContext: {ctx_preview}"

        questions = [
            Question(
                id="escalation_action",
                question=summary,
                why=reason,
                options=["skip", "retry", "abort"],
            ),
            Question(
                id="escalation_hint",
                question="If retrying, provide a hint or guidance (optional):",
                why="Your input will be injected as extra context for the retry attempt.",
                options=[],
            ),
        ]
        decisions = [
            Decision(
                id="escalation_trigger",
                topic="Escalation trigger",
                decision=reason,
            ),
        ]
        answers = ask_fn(questions, decisions, summary)
        return answers

    @staticmethod
    def _parse_escalation_response(answers, task_id):
        """Parse the human's escalation response.

        Returns:
            tuple of (action, hint) where action is "skip"|"retry"|"abort"
            and hint is the optional guidance text.
        """
        action = answers.get("escalation_action", "skip").strip().lower()
        if action not in ("skip", "retry", "abort"):
            action = "skip"
        hint = answers.get("escalation_hint", "").strip()
        return action, hint

    def _save_state(self, state: PipelineState, output_dir: str, on_state: Callable | None = None) -> None:
        """Write pipeline state to JSON for dashboard consumption."""
        state_path = os.path.join(output_dir, "pipeline_state.json")
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        with open(state_path, "w") as f:
            json.dump(state.to_dict(), f, indent=2, default=str)
        if on_state:
            on_state(state)

    @staticmethod
    def _load_state(state_path: str) -> PipelineState | None:
        """Load pipeline state from a JSON file."""
        if not os.path.exists(state_path):
            return None
        try:
            with open(state_path) as f:
                data = json.load(f)
            state = PipelineState.from_dict(data)
            if state.spec and state.spec.get("title"):
                return state
        except (json.JSONDecodeError, KeyError):
            pass
        return None

    def _resolve_output_dir(self, title: str) -> str:
        """Resolve the output directory for a given title."""
        slug = slugify(title)
        return os.path.join(self.config.output_dir, slug)

    @staticmethod
    def list_runs(base_output_dir: str = "output") -> list[dict]:
        """List all existing pipeline runs."""
        runs = []
        if not os.path.isdir(base_output_dir):
            return runs
        for entry in sorted(os.listdir(base_output_dir)):
            state_path = os.path.join(base_output_dir, entry, "pipeline_state.json")
            if os.path.isfile(state_path):
                try:
                    with open(state_path) as f:
                        data = json.load(f)
                    runs.append({
                        "slug": entry,
                        "title": data.get("title", entry),
                        "problem": data.get("problem", ""),
                        "mode": data.get("current_mode", "unknown"),
                        "completed": len(data.get("completed_tasks", [])),
                        "failed": len(data.get("failed_tasks", [])),
                        "total": len(data.get("task_graph", {}).get("tasks", [])),
                    })
                except (json.JSONDecodeError, KeyError):
                    pass
        return runs

    def run(
        self,
        problem: str,
        ask_fn: Callable[[list[Question], list[Decision], str], dict[str, str]],
        title: str | None = None,
        on_activity: Callable | None = None,
        on_state: Callable | None = None,
        on_llm_log: Callable | None = None,
    ) -> PipelineState:
        """Run the full pipeline from problem statement to execution.

        Each run is identified by its title (slugified into a directory name).
        If a run with the same title already exists, it resumes automatically.

        Args:
            problem: The problem statement.
            ask_fn: Callback for user interaction (from spec_agent).
            title: Project title for this run. Auto-generated from problem if omitted.
            on_state: Optional callback invoked after every state save for live updates.
            on_llm_log: Optional callback invoked after every LLM call with log entry.

        Returns:
            PipelineState with all intermediate results.
        """
        # Wrap LLM with logging if callback provided
        llm = self.llm
        logging_backend: LoggingBackend | None = None
        if on_llm_log:
            logging_backend = LoggingBackend(llm, on_log=on_llm_log)
            llm = logging_backend

        def _set_agent(label: str) -> None:
            if logging_backend:
                logging_backend.set_agent_label(label)

        # Resolve title and per-project output directory
        run_title = title or problem[:60]
        output_dir = self._resolve_output_dir(run_title)

        # Try to resume existing run
        state_path = os.path.join(output_dir, "pipeline_state.json")
        resumed_state = self._load_state(state_path)
        if resumed_state:
            state = resumed_state
            print(f'  Resuming run: "{state.title}"')
            print(f"  Last mode: {state.current_mode}")
            _emit(on_activity, "orchestrator", "resumed", f"Resuming: {state.title}")
        else:
            state = PipelineState(title=run_title, problem=problem)
            print(f'  New run: "{run_title}"')
            _emit(on_activity, "orchestrator", "started", f"New run: {run_title}")

        print(f"  Output: {output_dir}/")

        # ── Mode 1: Specification ──────────────────────────────────
        if not state.spec or not state.spec.get("title"):
            state.current_mode = Mode.SPECIFICATION.value
            self._save_state(state, output_dir, on_state)
            _emit(on_activity, "spec", "mode_change", "Entering Specification mode")
            try:
                _set_agent("spec")
                spec_agent = SpecAgent(problem=problem, llm=llm)
                project_spec = spec_agent.run(ask_fn=ask_fn)
                state.spec = project_spec.to_dict()

                spec_dir = os.path.join(output_dir, "spec_agent")
                save_spec_output(project_spec, output_dir=spec_dir)
                _emit(on_activity, "spec", "completed", f"Spec: {project_spec.title}", "success")
                # Emit spec output for Agents tab
                spec_summary = (
                    f"Title: {project_spec.title}\n"
                    f"Summary: {project_spec.summary}\n"
                    f"Goals: {', '.join(project_spec.goals)}\n"
                    f"Tech: {json.dumps(project_spec.tech_stack)}\n"
                    f"Requirements: {len(project_spec.functional_requirements)} functional, "
                    f"{len(project_spec.non_functional_requirements)} non-functional"
                )
                _emit(on_activity, "spec", "output", spec_summary, "info")
            except Exception as e:
                state.error = f"Specification failed: {e}"
                self._save_state(state, output_dir, on_state)
                _emit(on_activity, "spec", "error", str(e), "error")
                return state
        else:
            print(f"  Skipping Mode 1 (Specification) — already complete")
            _emit(on_activity, "spec", "skipped", "Specification already complete")

        # ── Mode 2: Task Graph ─────────────────────────────────────
        if not state.task_graph or not state.task_graph.get("tasks"):
            state.current_mode = Mode.TASK_GRAPH.value
            self._save_state(state, output_dir, on_state)
            _emit(on_activity, "task_graph", "mode_change", "Entering Task Graph mode")
            try:
                _set_agent("task_graph")
                tg_agent = TaskGraphAgent(llm=llm)
                task_graph = tg_agent.decompose(state.spec)
                state.task_graph = task_graph.to_dict()

                tg_dir = os.path.join(output_dir, "task_graph")
                save_task_graph(task_graph, output_dir=tg_dir)
                n = len(task_graph.tasks)
                _emit(on_activity, "task_graph", "completed", f"Decomposed into {n} task(s)", "success")
                # Emit task list for Agents tab
                task_lines = [f"  {t.id}: {t.title} (effort: {t.estimated_effort})" for t in task_graph.tasks]
                _emit(on_activity, "task_graph", "output", "\n".join(task_lines), "info")
            except Exception as e:
                state.error = f"Task graph decomposition failed: {e}"
                self._save_state(state, output_dir, on_state)
                _emit(on_activity, "task_graph", "error", str(e), "error")
                return state
        else:
            print(f"  Skipping Mode 2 (Task Graph) — already complete")
            task_graph = TaskGraph.from_dict(state.task_graph)
            _emit(on_activity, "task_graph", "skipped", "Task graph already complete")

        if self.config.skip_execution:
            return state

        # ── Load skill bank ────────────────────────────────────────
        skill_bank_path = os.path.join(output_dir, "skill_bank", "skills.json")
        skill_bank = load_skill_bank(skill_bank_path)

        # ── Create project directory before task loop ──────────────
        project_dir = os.path.join(output_dir, "project")
        Path(project_dir).mkdir(parents=True, exist_ok=True)

        # ── Process tasks by wave ──────────────────────────────────
        thresholds = GateThresholds(
            min_confidence=self.config.min_confidence,
            max_entropy=self.config.max_entropy,
            max_failures=self.config.max_task_retries,
            max_reflection_iterations=self.config.max_reflection_iterations,
            max_debate_rounds=self.config.max_debate_rounds,
        )
        controller = ControllerAgent(thresholds=thresholds)
        planner = PlannerAgent(
            llm=llm,
            entropy_threshold=self.config.max_entropy,
        )
        executor = ExecutorAgent(llm=llm)
        reflection_agent = ReflectionAgent(
            llm=llm,
            max_iterations=self.config.max_reflection_iterations,
        )
        debate_agent = DebateAgent(
            llm=llm,
            max_rounds=self.config.max_debate_rounds,
        )
        skill_agent = SkillLearningAgent(llm=llm)
        market_study_agent = MarketStudyAgent(llm=llm)

        groups = task_graph.get_parallel_groups()

        completed_ids = set(state.completed_tasks)
        failed_ids = set(state.failed_tasks)

        for group in groups:
            for task_node in group:
                # Skip tasks already completed or permanently failed in a previous run
                if task_node.id in completed_ids:
                    print(f"  Skipping task '{task_node.id}' — already completed")
                    continue
                if task_node.id in failed_ids:
                    # Retry previously failed tasks
                    state.failed_tasks.remove(task_node.id)
                    failed_ids.discard(task_node.id)

                task_dict = task_node.to_dict()
                _emit(on_activity, "orchestrator", "task_start", f"Task: {task_node.id} — {task_node.title}")

                try:
                    # ── Refresh project context ───────────────────────
                    project_context = _build_project_context(
                        state.spec, project_dir,
                        completed_tasks=state.completed_tasks,
                    )

                    # ── Mode 3: Planning ──────────────────────────────
                    state.current_mode = Mode.PLANNING.value
                    self._save_state(state, output_dir, on_state)
                    _set_agent("planner")
                    _emit(on_activity, "planner", "mode_change", f"Planning task: {task_node.id}")
                    available_skills = [
                        {"id": s.id, "name": s.name, "description": s.description}
                        for s in skill_bank.skills
                    ]
                    plan = planner.plan_task(
                        task_dict,
                        context=project_context,
                        available_skills=available_skills or None,
                    )
                    plan_dict = plan.to_dict()
                    state.plans.append(plan_dict)
                    _emit(on_activity, "planner", "completed", f"Plan confidence: {plan.metrics.confidence:.2f}", "success")
                    # Emit plan steps for Agents tab
                    step_lines = [f"  {s.get('id','?')}: {s.get('description', s.get('action',''))}" for s in plan_dict.get("steps", [])]
                    if step_lines:
                        _emit(on_activity, "planner", "output",
                              f"Task: {plan_dict.get('task_title','')}\n" + "\n".join(step_lines), "info")

                    # ── Market Study (if tagged) ──────────────────────
                    if "needs_market_study" in task_dict.get("tags", []):
                        _set_agent("market_study")
                        _emit(on_activity, "market_study", "mode_change", f"Market study for task: {task_node.id}")
                        market_result = market_study_agent.analyze(task_dict, context=project_context)
                        state.market_studies.append(market_result.to_dict())
                        project_context += "\n\nMarket Study:\n" + market_result.to_context_string()
                        _emit(on_activity, "market_study", "completed",
                              f"Market study: {len(market_result.competitors)} competitors analyzed", "success")

                    # ── Mode 4: Controller (plan gate) ────────────────
                    state.current_mode = Mode.CONTROLLER.value
                    self._save_state(state, output_dir, on_state)
                    _emit(on_activity, "controller", "mode_change", "Checking plan gate")
                    gate_result = controller.check_plan_gate(plan_dict)
                    _emit(on_activity, "controller", "gate_result", f"{gate_result.action}: {gate_result.reason}")

                    # ── Mode 8: Debate (if entropy too high) ──────────
                    if gate_result.action == "debate":
                        debate_gate = controller.check_debate_gate()
                        if debate_gate.passed:
                            state.current_mode = Mode.DEBATE.value
                            self._save_state(state, output_dir, on_state)
                            _set_agent("debate")
                            _emit(on_activity, "debate", "mode_change", "Starting multi-perspective debate")
                            controller.state.record_debate()
                            outcome = debate_agent.debate(plan_dict, context=project_context)
                            state.debates.append(outcome.to_dict())
                            if outcome.improved_plan:
                                plan_dict = outcome.improved_plan
                                _emit(on_activity, "debate", "completed", "Debate produced improved plan", "success")
                            else:
                                _emit(on_activity, "debate", "completed", "Debate completed, keeping original plan")
                        else:
                            _emit(on_activity, "debate", "skipped", "Debate gate not passed")

                    # ── Mode 5: Execution ─────────────────────────────
                    state.current_mode = Mode.EXECUTION.value
                    self._save_state(state, output_dir, on_state)
                    _set_agent("executor")
                    _emit(on_activity, "executor", "mode_change", f"Executing task: {task_node.id}")

                    exec_result = executor.execute(
                        plan_dict,
                        project_dir=project_dir,
                        project_file_context=project_context,
                    )
                    exec_dict = exec_result.to_dict()
                    state.execution_results.append(exec_dict)
                    if exec_result.success:
                        _emit(on_activity, "executor", "completed", f"Task {task_node.id} executed successfully", "success")
                    else:
                        _emit(on_activity, "executor", "failed", f"Task {task_node.id} execution failed", "error")
                    # Emit execution output for Agents tab
                    gen_files = exec_result.generated_files or []
                    exec_summary = (
                        f"Steps: {exec_result.steps_completed}/{exec_result.steps_total} completed\n"
                        f"Files: {', '.join(gen_files) if gen_files else 'none'}"
                    )
                    if exec_result.stop_reason:
                        exec_summary += f"\nStop reason: {exec_result.stop_reason}"
                    _emit(on_activity, "executor", "output", exec_summary, "info")

                    # ── Verification ──────────────────────────────────
                    _emit(on_activity, "executor", "verifying", f"Verifying project after task {task_node.id}")
                    verify_result = verify_project(project_dir, timeout=10)
                    state.verification_results.append(verify_result.to_dict())

                    if verify_result.success:
                        _emit(on_activity, "executor", "verified", "Verification passed", "success")
                    else:
                        _emit(on_activity, "executor", "verify_failed",
                               f"Verification failed: {verify_result.error_summary[:100]}", "error")
                        # Override exec_result success if verification fails
                        if exec_result.success:
                            exec_result = type(exec_result)(
                                task_id=exec_result.task_id,
                                success=False,
                                outcomes=exec_result.outcomes,
                                steps_completed=exec_result.steps_completed,
                                steps_total=exec_result.steps_total,
                                failure_count=exec_result.failure_count,
                                stop_reason="Verification failed: " + verify_result.error_summary[:200],
                                generated_files=exec_result.generated_files,
                            )
                            exec_dict = exec_result.to_dict()
                            state.execution_results[-1] = exec_dict

                    # ── Mode 4: Controller (execution gate) ───────────
                    state.current_mode = Mode.CONTROLLER.value
                    self._save_state(state, output_dir, on_state)
                    _emit(on_activity, "controller", "mode_change", "Checking execution gate")
                    exec_gate = controller.check_execution_gate(exec_dict)
                    _emit(on_activity, "controller", "gate_result", f"{exec_gate.action}: {exec_gate.reason}")

                    # ── Mode 7: Reflection (if execution failed) ──────
                    if exec_gate.action == "reflect":
                        current_plan = plan_dict
                        task_token_count = 0
                        _token_hook_installed = False
                        _original_on_log = None
                        if logging_backend:
                            _original_on_log = logging_backend._on_log
                            _token_hook_installed = True
                            def _token_tracking_hook(entry, _orig=_original_on_log):
                                nonlocal task_token_count
                                task_token_count += entry.get("est_input_tokens", 0) + entry.get("est_output_tokens", 0)
                                if _orig:
                                    _orig(entry)
                            logging_backend._on_log = _token_tracking_hook

                        for retry_num in range(self.config.max_reflection_iterations):
                            ref_gate = controller.check_reflection_gate()
                            if not ref_gate.passed:
                                _emit(on_activity, "reflection", "skipped", "Reflection gate not passed")
                                break

                            state.current_mode = Mode.REFLECTION.value
                            self._save_state(state, output_dir, on_state)
                            _set_agent("reflection")
                            _emit(on_activity, "reflection", "mode_change",
                                  f"Reflecting on failure (attempt {retry_num + 1})")
                            controller.state.record_reflection()

                            # Rebuild project context (files may have changed during execution)
                            project_context = _build_project_context(
                                state.spec, project_dir,
                                completed_tasks=state.completed_tasks,
                            )

                            # Append verification errors to context
                            reflect_context = project_context
                            if not verify_result.success:
                                reflect_context += (
                                    f"\n\nVerification error:\n"
                                    f"Command: {verify_result.command}\n"
                                    f"Error: {verify_result.error_summary}\n"
                                    f"Stderr: {verify_result.stderr[:500]}"
                                )

                            ref_result = reflection_agent.reflect(
                                exec_dict, current_plan, context=reflect_context
                            )
                            state.reflections.append(ref_result.to_dict())
                            _emit(on_activity, "reflection", "completed", f"Should retry: {ref_result.should_retry}")
                            # Emit reflection analysis for Agents tab
                            ref_detail = ref_result.to_dict()
                            analysis = ref_detail.get("analysis", "")
                            if analysis:
                                _emit(on_activity, "reflection", "output", analysis[:500], "info")

                            # ── Escalation Point 1: Human-required cause ──
                            if ref_result.needs_human and self.config.enable_human_escalation:
                                _emit(on_activity, "orchestrator", "escalation",
                                      f"Task {task_node.id}: needs human — {ref_result.escalation_reason}", "warning")
                                esc_answers = self._escalate_to_human(
                                    ask_fn, task_node,
                                    reason=f"Reflection identified human-required cause: {ref_result.escalation_reason}",
                                    context=reflect_context,
                                    reflection_result=ref_result,
                                )
                                esc_action, esc_hint = self._parse_escalation_response(esc_answers, task_node.id)
                                state.escalations.append({
                                    "task_id": task_node.id,
                                    "trigger": "needs_human",
                                    "reason": ref_result.escalation_reason,
                                    "action": esc_action,
                                    "hint": esc_hint,
                                })
                                self._save_state(state, output_dir, on_state)
                                if esc_action == "abort":
                                    _emit(on_activity, "orchestrator", "abort", "Human chose to abort pipeline", "error")
                                    return state
                                elif esc_action == "retry" and esc_hint:
                                    reflect_context += f"\n\nHuman guidance: {esc_hint}"
                                    continue
                                else:
                                    # skip
                                    break

                            if not ref_result.should_retry or not ref_result.modified_plan:
                                break

                            # Retry execution with modified plan
                            current_plan = ref_result.modified_plan

                            # ── Escalation Point 3: Token budget exceeded ──
                            if (self.config.enable_human_escalation
                                    and task_token_count > self.config.escalation_token_budget):
                                _emit(on_activity, "orchestrator", "escalation",
                                      f"Task {task_node.id}: token budget exceeded ({task_token_count} tokens)", "warning")
                                esc_answers = self._escalate_to_human(
                                    ask_fn, task_node,
                                    reason=f"Token budget exceeded ({task_token_count} tokens used, budget: {self.config.escalation_token_budget})",
                                    context=reflect_context,
                                )
                                esc_action, esc_hint = self._parse_escalation_response(esc_answers, task_node.id)
                                state.escalations.append({
                                    "task_id": task_node.id,
                                    "trigger": "token_budget",
                                    "reason": f"Token budget exceeded: {task_token_count}/{self.config.escalation_token_budget}",
                                    "action": esc_action,
                                    "hint": esc_hint,
                                })
                                self._save_state(state, output_dir, on_state)
                                if esc_action == "abort":
                                    _emit(on_activity, "orchestrator", "abort", "Human chose to abort pipeline", "error")
                                    if _token_hook_installed:
                                        logging_backend._on_log = _original_on_log
                                    return state
                                elif esc_action == "skip":
                                    break
                                elif esc_action == "retry" and esc_hint:
                                    project_context = _build_project_context(
                                        state.spec, project_dir,
                                        completed_tasks=state.completed_tasks,
                                    )
                                    project_context += f"\n\nHuman guidance: {esc_hint}"

                            _set_agent("executor")
                            _emit(on_activity, "executor", "mode_change",
                                  f"Retrying with modified plan (attempt {retry_num + 1})")

                            # Refresh context for retry
                            project_context = _build_project_context(
                                state.spec, project_dir,
                                completed_tasks=state.completed_tasks,
                            )

                            retry_result = executor.execute(
                                current_plan,
                                project_dir=project_dir,
                                project_file_context=project_context,
                            )
                            state.execution_results.append(retry_result.to_dict())

                            # Re-verify after retry
                            verify_result = verify_project(project_dir, timeout=10)
                            state.verification_results.append(verify_result.to_dict())

                            if retry_result.success and verify_result.success:
                                exec_result = retry_result
                                exec_dict = exec_result.to_dict()
                                _emit(on_activity, "executor", "completed", "Retry succeeded", "success")
                                _emit(on_activity, "executor", "verified", "Verification passed", "success")
                                break
                            else:
                                exec_dict = retry_result.to_dict()
                                if not verify_result.success:
                                    _emit(on_activity, "executor", "verify_failed",
                                          f"Retry verification failed: {verify_result.error_summary[:100]}", "error")
                                else:
                                    _emit(on_activity, "executor", "failed", "Retry execution failed", "error")
                        else:
                            _emit(on_activity, "reflection", "exhausted", "Max reflection iterations reached", "warning")

                            # ── Escalation Point 2: Reflection exhausted ──
                            if self.config.enable_human_escalation:
                                _emit(on_activity, "orchestrator", "escalation",
                                      f"Task {task_node.id}: all reflection retries exhausted", "warning")
                                esc_answers = self._escalate_to_human(
                                    ask_fn, task_node,
                                    reason="All reflection retries exhausted without success",
                                    context=project_context,
                                )
                                esc_action, esc_hint = self._parse_escalation_response(esc_answers, task_node.id)
                                state.escalations.append({
                                    "task_id": task_node.id,
                                    "trigger": "reflection_exhausted",
                                    "reason": "All reflection retries exhausted",
                                    "action": esc_action,
                                    "hint": esc_hint,
                                })
                                self._save_state(state, output_dir, on_state)
                                if esc_action == "abort":
                                    _emit(on_activity, "orchestrator", "abort", "Human chose to abort pipeline", "error")
                                    if _token_hook_installed:
                                        logging_backend._on_log = _original_on_log
                                    return state
                                elif esc_action == "retry" and esc_hint:
                                    # One more attempt with human hint
                                    _emit(on_activity, "executor", "mode_change",
                                          f"Retrying with human guidance for task {task_node.id}")
                                    hint_context = _build_project_context(
                                        state.spec, project_dir,
                                        completed_tasks=state.completed_tasks,
                                    )
                                    hint_context += f"\n\nHuman guidance: {esc_hint}"
                                    retry_result = executor.execute(
                                        current_plan,
                                        project_dir=project_dir,
                                        project_file_context=hint_context,
                                    )
                                    state.execution_results.append(retry_result.to_dict())
                                    verify_result = verify_project(project_dir, timeout=10)
                                    state.verification_results.append(verify_result.to_dict())
                                    if retry_result.success and verify_result.success:
                                        exec_result = retry_result
                                        exec_dict = exec_result.to_dict()
                                        _emit(on_activity, "executor", "completed", "Human-guided retry succeeded", "success")
                                    # else: falls through to normal failure handling

                        # Restore original logging hook
                        if _token_hook_installed:
                            logging_backend._on_log = _original_on_log

                    # ── Mode 6: Skill Learning ────────────────────────
                    if exec_result.success and not self.config.skip_skill_learning:
                        state.current_mode = Mode.SKILL_LEARNING.value
                        self._save_state(state, output_dir, on_state)
                        _set_agent("skill_learning")
                        _emit(on_activity, "skill_learning", "mode_change", "Extracting reusable skills")
                        try:
                            skill = skill_agent.extract_skill(
                                task_description=task_dict.get("description", ""),
                                solution_code=json.dumps(plan_dict.get("steps", [])[:3]),
                                outcome=f"Task '{task_dict.get('title', '')}' completed successfully",
                            )
                            skill_bank.add(skill)
                            state.learned_skills.append(skill.to_dict())
                            _emit(on_activity, "skill_learning", "completed", f"Learned: {skill.name}", "success")
                            _emit(on_activity, "skill_learning", "output",
                                  f"Skill: {skill.name}\nDescription: {skill.description}\nPattern: {skill.pattern}", "info")
                        except Exception:
                            _emit(on_activity, "skill_learning", "failed", "Skill extraction failed (non-fatal)", "warning")

                    # Track completion
                    if exec_result.success:
                        task_graph.mark_completed(task_node.id)
                        state.completed_tasks.append(task_node.id)
                        _emit(on_activity, "orchestrator", "task_done", f"Task {task_node.id} completed", "success")
                    else:
                        task_graph.mark_failed(task_node.id)
                        state.failed_tasks.append(task_node.id)
                        _emit(on_activity, "orchestrator", "task_done", f"Task {task_node.id} failed", "error")

                except Exception as e:
                    # Per-task error handling: mark failed, save state, continue
                    _emit(on_activity, "orchestrator", "error",
                          f"Task {task_node.id} failed with error: {e}", "error")
                    task_graph.mark_failed(task_node.id)
                    state.failed_tasks.append(task_node.id)
                    self._save_state(state, output_dir, on_state)

                # Reset reflection for next task
                reflection_agent.reset()

        # Save skill bank
        if state.learned_skills:
            save_skill_bank(skill_bank, skill_bank_path)

        # Update final task graph state
        state.task_graph = task_graph.to_dict()
        self._save_state(state, output_dir, on_state)
        _emit(on_activity, "orchestrator", "pipeline_done",
              f"Done: {len(state.completed_tasks)} completed, {len(state.failed_tasks)} failed", "success")

        return state
