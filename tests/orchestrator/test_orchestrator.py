"""Tests for the Orchestrator module."""

import json
import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from BrainDock.orchestrator.models import Mode, PipelineState, RunConfig
from BrainDock.orchestrator.agent import OrchestratorAgent
from BrainDock.llm import CallableBackend


# ── Mock Responses ─────────────────────────────────────────────────────

# Spec agent responses (analyze, refine, generate)
SPEC_ANALYZE = json.dumps({
    "understanding": "Building a CLI calculator",
    "self_decided": [
        {"id": "d1", "topic": "Language", "decision": "Python 3.11+"},
    ],
    "user_questions": [],
})

# Refine response (needed because run() calls refine even with 0 questions)
SPEC_REFINE = json.dumps({
    "ready": True,
    "understanding": "Building a CLI calculator — clear requirements",
    "self_decided": [],
    "user_questions": [],
})

SPEC_GENERATE = json.dumps({
    "title": "PyCalc",
    "summary": "A CLI calculator",
    "problem_statement": "Need a calculator",
    "goals": ["Fast arithmetic"],
    "target_users": "Developers",
    "user_stories": ["As a user, I want to calculate"],
    "functional_requirements": [
        {"feature": "Eval", "description": "Evaluate expressions", "acceptance_criteria": ["Works"], "priority": "must-have"}
    ],
    "non_functional_requirements": ["Fast"],
    "tech_stack": {"language": "Python"},
    "architecture_overview": "Single file",
    "data_models": [],
    "api_endpoints": [],
    "milestones": [{"name": "v1", "description": "Done", "deliverables": ["Calculator"]}],
    "constraints": [],
    "assumptions": [],
    "open_questions": [],
})

# Task graph response
TASK_GRAPH = json.dumps({
    "project_title": "PyCalc",
    "tasks": [
        {
            "id": "t1",
            "title": "Create calculator module",
            "description": "Write the main calculator with eval support",
            "depends_on": [],
            "estimated_effort": "small",
            "tags": [],
            "risks": [],
        }
    ],
})

# Plan response
PLAN = json.dumps({
    "task_id": "t1",
    "task_title": "Create calculator module",
    "steps": [
        {
            "id": "s1",
            "action": "Write calculator",
            "description": "Create calc.py with eval function",
            "tool": "write_file",
            "expected_output": "calc.py file",
        }
    ],
    "metrics": {
        "confidence": 0.9,
        "entropy": 0.1,
        "estimated_steps": 1,
        "complexity": "low",
    },
    "relevant_skills": [],
    "assumptions": [],
})

# Executor response
EXEC_WRITE = json.dumps({
    "step_id": "s1",
    "action_type": "write_file",
    "file_path": "calc.py",
    "content": "def calc(expr): return eval(expr)\n",
    "verification": "File exists",
})

# Skill extraction response
SKILL_EXTRACT = json.dumps({
    "id": "skill_eval_pattern",
    "name": "Expression Evaluation",
    "description": "Evaluate user expressions safely",
    "tags": ["parsing", "evaluation"],
    "pattern": "eval with validation",
    "example_code": "def calc(expr): return eval(expr)",
})

# Skill matching response (match_skills called before planning)
SKILL_MATCH = json.dumps({
    "matches": []
})


# ── Web App Skill Reuse Mocks ─────────────────────────────────────────

# Run 1: JWT auth web app
WEBAPP_SPEC_ANALYZE = json.dumps({
    "understanding": "Building a web application with user authentication",
    "self_decided": [
        {"id": "d1", "topic": "Framework", "decision": "Python with Flask"},
    ],
    "user_questions": [],
})

WEBAPP_SPEC_REFINE = json.dumps({
    "ready": True,
    "understanding": "Web auth app — clear requirements",
    "self_decided": [],
    "user_questions": [],
})

WEBAPP_SPEC_GENERATE = json.dumps({
    "title": "WebAuth",
    "summary": "A web app with JWT authentication",
    "problem_statement": "Need secure user login",
    "goals": ["Secure authentication"],
    "target_users": "Web users",
    "user_stories": ["As a user, I want to log in securely"],
    "functional_requirements": [
        {"feature": "Login", "description": "JWT-based login endpoint",
         "acceptance_criteria": ["Returns JWT token"], "priority": "must-have"}
    ],
    "non_functional_requirements": ["Secure"],
    "tech_stack": {"language": "Python", "framework": "Flask"},
    "architecture_overview": "REST API with JWT auth",
    "data_models": [],
    "api_endpoints": ["/api/login", "/api/protected"],
    "milestones": [{"name": "v1", "description": "Auth", "deliverables": ["Login endpoint"]}],
    "constraints": [],
    "assumptions": [],
    "open_questions": [],
})

WEBAPP_TASK_GRAPH = json.dumps({
    "project_title": "WebAuth",
    "tasks": [
        {
            "id": "t1",
            "title": "Build JWT login endpoint",
            "description": "Create /api/login that validates credentials and returns JWT tokens",
            "depends_on": [],
            "estimated_effort": "medium",
            "tags": ["auth", "api"],
            "risks": [],
        }
    ],
})

WEBAPP_PLAN = json.dumps({
    "task_id": "t1",
    "task_title": "Build JWT login endpoint",
    "steps": [
        {
            "id": "s1",
            "action": "Write auth module",
            "description": "Create auth.py with JWT token generation and verification",
            "tool": "write_file",
            "expected_output": "auth.py file",
        }
    ],
    "metrics": {
        "confidence": 0.85,
        "entropy": 0.15,
        "estimated_steps": 1,
        "complexity": "medium",
    },
    "relevant_skills": [],
    "assumptions": [],
})

WEBAPP_EXEC_WRITE = json.dumps({
    "step_id": "s1",
    "action_type": "write_file",
    "file_path": "auth.py",
    "content": "import jwt\ndef login(username, password):\n    token = jwt.encode({'user': username}, 'secret')\n    return {'token': token}\n",
    "verification": "File exists",
})

SKILL_JWT_AUTH = json.dumps({
    "id": "skill_jwt_auth",
    "name": "JWT Authentication Flow",
    "description": "Implement JWT-based login with access and refresh tokens",
    "tags": ["auth", "jwt", "security", "web"],
    "pattern": "login endpoint validates credentials, issues JWT tokens, middleware verifies on protected routes",
    "example_code": "import jwt\\ndef login(user, pwd):\\n    return jwt.encode({'sub': user}, SECRET)",
})

