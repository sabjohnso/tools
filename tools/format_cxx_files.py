#!/usr/bin/env python
"""Format C++ source files using clang-format."""

import os
import sys
import subprocess
from argparse import ArgumentParser
from itertools import batched
from pathlib import Path

CXX_EXTENSIONS = [".cc", ".cpp", ".cxx", ".C", ".hpp", ".hxx", ".ixx"]

# The number of files for one clang-format process. It keeps the command
# line below the limit of the operating system for a large source tree.
FORMAT_BATCH_SIZE = 500


def main(args):
    """Run the formatter and return 0 on success."""
    try:
        config = process_command_line(args)
        run(config)
        return 0
    except subprocess.CalledProcessError as e:
        return e.returncode
    except FileNotFoundError as e:
        print(f"format-cxx-files: cannot run {e.filename or e}", file=sys.stderr)
        return 1


def process_command_line(args):
    """Process the command line arguments and return the runtime configuration."""
    parser = make_command_line_parser(args[0])
    config = parser.parse_args(args[1:])
    return config


def make_command_line_parser(prog):
    """Return the command line parser."""
    parser = ArgumentParser(
        prog=prog,
        description="""
        Format C++ source files according to .clang-format
        """,
    )
    parser.add_argument(
        "--source-tree",
        type=Path,
        default=Path.cwd(),
        help="Path to the toplevel directory of the source tree",
    )
    parser.add_argument(
        "--clang-format",
        type=Path,
        default=Path("clang-format"),
        help="Path to the clang-format executable",
    )
    return parser


def run(config):
    """Find and format all C++ source files."""
    source_files = get_source_files(config.source_tree)
    format_files(config.clang_format, source_files)


def get_source_files(source_tree):
    """Return the C++ source files of the source tree, outside build directories."""
    return [
        path
        for path in files_outside_build_directories(source_tree)
        if path.suffix in CXX_EXTENSIONS
    ]


def format_files(clang_format, source_files, batch_size=FORMAT_BATCH_SIZE):
    """Run clang-format on the given source files, in batches."""
    for batch in batched(source_files, batch_size):
        subprocess.run([clang_format, "-i", *batch], check=True)


def files_outside_build_directories(root):
    """Yield each file under root, but skip the CMake build directories."""
    for directory, subdirectories, files in os.walk(root):
        subdirectories[:] = [
            name
            for name in subdirectories
            if not is_build_directory(Path(directory) / name)
        ]
        yield from (Path(directory) / name for name in files)


def is_build_directory(path):
    """Return True if path is a CMake build directory."""
    return (path / "CMakeCache.txt").exists()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
