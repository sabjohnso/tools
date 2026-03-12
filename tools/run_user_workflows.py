#!/usr/bin/env python
"""Run CMake user workflow presets."""

import sys
import json
import re
import subprocess
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tools.resource_monitor import (
    compute_resource_stats,
    format_resource_table,
    monitor_subprocess,
)


def main(args):
    """Run the user presets according to the input arguments and return
    0 on success"""
    try:
        config = process_command_line(args)
        run(config)
        return 0
    except subprocess.CalledProcessError as e:
        return e.returncode


def process_command_line(args):
    """Process the command line arguments and return the runtime
    configuration"""

    parser = make_command_line_parser(args[0])
    config = parser.parse_args(args[1:])
    return config


def make_command_line_parser(prog):
    """Return the command line parser."""
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
    parser.add_argument(
        "--jobs",
        "-j",
        type=int,
        default=1,
        help="Number of workflows to run in parallel (default: 1)",
    )
    return parser


def run(config):
    """Run workflows sequentially or in parallel based on config.jobs."""
    workflow_names = get_workflow_names(config)
    if config.jobs <= 1:
        run_sequential(workflow_names)
    else:
        groups = group_workflows_by_configure_preset(config.input_path, workflow_names)
        run_parallel(groups, config.jobs)


def group_workflows_by_configure_preset(input_path, workflow_names):
    """Group workflow names by their configure preset, preserving order."""
    with open(input_path, "r", encoding="utf-8") as inp:
        user_presets = json.load(inp)
    workflow_map = {wp["name"]: wp for wp in user_presets["workflowPresets"]}
    groups = {}
    group_order = []
    for name in workflow_names:
        configure_name = get_configure_step_name(workflow_map[name])
        if configure_name not in groups:
            groups[configure_name] = []
            group_order.append(configure_name)
        groups[configure_name].append(name)
    return [groups[key] for key in group_order]


def get_configure_step_name(workflow):
    """Return the name of the configure step in a workflow."""
    for step in workflow["steps"]:
        if step["type"] == "configure":
            return step["name"]
    raise KeyError(f"No configure step in workflow: {workflow['name']}")


def workflow_banner(name):
    """Return a visually distinct banner for a workflow name."""
    padding = 4
    width = len(name) + padding * 2
    border = "═" * width
    inner = f"║{' ' * padding}{name}{' ' * padding}║"
    return f"╔{border}╗\n{inner}\n╚{border}╝"


def run_sequential(workflow_names):
    """Run workflows one at a time with resource monitoring."""
    for workflow_name in workflow_names:
        print(workflow_banner(workflow_name))
        returncode, samples, elapsed = monitor_subprocess(
            ["cmake", "--workflow", "--preset", workflow_name]
        )
        stats = compute_resource_stats(samples)
        stats["elapsed"] = elapsed
        print(format_resource_table(stats))
        if returncode != 0:
            raise subprocess.CalledProcessError(returncode, "cmake")


def run_parallel(groups, jobs):
    """Run workflow groups in parallel, workflows within a group sequentially."""
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = {
            executor.submit(run_workflow_group, group): group for group in groups
        }
        failed = None
        for future in as_completed(futures):
            results = future.result()
            for name, result in results:
                print(workflow_banner(name))
                if result.stdout:
                    print(result.stdout, end="")
                if failed is None and result.returncode != 0:
                    failed = result.returncode
        if failed is not None:
            raise subprocess.CalledProcessError(failed, "cmake")


def run_workflow_group(group):
    """Run a group of workflows sequentially, capturing output."""
    results = []
    for workflow_name in group:
        result = subprocess.run(
            ["cmake", "--workflow", "--preset", workflow_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        results.append((workflow_name, result))
        if result.returncode != 0:
            break
    return results


def get_workflow_names(config):
    """Return the filtered list of workflow preset names."""
    all_workflow_names = get_all_workflow_names(config)
    workflow_names = filter_workflow_names(config, all_workflow_names)
    return workflow_names


def filter_workflow_names(config, all_workflow_names):
    """Filter workflow names by matching and exclusion patterns."""
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
            if not isinstance(re.search(config.exclude, workflow_name), re.Match)
        ]
    return workflow_names


def get_all_workflow_names(config):
    """Return all workflow preset names from the user presets file."""
    workflow_presets = get_workflow_presets(config)
    workflow_names = [workflow_preset["name"] for workflow_preset in workflow_presets]
    return workflow_names


def get_workflow_presets(config):
    """Return the workflow presets from the user presets file."""
    user_presets = get_user_presets(config)
    return user_presets["workflowPresets"]


def get_user_presets(config):
    """Load and return the user presets from disk."""
    with open(config.input_path, "r", encoding="utf-8") as inp:
        user_presets = json.load(inp)
    return user_presets


if __name__ == "__main__":
    sys.exit(main(sys.argv))