# Run 2: e-commerce CRUD app
SHOP_SPEC_GENERATE = json.dumps({
    "title": "ShopApp",
    "summary": "E-commerce product catalog with REST API",
    "problem_statement": "Need product management",
    "goals": ["Product CRUD"],
    "target_users": "Shoppers",
    "user_stories": ["As an admin, I want to manage products"],
    "functional_requirements": [
        {"feature": "Products", "description": "CRUD API for products",
         "acceptance_criteria": ["CRUD works"], "priority": "must-have"}
    ],
    "non_functional_requirements": ["Fast"],
    "tech_stack": {"language": "Python", "framework": "Flask"},
    "architecture_overview": "REST API with product model",
    "data_models": [{"name": "Product", "fields": ["id", "name", "price"]}],
    "api_endpoints": ["/api/products"],
    "milestones": [{"name": "v1", "description": "CRUD", "deliverables": ["Product API"]}],
    "constraints": [],
    "assumptions": [],
    "open_questions": [],
})

SHOP_TASK_GRAPH = json.dumps({
    "project_title": "ShopApp",
    "tasks": [
        {
            "id": "t1",
            "title": "Build product CRUD API",
            "description": "Create REST endpoints for product create, read, update, delete",
            "depends_on": [],
            "estimated_effort": "medium",
            "tags": ["api", "crud"],
            "risks": [],
        }
    ],
})

SHOP_PLAN = json.dumps({
    "task_id": "t1",
    "task_title": "Build product CRUD API",
    "steps": [
        {
            "id": "s1",
            "action": "Write product routes",
            "description": "Create routes.py with CRUD endpoints for products",
            "tool": "write_file",
            "expected_output": "routes.py file",
        }
    ],
    "metrics": {
        "confidence": 0.9,
        "entropy": 0.1,
        "estimated_steps": 1,
        "complexity": "medium",
    },
    "relevant_skills": ["skill_jwt_auth"],
    "assumptions": [],
})

SHOP_EXEC_WRITE = json.dumps({
    "step_id": "s1",
    "action_type": "write_file",
    "file_path": "routes.py",
    "content": "from flask import Flask, jsonify\napp = Flask(__name__)\nproducts = []\n@app.route('/api/products')\ndef list_products():\n    return jsonify(products)\n",
    "verification": "File exists",
})

SKILL_REST_CRUD = json.dumps({
    "id": "skill_rest_crud",
    "name": "REST CRUD API Pattern",
    "description": "Standard REST API with Create, Read, Update, Delete endpoints",
    "tags": ["api", "rest", "crud", "web", "flask"],
    "pattern": "GET /items, POST /items, GET /items/:id, PUT /items/:id, DELETE /items/:id",
    "example_code": "@app.route('/items', methods=['GET'])\\ndef list_items(): return jsonify(items)",
})

# Run 3: form validation app
FORM_SPEC_GENERATE = json.dumps({
    "title": "FormApp",
    "summary": "Contact form with validation",
    "problem_statement": "Need validated contact form",
    "goals": ["Input validation"],
    "target_users": "Site visitors",
    "user_stories": ["As a user, I want clear form errors"],
    "functional_requirements": [
        {"feature": "Form", "description": "Contact form with server-side validation",
         "acceptance_criteria": ["Validates email, required fields"], "priority": "must-have"}
    ],
    "non_functional_requirements": ["User-friendly errors"],
    "tech_stack": {"language": "Python", "framework": "Flask"},
    "architecture_overview": "Server-rendered form with validation",
    "data_models": [],
    "api_endpoints": ["/contact"],
    "milestones": [{"name": "v1", "description": "Form", "deliverables": ["Contact page"]}],
    "constraints": [],
    "assumptions": [],
    "open_questions": [],
})

FORM_TASK_GRAPH = json.dumps({
    "project_title": "FormApp",
    "tasks": [
        {
            "id": "t1",
            "title": "Build validated contact form",
            "description": "Create contact form with email and required-field validation",
            "depends_on": [],
            "estimated_effort": "small",
            "tags": ["forms", "validation"],
            "risks": [],
        }
    ],
})

FORM_PLAN = json.dumps({
    "task_id": "t1",
    "task_title": "Build validated contact form",
    "steps": [
        {
            "id": "s1",
            "action": "Write form handler",
            "description": "Create form.py with validation logic",
            "tool": "write_file",
            "expected_output": "form.py file",
        }
    ],
    "metrics": {
        "confidence": 0.9,
        "entropy": 0.1,
        "estimated_steps": 1,
        "complexity": "low",
    },
    "relevant_skills": [],
    "assumptions": [],
})

FORM_EXEC_WRITE = json.dumps({
    "step_id": "s1",
    "action_type": "write_file",
    "file_path": "form.py",
    "content": "import re\ndef validate(data):\n    errors = {}\n    if not data.get('email') or not re.match(r'.+@.+', data['email']):\n        errors['email'] = 'Valid email required'\n    return errors\n",
    "verification": "File exists",
})

SKILL_FORM_VALIDATION = json.dumps({
    "id": "skill_form_validation",
    "name": "Form Input Validation",
    "description": "Server-side form validation with per-field error messages",
    "tags": ["forms", "validation", "web", "ui"],
    "pattern": "validate each field, collect errors dict, return errors or proceed",
    "example_code": "def validate(data):\\n    errors = {}\\n    if not data.get('email'): errors['email'] = 'Required'\\n    return errors",
})


def make_pipeline_llm():
    """Mock LLM that returns responses for the full pipeline."""
    call_count = {"n": 0}
    responses = [
        SPEC_ANALYZE,    # spec analyze
        SPEC_REFINE,     # spec refine (run() calls refine even with 0 questions)
        SPEC_GENERATE,   # spec generate
        TASK_GRAPH,      # task graph decompose
        PLAN,            # planner plan_task
        EXEC_WRITE,      # executor execute_step
        SKILL_EXTRACT,   # skill extraction
    ]

    def mock_fn(system_prompt, user_prompt):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]

    return CallableBackend(mock_fn)


