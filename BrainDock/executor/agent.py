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
    RETRY_VALIDATION_PROMPT,
    VERIFY_STEP_PROMPT,
)
from .sandbox import run_sandboxed, write_file_safe, read_file_safe, _looks_like_description, _looks_like_shell_command


class _ExecutionSession:
    """Tracks accumulated context across batches within a task."""

    def __init__(self, session_token_limit: int = 8000):
        self._entries: list[str] = []
        self._char_count: int = 0
        self._limit = session_token_limit
        self._compressed_summary: str = ""
        # Track files modified during this task for context diff mode
        self._modified_files: set[str] = set()

    def record_modified_file(self, file_path: str) -> None:
        """Record that a file was written/modified in this session."""
        if file_path:
            self._modified_files.add(file_path)

    @property
    def modified_files(self) -> set[str]:
        return self._modified_files

    def add_outcome(self, step_id: str, action_type: str, success: bool, output_snippet: str):
        # Truncate output aggressively — successful steps need minimal context,
        # only failed steps need enough detail for debugging
        max_snippet = 50 if success else 150
        status = "OK" if success else "FAIL"
        entry = f"[{step_id}] {action_type} -> {status}: {output_snippet[:max_snippet]}"
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
                        f"---\n{content[:4000]}\n---"
                    )

        prompt = EXECUTE_STEP_PROMPT.format(
            step_json=json.dumps(step, indent=2),
            project_dir=project_dir,
            previous_outcomes=prev_str,
            step_id=step.get("id", ""),
            project_file_context=project_file_context or "(no files yet)",
            edit_file_context=edit_file_context,
        )

        try:
            data = self._llm_query_json(self._sys_prompt, prompt)
        except (RuntimeError, ValueError) as e:
            import sys
            print(f"  [Executor] Step LLM call failed: {e}", file=sys.stderr)
            return TaskOutcome(
                step_id=step.get("id", ""),
                success=False,
                output=f"LLM failed to return valid JSON: {e}",
                error=f"LLM failed to return valid JSON: {e}",
            )
        return self._apply_action(data, project_dir, step.get("id", ""))

    @staticmethod
    def _is_validation_error(output: str) -> bool:
        """Check if a failure output is from content validation (not a runtime error)."""
        markers = ("appears to be a natural-language description",
                   "Python syntax error in",
                   "Import validation failed in")
        return any(m in output for m in markers)

    def _apply_action(self, data: dict, project_dir: str, step_id: str = "") -> TaskOutcome:
        """Apply a single action dict (from LLM response) to the filesystem."""
        action_type = data.get("action_type", "")
        file_path = data.get("file_path", "")
        content = data.get("content", "")
        affected_file = ""

        # Handle auto-skip (LLM indicated work was already done)
        if action_type == "skip" or data.get("_auto_skip"):
            return TaskOutcome(
                step_id=data.get("step_id", step_id),
                success=True,
                output=content or "(skipped — already complete)",
            )

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
            # Strip leading/trailing whitespace and remove any markdown fencing
            content = content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:]).strip()
            # Guard against descriptions sneaking in as run_command content
            # but allow actual shell commands through
            if not _looks_like_shell_command(content) and _looks_like_description(content):
                # Check if this is an "already done" response masquerading as run_command
                _lower_content = content[:200].lower()
                _done_markers = ("all", "already", "complete", "pass", "tests pass",
                                 "no changes", "nothing to", "verified")
                if any(_lower_content.startswith(m) or m in _lower_content for m in _done_markers):
                    # Treat as successful skip — the LLM is reporting results, not a command
                    success = True
                    output = f"(auto-skip: LLM reported results instead of command) {content[:200]}"
                else:
                    success = False
                    output = (
                        f"Content for run_command appears to be a natural-language "
                        f"description, not a shell command: {content[:100]!r}"
                    )
            else:
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

    def _retry_step_validation(
        self,
        step: dict,
        action_data: dict,
        validation_error: str,
        project_dir: str,
    ) -> TaskOutcome:
        """Re-query the LLM for a single step that failed content validation."""
        prompt = RETRY_VALIDATION_PROMPT.format(
            validation_error=validation_error,
            step_json=json.dumps(step, indent=2),
            project_dir=project_dir,
            step_id=step.get("id", ""),
            action_type=action_data.get("action_type", "write_file"),
            file_path=action_data.get("file_path", ""),
        )
        try:
            data = self._llm_query_json(self._sys_prompt, prompt)
        except RuntimeError:
            return TaskOutcome(
                step_id=step.get("id", ""),
                success=False,
                output="Retry LLM query failed",
                error="Retry LLM query failed",
            )
        # Handle case where LLM returns a list instead of a dict
        if isinstance(data, list):
            data = data[0] if data else {}
        return self._apply_action(data, project_dir, step.get("id", ""))

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
                        f"---\n{content[:4000]}\n---"
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

    def _build_changed_files_context(
        self,
        steps: list[dict],
        project_dir: str,
        session: _ExecutionSession,
    ) -> str:
        """Build context only for files that changed or are edit targets.

        In continuation batches, instead of re-sending all edit_file contexts,
        only include:
        1. Files modified in previous batches that this batch's steps reference
        2. New edit targets not yet seen
        This dramatically reduces token usage in multi-batch tasks.
        """
        parts = []
        seen_paths: set[str] = set()

        for step in steps:
            target_path = step.get("file_path", "")
            if not target_path and step.get("tool") == "edit_file":
                for word in step.get("description", "").split():
                    if "/" in word or word.endswith((".py", ".js", ".ts", ".json", ".html", ".css")):
                        target_path = word.strip("'\"`,;:")
                        break

            if not target_path or target_path in seen_paths:
                continue
            seen_paths.add(target_path)

            # Only include if: it's an edit target, OR it was modified earlier
            is_edit = step.get("tool") == "edit_file"
            was_modified = target_path in session.modified_files
            if not is_edit and not was_modified:
                continue

            content = read_file_safe(target_path, project_dir)
            if content is not None:
                parts.append(
                    f"Current content of {target_path}:\n"
                    f"---\n{content[:4000]}\n---"
                )

        # Also include a brief summary of other modified files not in this batch
        other_modified = session.modified_files - seen_paths
        if other_modified:
            parts.append(
                f"Other files modified in earlier steps: {', '.join(sorted(other_modified))}"
            )

        return "\n\n".join(parts)

    def _execute_batch(
        self,
        steps: list[dict],
        project_dir: str,
        session: _ExecutionSession,
        project_file_context: str,
        user_guidance: str = "",
    ) -> list[TaskOutcome]:
        """Execute a batch of steps with one LLM call."""
        if session.is_empty:
            edit_ctx = self._build_edit_file_context(steps, project_dir)
            prompt = EXECUTE_BATCH_PROMPT.format(
                steps_json=json.dumps(steps, indent=2),
                project_dir=project_dir,
                project_file_context=project_file_context or "(no files yet)",
                edit_file_context=edit_ctx,
            )
        else:
            # Context diff mode: only send changed/relevant file contents
            edit_ctx = self._build_changed_files_context(steps, project_dir, session)
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

        try:
            actions = self._llm_query_json_list(self._sys_prompt, prompt)
        except (RuntimeError, ValueError) as e:
            # LLM failed to return valid JSON after retries — return failed
            # outcomes for all steps so reflection can handle this gracefully
            # instead of crashing the entire task.
            import sys
            print(f"  [Executor] Batch LLM call failed: {e}", file=sys.stderr)
            return [
                TaskOutcome(
                    step_id=s.get("id", ""),
                    success=False,
                    output=f"LLM failed to return valid JSON: {e}",
                    error=f"LLM failed to return valid JSON: {e}",
                )
                for s in steps
            ]

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

            # Step-level retry: if validation rejected the content, re-query
            # the LLM once with the error feedback
            if not outcome.success and self._is_validation_error(outcome.output):
                retry_outcome = self._retry_step_validation(
                    step, action_data, outcome.output, project_dir,
                )
                if retry_outcome.success:
                    outcome = retry_outcome

            outcomes.append(outcome)
            # Track modified files for context diff mode
            if outcome.affected_file:
                session.record_modified_file(outcome.affected_file)
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
