"""End-to-end tests for SpecAgent with mock LLM backend.

Tests two use cases:
1. Todo app with authentication
2. Inventory management API
Also tests: session resume, zero-question flow, decision-only flow.
"""

import json
import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))

from BrainDock.spec_agent.agent import SpecAgent, AnalyzeResult
from BrainDock.spec_agent.llm import CallableBackend, extract_json
from BrainDock.spec_agent.models import ProjectSpec, Question, Decision, FunctionalRequirement, Milestone
from BrainDock.spec_agent.output import to_json, to_markdown, save_spec


# ── Mock LLM Responses ──────────────────────────────────────────────────

TODO_ANALYZE_RESPONSE = json.dumps({
    "understanding": "The user wants to build a todo application with user authentication.",
    "self_decided": [
        {
            "id": "d1",
            "topic": "Tech Stack",
            "decision": "React + TypeScript frontend, Python FastAPI backend, PostgreSQL database. Industry standard for this type of app."
        },
        {
            "id": "d2",
            "topic": "Architecture",
            "decision": "Client-server SPA with REST API. JWT-based stateless auth with bcrypt password hashing."
        },
        {
            "id": "d3",
            "topic": "Data Model",
            "decision": "Users table, Tasks table with foreign key to Users, Categories table for organization."
        }
    ],
    "user_questions": [
        {
            "id": "q1",
            "question": "What is the target scope: personal use only, or should it support shared/collaborative task lists?",
            "why": "Collaboration fundamentally changes the data model, permissions system, and feature scope",
            "options": ["Personal use only", "Shared lists with other users", "Full team workspaces"]
        },
        {
            "id": "q2",
            "question": "What's your priority: ship fast with basic features, or build a complete task management tool?",
            "why": "This determines MVP scope — basic CRUD vs full features like subtasks, recurring tasks, reminders",
            "options": ["MVP (create, complete, delete tasks)", "Standard (+ due dates, priorities, categories)", "Full-featured (+ subtasks, recurring, attachments, reminders)"]
        }
    ]
})

TODO_REFINE_RESPONSE = json.dumps({
    "ready": True,
    "understanding": "Building a personal web-based todo app with standard features (due dates, priorities, categories). No collaboration needed. Optimizing for a solid MVP.",
    "self_decided": [
        {
            "id": "d4",
            "topic": "Auth flow",
            "decision": "Email/password registration with JWT. No OAuth for MVP — keeps it simple."
        }
    ],
    "user_questions": []
})

TODO_SPEC_RESPONSE = json.dumps({
    "title": "TaskFlow — Personal Todo Application",
    "summary": "A web-based personal task management application with email/password authentication, supporting task organization with due dates, priorities, and categories.",
    "problem_statement": "Users need a simple, personal task management tool that helps them organize daily tasks with priorities and deadlines, accessible via any web browser.",
    "goals": [
        "Provide a clean, fast interface for managing personal tasks",
        "Secure user data with email/password authentication",
        "Support task organization via categories, priorities, and due dates",
        "Enable quick task capture and completion tracking"
    ],
    "target_users": "Individual users who want a lightweight personal task manager.",
    "user_stories": [
        "As a user, I want to sign up with email/password so that my tasks are private",
        "As a user, I want to create tasks with a title and optional description",
        "As a user, I want to set due dates on tasks so I know deadlines",
        "As a user, I want to assign priorities (high/medium/low)",
        "As a user, I want to organize tasks into categories",
        "As a user, I want to mark tasks as complete"
    ],
    "functional_requirements": [
        {
            "feature": "User Authentication",
            "description": "Email/password registration and login with JWT",
            "acceptance_criteria": ["User can register", "User can log in", "Passwords are hashed"],
            "priority": "must-have"
        },
        {
            "feature": "Task CRUD",
            "description": "Create, read, update, and delete tasks",
            "acceptance_criteria": ["Create task with title", "View task list", "Edit tasks", "Delete tasks"],
            "priority": "must-have"
        },
        {
            "feature": "Task Organization",
            "description": "Due dates, priorities, and categories",
            "acceptance_criteria": ["Set due dates", "Assign priority", "Create categories", "Filter tasks"],
            "priority": "must-have"
        }
    ],
    "non_functional_requirements": ["Page load under 2s", "HTTPS everywhere"],
    "tech_stack": {
        "frontend": "React with TypeScript",
        "backend": "Python FastAPI",
        "database": "PostgreSQL"
    },
    "architecture_overview": "Client-server SPA with REST API and JWT auth.",
    "data_models": [
        {"name": "User", "fields": {"id": "UUID", "email": "string", "password_hash": "string"}, "relationships": "Has many Tasks"},
        {"name": "Task", "fields": {"id": "UUID", "title": "string", "due_date": "date", "priority": "enum"}, "relationships": "Belongs to User"}
    ],
    "api_endpoints": [
        {"method": "POST", "path": "/api/auth/register", "description": "Register"},
        {"method": "POST", "path": "/api/auth/login", "description": "Login"},
        {"method": "GET", "path": "/api/tasks", "description": "List tasks"},
        {"method": "POST", "path": "/api/tasks", "description": "Create task"}
    ],
    "milestones": [
        {"name": "MVP", "description": "Core task management with auth", "deliverables": ["Auth", "Task CRUD", "Basic UI"]}
    ],
    "constraints": ["Single developer"],
    "assumptions": ["Modern browser", "No offline support for MVP"],
    "open_questions": ["Email notifications?", "Dark mode?"]
})


