# Dev Tools

A collection of command-line utilities for managing CMake-based C++ project
builds. These tools automate the generation of CMake user presets, execution of
build/test workflows, and source code formatting.

## Requirements

- Python >= 3.12
- [Poetry](https://python-poetry.org/) for dependency management
- CMake >= 3.21 (for the generated presets)
- clang-format (for C++ source formatting)

## Installation

```bash
poetry install
```

This installs three command-line tools into the Poetry virtual environment:

| Command              | Description                                           |
|----------------------|-------------------------------------------------------|
| `make-user-presets`  | Generate `CMakeUserPresets.json` from a compiler list |
| `run-user-workflows` | Execute CMake workflow presets                        |
| `format-cxx-files`   | Format C++ source files with clang-format             |

## Tools

### make-user-presets

Generates a `CMakeUserPresets.json` file from a JSON file describing available
compilers. For each compiler, it produces configure, build, test, and workflow
presets in three configurations: Release, RelWithDebInfo (devel), and Debug.

```bash
make-user-presets compilers.json
```

The input file is a JSON array of compiler descriptors:

```json
[
  {
    "name": "gcc-14",
    "root": "/usr/local/gcc-14",
    "cc": "gcc",
    "cxx": "g++",
    "addPaths": true
  }
]
```

Each compiler entry requires:

| Field  | Description                              |
|--------|------------------------------------------|
| `name` | A unique name used to identify presets   |
| `root` | Path to the compiler installation root   |
| `cc`   | C compiler executable name               |
| `cxx`  | C++ compiler executable name             |

The optional `addPaths` field (default: false) controls whether `PATH`,
`LIBRARY_PATH`, `LD_LIBRARY_PATH`, and `CPATH` are prepended with the
compiler's directories. When false, only `CC` and `CXX` are set using
fully-qualified paths.

The input is validated against a JSON Schema (`tools/compilers.schema.json`).
Malformed input — missing keys, wrong types, or unknown properties — is
rejected with a clear error message before preset generation begins.

**Options:**

```
positional arguments:
  filename                    Path to the compiler list JSON file

options:
  -o, --output-file PATH      Output file (default: CMakeUserPresets.json)
  --stdout                    Print to stdout instead of writing a file
  --shared-build-directory    All presets share the same build directory
  --shared-devel-build-directory
                              Normal and devel builds share the same directory
  --replace-existing          Overwrite the output file if it already exists
  --test-jobs N               Number of parallel test jobs (default: 1)
```

### run-user-workflows

Reads workflow presets from a `CMakeUserPresets.json` file and executes them
sequentially via `cmake --workflow --preset`. Supports regex-based filtering to
run a subset of workflows.

```bash
# Run all workflows
run-user-workflows

# Run only workflows matching a pattern
run-user-workflows --matching "gcc-14"

# Exclude debug workflows
run-user-workflows --exclude "debug"

# Combine both
run-user-workflows --matching "gcc" --exclude "devel"
```

**Options:**

```
options:
  -i, --input-path PATH   Presets file (default: CMakeUserPresets.json)
  -m, --matching REGEX    Only run workflows matching this pattern
  -e, --exclude REGEX     Skip workflows matching this pattern
```

### format-cxx-files

Recursively finds C++ source files in a directory tree and formats them
in-place using clang-format. Recognized extensions: `.cc`, `.cpp`, `.cxx`,
`.C`, `.hpp`, `.hxx`, `.ixx`.

```bash
# Format the current directory
format-cxx-files

# Format a specific source tree with a specific clang-format
format-cxx-files --source-tree /path/to/project --clang-format /usr/bin/clang-format-18
```

**Options:**

```
options:
  --source-tree PATH      Root of the source tree (default: current directory)
  --clang-format PATH     Path to clang-format executable (default: clang-format)
```

## Development

### Running tests

```bash
poetry run pytest
```

### Linting and formatting

The project uses [ruff](https://docs.astral.sh/ruff/) for linting and
formatting, enforced via pre-commit hooks:

```bash
poetry run pre-commit run --all-files
```

### Type checking

```bash
poetry run mypy tools
```

## License

MIT
