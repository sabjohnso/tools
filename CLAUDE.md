# Project: Dev Tools

Command-line utilities for managing CMake-based C++ project builds.
These tools are used by other C++ projects — they generate
`CMakeUserPresets.json` files and run workflows defined in those presets.

Five entry points: `make-user-presets`, `run-user-workflows`, `format-cxx-files`,
`clear-cmake-cache`, `set-cmake-variable`.

## Project structure

```
tools/                  # Main package
  __init__.py           # Package docstring; each tool module has its entry_point
  make_user_presets.py  # Generate CMakeUserPresets.json from compiler specs
  run_user_workflows.py # Execute CMake workflow presets
  format_cxx_files.py   # Format C++ sources with clang-format
  clear_cmake_cache.py  # Clear CMakeCache.txt from workflow build directories
  set_cmake_variable.py # Set CMake variables with the configure presets
  resource_monitor.py   # Monitor subprocess CPU and resident set size usage
  multi_config.py       # Detect multi-configuration generators in presets and caches
  error_policy.py       # Error messages, exit codes and the --stack-trace option
  errors.py             # Shared exception types (UserError)
  user_presets.py       # Find workflow facts in CMakeUserPresets.json
  build_documentation.py # Documentation builder (stub)
  compilers.schema.json # JSON Schema for compiler input validation
test/                   # Tests (pytest)
  test_package.py       # Package metadata and entry points
  test_make_user_presets.py
  test_format_cxx_files.py
  test_clear_cmake_cache.py
  test_resource_monitor.py
  test_set_cmake_variable.py
  test_multi_config.py
  test_error_policy.py
  test_user_presets.py
  test_run_user_workflows.py
  test_cmake_integration.py  # Marked cmake; runs real CMake builds
  conftest.py           # Shared preset fixtures
  preset_strategies.py  # Shared Hypothesis strategies and oracles
  test_workflow_selection.py  # Workflow filter laws for the three tools
```

## Build and test

```bash
poetry install              # Install dependencies
poetry run pytest -v        # Run tests (up to 8 workers, from addopts)
poetry run pytest -m "not cmake"  # Skip the slow CMake integration tests
poetry run pytest -n 0 test/x.py   # Run one file in one process
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

## Preset generation architecture

`make_user_presets.py` reads a JSON compiler specification (validated against
`compilers.schema.json`) and generates a complete `CMakeUserPresets.json` with
four preset types:

- **Configure presets**: one per compiler — sets compiler paths, environment
  variables, and build directory. Shared across all build types for that compiler.
- **Build presets**: one per compiler × build-type — inherits from `baseBuild`,
  sets `configuration` (the `--config` value of the multi-configuration build).
- **Test presets**: one per compiler × build-type — inherits from `baseTest`,
  mirrors build preset configuration.
- **Workflow presets**: one per compiler × build-type — chains configure → build → test.

### Build types and workflow suffixes

Each compiler produces three workflows, distinguished by a name suffix:

| Suffix    | Build Type        | Flags              | Purpose                          |
|-----------|-------------------|--------------------|----------------------------------|
| (none)    | `Release`         | (CMake default)    | Optimized production builds      |
| `-devel`  | `RelWithAsserts`  | `-O3`              | Optimized with asserts active    |
| `-debug`  | `Debug`           | (CMake default)    | Unoptimized, full debug symbols  |

Additionally, `RelWithDebInfo` is overridden via `cacheVariables` to use
`-O3 -g -DNDEBUG` (optimized with debug info, asserts disabled). This
overrides the project-level `CMakePresets.json` definition.

All workflows of one compiler share one build directory, so the inherited
configure preset must use a multi-configuration generator (for example
`Ninja Multi-Config`). The `configuration` field of the build and test presets
selects the build type in that build directory. It does not set
`CMAKE_BUILD_TYPE`. For a custom build type, the configure presets set the
`CMAKE_<LANG>_FLAGS_<BUILDTYPE>` cache variables.

### Shared modules across tools

`user_presets.py` reads `CMakeUserPresets.json` and finds facts about its
workflows. `run_user_workflows.py`, `clear_cmake_cache.py` and
`set_cmake_variable.py` use it for these jobs:

- `add_workflow_selection_options` adds `--input-path`/`-i`, `--matching`/`-m`
  and `--exclude`/`-e` to the parser of each of the three tools.
- `read_user_presets` reads the presets file.
- `select_workflow_names` and `filter_workflow_names` select the workflows
  with the `--matching`/`--exclude` regular expressions (`re.search`).
- `find_workflow`, `get_configure_step_name` and `find_configure_preset` find
  the configure preset of a workflow.
- `build_directory` and `resolve_binary_dir` find the build directory of a
  workflow and replace `${sourceDir}` with the directory of the presets file.
- `JsonObject` is the type alias for a JSON object. Define it only in this
  module.

`clear_cmake_cache.py` finds the build directory of each selected workflow
and removes duplicates. `set_cmake_variable.py` finds the configure preset of
each selected workflow and removes duplicates. Then it runs
`cmake --preset <configure preset> -DVAR=VALUE` in the directory of the
presets file. `run_user_workflows.py` uses the build directory to read
`CMakeCache.txt`. With `--jobs`, it groups the workflows by configure preset.

`error_policy.py` gives all five tools the same error messages, exit codes
and `--stack-trace` option. `errors.py` holds `UserError`.

## Files not to commit

- `ISSUES.org`, `PLAN.org` — private working files
- Editor backup files (`*~`) — already in `.gitignore`
