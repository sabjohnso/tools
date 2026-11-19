#!/usr/bin/env python
"""Clear CMakeCache.txt from build directories associated with workflow presets.

The option --remove-cmake-files also removes the CMakeFiles directory, as
CMake recommends when the compiler changes.
"""

import shutil
import sys
from argparse import ArgumentParser
from pathlib import Path

from tools.error_policy import add_stack_trace_option, run_tool
from tools.user_presets import (
    add_workflow_selection_options,
    build_directory,
    read_user_presets,
    select_workflow_names,
)


def main(args):
    """Run the tool with the error policy and return the exit code."""
    return run_tool(execute, args)


def entry_point():
    """Run the tool with the command line of the process and exit with its code."""
    sys.exit(main(sys.argv))


def execute(args):
    """Clear cmake caches according to the input arguments and return 0."""
    config = process_command_line(args)
    run(config)
    return 0


def process_command_line(args):
    """Process command line arguments and return the runtime configuration."""
    parser = make_command_line_parser(Path(args[0]).name)
    return parser.parse_args(args[1:])


def make_command_line_parser(prog):
    """Return the command line parser."""
    parser = ArgumentParser(prog=prog)
    add_workflow_selection_options(parser)
    parser.add_argument(
        "--remove-cmake-files",
        action="store_true",
        help="Also remove the CMakeFiles directory of each build directory",
    )
    add_stack_trace_option(parser)
    return parser


def run(config):
    """Clear the CMake state of each matched build directory."""
    for directory in get_build_directories(config):
        clear_cache(directory)
        if config.remove_cmake_files:
            remove_cmake_files(directory)


def get_build_directories(config):
    """Return deduplicated build directories for matched workflow presets."""
    user_presets = read_user_presets(config.input_path)
    source_dir = config.input_path.resolve().parent
    workflow_names = select_workflow_names(
        user_presets, config.matching, config.exclude
    )
    directories = (
        build_directory(user_presets, name, source_dir) for name in workflow_names
    )
    return list(dict.fromkeys(directories))


def clear_cache(directory):
    """Delete CMakeCache.txt from a build directory."""
    cache_file = directory / "CMakeCache.txt"
    if cache_file.exists():
        cache_file.unlink()
        print(f"Cleared {cache_file}")
    else:
        print(f"No cache found in {directory}")


def remove_cmake_files(directory):
    """Delete the CMakeFiles directory from a build directory, if it exists."""
    cmake_files = directory / "CMakeFiles"
    if cmake_files.is_symlink():
        cmake_files.unlink()
        print(f"Removed {cmake_files}")
    elif cmake_files.is_dir():
        shutil.rmtree(cmake_files)
        print(f"Removed {cmake_files}")


if __name__ == "__main__":
    entry_point()
