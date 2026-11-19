# Dev Tools

Command-line utilities for managing CMake-based C++ project builds across
multiple compilers and configurations.

## Overview

Working with CMake presets across several compilers (GCC, Clang, etc.) and
build types (Release, RelWithAsserts, Debug) involves a lot of boilerplate.
This toolkit automates the repetitive parts:

1. **Define** your compilers in a simple JSON file.
2. **Generate** a full `CMakeUserPresets.json` with configure, build, test,
   and workflow presets for every compiler and build type.
3. **Run** selected workflow presets with a single command.
4. **Manage** build directories — clear caches or set CMake variables across
   all of them at once.
5. **Format** your C++ source files with clang-format.

## Installation

Requires **Python 3.12+** and [Poetry](https://python-poetry.org/).

```bash
git clone <repo-url>
cd tools
poetry install
```

This installs five commands into the Poetry virtual environment:

| Command              | Description                                          |
|----------------------|------------------------------------------------------|
| `make-user-presets`  | Generate `CMakeUserPresets.json` from compiler specs |
| `run-user-workflows` | Execute CMake workflow presets                       |
| `format-cxx-files`   | Format C++ sources with clang-format                 |
| `clear-cmake-cache`  | Delete `CMakeCache.txt` from build directories       |
| `set-cmake-variable` | Set CMake variables across build directories         |

## Usage

### 1. Define compilers

Create a JSON file listing your compiler installations. The schema is
validated automatically on input.

```json
[
  {
    "name": "gcc-14",
    "root": "/usr/local/gcc-14",
    "cc": "gcc",
    "cxx": "g++",
    "addPaths": true
  },
  {
    "name": "clang-18",
    "root": "/usr/local/clang-18",
    "cc": "clang",
    "cxx": "clang++"
  }
]
```

Each compiler requires:

| Field      | Description                                          |
|------------|------------------------------------------------------|
| `name`     | Identifier used as the CMake preset name             |
| `root`     | Absolute path to the compiler installation directory |
| `cc`       | C compiler executable name                           |
| `cxx`      | C++ compiler executable name                         |
| `addPaths` | *(optional)* Add compiler dirs to environment paths  |

With `addPaths`, the compiler directories come first in `PATH`, `LIBRARY_PATH`,
`LD_LIBRARY_PATH` and `CPATH`. The preset keeps the value of a variable from
the parent environment. It does this only if the variable has a value when
you run `make-user-presets`. An empty element in a search path means the
current directory, so the tool does not write one. If you set one of these
variables later, run `make-user-presets` again.

### 2. Generate presets

```bash
make-user-presets compilers.json
```

This reads `compilers.json` and writes `CMakeUserPresets.json`. The file
contains one configure preset for each compiler, and build, test, and
workflow presets for each compiler in three configurations:

| Workflow name       | Configuration    | Flags         | Use                           |
|---------------------|------------------|---------------|-------------------------------|
| `<compiler>`        | `Release`        | CMake default | Optimized builds              |
| `<compiler>-devel`  | `RelWithAsserts` | `-O3`         | Optimized builds with asserts |
| `<compiler>-debug`  | `Debug`          | CMake default | Builds with no optimization   |

The configure presets also set the `RelWithDebInfo` flags to
`-O3 -g -DNDEBUG`. No workflow uses `RelWithDebInfo`.

The workflows of one compiler share one build directory. Thus the inherited
configure preset (`--inherits`, default `default`) must use a
multi-configuration generator, for example `Ninja Multi-Config`. The tool
reads `CMakePresets.json` next to the output file. It stops with an
error if the inherited preset or its parents set a different generator or
no generator. `run-user-workflows` also stops after a workflow whose
`CMakeCache.txt` records a single-configuration generator.

Options:

```
-o, --output-file FILE   Output path (default: CMakeUserPresets.json)
--stdout                 Print to stdout instead of writing a file
--replace-existing       Overwrite the output file if it exists
--build-jobs N           Number of parallel build jobs (default: 16)
--test-jobs N            Number of parallel test jobs (default: 1)
--inherits PRESET        Configure preset to inherit from (default: default)
--stack-trace            Show the Python stack trace of an error
```

### 3. Run workflows

```bash
run-user-workflows                    # Run all workflows
run-user-workflows -m gcc             # Only workflows matching "gcc"
run-user-workflows -m gcc -e devel    # Match "gcc", exclude "devel"
```

Options:

```
-i, --input-path FILE   Presets file (default: CMakeUserPresets.json)
-m, --matching REGEX    Include only workflows matching this pattern
-e, --exclude REGEX     Exclude workflows matching this pattern
-j, --jobs N            Number of workflows to run in parallel (default: 1)
--stack-trace           Show the Python stack trace of an error
```

With `--jobs` greater than 1, the tool runs the workflows of different
configure presets in parallel. The workflows of one configure preset use
one build directory, so the tool runs them one after the other.

### 4. Clear CMake caches

```bash
clear-cmake-cache                     # Clear all build directories
clear-cmake-cache -m clang            # Only clang build directories
clear-cmake-cache --remove-cmake-files  # Also remove CMakeFiles
```

The tool deletes `CMakeCache.txt` from the build directory of each selected
workflow. Thus the next build configures the project again from the start.
With `--remove-cmake-files`, the tool also deletes the `CMakeFiles`
directory of each build directory.

Options:

```
-i, --input-path FILE   Presets file (default: CMakeUserPresets.json)
-m, --matching REGEX    Include only workflows matching this pattern
-e, --exclude REGEX     Exclude workflows matching this pattern
--remove-cmake-files    Also remove the CMakeFiles directory
--stack-trace           Show the Python stack trace of an error
```

### 5. Set CMake variables

```bash
set-cmake-variable -D CMAKE_EXPORT_COMPILE_COMMANDS=ON
set-cmake-variable -m gcc -D CMAKE_EXPORT_COMPILE_COMMANDS=ON -D ENABLE_TESTS=ON
```

The tool finds the configure preset of each selected workflow. For each
configure preset, it runs `cmake --preset <configure preset> -DVAR=VALUE`
one time, in the directory of the presets file. The `-D` option has the
same syntax as in CMake. You must give one or more `-D` options.

Options:

```
-i, --input-path FILE   Presets file (default: CMakeUserPresets.json)
-m, --matching REGEX    Include only workflows matching this pattern
-e, --exclude REGEX     Exclude workflows matching this pattern
-D VAR=VALUE            CMake variable to set (you can repeat it)
--stack-trace           Show the Python stack trace of an error
```

### 6. Format C++ files

```bash
format-cxx-files                          # Format current directory
format-cxx-files --source-tree src/       # Format a specific tree
format-cxx-files --clang-format clang-format-18
```

The tool finds all C++ source files (`.cc`, `.cpp`, `.cxx`, `.C`, `.hpp`,
`.hxx`, `.ixx`) and formats them with clang-format. It skips each CMake
build directory, which it identifies by its `CMakeCache.txt`. Thus the
sources that `FetchContent` downloads stay unchanged. It runs clang-format
on batches of files. It returns 0 when it finds no files.

Options:

```
--source-tree DIR       Top-level directory of the source tree
--clang-format PATH     Path to the clang-format executable
--stack-trace           Show the Python stack trace of an error
```

## Errors

When a tool stops because of an error, it prints one line that starts with
the name of the tool. It does not print a Python stack trace. The exit codes
are:

| Code | Meaning                                                         |
|------|-----------------------------------------------------------------|
| 0    | Success                                                         |
| 1    | An error that you can correct, for example a missing file       |
| 2    | An incorrect command line                                       |
| 70   | An internal error (a defect in the tools)                       |
| 130  | Interrupted with Ctrl+C                                         |

If `cmake` or `clang-format` fails, the tool returns its exit code.

To see the stack trace, add `--stack-trace` to the command line, or set
`TOOLS_STACK_TRACE=1`. Do this when you report an internal error.

## Typical Workflow

```bash
# One-time setup
make-user-presets compilers.json

# Build and test everything
run-user-workflows

# Build only GCC release
run-user-workflows -m "gcc-14$"

# Change a CMake variable across all builds
set-cmake-variable -D CMAKE_EXPORT_COMPILE_COMMANDS=ON

# Clean slate for a specific compiler
clear-cmake-cache -m clang

# Format before committing
format-cxx-files
```

## Development

### Running tests

```bash
poetry run pytest -v
```

### Linting and formatting

```bash
poetry run pre-commit run --all-files
```

Pre-commit hooks include trailing whitespace checks, AST validation,
ruff linting with auto-fix, and ruff-format for code formatting.

### Type checking

```bash
poetry run mypy tools
```

## Project Structure

```
tools/                     # Main package
  __init__.py              # Package docstring; each tool has its entry_point
  make_user_presets.py     # Generate CMakeUserPresets.json from compiler specs
  run_user_workflows.py    # Execute CMake workflow presets
  format_cxx_files.py      # Format C++ sources with clang-format
  clear_cmake_cache.py     # Clear CMakeCache.txt from workflow build directories
  set_cmake_variable.py    # Set CMake variables with the configure presets
  resource_monitor.py      # Monitor the CPU and resident set size use of a subprocess
  multi_config.py          # Find multi-configuration generators
  error_policy.py          # Error messages, exit codes and --stack-trace
  errors.py                # Shared exception types (UserError)
  user_presets.py          # Read workflow facts from CMakeUserPresets.json
  build_documentation.py   # Documentation builder (stub)
  compilers.schema.json    # JSON Schema for compiler input validation
test/                      # Tests (pytest)
  conftest.py              # Shared preset fixtures
  preset_strategies.py     # Shared Hypothesis strategies and oracles
  test_package.py
  test_make_user_presets.py
  test_run_user_workflows.py
  test_format_cxx_files.py
  test_clear_cmake_cache.py
  test_set_cmake_variable.py
  test_resource_monitor.py
  test_multi_config.py
  test_error_policy.py
  test_user_presets.py
  test_workflow_selection.py
  test_cmake_integration.py  # Marked cmake; runs real CMake builds
pyproject.toml             # Project metadata and dependencies
```

## License

MIT
