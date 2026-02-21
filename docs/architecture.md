# BrainDock Architecture Reference

## Directory Structure

```
BrainDock/
├── __init__.py, __main__.py     # Package root + CLI entry
├── llm.py                       # LLMBackend protocol + 3 implementations
├── base_agent.py                # BaseAgent with _llm_query_json (3 retries)
├── session.py                   # SessionMixin (JSON save/load/clear)
├── project_memory.py            # ProjectSnapshot (file tree + contents, 50KB cap)
├── preambles/                   # User-editable .md files auto-prepended to prompts
│   ├── __init__.py              # get_preamble(), build_system_prompt()
│   ├── dev_ops.md, exec_ops.md, business_ops.md
├── spec_agent/                  # Mode 1: Interactive specification
├── task_graph/                  # Mode 2: Dependency graph decomposition
├── planner/                     # Mode 3: Step-by-step action plans
├── controller/                  # Mode 4: Deterministic quality gates (no LLM)
├── executor/                    # Mode 5: Sandboxed execution + verification
├── skill_bank/                  # Mode 6: Reusable skill extraction
├── reflection/                  # Mode 7: Failure analysis (max 2 iterations)
├── debate/                      # Mode 8: Multi-perspective resolution (max 3 rounds)
├── market_study/                # Bonus: Competitive analysis (tagged tasks)
├── orchestrator/                # Pipeline coordinator + CLI
│   ├── agent.py                 # OrchestratorAgent.run() — main loop
│   ├── models.py                # Mode enum, RunConfig, PipelineState
│   └── cli.py                   # Full-system CLI
└── dashboard/                   # Web UI
    ├── server.py                # HTTP server + REST API
    ├── runner.py                # Thread-safe pipeline runner
    └── index.html               # Single-page dashboard
```

## Module Pattern
Each agent module follows: `agent.py` (logic), `models.py` (dataclasses), `prompts.py` (templates), `__init__.py`.

## Key Configuration (RunConfig)
- max_task_retries=2, max_reflection_iterations=2, max_debate_rounds=3
- min_confidence=0.6, max_entropy=0.7
- enable_human_escalation=True, escalation_token_budget=50000

## Pipeline Flow
```
SPEC (ask_fn) → TASK_GRAPH → per-task waves:
  PLAN → GATE (confidence/entropy) → [DEBATE if uncertain] →
  EXECUTE → VERIFY → [REFLECT if failed, up to 2x] →
  [ESCALATE to human if stuck] → SKILL_LEARN (if success)
```

## Human Escalation (3 triggers)
1. Reflection detects needs_human (auth, credentials, external setup, physical action)
2. All reflection retries exhausted
3. Token budget exceeded per task
Options: skip (mark failed), retry with hint, abort pipeline

## LLM Backends
- `ClaudeCLIBackend`: `claude -p --dangerously-skip-permissions` subprocess, 900s timeout
- `CallableBackend`: wraps `(sys, user) -> str` for tests
- `LoggingBackend`: decorator — logs ts, agent, duration, prompts, response, est tokens

## Testing
- 261 tests, unittest only, no external deps
- `python -m unittest discover -s tests -v`
- All tests use CallableBackend with pre-recorded JSON responses
- Each module has tests/<module>/test_<module>.py

## Dashboard REST API
- GET: /api/state, /api/runs, /api/activities?since=N, /api/chat?since=N, /api/logs?since=N
- POST: /api/start {title,problem}, /api/resume {title}, /api/answers {answers}, /api/chat {message}

## Output Structure
```
output/<slug>/
├── pipeline_state.json          # Resume state + dashboard polling
├── spec_agent/spec.json, spec.md
├── task_graph/task_graph.json
├── project/                     # Generated project files
├── skill_bank/skills.json       # Persisted learned skills
├── dashboard_chat.json          # Chat history
├── dashboard_activities.json    # Activity log
└── dashboard_llm_logs.json      # LLM call log
```