INVENTORY_ANALYZE_RESPONSE = json.dumps({
    "understanding": "The user wants to build an API for inventory management.",
    "self_decided": [
        {
            "id": "d1",
            "topic": "Tech Stack",
            "decision": "Python FastAPI with PostgreSQL and Redis caching. Proven stack for transactional inventory systems."
        },
        {
            "id": "d2",
            "topic": "Architecture",
            "decision": "Stateless REST API with row-level locking for atomic stock operations. API key auth."
        },
        {
            "id": "d3",
            "topic": "Data Model",
            "decision": "Products with SKU, Warehouses with locations, StockEntry as the join with quantity tracking."
        }
    ],
    "user_questions": [
        {
            "id": "q1",
            "question": "What type of inventory: e-commerce products, warehouse goods, digital assets, or raw materials?",
            "why": "Different inventory types have fundamentally different tracking and workflow needs",
            "options": ["E-commerce products", "Warehouse/physical goods", "Digital assets/licenses", "Raw materials"]
        }
    ]
})

INVENTORY_REFINE_RESPONSE = json.dumps({
    "ready": True,
    "understanding": "Building a REST API for e-commerce product inventory with multi-warehouse support.",
    "self_decided": [],
    "user_questions": []
})

INVENTORY_SPEC_RESPONSE = json.dumps({
    "title": "StockAPI — E-commerce Inventory Management API",
    "summary": "A RESTful API for managing e-commerce product inventory across multiple warehouse locations.",
    "problem_statement": "E-commerce businesses need reliable inventory tracking across warehouses.",
    "goals": ["Real-time inventory tracking", "Prevent overselling", "Audit trail"],
    "target_users": "E-commerce backend developers.",
    "user_stories": ["As a developer, I want to query stock levels by product and location"],
    "functional_requirements": [
        {"feature": "Product Management", "description": "CRUD for products", "acceptance_criteria": ["Create products", "SKU lookup"], "priority": "must-have"},
        {"feature": "Stock Tracking", "description": "Track stock per product per location", "acceptance_criteria": ["Query stock", "Atomic updates"], "priority": "must-have"}
    ],
    "non_functional_requirements": ["API response under 100ms", "ACID transactions"],
    "tech_stack": {"backend": "Python FastAPI", "database": "PostgreSQL", "cache": "Redis"},
    "architecture_overview": "Stateless REST API with PostgreSQL and Redis.",
    "data_models": [{"name": "Product", "fields": {"id": "UUID", "sku": "string"}, "relationships": "Has many StockEntries"}],
    "api_endpoints": [
        {"method": "GET", "path": "/api/products", "description": "List products"},
        {"method": "POST", "path": "/api/stock/adjust", "description": "Adjust stock"}
    ],
    "milestones": [{"name": "MVP", "description": "Core product and stock management", "deliverables": ["Product CRUD", "Stock adjustments"]}],
    "constraints": ["API-only"],
    "assumptions": ["Stock quantities are non-negative integers"],
    "open_questions": ["CSV batch import?"]
})


