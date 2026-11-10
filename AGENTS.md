# Repository Guidelines

## Project layout

- Package code lives in `src/scrapyrus/`.
- Tests live in `tests/` and use pytest.
- Put reusable functionality in the package.
- Put one-off scripts in `scripts/`; each must begin with a comment explaining its purpose.

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

## Restrictions

-do not commit anything to git unless told so explicitly

- never commit secrets into git, e.g., API keys
- never edit code without asking first and giving a clear step-by-step plan first
- never modify the data in the ./datasets directory unless explicitly told to do so. It contains the data of the project in various stages or. processing and must hence be held sacred! If told to modify it, raise the concern that this is normally forbidden first, plan out a step-by-step workflow and ask for explicit permission to execute it first.
- config files are treated as ephemeral and do not need tests

## Workflow

- when asked to make a change, always follow this workflow:
  - follow a test-driven development approach. tests come first (will fail, red phase), then code that fulfills them, then refactor as desired while preserving functionality and correctness.
  - propose an implementation plan for tests and implementation, surface any open elements that could change behavior or outcome.
  - present plan to the user for confirmation, and ask them for specification of open questions.
  - rework plan if asked for, answer all question they have
  - plan is only ready to go when all open elements have been specified and the user confirms
  - write test first and have user review them (red phase)
  - then write code to fulfill them (green phase). Present for review.
  - refactor as review and user indication indicates until complete as reviewer judges it.

## Coding guidelines

-Adhere to SOLID principles

- single responsibility principle: One code unit (function, class, module) should have one single purpose
- open-closed principle: Code should be open to extension, but closed to modification, i.e., we should not have to modify existing code extensively to extend the functionality of the system
- liskov substitution: derived-or child classes must be able to replace their parent classes, i.e., child classes should extend the parent classes without breaking the behavioral contract
- interface segregation: A client should not be forced to depend on parts of an interface that is not relevant to it
- dependency inversion: Higher-level elements of the code should not depend on lower-level elements of the code, both should depend on abstractions that define behavior, not restrict implementation.

- keep control flow and data flow as flat as possible. Go with the minimum amount of hierarchical dept that solves the problem at hand.
- avoid module-level variables
- use classes as soon as data and functions work together to create a functionality
- avoid deeply nested branching
- branches should be self-explanatory
- make branches explicit. Do not rely on handling a case by leaving it as the last one that's missing, rather use explicit if-elif-else blocks
- when writing tests, test behavior and state, not it's implementation details
- keep the hot path of a function clean: configuration, parameter handling and preparation should happen on as high a level as possible
- handle edge cases explicitly. Do not rely on silent defaults that can alter behavior without the user knowing
- exceptions should be handled explicitly and early when they are expected or anticipated. In cases where unexpected/unanticipated things happen, make them bubble up to the highest level and handle them there:

```python
try:
    func()
except AnticipatedException1 as e1:  # might happen and we know what to do
    handle_e1()
except AnticipatedException2 as e2:  # might happen and we know what to do
    handle_e2()
except Exception as e:  # unknown exception branch for unexpected stuff
    raise SpecificErrorForThisCase("Specific message here")
```

-no changes to the code are made without a corresponding test of the new or changed funcationality
-property-based testing is a first-class test system
-all public methods and classes should have google style docstrings
-all private methods or classes should have at least freeform docstrings
-code should have explanatory comments that explains decisions taken where multiple alternatives would be possible or where a certain algorithm to solve a problem is first introduced
-all function arguments have type hints.
-adhere to clean code principles with practical application of the principles of "Clean Code" by Robert C. Martin, and "Refactoring" by Martin Fowler, but with relaxed rules on naming conventions and function length. The code should be readable and understandable, but not necessarily follow strict naming conventions or have very short functions. The focus is on clarity and maintainability rather than strict adherence to style guides.
