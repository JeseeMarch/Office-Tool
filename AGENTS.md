# AGENTS.md

## Workflow

- Before making changes, assess the task objective; prioritize making only the minimum necessary modifications.
- Do not edit unrelated files.
- Avoid unnecessary, large-scale refactoring.
- Preserve existing behavior unless the task explicitly requires a change.
- Ask me before adding new dependencies.
- Do not claim to have executed commands that were not actually run.

## Python Project Rules

- Prioritize adhering to the project's existing code style.
- After modifying business logic, prioritize running the project's existing test commands.
- If the project uses `pytest`, run `python -m pytest`.
- If the project uses `uv`, prioritize running `uv run pytest`.
- If test commands are unavailable, explain why and provide instructions for manual verification.
- Do not automatically apply Node.js project commands—such as `npm test`—to Python projects by default.

## Output Requirements

- Briefly explain what changes were made.
- Indicate whether tests were executed.
- If tests were not executed, explain the reason.
- Highlight any potential risks or areas requiring my confirmation.