# Zero user questions scenario — LLM decides everything
CLEAR_PROBLEM_ANALYZE = json.dumps({
    "understanding": "The user wants a CLI calculator in Python. Very clear requirements.",
    "self_decided": [
        {"id": "d1", "topic": "Language", "decision": "Python 3.11+ as specified."},
        {"id": "d2", "topic": "Interface", "decision": "REPL-style CLI with readline support."},
        {"id": "d3", "topic": "Features", "decision": "Basic arithmetic, parentheses, variables, history."}
    ],
    "user_questions": []
})

CLEAR_PROBLEM_SPEC = json.dumps({
    "title": "PyCalc — CLI Calculator",
    "summary": "A Python CLI calculator with REPL interface.",
    "problem_statement": "Need a command-line calculator.",
    "goals": ["Fast arithmetic evaluation"],
    "target_users": "Developers",
    "user_stories": ["As a user, I want to type expressions and see results"],
    "functional_requirements": [
        {"feature": "Expression evaluation", "description": "Parse and evaluate arithmetic", "acceptance_criteria": ["Supports +, -, *, /"], "priority": "must-have"}
    ],
    "non_functional_requirements": ["Instant response"],
    "tech_stack": {"language": "Python"},
    "architecture_overview": "Single-file REPL.",
    "data_models": [],
    "api_endpoints": [],
    "milestones": [{"name": "v1.0", "description": "Full calculator", "deliverables": ["REPL", "Arithmetic"]}],
    "constraints": ["No external dependencies"],
    "assumptions": ["Python 3.11+"],
    "open_questions": []
})


# ── Mock LLM Backend ────────────────────────────────────────────────────

def make_mock_llm(scenario: str):
    """Create a mock LLM backend that returns canned responses."""
    responses = {
        "todo": [TODO_ANALYZE_RESPONSE, TODO_REFINE_RESPONSE, TODO_SPEC_RESPONSE],
        "inventory": [INVENTORY_ANALYZE_RESPONSE, INVENTORY_REFINE_RESPONSE, INVENTORY_SPEC_RESPONSE],
        "clear": [CLEAR_PROBLEM_ANALYZE, CLEAR_PROBLEM_SPEC],
    }
    call_count = {"n": 0}

    def mock_query(system_prompt: str, user_prompt: str) -> str:
        idx = min(call_count["n"], len(responses[scenario]) - 1)
        call_count["n"] += 1
        return responses[scenario][idx]

    return CallableBackend(mock_query)


# ── Tests ────────────────────────────────────────────────────────────────

class TestExtractJson(unittest.TestCase):
    def test_plain_json(self):
        result = extract_json('{"key": "value"}')
        self.assertEqual(result, {"key": "value"})

    def test_json_in_code_fence(self):
        text = '```json\n{"key": "value"}\n```'
        result = extract_json(text)
        self.assertEqual(result, {"key": "value"})

    def test_json_in_bare_fence(self):
        text = '```\n{"key": "value"}\n```'
        result = extract_json(text)
        self.assertEqual(result, {"key": "value"})


class TestModels(unittest.TestCase):
    def test_question_to_dict(self):
        q = Question(id="q1", question="test?", why="because", options=["a", "b"])
        d = q.to_dict()
        self.assertEqual(d["id"], "q1")
        self.assertEqual(len(d["options"]), 2)

    def test_decision_to_dict(self):
        d = Decision(id="d1", topic="Stack", decision="Use Python")
        dd = d.to_dict()
        self.assertEqual(dd["topic"], "Stack")
        self.assertEqual(dd["decision"], "Use Python")

    def test_project_spec_roundtrip(self):
        data = json.loads(TODO_SPEC_RESPONSE)
        spec = ProjectSpec.from_dict(data)
        self.assertEqual(spec.title, "TaskFlow — Personal Todo Application")
        self.assertEqual(len(spec.goals), 4)
        self.assertEqual(len(spec.functional_requirements), 3)
        self.assertIsInstance(spec.functional_requirements[0], FunctionalRequirement)
        self.assertEqual(len(spec.milestones), 1)
        self.assertIsInstance(spec.milestones[0], Milestone)

        d = spec.to_dict()
        self.assertEqual(d["title"], spec.title)

    def test_project_spec_to_json(self):
        data = json.loads(TODO_SPEC_RESPONSE)
        spec = ProjectSpec.from_dict(data)
        j = spec.to_json()
        parsed = json.loads(j)
        self.assertEqual(parsed["title"], spec.title)


