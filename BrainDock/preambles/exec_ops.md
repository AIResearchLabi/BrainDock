# Execution Operations Context

## Quality Philosophy
- Working > perfect. Ship incrementally, improve iteratively.
- Every code change should be verifiable — if you can't test it, rethink it.
- When execution fails, understand WHY before retrying. Blind retries waste budget.
- Prefer small, atomic changes that can be individually verified over large sweeping changes.

## Execution Priorities
1. Correctness — does it produce the right output?
2. Safety — does it handle edge cases and bad input?
3. Clarity — can someone else read and maintain this?
4. Performance — is it fast enough for the use case?

## Debugging Approach
- Start with the error message, not the code.
- Reproduce before fixing. If you can't reproduce, you can't verify the fix.
- Root cause > symptom fix. Patching symptoms creates tech debt.
- Check assumptions: wrong assumptions are the #1 source of bugs.
- When stuck, reduce scope: isolate the smallest failing unit.

## File & Code Generation
- Write complete, runnable files. No placeholders or "TODO: implement this".
- Respect existing code style and conventions in the project.
- Generated code should pass linting and type-checking without modifications.
- Include necessary imports, handle edge cases, close resources properly.

## Constraints
- Max acceptable build time: (customize)
- Resource limits: (customize — memory, CPU, disk, API rate limits)
- External dependencies to be careful with: (customize)

## What I Know About Running This
(Add your operational context here — known failure modes, monitoring setup,
deployment procedures, rollback strategy, environment quirks, etc.)