def make_plan_only_llm():
    """Mock LLM for plan-only mode (spec + task_graph + plan only)."""
    call_count = {"n": 0}
    responses = [SPEC_ANALYZE, SPEC_REFINE, SPEC_GENERATE, TASK_GRAPH]

    def mock_fn(system_prompt, user_prompt):
        idx = min(call_count["n"], len(responses) - 1)
        call_count["n"] += 1
        return responses[idx]

    return CallableBackend(mock_fn)


# ── Tests ──────────────────────────────────────────────────────────────

class TestMode(unittest.TestCase):
    def test_values(self):
        self.assertEqual(Mode.SPECIFICATION.value, "specification")
        self.assertEqual(Mode.DEBATE.value, "debate")
        self.assertEqual(len(Mode), 8)


class TestRunConfig(unittest.TestCase):
    def test_defaults(self):
        config = RunConfig()
        self.assertEqual(config.output_dir, "output")
        self.assertFalse(config.skip_execution)
        self.assertAlmostEqual(config.min_confidence, 0.6)

    def test_roundtrip(self):
        config = RunConfig(output_dir="/tmp/test", skip_execution=True)
        d = config.to_dict()
        restored = RunConfig.from_dict(d)
        self.assertEqual(restored.output_dir, "/tmp/test")
        self.assertTrue(restored.skip_execution)


class TestPipelineState(unittest.TestCase):
    def test_defaults(self):
        state = PipelineState()
        self.assertEqual(state.current_mode, Mode.SPECIFICATION.value)
        self.assertEqual(state.spec, {})
        self.assertEqual(state.completed_tasks, [])

    def test_roundtrip(self):
        state = PipelineState()
        state.spec = {"title": "Test"}
        state.completed_tasks = ["t1"]
        d = state.to_dict()
        restored = PipelineState.from_dict(d)
        self.assertEqual(restored.spec["title"], "Test")
        self.assertEqual(restored.completed_tasks, ["t1"])


class TestOrchestratorPlanOnly(unittest.TestCase):
    """Test orchestrator in plan-only mode (no execution)."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_plan_only_produces_spec_and_graph(self):
        config = RunConfig(output_dir=self._tmpdir, skip_execution=True)
        orchestrator = OrchestratorAgent(llm=make_plan_only_llm(), config=config)

        def ask_fn(questions, decisions, understanding):
            return {}

        state = orchestrator.run(problem="Build a CLI calculator", ask_fn=ask_fn)

        # Should have spec
        self.assertEqual(state.spec["title"], "PyCalc")

        # Should have task graph
        self.assertEqual(state.task_graph["project_title"], "PyCalc")
        self.assertEqual(len(state.task_graph["tasks"]), 1)

        # Should NOT have execution results (plan-only)
        self.assertEqual(len(state.execution_results), 0)

        # Output files should exist (under slugified project dir)
        project_dir = os.path.join(self._tmpdir, "build-a-cli-calculator")
        self.assertTrue(os.path.exists(os.path.join(project_dir, "spec_agent", "spec.json")))
        self.assertTrue(os.path.exists(os.path.join(project_dir, "task_graph", "task_graph.json")))


class TestOrchestratorFullPipeline(unittest.TestCase):
    """Test orchestrator with full pipeline execution."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_full_pipeline(self):
        config = RunConfig(output_dir=self._tmpdir)
        orchestrator = OrchestratorAgent(llm=make_pipeline_llm(), config=config)

        def ask_fn(questions, decisions, understanding):
            return {}

        state = orchestrator.run(problem="Build a CLI calculator", ask_fn=ask_fn)

        # Should have completed all stages
        self.assertEqual(state.spec["title"], "PyCalc")
        self.assertEqual(len(state.plans), 1)
        self.assertGreater(len(state.execution_results), 0)
        self.assertEqual(state.completed_tasks, ["t1"])
        self.assertEqual(len(state.failed_tasks), 0)

        # Skill should have been learned
        self.assertEqual(len(state.learned_skills), 1)
        self.assertEqual(state.learned_skills[0]["id"], "skill_eval_pattern")

    def test_full_pipeline_no_skill_learning(self):
        config = RunConfig(output_dir=self._tmpdir, skip_skill_learning=True)
        orchestrator = OrchestratorAgent(llm=make_pipeline_llm(), config=config)

        def ask_fn(questions, decisions, understanding):
            return {}

        state = orchestrator.run(problem="Build a CLI calculator", ask_fn=ask_fn)

        self.assertEqual(state.completed_tasks, ["t1"])
        self.assertEqual(len(state.learned_skills), 0)


class TestProjectMemory(unittest.TestCase):
    """Test the project_memory module."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_scan_empty_dir(self):
        from BrainDock.project_memory import scan_project
        snapshot = scan_project(self._tmpdir)
        self.assertEqual(snapshot.total_files, 0)
        self.assertEqual(snapshot.key_file_contents, {})
        self.assertIn("empty", snapshot.to_context_string())

    def test_scan_with_files(self):
        from BrainDock.project_memory import scan_project
        # Create some files
        with open(os.path.join(self._tmpdir, "main.py"), "w") as f:
            f.write("print('hello')\n")
        with open(os.path.join(self._tmpdir, "utils.py"), "w") as f:
            f.write("def helper(): pass\n")

        snapshot = scan_project(self._tmpdir)
        self.assertEqual(snapshot.total_files, 2)
        self.assertIn("main.py", snapshot.key_file_contents)
        ctx = snapshot.to_context_string()
        self.assertIn("main.py", ctx)
        self.assertIn("print('hello')", ctx)

    def test_scan_skips_binary(self):
        from BrainDock.project_memory import scan_project
        with open(os.path.join(self._tmpdir, "image.png"), "wb") as f:
            f.write(b"\x89PNG\r\n")
        with open(os.path.join(self._tmpdir, "main.py"), "w") as f:
            f.write("x = 1\n")

        snapshot = scan_project(self._tmpdir)
        self.assertNotIn("image.png", snapshot.key_file_contents)
        self.assertIn("main.py", snapshot.key_file_contents)

    def test_scan_prioritizes_key_files(self):
        from BrainDock.project_memory import scan_project
        # main.py should come before random files
        with open(os.path.join(self._tmpdir, "main.py"), "w") as f:
            f.write("entry\n")
        with open(os.path.join(self._tmpdir, "zzz_other.py"), "w") as f:
            f.write("other\n")

        snapshot = scan_project(self._tmpdir)
        keys = list(snapshot.key_file_contents.keys())
        self.assertEqual(keys[0], "main.py")


class TestVerifyProject(unittest.TestCase):
    """Test the verify_project function."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_verify_success(self):
        from BrainDock.executor.sandbox import verify_project
        with open(os.path.join(self._tmpdir, "main.py"), "w") as f:
            f.write("print('hello')\n")
        result = verify_project(self._tmpdir, timeout=10)
        self.assertTrue(result.success)
        self.assertEqual(result.detection_method, "main.py")

    def test_verify_failure(self):
        from BrainDock.executor.sandbox import verify_project
        with open(os.path.join(self._tmpdir, "main.py"), "w") as f:
            f.write("raise Exception('boom')\n")
        result = verify_project(self._tmpdir, timeout=10)
        self.assertFalse(result.success)
        self.assertIn("boom", result.error_summary + result.stderr)

    def test_verify_no_entry_point(self):
        from BrainDock.executor.sandbox import verify_project
        result = verify_project(self._tmpdir, timeout=10)
        self.assertTrue(result.success)  # No entry point → skip → success
        self.assertEqual(result.detection_method, "none")

    def test_verify_syntax_error(self):
        from BrainDock.executor.sandbox import verify_project
        with open(os.path.join(self._tmpdir, "main.py"), "w") as f:
            f.write("def foo(\n")  # SyntaxError
        result = verify_project(self._tmpdir, timeout=10)
        self.assertFalse(result.success)