class TestAgent(unittest.TestCase):
    def test_todo_app_full_flow(self):
        """E2E: todo app — LLM decides tech, asks user about scope."""
        mock = make_mock_llm("todo")
        agent = SpecAgent(problem="Build a todo app with authentication", llm=mock)

        # Step 1: Analyze — should have decisions AND questions
        result = agent.analyze()
        self.assertIsInstance(result, AnalyzeResult)
        self.assertGreater(len(result.decisions), 0)
        self.assertGreater(len(result.questions), 0)
        self.assertEqual(len(result.questions), 2)  # only critical ones
        self.assertTrue(agent.understanding)

        # Step 2: Refine
        answers = {q.id: q.options[0] for q in result.questions}
        result2 = agent.refine(answers)
        self.assertTrue(result2.ready)

        # Step 3: Generate spec
        spec = agent.generate_spec()
        self.assertIsInstance(spec, ProjectSpec)
        self.assertEqual(spec.title, "TaskFlow — Personal Todo Application")

    def test_inventory_api_full_flow(self):
        """E2E: inventory API — LLM decides most, asks user 1 question."""
        mock = make_mock_llm("inventory")
        agent = SpecAgent(problem="Create an API for inventory management", llm=mock)

        result = agent.analyze()
        self.assertEqual(len(result.decisions), 3)
        self.assertEqual(len(result.questions), 1)  # only 1 critical question

        answers = {q.id: q.options[0] for q in result.questions}
        result2 = agent.refine(answers)
        self.assertTrue(result2.ready)

        spec = agent.generate_spec()
        self.assertEqual(spec.title, "StockAPI — E-commerce Inventory Management API")

    def test_zero_user_questions_flow(self):
        """When problem is clear, LLM decides everything — no user questions."""
        mock = make_mock_llm("clear")
        agent = SpecAgent(problem="Build a CLI calculator in Python", llm=mock)

        result = agent.analyze()
        self.assertGreater(len(result.decisions), 0)
        self.assertEqual(len(result.questions), 0)  # no user questions!

    def test_run_with_callback(self):
        """Test run() with the new 3-arg callback signature."""
        mock = make_mock_llm("todo")
        agent = SpecAgent(problem="Build a todo app", llm=mock)

        callback_calls = []

        def ask_fn(questions, decisions, understanding):
            callback_calls.append({
                "questions": len(questions),
                "decisions": len(decisions),
            })
            return {q.id: q.options[0] if q.options else "auto" for q in questions}

        spec = agent.run(ask_fn=ask_fn)
        self.assertIsInstance(spec, ProjectSpec)
        self.assertTrue(spec.title)
        # Callback should have been called at least once
        self.assertGreater(len(callback_calls), 0)
        # First call should include decisions
        self.assertGreater(callback_calls[0]["decisions"], 0)

    def test_run_zero_questions(self):
        """run() completes without asking user when no questions needed."""
        mock = make_mock_llm("clear")
        agent = SpecAgent(problem="Build a CLI calculator in Python", llm=mock)

        callback_calls = []

        def ask_fn(questions, decisions, understanding):
            callback_calls.append({"questions": len(questions), "decisions": len(decisions)})
            return {}

        spec = agent.run(ask_fn=ask_fn)
        self.assertIsInstance(spec, ProjectSpec)
        self.assertEqual(spec.title, "PyCalc — CLI Calculator")
        # Callback called once (to show decisions), but with 0 questions
        self.assertEqual(callback_calls[0]["questions"], 0)
        self.assertGreater(callback_calls[0]["decisions"], 0)

    def test_max_rounds_enforced(self):
        """Agent should force spec generation after max rounds."""
        never_ready = json.dumps({
            "ready": False,
            "understanding": "Still not ready",
            "self_decided": [],
            "user_questions": [{"id": "q_extra", "question": "More?", "why": "Testing", "options": ["A"]}]
        })
        call_count = {"n": 0}
        responses = [TODO_ANALYZE_RESPONSE, never_ready, never_ready, TODO_SPEC_RESPONSE]

        def mock_fn(sys_prompt, user_prompt):
            idx = min(call_count["n"], len(responses) - 1)
            call_count["n"] += 1
            return responses[idx]

        agent = SpecAgent(
            problem="Test max rounds",
            llm=CallableBackend(mock_fn),
            max_rounds=2,
        )

        def ask_fn(questions, decisions, understanding):
            return {q.id: "auto" for q in questions}

        spec = agent.run(ask_fn=ask_fn)
        self.assertIsInstance(spec, ProjectSpec)

    def test_decisions_in_conversation_history(self):
        """Verify decisions appear in conversation history for the LLM."""
        mock = make_mock_llm("todo")
        agent = SpecAgent(problem="Build a todo app", llm=mock)
        agent.analyze()

        history = agent._build_history()
        self.assertIn("AGENT DECIDED:", history)
        self.assertIn("Tech Stack", history)
        self.assertIn("AGENT ASKED USER:", history)


