"""Orchestrator Agent — coordinates the 8-mode pipeline."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

from BrainDock.llm import LLMBackend, ClaudeCLIBackend
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
from BrainDock.executor.models import StopCondition
from BrainDock.skill_bank.agent import SkillLearningAgent
from BrainDock.skill_bank.storage import load_skill_bank, save_skill_bank
from BrainDock.reflection.agent import ReflectionAgent
from BrainDock.debate.agent import DebateAgent
from .models import Mode, PipelineState, RunConfig


class OrchestratorAgent:
    """Main orchestrator that coordinates all 8 modes.

    Pipeline: SPEC → TASK_GRAPH → (for each task: PLAN → CONTROLLER →
    EXECUTE → SKILL_LEARN) with REFLECT on failure and DEBATE on uncertainty.

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

    def _save_state(self, state: PipelineState, output_dir: str) -> None:
        """Write pipeline state to JSON for dashboard consumption."""
        state_path = os.path.join(output_dir, "pipeline_state.json")
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        with open(state_path, "w") as f:
            json.dump(state.to_dict(), f, indent=2, default=str)

    def run(
        self,
        problem: str,
        ask_fn: Callable[[list[Question], list[Decision], str], dict[str, str]],
    ) -> PipelineState:
        """Run the full pipeline from problem statement to execution.

        Args:
            problem: The problem statement.
            ask_fn: Callback for user interaction (from spec_agent).

        Returns:
            PipelineState with all intermediate results.
        """
        state = PipelineState()
        output_dir = self.config.output_dir

        # ── Mode 1: Specification ──────────────────────────────────
        state.current_mode = Mode.SPECIFICATION.value
        self._save_state(state, output_dir)
        spec_agent = SpecAgent(problem=problem, llm=self.llm)
        project_spec = spec_agent.run(ask_fn=ask_fn)
        state.spec = project_spec.to_dict()

        spec_dir = os.path.join(output_dir, "spec_agent")
        save_spec_output(project_spec, output_dir=spec_dir)

        # ── Mode 2: Task Graph ─────────────────────────────────────
        state.current_mode = Mode.TASK_GRAPH.value
        self._save_state(state, output_dir)
        tg_agent = TaskGraphAgent(llm=self.llm)
        task_graph = tg_agent.decompose(state.spec)
        state.task_graph = task_graph.to_dict()

        tg_dir = os.path.join(output_dir, "task_graph")
        save_task_graph(task_graph, output_dir=tg_dir)

        if self.config.skip_execution:
            return state

        # ── Load skill bank ────────────────────────────────────────
        skill_bank_path = os.path.join(output_dir, "skill_bank", "skills.json")
        skill_bank = load_skill_bank(skill_bank_path)

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
            llm=self.llm,
            entropy_threshold=self.config.max_entropy,
        )
        executor = ExecutorAgent(llm=self.llm)
        reflection_agent = ReflectionAgent(
            llm=self.llm,
            max_iterations=self.config.max_reflection_iterations,
        )
        debate_agent = DebateAgent(
            llm=self.llm,
            max_rounds=self.config.max_debate_rounds,
        )
        skill_agent = SkillLearningAgent(llm=self.llm)

        groups = task_graph.get_parallel_groups()
        project_context = f"Project: {state.spec.get('title', 'Unknown')}"

        for group in groups:
            for task_node in group:
                task_dict = task_node.to_dict()

                # ── Mode 3: Planning ───────────────────────────────
                state.current_mode = Mode.PLANNING.value
                self._save_state(state, output_dir)
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

                # ── Mode 4: Controller (plan gate) ─────────────────
                state.current_mode = Mode.CONTROLLER.value
                self._save_state(state, output_dir)
                gate_result = controller.check_plan_gate(plan_dict)

                # ── Mode 8: Debate (if entropy too high) ───────────
                if gate_result.action == "debate":
                    debate_gate = controller.check_debate_gate()
                    if debate_gate.passed:
                        state.current_mode = Mode.DEBATE.value
                        self._save_state(state, output_dir)
                        controller.state.record_debate()
                        outcome = debate_agent.debate(plan_dict, context=project_context)
                        state.debates.append(outcome.to_dict())
                        if outcome.improved_plan:
                            plan_dict = outcome.improved_plan

                # ── Mode 5: Execution ──────────────────────────────
                state.current_mode = Mode.EXECUTION.value
                self._save_state(state, output_dir)
                project_dir = os.path.join(output_dir, "project")
                Path(project_dir).mkdir(parents=True, exist_ok=True)

                exec_result = executor.execute(plan_dict, project_dir=project_dir)
                exec_dict = exec_result.to_dict()
                state.execution_results.append(exec_dict)

                # ── Mode 4: Controller (execution gate) ────────────
                state.current_mode = Mode.CONTROLLER.value
                self._save_state(state, output_dir)
                exec_gate = controller.check_execution_gate(exec_dict)

                # ── Mode 7: Reflection (if execution failed) ───────
                if exec_gate.action == "reflect":
                    ref_gate = controller.check_reflection_gate()
                    if ref_gate.passed:
                        state.current_mode = Mode.REFLECTION.value
                        self._save_state(state, output_dir)
                        controller.state.record_reflection()
                        ref_result = reflection_agent.reflect(
                            exec_dict, plan_dict, context=project_context
                        )
                        state.reflections.append(ref_result.to_dict())

                        if ref_result.should_retry and ref_result.modified_plan:
                            # Retry with modified plan
                            retry_result = executor.execute(
                                ref_result.modified_plan, project_dir=project_dir
                            )
                            state.execution_results.append(retry_result.to_dict())
                            if retry_result.success:
                                exec_result = retry_result

                # ── Mode 6: Skill Learning ─────────────────────────
                if exec_result.success and not self.config.skip_skill_learning:
                    state.current_mode = Mode.SKILL_LEARNING.value
                    self._save_state(state, output_dir)
                    try:
                        skill = skill_agent.extract_skill(
                            task_description=task_dict.get("description", ""),
                            solution_code=json.dumps(plan_dict.get("steps", [])[:3]),
                            outcome=f"Task '{task_dict.get('title', '')}' completed successfully",
                        )
                        skill_bank.add(skill)
                        state.learned_skills.append(skill.to_dict())
                    except Exception:
                        pass  # Skill learning is best-effort

                # Track completion
                if exec_result.success:
                    task_graph.mark_completed(task_node.id)
                    state.completed_tasks.append(task_node.id)
                else:
                    task_graph.mark_failed(task_node.id)
                    state.failed_tasks.append(task_node.id)

                # Reset reflection for next task
                reflection_agent.reset()

        # Save skill bank
        if state.learned_skills:
            save_skill_bank(skill_bank, skill_bank_path)

        # Update final task graph state
        state.task_graph = task_graph.to_dict()
        self._save_state(state, output_dir)

        return state