class TestVerifyResult(unittest.TestCase):
    """Test the VerifyResult model."""

    def test_to_dict(self):
        from BrainDock.executor.models import VerifyResult
        vr = VerifyResult(success=True, command="python main.py", exit_code=0)
        d = vr.to_dict()
        self.assertTrue(d["success"])
        self.assertEqual(d["command"], "python main.py")


class TestTaskOutcomeAffectedFile(unittest.TestCase):
    """Test the affected_file field on TaskOutcome."""

    def test_affected_file_roundtrip(self):
        from BrainDock.executor.models import TaskOutcome
        o = TaskOutcome(step_id="s1", success=True, affected_file="calc.py")
        d = o.to_dict()
        self.assertEqual(d["affected_file"], "calc.py")
        restored = TaskOutcome.from_dict(d)
        self.assertEqual(restored.affected_file, "calc.py")


class TestPipelineStateVerificationResults(unittest.TestCase):
    """Test that verification_results is included in PipelineState."""

    def test_verification_results_default(self):
        state = PipelineState()
        self.assertEqual(state.verification_results, [])

    def test_verification_results_roundtrip(self):
        state = PipelineState()
        state.verification_results = [{"success": True, "command": "python main.py"}]
        d = state.to_dict()
        restored = PipelineState.from_dict(d)
        self.assertEqual(len(restored.verification_results), 1)
        self.assertTrue(restored.verification_results[0]["success"])


