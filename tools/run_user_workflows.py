#!/usr/bin/env python
import sys
import json
import re
import subprocess
from argparse import ArgumentParser
from pathlib import Path


def main(args):
    """Run the user presets according to the input arguments and return
    0 on success"""
    try:
        config = process_command_line(args)
        run(config)
        return 0
    except Exception as e:
        print(type(e), sys.stderr)
        print(e, sys.stderr)
        return 1


def process_command_line(args):
    """Process the command line arguments and return the runtime
    configuration"""

    parser = make_command_line_parser(args[0])
    config = parser.parse_args(args[1:])
    return config


def make_command_line_parser(prog):
    """Return the command line parser"""
    parser = ArgumentParser(prog=prog)
    parser.add_argument(
        "--input-path",
        "-i",
        type=Path,
        default=Path("CMakeUserPresets.json"),
        help="The file providing the user presets",
    )
    parser.add_argument(
        "--matching",
        "-m",
        type=str,
        default=None,
        help="A regular expression matching workflow presets to include",
    )
    parser.add_argument(
        "--exclude",
        "-e",
        type=str,
        default=None,
        help="A regular expression matching workflow presets to exclude",
    )
    return parser


def run(config):
    workflow_names = get_workflow_names(config)
    for workflow_name in workflow_names:
        subprocess.run(
            ["cmake", "--workflow", "--preset", workflow_name], check=True
        )


def get_workflow_names(config):
    all_workflow_names = get_all_workflow_names(config)
    workflow_names = filter_workflow_names(config, all_workflow_names)
    return workflow_names


def filter_workflow_names(config, all_workflow_names):
    workflow_names = all_workflow_names
    if config.matching:
        workflow_names = [
            workflow_name
            for workflow_name in workflow_names
            if isinstance(re.search(config.matching, workflow_name), re.Match)
        ]
    if config.exclude:
        workflow_names = [
            workflow_name
            for workflow_name in workflow_names
            if not isinstance(
                re.search(config.exclude, workflow_name), re.Match
            )
        ]
    return workflow_names


def get_all_workflow_names(config):
    workflow_presets = get_workflow_presets(config)
    workflow_names = [
        workflow_preset["name"] for workflow_preset in workflow_presets
    ]
    return workflow_names


def get_workflow_presets(config):
    user_presets = get_user_presets(config)
    return user_presets["workflowPresets"]


def get_user_presets(config):
    with open(config.input_path, "r", encoding="utf-8") as inp:
        user_presets = json.load(inp)
    return user_presets


if __name__ == "__main__":
    sys.exit(main(sys.argv))
