"""Prompt templates for the Controller.

Note: The Controller uses deterministic threshold checks, not LLM calls.
This file exists for consistency with other modules but contains only
documentation of the gate logic.
"""

# Controller gate logic is deterministic — no LLM prompts needed.
#
# Plan Gate:
#   - confidence >= min_confidence AND entropy <= max_entropy → PROCEED
#   - entropy > max_entropy → DEBATE
#   - confidence < min_confidence → REFLECT
#
# Execution Gate:
#   - success == True → PROCEED
#   - failure_count < max_failures → REFLECT
#   - failure_count >= max_failures → ABORT
#
# Reflection Gate:
#   - reflection_count < max_reflection_iterations → allow another reflection
#   - reflection_count >= max_reflection_iterations → ABORT