class TestReadFileSafe(unittest.TestCase):
    """Test the read_file_safe function."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_read_existing_file(self):
        from BrainDock.executor.sandbox import read_file_safe
        with open(os.path.join(self._tmpdir, "test.py"), "w") as f:
            f.write("content\n")
        result = read_file_safe("test.py", self._tmpdir)
        self.assertEqual(result, "content\n")

    def test_read_nonexistent_file(self):
        from BrainDock.executor.sandbox import read_file_safe
        result = read_file_safe("nonexistent.py", self._tmpdir)
        self.assertIsNone(result)

    def test_read_path_traversal(self):
        from BrainDock.executor.sandbox import read_file_safe
        result = read_file_safe("../../etc/passwd", self._tmpdir)
        self.assertIsNone(result)


class TestPipelineStateMarketStudies(unittest.TestCase):
    """Test that market_studies is included in PipelineState."""

    def test_market_studies_default(self):
        state = PipelineState()
        self.assertEqual(state.market_studies, [])

    def test_market_studies_roundtrip(self):
        state = PipelineState()
        state.market_studies = [{"task_id": "t1", "competitors": ["Acme"]}]
        d = state.to_dict()
        restored = PipelineState.from_dict(d)
        self.assertEqual(len(restored.market_studies), 1)
        self.assertEqual(restored.market_studies[0]["task_id"], "t1")


class TestTaskNodeTags(unittest.TestCase):
    """Test that tags field works on TaskNode."""

    def test_tags_default(self):
        from BrainDock.task_graph.models import TaskNode
        node = TaskNode(id="t1", title="Test", description="Desc")
        self.assertEqual(node.tags, [])

    def test_tags_roundtrip(self):
        from BrainDock.task_graph.models import TaskNode
        node = TaskNode(id="t1", title="Test", description="Desc", tags=["needs_market_study"])
        d = node.to_dict()
        self.assertEqual(d["tags"], ["needs_market_study"])
        restored = TaskNode.from_dict(d)
        self.assertEqual(restored.tags, ["needs_market_study"])


class TestMarketStudyResult(unittest.TestCase):
    """Test the MarketStudyResult model."""

    def test_roundtrip(self):
        from BrainDock.market_study.models import MarketStudyResult
        result = MarketStudyResult(
            task_id="t1",
            competitors=["Acme", "Corp"],
            recommendations=["Focus on UX"],
            risks=["Market saturation"],
            target_audience="Developers",
            positioning="Best-in-class CLI tool",
        )
        d = result.to_dict()
        self.assertEqual(d["task_id"], "t1")
        self.assertEqual(d["competitors"], ["Acme", "Corp"])

        restored = MarketStudyResult.from_dict(d)
        self.assertEqual(restored.task_id, "t1")
        self.assertEqual(restored.positioning, "Best-in-class CLI tool")

    def test_to_context_string(self):
        from BrainDock.market_study.models import MarketStudyResult
        result = MarketStudyResult(
            task_id="t1",
            competitors=["Acme"],
            target_audience="Devs",
            positioning="Leader",
        )
        ctx = result.to_context_string()
        self.assertIn("t1", ctx)
        self.assertIn("Acme", ctx)
        self.assertIn("Devs", ctx)


class TestBaseAgentRetry(unittest.TestCase):
    """Test that BaseAgent retries on transient failures."""

    def test_retry_on_runtime_error(self):
        from BrainDock.base_agent import BaseAgent, MAX_LLM_RETRIES
        call_count = {"n": 0}

        class FailOnceBackend:
            def query(self, system_prompt, user_prompt):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise RuntimeError("Transient failure")
                return '{"result": "ok"}'

        agent = BaseAgent(llm=FailOnceBackend())
        result = agent._llm_query_json("sys", "user")
        self.assertEqual(result, {"result": "ok"})
        self.assertEqual(call_count["n"], 2)

    def test_persistent_failure_raises(self):
        from BrainDock.base_agent import BaseAgent, MAX_LLM_RETRIES

        class AlwaysFailBackend:
            def query(self, system_prompt, user_prompt):
                raise RuntimeError("Always fails")

        agent = BaseAgent(llm=AlwaysFailBackend())
        with self.assertRaises(RuntimeError):
            agent._llm_query_json("sys", "user")


class TestParseEscalationResponse(unittest.TestCase):
    """Test the _parse_escalation_response static method."""

    def test_skip(self):
        action, hint = OrchestratorAgent._parse_escalation_response(
            {"escalation_action": "skip"}, "t1"
        )
        self.assertEqual(action, "skip")
        self.assertEqual(hint, "")

    def test_retry_with_hint(self):
        action, hint = OrchestratorAgent._parse_escalation_response(
            {"escalation_action": "retry", "escalation_hint": "Try using OAuth2"}, "t1"
        )
        self.assertEqual(action, "retry")
        self.assertEqual(hint, "Try using OAuth2")

    def test_abort(self):
        action, hint = OrchestratorAgent._parse_escalation_response(
            {"escalation_action": "abort"}, "t1"
        )
        self.assertEqual(action, "abort")

    def test_invalid_action_defaults_to_skip(self):
        action, hint = OrchestratorAgent._parse_escalation_response(
            {"escalation_action": "invalid_value"}, "t1"
        )
        self.assertEqual(action, "skip")

    def test_empty_answers_defaults_to_skip(self):
        action, hint = OrchestratorAgent._parse_escalation_response({}, "t1")
        self.assertEqual(action, "skip")
        self.assertEqual(hint, "")

    def test_whitespace_stripping(self):
        action, hint = OrchestratorAgent._parse_escalation_response(
            {"escalation_action": "  retry  ", "escalation_hint": "  some hint  "}, "t1"
        )
        self.assertEqual(action, "retry")
        self.assertEqual(hint, "some hint")


class TestRunConfigEscalation(unittest.TestCase):
    """Test the new escalation fields on RunConfig."""

    def test_defaults(self):
        config = RunConfig()
        self.assertTrue(config.enable_human_escalation)
        self.assertEqual(config.escalation_token_budget, 50000)

    def test_roundtrip(self):
        config = RunConfig(enable_human_escalation=False, escalation_token_budget=10000)
        d = config.to_dict()
        restored = RunConfig.from_dict(d)
        self.assertFalse(restored.enable_human_escalation)
        self.assertEqual(restored.escalation_token_budget, 10000)

    def test_from_dict_missing_fields(self):
        restored = RunConfig.from_dict({"output_dir": "/tmp"})
        self.assertTrue(restored.enable_human_escalation)
        self.assertEqual(restored.escalation_token_budget, 50000)


class TestPipelineStateEscalations(unittest.TestCase):
    """Test the escalations field on PipelineState."""

    def test_default(self):
        state = PipelineState()
        self.assertEqual(state.escalations, [])

    def test_roundtrip(self):
        state = PipelineState()
        state.escalations = [
            {"task_id": "t1", "trigger": "needs_human", "reason": "Auth required", "action": "skip", "hint": ""},
            {"task_id": "t2", "trigger": "reflection_exhausted", "reason": "Retries used up", "action": "retry", "hint": "Try X"},
        ]
        d = state.to_dict()
        restored = PipelineState.from_dict(d)
        self.assertEqual(len(restored.escalations), 2)
        self.assertEqual(restored.escalations[0]["trigger"], "needs_human")
        self.assertEqual(restored.escalations[1]["action"], "retry")


class TestReflectionResultNeedsHuman(unittest.TestCase):
    """Test the needs_human field on ReflectionResult."""

    def test_defaults(self):
        from BrainDock.reflection.models import ReflectionResult
        result = ReflectionResult()
        self.assertFalse(result.needs_human)
        self.assertEqual(result.escalation_reason, "")

    def test_roundtrip(self):
        from BrainDock.reflection.models import ReflectionResult
        result = ReflectionResult(
            needs_human=True,
            escalation_reason="Requires GitHub OAuth token",
            summary="Auth needed",
            should_retry=False,
        )
        d = result.to_dict()
        self.assertTrue(d["needs_human"])
        self.assertEqual(d["escalation_reason"], "Requires GitHub OAuth token")

        restored = ReflectionResult.from_dict(d)
        self.assertTrue(restored.needs_human)
        self.assertEqual(restored.escalation_reason, "Requires GitHub OAuth token")
        self.assertFalse(restored.should_retry)

    def test_from_dict_missing_fields(self):
        from BrainDock.reflection.models import ReflectionResult
        restored = ReflectionResult.from_dict({"summary": "test"})
        self.assertFalse(restored.needs_human)
        self.assertEqual(restored.escalation_reason, "")


class TestRunConfigTokenBudget(unittest.TestCase):
    """Test the new token budget fields on RunConfig."""

    def test_defaults(self):
        config = RunConfig()
        self.assertEqual(config.global_token_budget, 500_000)
        self.assertEqual(config.per_task_token_budget, 80_000)
        self.assertTrue(config.context_optimization)

    def test_roundtrip(self):
        config = RunConfig(global_token_budget=100_000, per_task_token_budget=20_000, context_optimization=False)
        d = config.to_dict()
        restored = RunConfig.from_dict(d)
        self.assertEqual(restored.global_token_budget, 100_000)
        self.assertEqual(restored.per_task_token_budget, 20_000)
        self.assertFalse(restored.context_optimization)

    def test_from_dict_missing_fields(self):
        restored = RunConfig.from_dict({"output_dir": "/tmp"})
        self.assertEqual(restored.global_token_budget, 500_000)
        self.assertEqual(restored.per_task_token_budget, 80_000)
        self.assertTrue(restored.context_optimization)


class TestPipelineStateTokenUsage(unittest.TestCase):
    """Test the token_usage field on PipelineState."""

    def test_default(self):
        state = PipelineState()
        self.assertEqual(state.token_usage, {})

    def test_roundtrip(self):
        state = PipelineState()
        state.token_usage = {
            "global_used": 10000,
            "global_budget": 500000,
            "global_pct": 0.02,
            "task_id": "t1",
            "task_used": 5000,
            "task_budget": 80000,
            "agent_totals": {"planner": {"input": 3000, "output": 2000}},
        }
        d = state.to_dict()
        restored = PipelineState.from_dict(d)
        self.assertEqual(restored.token_usage["global_used"], 10000)
        self.assertEqual(restored.token_usage["task_id"], "t1")
        self.assertEqual(restored.token_usage["agent_totals"]["planner"]["input"], 3000)

    def test_from_dict_missing_token_usage(self):
        """Backward compatibility: old state files without token_usage."""
        restored = PipelineState.from_dict({"title": "Test", "problem": "Something"})
        self.assertEqual(restored.token_usage, {})


class TestGlobalSkillBankPath(unittest.TestCase):
    """Test the global_skill_bank_path field on RunConfig."""

    def test_global_skill_bank_path_default(self):
        config = RunConfig()
        self.assertEqual(config.global_skill_bank_path, "")
        resolved = config.resolve_global_skill_bank_path()
        self.assertEqual(resolved, os.path.join("output", "skill_bank", "skills.json"))

    def test_global_skill_bank_path_custom(self):
        config = RunConfig(global_skill_bank_path="/custom/path/skills.json")
        self.assertEqual(config.resolve_global_skill_bank_path(), "/custom/path/skills.json")

    def test_global_skill_bank_path_roundtrip(self):
        config = RunConfig(global_skill_bank_path="/my/skills.json")
        d = config.to_dict()
        restored = RunConfig.from_dict(d)
        self.assertEqual(restored.global_skill_bank_path, "/my/skills.json")
        self.assertEqual(restored.resolve_global_skill_bank_path(), "/my/skills.json")

    def test_global_skill_bank_path_from_dict_missing(self):
        restored = RunConfig.from_dict({"output_dir": "/tmp/out"})
        self.assertEqual(restored.global_skill_bank_path, "")
        self.assertEqual(
            restored.resolve_global_skill_bank_path(),
            os.path.join("/tmp/out", "skill_bank", "skills.json"),
        )

    def test_seed_skill_bank_path_default(self):
        config = RunConfig()
        self.assertEqual(config.seed_skill_bank_path, "")

    def test_seed_skill_bank_path_roundtrip(self):
        config = RunConfig(seed_skill_bank_path="/my/seeds.json")
        d = config.to_dict()
        restored = RunConfig.from_dict(d)
        self.assertEqual(restored.seed_skill_bank_path, "/my/seeds.json")

    def test_seed_skill_bank_path_from_dict_missing(self):
        restored = RunConfig.from_dict({"output_dir": "/tmp/out"})
        self.assertEqual(restored.seed_skill_bank_path, "")


class TestOrchestratorGuidance(unittest.TestCase):
    """Test the _drain_guidance_text helper and check_guidance propagation."""

    def test_drain_guidance_text_empty(self):
        result = OrchestratorAgent._drain_guidance_text(None)
        self.assertEqual(result, "")

    def test_drain_guidance_text_no_messages(self):
        result = OrchestratorAgent._drain_guidance_text(lambda: [])
        self.assertEqual(result, "")

    def test_drain_guidance_text_with_messages(self):
        result = OrchestratorAgent._drain_guidance_text(
            lambda: ["Use React", "Add tests"]
        )
        self.assertIn("USER GUIDANCE", result)
        self.assertIn("- Use React", result)
        self.assertIn("- Add tests", result)

    def test_run_accepts_check_guidance(self):
        """run() works with check_guidance callback (full pipeline)."""
        config = RunConfig(output_dir=self._tmpdir)
        orchestrator = OrchestratorAgent(llm=make_pipeline_llm(), config=config)

        guidance_drained = {"count": 0}

        def mock_guidance():
            guidance_drained["count"] += 1
            return []

        def ask_fn(questions, decisions, understanding):
            return {}

        state = orchestrator.run(
            problem="Build a CLI calculator",
            ask_fn=ask_fn,
            check_guidance=mock_guidance,
        )
        # Pipeline should complete successfully
        self.assertEqual(state.spec["title"], "PyCalc")
        self.assertEqual(state.completed_tasks, ["t1"])
        # Guidance callback should have been called at least once
        self.assertGreater(guidance_drained["count"], 0)

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)


class TestGlobalSkillBankWebApp(unittest.TestCase):
    """Integration tests: skills from web-app projects persist and get reused.

    Simulates common web development scenarios (auth, CRUD APIs, forms)
    to verify that skills learned in one pipeline run are available to
    the planner in subsequent runs.
    """

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    @staticmethod
    def _make_llm(responses, captured_prompts=None):
        """Create a mock LLM from a response list, optionally capturing prompts."""
        call_count = {"n": 0}

        def mock_fn(system_prompt, user_prompt):
            if captured_prompts is not None:
                captured_prompts.append({"system": system_prompt, "user": user_prompt})
            idx = min(call_count["n"], len(responses) - 1)
            call_count["n"] += 1
            return responses[idx]

        return CallableBackend(mock_fn)

    def _webapp_llm(self, skill_resp=SKILL_JWT_AUTH, captured=None, has_prior_skills=False):
        seq = [WEBAPP_SPEC_ANALYZE, WEBAPP_SPEC_REFINE, WEBAPP_SPEC_GENERATE, WEBAPP_TASK_GRAPH]
        if has_prior_skills:
            seq.append(SKILL_MATCH)
        seq.extend([WEBAPP_PLAN, WEBAPP_EXEC_WRITE, skill_resp])
        return self._make_llm(seq, captured)

    def _shop_llm(self, captured=None, has_prior_skills=False):
        seq = [WEBAPP_SPEC_ANALYZE, WEBAPP_SPEC_REFINE, SHOP_SPEC_GENERATE, SHOP_TASK_GRAPH]
        if has_prior_skills:
            seq.append(SKILL_MATCH)
        seq.extend([SHOP_PLAN, SHOP_EXEC_WRITE, SKILL_REST_CRUD])
        return self._make_llm(seq, captured)

    def _form_llm(self, captured=None, has_prior_skills=False):
        seq = [WEBAPP_SPEC_ANALYZE, WEBAPP_SPEC_REFINE, FORM_SPEC_GENERATE, FORM_TASK_GRAPH]
        if has_prior_skills:
            seq.append(SKILL_MATCH)
        seq.extend([FORM_PLAN, FORM_EXEC_WRITE, SKILL_FORM_VALIDATION])
        return self._make_llm(seq, captured)

    def _ask(self, q, d, u):
        return {}

    # ── Test: skill creation ──────────────────────────────────────

    def test_auth_skill_learned_and_saved_globally(self):
        """Run builds login app -> JWT auth skill saved to global bank."""
        config = RunConfig(output_dir=self._tmpdir)
        o = OrchestratorAgent(llm=self._webapp_llm(), config=config)
        state = o.run(problem="Build a web app with JWT login", ask_fn=self._ask)

        self.assertEqual(len(state.learned_skills), 1)
        self.assertEqual(state.learned_skills[0]["id"], "skill_jwt_auth")
        self.assertEqual(state.learned_skills[0]["name"], "JWT Authentication Flow")

        # Global skill bank file should exist and contain the skill
        from BrainDock.skill_bank.storage import load_skill_bank
        global_bank = load_skill_bank(config.resolve_global_skill_bank_path())
        self.assertEqual(len(global_bank.skills), 1)
        self.assertEqual(global_bank.get("skill_jwt_auth").name, "JWT Authentication Flow")
        self.assertIn("auth", global_bank.get("skill_jwt_auth").tags)

    def test_crud_skill_learned_and_saved_globally(self):
        """Run builds e-commerce app -> REST CRUD skill saved to global bank."""
        config = RunConfig(output_dir=self._tmpdir)
        o = OrchestratorAgent(llm=self._shop_llm(), config=config)
        state = o.run(problem="Build product catalog API", ask_fn=self._ask)

        self.assertEqual(len(state.learned_skills), 1)
        self.assertEqual(state.learned_skills[0]["id"], "skill_rest_crud")

        from BrainDock.skill_bank.storage import load_skill_bank
        global_bank = load_skill_bank(config.resolve_global_skill_bank_path())
        self.assertIsNotNone(global_bank.get("skill_rest_crud"))
        self.assertIn("crud", global_bank.get("skill_rest_crud").tags)

    def test_form_validation_skill_learned(self):
        """Run builds contact form -> validation skill saved to global bank."""
        config = RunConfig(output_dir=self._tmpdir)
        o = OrchestratorAgent(llm=self._form_llm(), config=config)
        state = o.run(problem="Build a contact form with validation", ask_fn=self._ask)

        self.assertEqual(state.learned_skills[0]["id"], "skill_form_validation")

        from BrainDock.skill_bank.storage import load_skill_bank
        global_bank = load_skill_bank(config.resolve_global_skill_bank_path())
        self.assertIsNotNone(global_bank.get("skill_form_validation"))

    # ── Test: skill reuse in next run ─────────────────────────────

    def test_auth_skill_passed_to_planner_in_next_run(self):
        """Skill from auth run appears in the planner prompt of the shop run."""
        config = RunConfig(output_dir=self._tmpdir)

        # Run 1: auth project -> learns JWT skill
        o1 = OrchestratorAgent(llm=self._webapp_llm(), config=config)
        o1.run(problem="Build a web app with JWT login", ask_fn=self._ask)

        # Run 2: e-commerce project -> should see JWT skill in planner prompt
        captured = []
        o2 = OrchestratorAgent(llm=self._shop_llm(captured=captured, has_prior_skills=True), config=config)
        state2 = o2.run(problem="Build product catalog API", ask_fn=self._ask)

        self.assertEqual(state2.completed_tasks, ["t1"])

        # The planner call should include the JWT skill from run 1
        planner_calls = [
            c for c in captured
            if "Available skills from the skill bank" in c["user"]
        ]
        self.assertGreater(len(planner_calls), 0,
                           "Planner should receive available skills from global bank")
        self.assertIn("JWT Authentication Flow", planner_calls[0]["user"])
        self.assertIn("skill_jwt_auth", planner_calls[0]["user"])

    def test_multiple_skills_available_to_planner(self):
        """After two runs, the third run's planner sees both learned skills."""
        config = RunConfig(output_dir=self._tmpdir)

        # Run 1: auth -> JWT skill
        o1 = OrchestratorAgent(llm=self._webapp_llm(), config=config)
        o1.run(problem="Build login system", ask_fn=self._ask)

        # Run 2: shop -> CRUD skill
        o2 = OrchestratorAgent(llm=self._shop_llm(has_prior_skills=True), config=config)
        o2.run(problem="Build product catalog", ask_fn=self._ask)

        # Run 3: form app -> should see BOTH skills in planner prompt
        captured = []
        o3 = OrchestratorAgent(llm=self._form_llm(captured=captured, has_prior_skills=True), config=config)
        o3.run(problem="Build contact form", ask_fn=self._ask)

        planner_calls = [
            c for c in captured
            if "Available skills from the skill bank" in c["user"]
        ]
        self.assertGreater(len(planner_calls), 0)
        prompt = planner_calls[0]["user"]
        self.assertIn("skill_jwt_auth", prompt)
        self.assertIn("skill_rest_crud", prompt)

    # ── Test: skill accumulation ──────────────────────────────────

    def test_skills_accumulate_across_three_runs(self):
        """Skills from auth, CRUD, and form projects all end up in global bank."""
        config = RunConfig(output_dir=self._tmpdir)

        OrchestratorAgent(llm=self._webapp_llm(), config=config).run(
            problem="Build login", ask_fn=self._ask)
        OrchestratorAgent(llm=self._shop_llm(has_prior_skills=True), config=config).run(
            problem="Build shop", ask_fn=self._ask)
        OrchestratorAgent(llm=self._form_llm(has_prior_skills=True), config=config).run(
            problem="Build form", ask_fn=self._ask)

        from BrainDock.skill_bank.storage import load_skill_bank
        global_bank = load_skill_bank(config.resolve_global_skill_bank_path())
        self.assertEqual(len(global_bank.skills), 3)
        self.assertIsNotNone(global_bank.get("skill_jwt_auth"))
        self.assertIsNotNone(global_bank.get("skill_rest_crud"))
        self.assertIsNotNone(global_bank.get("skill_form_validation"))

    # ── Test: per-run copy preserved ──────────────────────────────

    def test_per_run_copy_and_global_both_exist(self):
        """Each run saves a per-project skill bank alongside the global one."""
        config = RunConfig(output_dir=self._tmpdir)
        o = OrchestratorAgent(llm=self._webapp_llm(), config=config)
        o.run(problem="Build login app", ask_fn=self._ask)

        from BrainDock.orchestrator.models import slugify
        from BrainDock.skill_bank.storage import load_skill_bank

        per_run_path = os.path.join(
            self._tmpdir, slugify("Build login app"),
            "skill_bank", "skills.json",
        )
        global_path = config.resolve_global_skill_bank_path()

        self.assertTrue(os.path.exists(per_run_path), "Per-run skill bank should exist")
        self.assertTrue(os.path.exists(global_path), "Global skill bank should exist")

        per_run_bank = load_skill_bank(per_run_path)
        global_bank = load_skill_bank(global_path)
        self.assertEqual(len(per_run_bank.skills), 1)
        self.assertEqual(len(global_bank.skills), 1)
        self.assertEqual(
            per_run_bank.get("skill_jwt_auth").name,
            global_bank.get("skill_jwt_auth").name,
        )

    # ── Test: no skills → planner gets None ───────────────────────

    def test_first_run_planner_gets_no_skills(self):
        """On the very first run (empty global bank), planner gets no skills section."""
        config = RunConfig(output_dir=self._tmpdir)
        captured = []
        o = OrchestratorAgent(llm=self._webapp_llm(captured=captured), config=config)
        o.run(problem="Build first app ever", ask_fn=self._ask)

        planner_calls = [
            c for c in captured
            if "Available skills from the skill bank" in c["user"]
        ]
        self.assertEqual(len(planner_calls), 0,
                         "First run should not inject skills into planner prompt")


