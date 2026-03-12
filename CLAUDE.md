# Project: Dev Tools

Command-line utilities for managing CMake-based C++ project builds.
Five entry points: `make-user-presets`, `run-user-workflows`, `format-cxx-files`, `clear-cmake-cache`, `set-cmake-variable`.

## Project structure

```
tools/                  # Main package
  __init__.py           # Entry points for all five CLI tools
  make_user_presets.py  # Generate CMakeUserPresets.json from compiler specs
  run_user_workflows.py # Execute CMake workflow presets
  format_cxx_files.py   # Format C++ sources with clang-format
  clear_cmake_cache.py  # Clear CMakeCache.txt from workflow build directories
  set_cmake_variable.py # Set CMake variables in workflow build directories
  resource_monitor.py   # Monitor subprocess CPU and RSS usage
  build_documentation.py # Documentation builder (stub)
  compilers.schema.json # JSON Schema for compiler input validation
test/                   # Tests (pytest)
  test_make_user_presets.py
  test_format_cxx_files.py
  test_clear_cmake_cache.py
  test_resource_monitor.py
  test_set_cmake_variable.py
```

## Build and test

```bash
poetry install              # Install dependencies
poetry run pytest -v        # Run tests
poetry run pre-commit run --all-files  # Lint and format
poetry run mypy tools       # Type checking
```

## Pre-commit hooks

Pre-commit is configured with:
- Standard checks (trailing whitespace, AST, merge conflicts, etc.)
- `ruff --fix` for linting
- `ruff-format` for formatting

Hooks run automatically on commit. If `ruff-format` modifies files,
re-stage and commit again.

## Conventions

- **Python >= 3.12** required
- **Docstring style**: single-line, imperative: `"""Return the command line parser."""`
- **Top-down design**: high-level `main` -> `process_command_line` -> `run` pattern;
  abstract logic at the top, concrete details below
- **Line length**: 88 characters (ruff)
- **Test files**: module docstring only; test function names are self-documenting
- **No attribution**: do not add Co-Authored-By or similar to commits or source files

## Files not to commit

- `ISSUES.org`, `PLAN.org` — private working files
- Editor backup files (`*~`) — already in `.gitignore`
