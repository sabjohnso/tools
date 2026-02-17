#!/usr/bin/env python
"""Format C++ source files using clang-format."""

import sys
import subprocess
from argparse import ArgumentParser
from pathlib import Path

CXX_EXTENSIONS = [".cc", ".cpp", ".cxx", ".C", ".hpp", ".hxx", ".ixx"]


def main(args):
    """Run the formatter and return 0 on success."""
    try:
        config = process_command_line(args)
        run(config)
        return 0
    except subprocess.CalledProcessError as e:
        return e.returncode


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
    source_files = get_source_files(config)
    format_files(config, source_files)


def get_source_files(config):
    """Return all C++ source files under the configured source tree."""
    source_files = []
    for extension in CXX_EXTENSIONS:
        source_files += list(config.source_tree.rglob(f"*{extension}"))
    return source_files


def format_files(config, source_files):
    """Run clang-format on the given source files."""
    subprocess.run([config.clang_format, "-i"] + source_files, check=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
