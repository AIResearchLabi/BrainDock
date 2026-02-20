# BrainDock

Autonomous AI Project Creator — an 8-mode gated pipeline that takes a problem statement and autonomously builds a complete project through specification, planning, execution, and learning.

## Architecture: 8-Mode Gated Pipeline

```
USER INPUT → SPECIFICATION → TASK GRAPH → PLANNING → CONTROLLER
→ EXECUTION → SKILL LEARNING → (REFLECTION on failure) → (DEBATE on uncertainty) → LOOP
```

| Mode | Module | Description |
|------|--------|-------------|
| 1 | `spec_agent` | Interactive project specification builder |
| 2 | `task_graph` | Task decomposition into dependency graph |
| 3 | `planner` | Detailed action planning with confidence metrics |
| 4 | `controller` | Deterministic quality gates (no LLM calls) |
| 5 | `executor` | Sandboxed task execution with budget enforcement |
| 6 | `skill_bank` | Reusable skill/pattern library (persists across runs) |
| 7 | `reflection` | Failure root-cause analysis (max 2 iterations) |
| 8 | `debate` | Multi-perspective reasoning for uncertain plans (max 3 rounds) |

## Quick Start

```bash
# Run the full pipeline
python -m BrainDock "Build a todo app with authentication"

# Plan only (skip execution)
python -m BrainDock --plan-only "Build a todo app"

# See all options
python -m BrainDock --help
```

### Individual Modules

```bash
# Specification only
python -m BrainDock.spec_agent "Build a todo app with auth"

# Task decomposition (from a spec.json)
python -m BrainDock.task_graph output/spec_agent/spec.json

# Planning (from a task_graph.json)
python -m BrainDock.planner output/task_graph/task_graph.json

# Execution (from a plan.json)
python -m BrainDock.executor output/planner/plan_t1.json
```

### Library Usage

```python
from BrainDock.orchestrator import OrchestratorAgent, RunConfig

config = RunConfig(output_dir="output", skip_execution=False)
orchestrator = OrchestratorAgent(config=config)

def ask_fn(questions, decisions, understanding):
    # Handle user interaction
    return {q.id: q.options[0] for q in questions}

state = orchestrator.run(problem="Build a todo app", ask_fn=ask_fn)
print(f"Completed: {state.completed_tasks}")
print(f"Skills learned: {len(state.learned_skills)}")
```

### Using Individual Agents

```python
# Spec Agent
from BrainDock.spec_agent import SpecAgent, ProjectSpec
agent = SpecAgent(problem="Build a todo app")
spec = agent.run(ask_fn=my_handler)

# Task Graph
from BrainDock.task_graph import TaskGraphAgent
agent = TaskGraphAgent()
graph = agent.decompose(spec.to_dict())

# Planner
from BrainDock.planner import PlannerAgent
agent = PlannerAgent()
plan = agent.plan_task(task.to_dict(), context="Project context")

# Controller (no LLM needed — deterministic)
from BrainDock.controller import ControllerAgent
controller = ControllerAgent()
gate = controller.check_plan_gate(plan.to_dict())

# Executor
from BrainDock.executor import ExecutorAgent
agent = ExecutorAgent()
result = agent.execute(plan.to_dict(), project_dir="./output/project")

# Skill Bank
from BrainDock.skill_bank import SkillLearningAgent, load_skill_bank, save_skill_bank
agent = SkillLearningAgent()
skill = agent.extract_skill(task_desc, solution, outcome)
bank = load_skill_bank()
bank.add(skill)
save_skill_bank(bank)

# Reflection (on failure)
from BrainDock.reflection import ReflectionAgent
agent = ReflectionAgent()
result = agent.reflect(execution_result, plan, context)

# Debate (on uncertainty)
from BrainDock.debate import DebateAgent
agent = DebateAgent()
outcome = agent.debate(plan.to_dict(), context)
```

## Project Structure

