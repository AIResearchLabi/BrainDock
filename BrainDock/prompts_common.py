"""Shared prompt constants used across all BrainDock agents.

Consolidates repeated instructions to reduce token usage.
"""

JSON_FORMAT_INSTRUCTION = (
    "IMPORTANT: Always respond in valid JSON format as specified in each prompt. "
    "Do not include any text outside the JSON object."
)

JSON_FORMAT_INSTRUCTION_STRICT = (
    "CRITICAL: ALWAYS respond in valid JSON format as specified in each prompt. "
    "Do not include any text outside the JSON object. NEVER respond with prose, "
    "summaries, or explanations outside of JSON."
)

ASCII_ONLY_RULE = (
    "Use ONLY ASCII characters in code and descriptions. "
    "No Unicode arrows, bullets, em-dashes, or smart quotes "
    "(no \\u2192, \\u2022, \\u2014, \\u201c\\u201d). "
    "Use -> instead of \\u2192, - instead of \\u2022, -- instead of \\u2014."
)

CONTENT_FIELD_RULE = (
    'CRITICAL -- "content" field rules:\n'
    "- For write_file/edit_file: content MUST be COMPLETE, LITERAL source code "
    "ready to save and execute. NEVER a description or summary.\n"
    "- If the file is long, include the FULL source code. No abbreviations.\n"
    "- " + ASCII_ONLY_RULE
)

IMPORT_ISOLATION_RULE = (
    "CRITICAL -- Import isolation: Only import from (1) Python stdlib, "
    "(2) files YOU created in the project, (3) pip packages in requirements.txt. "
    "NEVER import from BrainDock, braindock, or parent framework modules."
)

POSIX_SHELL_RULES = (
    "CRITICAL -- Shell commands: Use POSIX-compatible syntax only.\n"
    "- No ( cmd ), [[ ]], arrays, process substitution, $() if avoidable.\n"
    "- No local keyword, no function keyword. Chain with && or ;."
)

TEST_SCOPING_RULE = (
    "CRITICAL -- Test scoping: ONLY run tests for the current task's module. "
    "NEVER run the full test suite.\n"
    '- BAD: "python -m unittest discover -s tests -v" (runs ALL, will timeout)\n'
    '- GOOD: "python -m unittest tests.module.test_X -v" (module-scoped)'
)

HUMAN_INTERACTION_RULE = (
    "CRITICAL -- Human interaction tasks: Write CODE for detection and escalation, "
    "do NOT perform human actions.\n"
    "- Write detection functions (e.g. detect_login_required())\n"
    "- Write escalation functions calling ask_fn (optional param, Callable | None)\n"
    "- Test with mocks. NEVER assume a real browser or human is present."
)

PATH_RULES = (
    "CRITICAL -- Path rules: Use RELATIVE paths from project root, not absolute.\n"
    '- BAD: "python /home/user/project/tests/test_foo.py"\n'
    '- GOOD: "python -m unittest tests.module.test_X -v"'
)

SKIP_ACTION_HINT = (
    'If work is ALREADY DONE, respond with action_type "skip" and '
    'content "Work already complete: <reason>".'
)