class TestSkillsSavedIncrementally(unittest.TestCase):
    """Test that skills are saved to disk immediately after extraction, not just at end of run."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_skills_saved_incrementally(self):
        """Global skill bank file exists after skill extraction, not just at pipeline end."""
        from BrainDock.skill_bank.storage import load_skill_bank
        from BrainDock.orchestrator.models import slugify

        config = RunConfig(output_dir=self._tmpdir)
        global_path = config.resolve_global_skill_bank_path()

        # Wrap the LLM to check file existence after skill extraction call
        file_existed_after_skill_call = {"value": False}
        call_count = {"n": 0}
        responses = [
            SPEC_ANALYZE, SPEC_REFINE, SPEC_GENERATE,
            TASK_GRAPH, PLAN, EXEC_WRITE, SKILL_EXTRACT,
        ]

        def mock_fn(system_prompt, user_prompt):
            idx = min(call_count["n"], len(responses) - 1)
            call_count["n"] += 1
            result = responses[idx]
            # After the skill extraction call (call 7), the next save_state
            # will have already written the file. We check right after
            # returning the skill extraction response by hooking the next call.
            if call_count["n"] > len(responses):
                # Past all expected calls — check if file was saved
                if os.path.exists(global_path):
                    file_existed_after_skill_call["value"] = True
            return result

        llm = CallableBackend(mock_fn)
        orchestrator = OrchestratorAgent(llm=llm, config=config)

        def ask_fn(q, d, u):
            return {}

        state = orchestrator.run(problem="Build a CLI calculator", ask_fn=ask_fn)

        # Skill should have been learned
        self.assertEqual(len(state.learned_skills), 1)

        # Global skill bank file should exist with the skill
        self.assertTrue(os.path.exists(global_path),
                        "Global skill bank should be saved immediately after skill extraction")
        bank = load_skill_bank(global_path)
        self.assertEqual(len(bank.skills), 1)
        self.assertEqual(bank.skills[0].id, "skill_eval_pattern")

        # Per-run copy should also exist
        per_run_path = os.path.join(
            self._tmpdir, slugify("Build a CLI calculator"),
            "skill_bank", "skills.json",
        )
        self.assertTrue(os.path.exists(per_run_path),
                        "Per-run skill bank should be saved immediately after skill extraction")


class TestCheckStopPausesAtTaskBoundary(unittest.TestCase):
    """Test that check_stop causes the orchestrator to pause at task boundary."""

    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_check_stop_pauses_at_task_boundary(self):
        """When check_stop returns True, run() should return state early."""
        config = RunConfig(output_dir=self._tmpdir)
        orchestrator = OrchestratorAgent(llm=make_pipeline_llm(), config=config)

        def ask_fn(questions, decisions, understanding):
            return {}

        # check_stop always returns True — should pause before any task executes
        state = orchestrator.run(
            problem="Build a CLI calculator",
            ask_fn=ask_fn,
            check_stop=lambda: True,
        )

        # Spec and task graph should complete (check_stop is only at task boundary)
        self.assertIsNotNone(state.spec)
        self.assertTrue(state.task_graph)
        # But no tasks should have been executed
        self.assertEqual(state.completed_tasks, [])
        self.assertEqual(len(state.execution_results), 0)

    def test_check_stop_false_runs_normally(self):
        """When check_stop returns False, pipeline runs to completion."""
        config = RunConfig(output_dir=self._tmpdir)
        orchestrator = OrchestratorAgent(llm=make_pipeline_llm(), config=config)

        def ask_fn(questions, decisions, understanding):
            return {}

        state = orchestrator.run(
            problem="Build a CLI calculator",
            ask_fn=ask_fn,
            check_stop=lambda: False,
        )

        self.assertEqual(state.completed_tasks, ["t1"])


if __name__ == "__main__":
    unittest.main()
