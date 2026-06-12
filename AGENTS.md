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

## Architectural Principles

The project must follow these principles as non-negotiable foundations:

1. **SSOT (Single Source of Truth)**
   - Every persistent project setting must have exactly one canonical source in the data model.
   - UI, renderer, export pipeline, and headless API must read from the same source instead of duplicating state.

2. **DRY (Don't Repeat Yourself)**
   - Validation rules, default values, and transformation logic must be defined once and reused.
   - Avoid parallel representations of the same setting in multiple layers.

3. **SRP (Single Responsibility Principle)**
   - `ProjectData` / models: structure and validation of persistent data
   - `ProjectManager`: mutation of project state and undo/redo
   - `ProjectController`: Qt-compatible proxy over manager
   - `ProjectRenderer`: drawing on matplotlib axes
   - `export.py`: figure/export layout and file output
   - `ui/`: user interaction only, without business logic duplication

### Practical Rules

- If a setting is saved to JSON, it must live in the model layer.
- Renderer must not be the source of truth for project settings.
- GUI widgets must not own persistent state that duplicates project data.
- Backward compatibility migrations must happen at model boundary, not be scattered across UI/business logic.

## Workflow Rules

Every change to the project must follow this sequence:

1. Make code changes
2. Run quality checks (ruff + mypy — both must pass, see above)
