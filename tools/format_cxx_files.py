#!/usr/bin/env python
import sys
import os
import subprocess
from argparse import ArgumentParser
from pathlib import Path

CXX_EXTENSIONS = [".cc", ".cpp", ".cxx", ".C", ".hpp", ".hxx", ".ixx"]


def main(args):
    config = process_command_line(args)
    run(config)
    return 0


def process_command_line(args):
    parser = make_command_line_parser(args[0])
    config = parser.parse_args(args[1:])
    return config


def make_command_line_parser(args):
    parser = ArgumentParser(
        prog=args[0],
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
        "--clang-format", type=Path, help="Path to the clang-format executable"
    )
    return parser


def run(config):
    source_files = get_source_files(config)
    format_files(config, source_files)


def get_source_files(config):
    os.chdir(config.source_tree)
    cwd = Path.cwd()
    source_files = []
    for extension in CXX_EXTENSIONS:
        source_files += list(cwd.rglob(f"**/*{extension}")) + list(
            cwd.rglob(f"*{extension}")
        )
    return source_files


def format_files(config, source_files):
    subprocess.run([config.clang_format, "-i"] + source_files, check=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
