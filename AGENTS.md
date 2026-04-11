# Agent Guidelines

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
