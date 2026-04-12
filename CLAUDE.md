# Claude Code Instructions

## Quality Checks

Run both checks before committing and after making changes:

```bash
uv run ruff check . --fix
uv run mypy . --pretty
```

On Windows, mypy may crash with UnicodeEncodeError when source files contain
non-ASCII characters (e.g. Cyrillic comments). Use the UTF-8 override:

```bash
PYTHONUTF8=1 uv run mypy . --pretty
```

Both commands must exit with no errors before a commit is made.

## Workflow Rules

Every change to the project must follow this sequence:

1. Make code changes
2. Run quality checks (ruff + mypy — both must pass, see above)
3. Update user-facing documentation (`README.md`, `MANUAL.md`) if the change adds, removes, or alters visible functionality
4. Bump the version in `pyproject.toml`
5. Run `uv sync` to update the lock file after the version bump
6. Commit with a descriptive message
