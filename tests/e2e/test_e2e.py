"""End-to-end tests for the BrainDock pipeline.

Each test wires a SequencedLLM through the full OrchestratorAgent.run(),
exercising different pipeline paths without any real LLM calls.
"""

import json
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from BrainDock.orchestrator.agent import OrchestratorAgent
from BrainDock.orchestrator.models import RunConfig, PipelineState

from tests.e2e.mock_responses import (
    make_spec_responses,
    make_task_graph,
    make_plan,
    make_exec_batch,
    make_exec_write,
    make_exec_fail,
    make_reflection,
    make_debate_responses,
    make_market_study,
    make_skill,
    make_skill_match,
    make_sequenced_llm,
)


def _noop_ask_fn(questions, decisions, understanding):
    """Default ask_fn: no user questions expected, return empty answers."""
    return {}


# ── 1. Happy Path ─────────────────────────────────────────────────────

class TestE2EHappyPath(unittest.TestCase):
    """Full pipeline: 1 task, all gates pass, skill learned."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_full_pipeline_produces_complete_state(self):
        # LLM call sequence:
        #   spec_analyze, spec_generate (refine skipped when no questions),
        #   task_graph,
        #   plan (confidence=0.9),
        #   execute (write main.py with valid content),
        #   skill_extract
        llm = make_sequenced_llm([
            *make_spec_responses(),
            make_task_graph(),
            make_plan(),
            make_exec_batch(),       # writes main.py → verify passes
            make_skill(),
        ])

        config = RunConfig(output_dir=self._tmpdir)
        orchestrator = OrchestratorAgent(llm=llm.backend, config=config)
        state = orchestrator.run(problem="Build a CLI calculator", ask_fn=_noop_ask_fn)

        # Spec generated
        self.assertEqual(state.spec["title"], "PyCalc")

        # Task graph generated
        self.assertEqual(len(state.task_graph["tasks"]), 1)

        # Plan created
        self.assertEqual(len(state.plans), 1)
        self.assertEqual(state.plans[0]["task_id"], "t1")

        # Execution succeeded
        self.assertGreater(len(state.execution_results), 0)
        self.assertTrue(state.execution_results[0]["success"])

        # Task completed
        self.assertEqual(state.completed_tasks, ["t1"])
        self.assertEqual(state.failed_tasks, [])

        # Skill learned
        self.assertEqual(len(state.learned_skills), 1)
        self.assertEqual(state.learned_skills[0]["name"], "Expression Evaluation")

        # No reflections or debates needed
        self.assertEqual(state.reflections, [])
        self.assertEqual(state.debates, [])

        # Pipeline state persisted to disk
        project_dir = os.path.join(self._tmpdir, "build-a-cli-calculator")
        state_path = os.path.join(project_dir, "pipeline_state.json")
        self.assertTrue(os.path.exists(state_path))

        # main.py was written to project/
        main_path = os.path.join(project_dir, "project", "main.py")
        self.assertTrue(os.path.exists(main_path))

    def test_verification_runs(self):
        """Verification auto-runs after execution; verify results stored."""
        llm = make_sequenced_llm([
            *make_spec_responses(),
            make_task_graph(),
            make_plan(),
            make_exec_batch(),
            make_skill(),
        ])

        config = RunConfig(output_dir=self._tmpdir)
        orchestrator = OrchestratorAgent(llm=llm.backend, config=config)
        state = orchestrator.run(problem="Build a CLI calculator", ask_fn=_noop_ask_fn)

        self.assertGreater(len(state.verification_results), 0)
        self.assertTrue(state.verification_results[0]["success"])


# ── 2. Reflection Retry Success ───────────────────────────────────────

class TestE2EReflectionRetrySuccess(unittest.TestCase):
    """Execution fails → reflect → retry with modified plan → success."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_reflection_produces_successful_retry(self):
        # Modified plan that the reflection agent produces — writes main.py
        fixed_plan = {
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

        llm = make_sequenced_llm([
            *make_spec_responses(),                          # 0-2: spec
            make_task_graph(),                               # 3: task graph
            make_plan(),                                     # 4: plan
            make_exec_fail(),                                # 5: execute → fails
            make_reflection(                                 # 6: reflect → retry
                should_retry=True,
                modified_plan=fixed_plan,
            ),
            make_exec_batch([{                               # 7: retry → writes main.py
                "step_id": "s1_fix",
                "action_type": "write_file",
                "file_path": "main.py",
                "content": "print('hello')\n",
                "verification": "File exists",
            }]),
            make_skill(),                                    # 8: skill (retry succeeded)
        ])

        config = RunConfig(output_dir=self._tmpdir)
        orchestrator = OrchestratorAgent(llm=llm.backend, config=config)
        state = orchestrator.run(problem="Build a CLI calculator", ask_fn=_noop_ask_fn)

        # Task completed on retry
        self.assertEqual(state.completed_tasks, ["t1"])
        self.assertEqual(state.failed_tasks, [])

        # Should have 2 execution results (fail + retry success)
        self.assertGreaterEqual(len(state.execution_results), 2)

        # Should have 1 reflection
        self.assertEqual(len(state.reflections), 1)
        self.assertTrue(state.reflections[0]["should_retry"])

        # No escalations
        self.assertEqual(state.escalations, [])


# ── 3. Reflection Exhausted → Escalation ──────────────────────────────

class TestE2EReflectionExhausted(unittest.TestCase):
    """All reflection retries fail → human escalation → skip."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_exhausted_reflections_trigger_escalation(self):
        # Plan whose steps always fail, reflection always retries with
        # another failing plan. After max_reflection_iterations (2) we
        # expect escalation.

        # Both the original and modified plans use run_command "exit 1"
        failing_plan = {
            "task_id": "t1",
            "task_title": "Create calculator module",
            "steps": [{
                "id": "s1_retry",
                "action": "Still fails",
                "description": "Run a failing command",
                "tool": "run_command",
                "expected_output": "",
            }],
            "metrics": {"confidence": 0.9, "entropy": 0.1,
                        "estimated_steps": 1, "complexity": "low"},
            "relevant_skills": [],
            "assumptions": [],
        }

        llm = make_sequenced_llm([
            *make_spec_responses(),                          # 0-2: spec
            make_task_graph(),                               # 3: task graph
            make_plan(steps=[{                               # 4: plan with run_command
                "id": "s1",
                "action": "Run failing",
                "description": "Run a failing command",
                "tool": "run_command",
                "expected_output": "",
            }]),
            make_exec_fail("s1"),                            # 5: exec fails
            # Reflection iteration 1
            make_reflection(                                 # 6: reflect → retry
                should_retry=True,
                modified_plan=failing_plan,
            ),
            make_exec_fail("s1_retry"),                      # 7: retry 1 fails
            # Reflection iteration 2
            make_reflection(                                 # 8: reflect → retry again
                should_retry=True,
                modified_plan=failing_plan,
            ),
            make_exec_fail("s1_retry"),                      # 9: retry 2 fails
            # ReflectionAgent internal iteration limit hit (iteration 3 > max 2)
            # → returns should_retry=False automatically from the agent itself
            # But the orchestrator for-loop exhausts at max_reflection_iterations=2
            # and the else branch fires → escalation
        ])

        escalation_calls = []

        def ask_fn_skip(questions, decisions, understanding):
            escalation_calls.append({
                "questions": [q.id if hasattr(q, "id") else q.get("id") for q in questions],
                "understanding": understanding,
            })
            return {"escalation_action": "skip", "escalation_hint": ""}

        config = RunConfig(
            output_dir=self._tmpdir,
            max_reflection_iterations=2,
            enable_human_escalation=True,
        )
        orchestrator = OrchestratorAgent(llm=llm.backend, config=config)
        state = orchestrator.run(problem="Build a CLI calculator", ask_fn=ask_fn_skip)

        # Task failed
        self.assertIn("t1", state.failed_tasks)
        self.assertNotIn("t1", state.completed_tasks)

        # Escalation occurred
        self.assertGreater(len(state.escalations), 0)
        found = any(e.get("trigger") == "reflection_exhausted" for e in state.escalations)
        self.assertTrue(found, f"Expected reflection_exhausted escalation, got: {state.escalations}")

        # Human was asked
        self.assertGreater(len(escalation_calls), 0)


# ── 4. Debate Path ───────────────────────────────────────────────────

class TestE2EDebatePath(unittest.TestCase):
    """High-entropy plan triggers debate → improved plan → execution."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_high_entropy_triggers_debate_and_improved_plan(self):
        llm = make_sequenced_llm([
            *make_spec_responses(),                          # 0-2: spec
            make_task_graph(),                               # 3: task graph
            make_plan(confidence=0.9, entropy=0.9),          # 4: plan with high entropy (> 0.85 threshold)
            *make_debate_responses(),                        # 5-7: propose, critique, synthesize
            make_exec_batch([{                               # 8: execute improved plan
                "step_id": "s1_debated",
                "action_type": "write_file",
                "file_path": "main.py",
                "content": "print('safe calc')\n",
                "verification": "File exists",
            }]),
            make_skill("skill_debate_resolved"),             # 9: skill extraction
        ])

        config = RunConfig(output_dir=self._tmpdir)
        orchestrator = OrchestratorAgent(llm=llm.backend, config=config)
        state = orchestrator.run(problem="Build a CLI calculator", ask_fn=_noop_ask_fn)

        # Task completed
        self.assertEqual(state.completed_tasks, ["t1"])
        self.assertEqual(state.failed_tasks, [])

        # Debate happened
        self.assertEqual(len(state.debates), 1)
        self.assertIn("improved_plan", state.debates[0])
        self.assertTrue(state.debates[0]["improved_plan"])

        # No reflections needed
        self.assertEqual(state.reflections, [])


# ── 5. Multiple Tasks with Dependencies ──────────────────────────────

class TestE2EMultipleTasks(unittest.TestCase):
    """Two tasks where t2 depends on t1; both succeed."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_two_tasks_in_dependency_order(self):
        tasks = [
            {
                "id": "t1",
                "title": "Create core module",
                "description": "Core logic",
                "depends_on": [],
                "estimated_effort": "small",
                "tags": [],
                "risks": [],
            },
            {
                "id": "t2",
                "title": "Create CLI wrapper",
                "description": "Wraps core in CLI",
                "depends_on": ["t1"],
                "estimated_effort": "small",
                "tags": [],
                "risks": [],
            },
        ]

        llm = make_sequenced_llm([
            *make_spec_responses(),                          # 0-2: spec
            make_task_graph(tasks=tasks),                    # 3: task graph with 2 tasks
            # Task t1
            make_plan(task_id="t1", task_title="Create core module"),  # 4: plan t1
            make_exec_batch([{                               # 5: execute t1
                "step_id": "s1",
                "action_type": "write_file",
                "file_path": "core.py",
                "content": "def calc(x): return eval(x)\n",
                "verification": "",
            }]),
            make_skill("skill_core"),                        # 6: skill t1
            # Task t2 (skill matching is now heuristic, no LLM call)
            make_plan(task_id="t2", task_title="Create CLI wrapper"),  # 7: plan t2
            make_exec_batch([{                               # 8: execute t2
                "step_id": "s1",
                "action_type": "write_file",
                "file_path": "main.py",
                "content": "from core import calc\nprint(calc('1+1'))\n",
                "verification": "",
            }]),
            make_skill("skill_cli"),                         # 9: skill t2
        ])

        config = RunConfig(output_dir=self._tmpdir)
        orchestrator = OrchestratorAgent(llm=llm.backend, config=config)
        state = orchestrator.run(problem="Build a CLI calculator", ask_fn=_noop_ask_fn)

        # Both tasks completed
        self.assertEqual(state.completed_tasks, ["t1", "t2"])
        self.assertEqual(state.failed_tasks, [])

        # 2 plans, 2 execution results
        self.assertEqual(len(state.plans), 2)
        self.assertEqual(len(state.execution_results), 2)

        # 2 skills learned
        self.assertEqual(len(state.learned_skills), 2)

        # Both files exist
        project_dir = os.path.join(self._tmpdir, "build-a-cli-calculator", "project")
        self.assertTrue(os.path.exists(os.path.join(project_dir, "core.py")))
        self.assertTrue(os.path.exists(os.path.join(project_dir, "main.py")))


# ── 6. Guidance Injection ─────────────────────────────────────────────

class TestE2EGuidanceInjection(unittest.TestCase):
    """User guidance via check_guidance reaches agent prompts."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_guidance_appears_in_planner_prompt(self):
        llm = make_sequenced_llm([
            *make_spec_responses(),
            make_task_graph(),
            make_plan(),
            make_exec_batch(),
            make_skill(),
        ])

        guidance_drained = {"count": 0}

        def mock_guidance():
            guidance_drained["count"] += 1
            # Return guidance on the first drain (before planning)
            if guidance_drained["count"] == 1:
                return ["Use PostgreSQL instead of SQLite"]
            return []

        activities = []

        def on_activity(agent, action, detail="", status="info"):
            activities.append({"agent": agent, "action": action, "detail": detail})

        config = RunConfig(output_dir=self._tmpdir)
        orchestrator = OrchestratorAgent(llm=llm.backend, config=config)
        state = orchestrator.run(
            problem="Build a CLI calculator",
            ask_fn=_noop_ask_fn,
            check_guidance=mock_guidance,
            on_activity=on_activity,
        )

        # Pipeline completed
        self.assertEqual(state.completed_tasks, ["t1"])

        # Guidance callback was called
        self.assertGreater(guidance_drained["count"], 0)

        # Guidance text reached the planner's LLM prompt
        # The planner call is index 3 (after spec[0-1] + task_graph[2])
        planner_prompt = llm.user_prompts[3]
        self.assertIn("PostgreSQL", planner_prompt)

        # Activity log contains guidance event
        guidance_activities = [
            a for a in activities
            if a["action"] == "guidance"
        ]
        self.assertGreater(len(guidance_activities), 0)
        self.assertIn("PostgreSQL", guidance_activities[0]["detail"])


# ── 7. Token Budget Escalation ────────────────────────────────────────

class TestE2ETokenBudgetEscalation(unittest.TestCase):
    """Budget exhaustion before planning triggers escalation → skip."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_budget_exhausted_triggers_escalation_skip(self):
        # Use normal spec + task_graph responses but set budget very low.
        # The budget tracker accumulates estimated tokens from LoggingBackend.
        # We set global_token_budget=1 so it's exceeded after spec calls.
        llm = make_sequenced_llm([
            *make_spec_responses(),
            make_task_graph(),
            # We should never reach these — budget exhausted before planning
            make_plan(),
            make_exec_batch(),
            make_skill(),
        ])

        escalation_calls = []

        def ask_fn_skip(questions, decisions, understanding):
            escalation_calls.append(True)
            return {"escalation_action": "skip", "escalation_hint": ""}

        config = RunConfig(
            output_dir=self._tmpdir,
            global_token_budget=1,       # Impossibly low
            per_task_token_budget=1,
            enable_human_escalation=True,
        )
        orchestrator = OrchestratorAgent(llm=llm.backend, config=config)
        state = orchestrator.run(problem="Build a CLI calculator", ask_fn=ask_fn_skip)

        # Task should have failed (skipped due to budget)
        self.assertIn("t1", state.failed_tasks)
        self.assertNotIn("t1", state.completed_tasks)

        # Escalation recorded
        self.assertGreater(len(state.escalations), 0)
        budget_escalation = any(
            "token_budget" in e.get("trigger", "")
            for e in state.escalations
        )
        self.assertTrue(budget_escalation,
                        f"Expected token_budget escalation, got: {state.escalations}")


# ── 8. Activity and State Callbacks ──────────────────────────────────

class TestE2ECallbacks(unittest.TestCase):
    """Verify on_activity, on_state, and on_llm_log fire during pipeline."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_callbacks_fire_throughout_pipeline(self):
        llm = make_sequenced_llm([
            *make_spec_responses(),
            make_task_graph(),
            make_plan(),
            make_exec_batch(),
            make_skill(),
        ])

        activities = []
        states = []
        llm_logs = []

        def on_activity(agent, action, detail="", status="info"):
            activities.append({"agent": agent, "action": action})

        def on_state(state):
            states.append(state.current_mode)

        def on_llm_log(entry):
            llm_logs.append(entry.get("agent", "unknown"))

        config = RunConfig(output_dir=self._tmpdir)
        orchestrator = OrchestratorAgent(llm=llm.backend, config=config)
        state = orchestrator.run(
            problem="Build a CLI calculator",
            ask_fn=_noop_ask_fn,
            on_activity=on_activity,
            on_state=on_state,
            on_llm_log=on_llm_log,
        )

        # Activities should include mode changes for each phase
        activity_actions = [a["action"] for a in activities]
        self.assertIn("mode_change", activity_actions)
        self.assertIn("completed", activity_actions)

        # Multiple state saves happened
        self.assertGreater(len(states), 3)

        # LLM logs captured for each agent call
        self.assertGreater(len(llm_logs), 0)
        self.assertIn("spec", llm_logs)

    def test_pipeline_state_json_complete(self):
        """The persisted pipeline_state.json can be deserialized back."""
        llm = make_sequenced_llm([
            *make_spec_responses(),
            make_task_graph(),
            make_plan(),
            make_exec_batch(),
            make_skill(),
        ])

        config = RunConfig(output_dir=self._tmpdir)
        orchestrator = OrchestratorAgent(llm=llm.backend, config=config)
        orchestrator.run(problem="Build a CLI calculator", ask_fn=_noop_ask_fn)

        state_path = os.path.join(
            self._tmpdir, "build-a-cli-calculator", "pipeline_state.json"
        )
        with open(state_path) as f:
            data = json.load(f)

        restored = PipelineState.from_dict(data)
        self.assertEqual(restored.spec["title"], "PyCalc")
        self.assertEqual(restored.completed_tasks, ["t1"])
        self.assertGreater(len(restored.execution_results), 0)


if __name__ == "__main__":
    unittest.main()
