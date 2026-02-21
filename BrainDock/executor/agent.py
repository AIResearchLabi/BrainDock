"""Executor Agent — executes action plans with budget enforcement."""

from __future__ import annotations

import json

from BrainDock.base_agent import BaseAgent
from BrainDock.llm import LLMBackend
from BrainDock.preambles import build_system_prompt, EXEC_OPS, DEV_OPS
from .models import TaskOutcome, StopCondition, ExecutionResult
from .prompts import SYSTEM_PROMPT, EXECUTE_STEP_PROMPT, VERIFY_STEP_PROMPT
from .sandbox import run_sandboxed, write_file_safe, read_file_safe


class ExecutorAgent(BaseAgent):
    """Agent that executes action plans step by step with budget enforcement.

    Usage:
        agent = ExecutorAgent(llm=my_backend)
        result = agent.execute(plan_dict, project_dir="/path/to/project")
    """

    def __init__(
        self,
        llm: LLMBackend | None = None,
        stop_condition: StopCondition | None = None,
    ):
        super().__init__(llm=llm)
        self.stop_condition = stop_condition or StopCondition()
        self._sys_prompt = build_system_prompt(SYSTEM_PROMPT, EXEC_OPS, DEV_OPS)

    def execute_step(
        self,
        step: dict,
        project_dir: str,
        previous_outcomes: list[dict],
        project_file_context: str = "",
    ) -> TaskOutcome:
        """Execute a single action step.

        Args:
            step: ActionStep as a dict.
            project_dir: Project root directory.
            previous_outcomes: List of previous step outcome dicts.
            project_file_context: Context string describing existing project files.

        Returns:
            TaskOutcome with success status and output.
        """
        prev_str = json.dumps(previous_outcomes[-3:], indent=2) if previous_outcomes else "(none)"

        # Build edit_file context if this step's tool is edit_file
        edit_file_context = ""
        step_tool = step.get("tool", "")
        if step_tool == "edit_file":
            # Try to find the target file path from the step
            target_path = step.get("file_path", "") or step.get("description", "")
            # Look for file paths in description if not explicit
            if not step.get("file_path"):
                for word in step.get("description", "").split():
                    if "/" in word or word.endswith((".py", ".js", ".ts", ".json", ".html", ".css")):
                        target_path = word.strip("'\"`,;:")
                        break
            if target_path:
                content = read_file_safe(target_path, project_dir)
                if content is not None:
                    edit_file_context = (
                        f"Current content of {target_path}:\n"
                        f"---\n{content[:6000]}\n---"
                    )

        prompt = EXECUTE_STEP_PROMPT.format(
            step_json=json.dumps(step, indent=2),
            project_dir=project_dir,
            previous_outcomes=prev_str,
            step_id=step.get("id", ""),
            project_file_context=project_file_context or "(no files yet)",
            edit_file_context=edit_file_context,
        )

        data = self._llm_query_json(self._sys_prompt, prompt)
        action_type = data.get("action_type", "")
        file_path = data.get("file_path", "")
        content = data.get("content", "")
        affected_file = ""

        if action_type == "write_file" and file_path:
            success, output = write_file_safe(file_path, content, project_dir)
            if success:
                affected_file = file_path
        elif action_type == "edit_file" and file_path:
            # edit_file now writes the full new content via write_file_safe
            success, output = write_file_safe(file_path, content, project_dir)
            if success:
                affected_file = file_path
        elif action_type == "create_dir" and file_path:
            success, output = write_file_safe(
                file_path + "/.gitkeep", "", project_dir
            )
        elif action_type in ("run_command", "test") and content:
            success, output = run_sandboxed(
                content, cwd=project_dir,
                timeout=self.stop_condition.timeout_seconds,
            )
        else:
            success = True
            output = content or "(no output)"

        return TaskOutcome(
            step_id=step.get("id", ""),
            success=success,
            output=output[:2000],  # Truncate long outputs
            error="" if success else output[:500],
            affected_file=affected_file,
        )

    def execute(
        self,
        plan: dict,
        project_dir: str = ".",
        project_file_context: str = "",
    ) -> ExecutionResult:
        """Execute all steps in an action plan.

        Args:
            plan: ActionPlan as a dict (from ActionPlan.to_dict()).
            project_dir: Project root directory.
            project_file_context: Context string describing existing project files.

        Returns:
            ExecutionResult with overall success and per-step outcomes.
        """
        steps = plan.get("steps", [])
        task_id = plan.get("task_id", "")

        outcomes: list[TaskOutcome] = []
        failure_count = 0
        generated_files: list[str] = []

        for i, step in enumerate(steps):
            # Budget enforcement
            if i >= self.stop_condition.max_steps:
                return ExecutionResult(
                    task_id=task_id,
                    success=False,
                    outcomes=outcomes,
                    steps_completed=i,
                    steps_total=len(steps),
                    failure_count=failure_count,
                    stop_reason=f"Max steps ({self.stop_condition.max_steps}) reached",
                )

            if failure_count >= self.stop_condition.max_failures:
                return ExecutionResult(
                    task_id=task_id,
                    success=False,
                    outcomes=outcomes,
                    steps_completed=i,
                    steps_total=len(steps),
                    failure_count=failure_count,
                    stop_reason=f"Max failures ({self.stop_condition.max_failures}) reached",
                )

            outcome = self.execute_step(
                step,
                project_dir=project_dir,
                previous_outcomes=[o.to_dict() for o in outcomes],
                project_file_context=project_file_context,
            )
            outcomes.append(outcome)

            if outcome.affected_file and outcome.affected_file not in generated_files:
                generated_files.append(outcome.affected_file)

            if not outcome.success:
                failure_count += 1

        all_success = failure_count == 0
        return ExecutionResult(
            task_id=task_id,
            success=all_success,
            outcomes=outcomes,
            steps_completed=len(steps),
            steps_total=len(steps),
            failure_count=failure_count,
            stop_reason="" if all_success else "Some steps failed",
            generated_files=generated_files,
        )