```
BrainDock/
├── __init__.py              # Shared exports (LLMBackend, BaseAgent, etc.)
├── __main__.py              # python -m BrainDock entry point
├── llm.py                   # LLM backend protocol + ClaudeCLI + Callable
├── base_agent.py            # BaseAgent with _llm_query_json() helper
├── session.py               # SessionMixin for JSON persistence
├── spec_agent/              # Mode 1: Specification
│   ├── agent.py             # SpecAgent: analyze → ask → refine → generate
│   ├── cli.py               # Interactive terminal UI
│   ├── models.py            # ProjectSpec, Question, Decision, etc.
│   ├── output.py            # JSON + Markdown formatters
│   └── prompts.py           # LLM prompt templates
├── task_graph/              # Mode 2: Task Graph
│   ├── agent.py             # TaskGraphAgent.decompose()
│   ├── models.py            # TaskNode, RiskNode, TaskGraph
│   ├── output.py            # JSON + Markdown formatters
│   └── prompts.py           # Decomposition prompt
├── planner/                 # Mode 3: Planning
│   ├── agent.py             # PlannerAgent with entropy threshold
│   ├── models.py            # ActionStep, PlanMetrics, ActionPlan
│   ├── output.py            # JSON + Markdown formatters
│   └── prompts.py           # Planning prompt
├── controller/              # Mode 4: Quality Gates
│   ├── agent.py             # Deterministic threshold checks
│   ├── models.py            # GateThresholds, GateResult, ControllerState
│   └── prompts.py           # Documentation only (no LLM calls)
├── executor/                # Mode 5: Execution
│   ├── agent.py             # ExecutorAgent with budget enforcement
│   ├── models.py            # TaskOutcome, StopCondition, ExecutionResult
│   ├── prompts.py           # Execution + verification prompts
│   └── sandbox.py           # Safe command execution utilities
├── skill_bank/              # Mode 6: Skill Learning
│   ├── agent.py             # SkillLearningAgent
│   ├── models.py            # Skill, SkillBank
│   ├── prompts.py           # Extraction + matching prompts
│   └── storage.py           # JSON persistence
├── reflection/              # Mode 7: Reflection
│   ├── agent.py             # ReflectionAgent (max 2 iterations)
│   ├── models.py            # RootCause, PlanModification, ReflectionResult
│   └── prompts.py           # Root-cause analysis prompt
├── debate/                  # Mode 8: Debate
│   ├── agent.py             # DebateAgent (max 3 rounds)
│   ├── models.py            # DebatePlan, Critique, DebateOutcome
│   └── prompts.py           # Propose, critique, synthesize prompts
└── orchestrator/            # Pipeline Orchestrator
    ├── agent.py             # OrchestratorAgent main loop
    ├── cli.py               # Full-system CLI with progress display
    └── models.py            # Mode enum, PipelineState, RunConfig

tests/
├── spec_agent/test_agent.py        # 28 tests
├── task_graph/test_task_graph.py    # 18 tests
├── planner/test_planner.py          # 13 tests
├── controller/test_controller.py    # 20 tests
├── executor/test_executor.py        # 17 tests
├── skill_bank/test_skill_bank.py    # 15 tests
├── reflection/test_reflection.py    # 10 tests
├── debate/test_debate.py            # 9 tests
└── orchestrator/test_orchestrator.py # 8 tests (incl. E2E)

output/                              # All module outputs (gitignored)
├── spec_agent/<slug>/               # Per-project spec output
├── task_graph/                      # Task dependency graph
├── planner/                         # Action plans
├── skill_bank/skills.json           # Persistent skill library
└── project/                         # Generated project files
```

## Key Design Decisions

- **Zero external dependencies** — Python 3.10+ stdlib only, uses `claude -p` CLI as LLM backend
- **Protocol-based LLM backend** — `ClaudeCLIBackend` for production, `CallableBackend` for testing
- **Controller uses deterministic threshold checks** — no LLM calls, fast and cheap
- **Orchestrator stores all intermediate state as dicts** — avoids circular import issues
- **Each module only imports from shared infra** and its own models
- **Skill Bank persists to `output/skill_bank/skills.json`** — survives across runs
- **spec_agent is not refactored** — backward compatibility via re-exports from `BrainDock.llm`

## Running Tests

```bash
# All tests (136 total)
python -m unittest discover -s tests -v

# Individual module tests
python -m unittest tests.spec_agent.test_agent -v
python -m unittest tests.task_graph.test_task_graph -v
python -m unittest tests.planner.test_planner -v
python -m unittest tests.controller.test_controller -v
python -m unittest tests.executor.test_executor -v
python -m unittest tests.skill_bank.test_skill_bank -v
python -m unittest tests.reflection.test_reflection -v
python -m unittest tests.debate.test_debate -v
python -m unittest tests.orchestrator.test_orchestrator -v
```

## Requirements

- Python 3.10+
- `claude` CLI (Claude Code) for the default LLM backend
- No pip dependencies required