class TestSessionResume(unittest.TestCase):
    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.mkdtemp()
        self.session_file = os.path.join(self._tmpdir, "session.json")

    def tearDown(self):
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_save_and_load_session(self):
        """Session file is created after analyze and can be loaded."""
        mock = make_mock_llm("todo")
        agent = SpecAgent(
            problem="Build a todo app",
            llm=mock,
            session_file=self.session_file,
        )
        result = agent.analyze()

        self.assertTrue(os.path.exists(self.session_file))

        loaded = SpecAgent.load_session(
            session_file=self.session_file,
            llm=make_mock_llm("todo"),
        )
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.problem, "Build a todo app")
        self.assertEqual(loaded._round, 1)
        self.assertIsNotNone(loaded._pending_questions)
        self.assertEqual(len(loaded._pending_questions), len(result.questions))
        # Decisions should also be restored
        self.assertIsNotNone(loaded._pending_decisions)
        self.assertEqual(len(loaded._pending_decisions), len(result.decisions))

    def test_resume_completes_successfully(self):
        """Simulate interrupt-and-resume."""
        call_count = {"n": 0}
        responses = [TODO_ANALYZE_RESPONSE, TODO_REFINE_RESPONSE, TODO_SPEC_RESPONSE]

        def mock_fn(sys_prompt, user_prompt):
            idx = min(call_count["n"], len(responses) - 1)
            call_count["n"] += 1
            return responses[idx]

        agent1 = SpecAgent(
            problem="Build a todo app",
            llm=CallableBackend(mock_fn),
            session_file=self.session_file,
        )
        agent1.analyze()
        # "Crash" here

        resume_responses = [TODO_REFINE_RESPONSE, TODO_SPEC_RESPONSE]
        resume_count = {"n": 0}

        def resume_fn(sys_prompt, user_prompt):
            idx = min(resume_count["n"], len(resume_responses) - 1)
            resume_count["n"] += 1
            return resume_responses[idx]

        agent2 = SpecAgent.load_session(
            session_file=self.session_file,
            llm=CallableBackend(resume_fn),
        )
        self.assertIsNotNone(agent2)

        def ask_fn(questions, decisions, understanding):
            return {q.id: q.options[0] if q.options else "auto" for q in questions}

        spec = agent2.run(ask_fn=ask_fn)
        self.assertIsInstance(spec, ProjectSpec)
        self.assertTrue(spec.title)
        self.assertFalse(os.path.exists(self.session_file))

    def test_load_session_returns_none_if_no_file(self):
        result = SpecAgent.load_session(session_file="/tmp/nonexistent_session.json")
        self.assertIsNone(result)

    def test_session_cleared_after_successful_run(self):
        mock = make_mock_llm("todo")
        agent = SpecAgent(
            problem="Build a todo app",
            llm=mock,
            session_file=self.session_file,
        )

        def ask_fn(questions, decisions, understanding):
            return {q.id: q.options[0] if q.options else "auto" for q in questions}

        agent.run(ask_fn=ask_fn)
        self.assertFalse(os.path.exists(self.session_file))


