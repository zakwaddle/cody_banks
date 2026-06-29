# Python Skill

## When to use it

Use this skill for Python source changes, packaging, CLI behavior, tests, linting, typing, virtual environments, or dependency questions.

## Useful commands

```bash
python -m compileall cody_banks
python -m pytest
python -m unittest
python -m pip install -e .
python -m cody_banks.cli
```

## Project conventions

- Prefer standard library modules unless the project already depends on a package.
- Keep command line behavior in `cody_banks/cli.py`.
- Keep configuration parsing in `cody_banks/config.py`.
- Keep workspace path checks near workspace or tool code, not scattered through callers.
- Use dataclasses for small structured records when that matches the surrounding code.

## Common traps

- Do not assume optional tools like `pytest`, `ruff`, or `mypy` are installed.
- Do not write outside the workspace root.
- Do not hide network dependency installs inside tests or setup steps.
- Avoid broad refactors when the requested behavior is narrow.

## Done criteria

- Relevant Python files compile.
- CLI entry points still start.
- Behavior is covered by focused smoke checks or tests.
- Any skipped validation is stated clearly.
