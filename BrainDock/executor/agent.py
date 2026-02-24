"""Executor Agent — executes action plans with budget enforcement."""

from __future__ import annotations

import json

from BrainDock.base_agent import BaseAgent
from BrainDock.llm import LLMBackend
from BrainDock.preambles import build_system_prompt, EXEC_OPS, DEV_OPS
from .models import TaskOutcome, StopCondition, ExecutionResult
from .prompts import (
    SYSTEM_PROMPT,
    EXECUTE_STEP_PROMPT,
    EXECUTE_BATCH_PROMPT,
    EXECUTE_CONTINUATION_PROMPT,
    VERIFY_STEP_PROMPT,
)
from .sandbox import run_sandboxed, write_file_safe, read_file_safe


class _ExecutionSession:
    """Tracks accumulated context across batches within a task."""

    def __init__(self, session_token_limit: int = 8000):
        self._entries: list[str] = []
        self._char_count: int = 0
        self._limit = session_token_limit
        self._compressed_summary: str = ""

    def add_outcome(self, step_id: str, action_type: str, success: bool, output_snippet: str):
        entry = f"[{step_id}] {action_type} \u2192 {'OK' if success else 'FAIL'}: {output_snippet[:200]}"
        self._entries.append(entry)
        self._char_count += len(entry)

    def needs_compression(self) -> bool:
        return self._char_count > self._limit

    def compress(self):
        """Keep last 3 entries verbatim, summarize older ones."""
        if len(self._entries) <= 3:
            return
        old_entries = self._entries[:-3]
        summary = (
            f"[Completed {len(old_entries)} earlier steps: "
            + ", ".join(e.split("]")[0].strip("[") for e in old_entries)
            + "]"
        )
        self._compressed_summary = summary
        self._entries = self._entries[-3:]
        self._char_count = len(summary) + sum(len(e) for e in self._entries)

    def get_transcript(self) -> str:
        parts = []
        if self._compressed_summary:
            parts.append(self._compressed_summary)
        parts.extend(self._entries)
        return "\n".join(parts)

    @property
    def is_empty(self) -> bool:
        return not self._entries and not self._compressed_summary


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
        return self._apply_action(data, project_dir, step.get("id", ""))

    def _apply_action(self, data: dict, project_dir: str, step_id: str = "") -> TaskOutcome:
        """Apply a single action dict (from LLM response) to the filesystem."""
        action_type = data.get("action_type", "")
        file_path = data.get("file_path", "")
        content = data.get("content", "")
        affected_file = ""

        if action_type == "write_file" and file_path:
            success, output = write_file_safe(file_path, content, project_dir)
            if success:
                affected_file = file_path
        elif action_type == "edit_file" and file_path:
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
            step_id=data.get("step_id", step_id),
            success=success,
            output=output[:2000],
            error="" if success else output[:500],
            affected_file=affected_file,
        )

    def _build_edit_file_context(self, steps: list[dict], project_dir: str) -> str:
        """Build edit_file context for all edit_file steps in a batch."""
        parts = []
        for step in steps:
            if step.get("tool") != "edit_file":
                continue
            target_path = step.get("file_path", "") or step.get("description", "")
            if not step.get("file_path"):
                for word in step.get("description", "").split():
                    if "/" in word or word.endswith((".py", ".js", ".ts", ".json", ".html", ".css")):
                        target_path = word.strip("'\"`,;:")
                        break
            if target_path:
                content = read_file_safe(target_path, project_dir)
                if content is not None:
                    parts.append(
                        f"Current content of {target_path}:\n"
                        f"---\n{content[:6000]}\n---"
                    )
        return "\n\n".join(parts)

    def _make_batches(self, steps: list[dict], batch_size: int) -> list[list[dict]]:
        """Group steps into batches. run_command/test steps terminate a batch."""
        batches: list[list[dict]] = []
        current: list[dict] = []
        for step in steps:
            current.append(step)
            tool = step.get("tool", "")
            if tool in ("run_command", "test") or len(current) >= batch_size:
                batches.append(current)
                current = []
        if current:
            batches.append(current)
        return batches

    def _execute_batch(
        self,
        steps: list[dict],
        project_dir: str,
        session: _ExecutionSession,
        project_file_context: str,
        user_guidance: str = "",
    ) -> list[TaskOutcome]:
        """Execute a batch of steps with one LLM call."""
        edit_ctx = self._build_edit_file_context(steps, project_dir)

        if session.is_empty:
            prompt = EXECUTE_BATCH_PROMPT.format(
                steps_json=json.dumps(steps, indent=2),
                project_dir=project_dir,
                project_file_context=project_file_context or "(no files yet)",
                edit_file_context=edit_ctx,
            )
        else:
            prompt = EXECUTE_CONTINUATION_PROMPT.format(
                transcript=session.get_transcript(),
                steps_json=json.dumps(steps, indent=2),
                project_dir=project_dir,
                edit_file_context=edit_ctx,
            )

        if user_guidance:
            prompt += (
                "\n\nIMPORTANT — User guidance received during execution:\n"
                "---\n" + user_guidance + "\n---\n"
                "Incorporate this guidance into your implementation."
            )

        actions = self._llm_query_json_list(self._sys_prompt, prompt)

        outcomes: list[TaskOutcome] = []
        for i, step in enumerate(steps):
            if i < len(actions):
                action_data = actions[i]
            else:
                action_data = {
                    "action_type": "skip",
                    "step_id": step.get("id", ""),
                    "content": "(no action returned by LLM)",
                }
            outcome = self._apply_action(action_data, project_dir, step.get("id", ""))
            outcomes.append(outcome)
            session.add_outcome(
                step.get("id", ""),
                action_data.get("action_type", ""),
                outcome.success,
                outcome.output,
            )

        if user_guidance:
            session.add_outcome("_guidance", "user_message", True, user_guidance)

        if session.needs_compression():
            session.compress()

        return outcomes

    def execute(
        self,
        plan: dict,
        project_dir: str = ".",
        project_file_context: str = "",
        check_guidance: "Callable[[], list[str]] | None" = None,
    ) -> ExecutionResult:
        """Execute all steps in an action plan.

        Args:
            plan: ActionPlan as a dict (from ActionPlan.to_dict()).
            project_dir: Project root directory.
            project_file_context: Context string describing existing project files.
            check_guidance: Optional callback returning pending user guidance messages.

        Returns:
            ExecutionResult with overall success and per-step outcomes.
        """
        steps = plan.get("steps", [])
        task_id = plan.get("task_id", "")

        batches = self._make_batches(steps, self.stop_condition.batch_size)
        session = _ExecutionSession(self.stop_condition.session_token_limit)

        outcomes: list[TaskOutcome] = []
        failure_count = 0
        generated_files: list[str] = []
        steps_done = 0

        for batch in batches:
            if steps_done >= self.stop_condition.max_steps:
                return ExecutionResult(
                    task_id=task_id,
                    success=False,
                    outcomes=outcomes,
                    steps_completed=steps_done,
                    steps_total=len(steps),
                    failure_count=failure_count,
                    stop_reason=f"Max steps ({self.stop_condition.max_steps}) reached",
                    generated_files=generated_files,
                )

            if failure_count >= self.stop_condition.max_failures:
                return ExecutionResult(
                    task_id=task_id,
                    success=False,
                    outcomes=outcomes,
                    steps_completed=steps_done,
                    steps_total=len(steps),
                    failure_count=failure_count,
                    stop_reason=f"Max failures ({self.stop_condition.max_failures}) reached",
                    generated_files=generated_files,
                )

            # Drain pending user guidance at each batch checkpoint
            user_guidance = ""
            if check_guidance:
                messages = check_guidance()
                if messages:
                    user_guidance = "\n".join(f"- {m}" for m in messages)

            batch_outcomes = self._execute_batch(
                batch, project_dir, session, project_file_context,
                user_guidance=user_guidance,
            )

            for outcome in batch_outcomes:
                outcomes.append(outcome)
                steps_done += 1
                if outcome.affected_file and outcome.affected_file not in generated_files:
                    generated_files.append(outcome.affected_file)
                if not outcome.success:
                    failure_count += 1
                if failure_count >= self.stop_condition.max_failures:
                    break
                if steps_done >= self.stop_condition.max_steps:
                    break

        all_success = failure_count == 0
        return ExecutionResult(
            task_id=task_id,
            success=all_success,
            outcomes=outcomes,
            steps_completed=steps_done,
            steps_total=len(steps),
            failure_count=failure_count,
            stop_reason="" if all_success else "Some steps failed",
            generated_files=generated_files,
        )