class TestCLIHelpers(unittest.TestCase):
    def test_slugify_basic(self):
        from BrainDock.spec_agent.cli import _slugify
        self.assertEqual(_slugify("Build a todo app"), "build-a-todo-app")

    def test_slugify_special_chars(self):
        from BrainDock.spec_agent.cli import _slugify
        self.assertEqual(
            _slugify("Create an API for inventory management!"),
            "create-an-api-for-inventory-management"
        )

    def test_slugify_truncation(self):
        from BrainDock.spec_agent.cli import _slugify
        long = "this is a very long problem statement that goes on and on and should be truncated at word boundary"
        result = _slugify(long, max_len=30)
        self.assertLessEqual(len(result), 30)
        self.assertFalse(result.endswith("-"))

    def test_slugify_empty(self):
        from BrainDock.spec_agent.cli import _slugify
        self.assertEqual(_slugify("!!!"), "project")

    def test_find_project_dir_creates_folder(self):
        from BrainDock.spec_agent.cli import _find_project_dir
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp()
        try:
            result = _find_project_dir("Build a todo app", base_dir=tmpdir)
            self.assertTrue(os.path.isdir(result))
            self.assertTrue(result.endswith("build-a-todo-app"))
        finally:
            shutil.rmtree(tmpdir)

    def test_same_problem_same_folder(self):
        from BrainDock.spec_agent.cli import _find_project_dir
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp()
        try:
            dir1 = _find_project_dir("Build a todo app", base_dir=tmpdir)
            dir2 = _find_project_dir("Build a todo app", base_dir=tmpdir)
            self.assertEqual(dir1, dir2)
        finally:
            shutil.rmtree(tmpdir)

    def test_find_existing_sessions(self):
        from BrainDock.spec_agent.cli import _find_existing_sessions
        import tempfile, shutil
        tmpdir = tempfile.mkdtemp()
        try:
            # Create a fake project with a session
            project = os.path.join(tmpdir, "test-project")
            os.makedirs(project)
            mock = make_mock_llm("todo")
            agent = SpecAgent(
                problem="test problem",
                llm=mock,
                session_file=os.path.join(project, "session.json"),
            )
            agent.analyze()

            sessions = _find_existing_sessions(tmpdir)
            self.assertEqual(len(sessions), 1)
            self.assertEqual(sessions[0]["slug"], "test-project")
            self.assertEqual(sessions[0]["problem"], "test problem")
        finally:
            shutil.rmtree(tmpdir)


class TestOutput(unittest.TestCase):
    def setUp(self):
        data = json.loads(TODO_SPEC_RESPONSE)
        self.spec = ProjectSpec.from_dict(data)

    def test_to_json(self):
        j = to_json(self.spec)
        parsed = json.loads(j)
        self.assertEqual(parsed["title"], self.spec.title)

    def test_to_markdown_structure(self):
        md = to_markdown(self.spec)
        self.assertIn("# TaskFlow", md)
        self.assertIn("## Problem Statement", md)
        self.assertIn("## Goals", md)
        self.assertIn("## User Stories", md)
        self.assertIn("## Functional Requirements", md)
        self.assertIn("## Tech Stack", md)
        self.assertIn("| Layer | Technology |", md)

    def test_save_spec(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path, md_path = save_spec(self.spec, output_dir=tmpdir)
            self.assertTrue(os.path.exists(json_path))
            self.assertTrue(os.path.exists(md_path))
            with open(json_path) as f:
                parsed = json.load(f)
                self.assertEqual(parsed["title"], self.spec.title)
            with open(md_path) as f:
                md = f.read()
                self.assertIn("# TaskFlow", md)


if __name__ == "__main__":
    unittest.main()
