#!/usr/bin/env python
"""Set CMake variables with the configure presets of workflow presets."""

import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path

from tools.error_policy import add_stack_trace_option, run_tool
from tools.errors import UserError
from tools.user_presets import (
    add_workflow_selection_options,
    find_workflow,
    get_configure_step_name,
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
    """Set cmake variables according to the input arguments and return 0."""
    config = process_command_line(args)
    validate_definitions(config)
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
        "-D",
        dest="definitions",
        action="append",
        default=[],
        help="CMake variable definition (VAR=VALUE)",
    )
    add_stack_trace_option(parser)
    return parser


def validate_definitions(config):
    """Raise UserError if no definitions were provided."""
    if not config.definitions:
        raise UserError("at least one -D definition is required")


def run(config):
    """Reconfigure each selected configure preset with the given definitions."""
    configure_names = get_configure_preset_names(config)
    source_dir = config.input_path.resolve().parent
    set_variables(configure_names, config.definitions, source_dir)


def set_variables(configure_names, definitions, source_dir):
    """Reconfigure each configure preset with the given definitions."""
    for configure_name in configure_names:
        reconfigure(configure_name, definitions, source_dir)


def reconfigure(configure_name, definitions, source_dir):
    """Run cmake with a configure preset and the given definitions."""
    command = make_cmake_command(configure_name, definitions)
    print(f"Reconfiguring {configure_name}")
    subprocess.run(command, check=True, cwd=source_dir)


def make_cmake_command(configure_name, definitions):
    """Return the cmake command to reconfigure with a configure preset."""
    return ["cmake", "--preset", configure_name] + [f"-D{d}" for d in definitions]


# --- Configure preset discovery ---


def get_configure_preset_names(config):
    """Return the distinct configure presets of the selected workflows."""
    user_presets = read_user_presets(config.input_path)
    workflow_names = select_workflow_names(
        user_presets, config.matching, config.exclude
    )
    configure_names = (
        get_configure_step_name(find_workflow(user_presets, name))
        for name in workflow_names
    )
    return list(dict.fromkeys(configure_names))


if __name__ == "__main__":
    entry_point()
