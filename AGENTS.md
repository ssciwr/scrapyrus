# Repository Guidelines

## Project layout

- Package code lives in `src/scrapyrus/`.
- Tests live in `tests/` and use pytest.
- Keep reusable functionality in the package, not in ad hoc utilities.
- Put one-off scripts in `./scripts/`. Each script must start with a comment explaining what it is used for.

## Development

- Use Python 3.10 or newer.
- Install development dependencies with `python -m pip install --editable '.[tests]'`.
- Run the test suite with `python -m pytest`.
- Add or update tests for behavior changes.

## Changes

- Keep changes focused. Backwards compatibility is not required when introducing a change.
- Update the test suite to cover only the new behavior; remove tests and fixtures that preserve or reference old behavior.
- Follow the existing code style and use clear, descriptive names.
- Do not modify unrelated or generated data.
