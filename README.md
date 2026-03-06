# Dev Tools

Command-line utilities for managing CMake-based C++ project builds across
multiple compilers and configurations.

## Overview

Working with CMake presets across several compilers (GCC, Clang, etc.) and
build types (Release, Debug, RelWithDebInfo) involves a lot of boilerplate.
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

### 2. Generate presets

```bash
make-user-presets compilers.json
```

This reads `compilers.json` and writes `CMakeUserPresets.json` containing
configure, build, test, and workflow presets for each compiler in Release,
Debug, and RelWithDebInfo configurations.

Options:

```
-o, --output-file FILE   Output path (default: CMakeUserPresets.json)
--stdout                 Print to stdout instead of writing a file
--replace-existing       Overwrite the output file if it exists
--shared-build-directory All presets share the same build directory
--test-jobs N            Number of parallel test jobs (default: 1)
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
```

### 4. Clear CMake caches

```bash
clear-cmake-cache                     # Clear all build directories
clear-cmake-cache -m clang            # Only clang build directories
```

Deletes `CMakeCache.txt` from each matched workflow's build directory,
forcing a clean reconfigure on the next build.

### 5. Set CMake variables

```bash
set-cmake-variable -D CMAKE_BUILD_TYPE=Debug
set-cmake-variable -m gcc -D CMAKE_BUILD_TYPE=Debug -D ENABLE_TESTS=ON
```

Runs `cmake <build_dir> -DVAR=VALUE` for each matched workflow's build
directory. Accepts one or more `-D` flags, mimicking CMake's own syntax.

### 6. Format C++ files

```bash
format-cxx-files                          # Format current directory
format-cxx-files --source-tree src/       # Format a specific tree
format-cxx-files --clang-format clang-format-18
```

Finds all C++ source files (`.cc`, `.cpp`, `.cxx`, `.C`, `.hpp`, `.hxx`,
`.ixx`) and formats them with clang-format.

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
  __init__.py              # Entry points for all five CLI tools
  make_user_presets.py     # Generate CMakeUserPresets.json from compiler specs
  run_user_workflows.py    # Execute CMake workflow presets
  format_cxx_files.py      # Format C++ sources with clang-format
  clear_cmake_cache.py     # Clear CMakeCache.txt from workflow build directories
  set_cmake_variable.py    # Set CMake variables in workflow build directories
  build_documentation.py   # Documentation builder (stub)
  compilers.schema.json    # JSON Schema for compiler input validation
test/                      # Tests (pytest)
  test_make_user_presets.py
  test_format_cxx_files.py
  test_clear_cmake_cache.py
  test_set_cmake_variable.py
pyproject.toml             # Project metadata and dependencies
```

## License

MIT
