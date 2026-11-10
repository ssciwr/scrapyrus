# Repository Guidelines

## Project layout

- Package code lives in `src/scrapyrus/`.
- Tests live in `tests/` and use pytest.
- Put reusable functionality in the package.
- Put one-off scripts in `scripts/`; each must begin with a comment explaining its purpose.
- Exception: `scripts/postgres_dump.sh` and `scripts/postgres_restore.sh` are maintained tools documented in the README, not one-off scripts.
- The published tables, `embedding_table_metadata`, and `public.scrapyrus_semantic_catalog` form the contract read by consumers such as papyri-assistant. A change to published tables, embedding specifications, or catalog meanings must update the catalog definitions in `src/scrapyrus/semantics.py` and, where the contract changes, `CATALOG_SCHEMA_VERSION` or `EMBEDDING_CONTRACT_VERSION` in the same change.

## Development

- Use `uv` for dependency and environment management.
- The user creates Git worktrees.
- The agent must not create, remove, or switch worktrees.
- Each worktree has its own `.venv`; never share environments between worktrees.
- Run tests using the existing environment:

```bash
.venv/bin/python -m pytest
```

- Verify that the package resolves to the current worktree with:

```bash
.venv/bin/python -c "import scrapyrus; print(scrapyrus.__file__)"
```

- If `.venv` is missing or incomplete, ask the user to grant permission to initialize it with:

```bash
UV_CACHE_DIR=/tmp/uv-cache uv sync --extra tests
```

- After permission is granted, initialize the environment, verify the import path, and continue the requested task.
- If the import path points to another worktree, ask for permission before deleting and recreating only the current worktree’s `.venv`.
- Do not use `pip install --editable`; `uv sync` installs the package in editable mode.
- Do not run `uv sync` during ordinary test runs unless the environment is missing or dependencies changed.
- Commit `uv.lock`.
- When dependencies change, update both `pyproject.toml` and `uv.lock`.
- Do not commit `.venv` or cache directories.
- The test suite uses generated fixtures and does not need `idp.data`. Ingestion commands read `idp.data` from the current directory, or from the path given by the top-level `--idp-data` option, which precedes the subcommand (`scrapyrus --idp-data /path/to/idp.data metadata ingest`).
- Never clone `idp.data` yourself; the clone is several gigabytes. Ask the user where it is.
- The embedding `ingest`, `update`, and `query` commands call real inference servers with real credentials (`SCRAPYRUS_EMBEDDINGS_API_KEY`); run them only when the user explicitly asks.

## Restrictions

- do not commit anything to git unless told so explicitly
- never commit secrets into git, e.g., API keys
- never edit code without asking first. Larger changes additionally require the plan described in the workflow below; small fixes skip that workflow but still require asking first.
- never modify the data in `idp.data` or the PostgreSQL database (the `scrapyrus` database selected via `SCRAPYRUS_DATABASE_URL`, `--database-url`, or the `PG*` variables, including the Docker volume `scrapyrus-pgdata`) unless explicitly told to do so.
- without that permission, do not run commands that write to the database:
  - `metadata ingest` and `transcriptions ingest`, which drop and recreate their tables on every run;
  - `embeddings ingest`, `update`, `import`, and `delete`, where `--force` additionally discards existing vectors;
  - `catalog`;
  - `scripts/postgres_restore.sh`.

## Workflow

- when asked to make a larger change that introduces new or changes existing functionality (not just a one-line typo correction or a tiny bugfix), always follow this workflow:
  - follow a test-driven development approach. Tests come first (will fail, red phase), then code that fulfills them, then refactor as desired while preserving functionality and correctness.
  - propose an implementation plan for tests and implementation, surface any open elements that could change behavior or outcome.
  - present plan to the user for confirmation, and ask them to answer any open questions.
  - rework plan if asked for, answer all questions the user might have
  - plan is only ready to go when all open elements have been specified and the user confirms readiness.
  - write tests first and have user review them (red phase). Only proceed when they give the ok.
  - then write code to fulfill the tests (green phase). Present for review.
  - refactor as indicated until code is complete as reviewer judges it.

## Coding guidelines

- Adhere to SOLID principles:
  - single responsibility principle: One code unit (function, class, module) should have one single purpose
  - open-closed principle: Code should be open to extension, but closed to modification, i.e., we should not have to modify existing code extensively to extend the functionality of the system
  - liskov substitution: derived or child classes must be able to replace their parent classes, i.e., child classes should extend the parent classes without breaking the behavioral contract
  - interface segregation: A client should not be forced to depend on parts of an interface that is not relevant to it
  - dependency inversion: Higher-level elements of the code should not depend on lower-level elements of the code, both should depend on abstractions that define behavior, not restrict implementation.
- keep control flow and data flow as flat as possible. Go with the minimum amount of hierarchical depth that solves the problem at hand.
- avoid module-level variables
- use classes as soon as data and functions work together to create a functionality
- avoid deeply nested branching
- branches should be self-explanatory
- make branches explicit. Do not rely on handling a case by leaving it as the last one that's missing, rather use explicit if-elif-else blocks
- when writing tests, test behavior and state, not its implementation details
- keep the hot path of a function clean: configuration, parameter handling and preparation should happen on as high a level as possible
- handle edge cases explicitly. Do not rely on silent defaults that can alter behavior without the user knowing
- exceptions should be handled explicitly and early when they are expected or anticipated. In cases where unexpected/unanticipated things happen, make them bubble up to the highest level and handle them there. Lower-level code never catches `Exception`; only the top-level boundary (the CLI entry point) does. When re-raising as a project exception, chain with `from e` so the original traceback is kept:

```python
def low_level_step() -> Result:
    """Handles only anticipated exceptions; everything else propagates."""
    try:
        return func()
    except AnticipatedException1:  # might happen and we know what to do
        return handle_e1()
    except AnticipatedException2 as e:  # anticipated, re-raised in project terms
        raise SpecificErrorForThisCase("Specific message here") from e
    # no `except Exception` here: unexpected errors bubble up


def main() -> int:
    """CLI entry point: the single place where unexpected exceptions are caught."""
    try:
        report(low_level_step())
        return 0
    except SpecificErrorForThisCase as e:
        print_error(str(e))
        return 1
    except Exception:
        logger.exception("Unexpected error")
        return 1
```

- no changes to the code are made without a corresponding test of the new or changed functionality
- all public methods and classes should have google style docstrings
- all private methods or classes should have at least freeform docstrings
- documentation is considered part of the code base and must be maintained alongside it.
- code should have explanatory comments that explain decisions taken where multiple alternatives would be possible or where a certain algorithm to solve a problem is first introduced
- all function arguments have type hints.
- adhere to clean code principles with practical application of the principles of "Clean Code" by Robert C. Martin, and "Refactoring" by Martin Fowler, but with relaxed rules on naming conventions and function length. The code should be readable and understandable, but not necessarily follow strict naming conventions or have very short functions. The focus is on clarity and maintainability rather than strict adherence to style guides.
