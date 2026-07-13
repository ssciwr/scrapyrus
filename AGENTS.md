# Repository Guidelines

## Project layout

* Package code lives in `src/scrapyrus/`.
* Tests live in `tests/` and use pytest.
* Put reusable functionality in the package.
* Put one-off scripts in `scripts/`; each must begin with a comment explaining its purpose.

## Development

* Use `uv` for dependency and environment management.
* The user creates Git worktrees.
* The agent must not create, remove, or switch worktrees.
* Each worktree has its own `.venv`; never share environments between worktrees.
* Run tests using the existing environment:

```bash
.venv/bin/python -m pytest
```

* Verify that the package resolves to the current worktree with:

```bash
.venv/bin/python -c "import scrapyrus; print(scrapyrus.__file__)"
```

* If `.venv` is missing or incomplete, ask the user to grant permission to initialize it with:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv sync --extra tests
```

* After permission is granted, initialize the environment, verify the import path, and continue the requested task.
* If the import path points to another worktree, ask for permission before deleting and recreating only the current worktree’s `.venv`.
* Do not use `pip install --editable`; `uv sync` installs the package in editable mode.
* Do not run `uv sync` during ordinary test runs unless the environment is missing or dependencies changed.
* Commit `uv.lock`.
* When dependencies change, update both `pyproject.toml` and `uv.lock`.
* Do not commit `.venv` or cache directories.

## Changes

* Keep changes focused.
* Add or update tests for behavior changes.
* Backwards compatibility is not required.
* Remove tests and fixtures that only preserve old behavior.
* Follow the existing style and use descriptive names.
* Do not modify unrelated or generated data.
