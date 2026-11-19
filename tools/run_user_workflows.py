#!/usr/bin/env python
"""Run CMake user workflow presets."""

import sys
import subprocess
from argparse import ArgumentParser
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from tools.resource_monitor import (
    compute_resource_stats,
    format_resource_table,
    monitor_subprocess,
)
from tools.error_policy import add_stack_trace_option, run_tool
from tools.multi_config import SingleConfigError, cache_is_multi_config
from tools.user_presets import (
    add_workflow_selection_options,
    build_directory,
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
    """Run the user presets according to the input arguments and return 0."""
    config = process_command_line(args)
    run(config)
    return 0


def process_command_line(args):
    """Process the command line arguments and return the runtime
    configuration"""

    parser = make_command_line_parser(Path(args[0]).name)
    config = parser.parse_args(args[1:])
    return config


def make_command_line_parser(prog):
    """Return the command line parser."""
    parser = ArgumentParser(prog=prog)
    add_workflow_selection_options(parser)
    parser.add_argument(
        "--jobs",
        "-j",
        type=int,
        default=1,
        help="Number of workflows to run in parallel (default: 1)",
    )
    add_stack_trace_option(parser)
    return parser


def run(config):
    """Run workflows sequentially or in parallel based on config.jobs."""
    user_presets = read_user_presets(config.input_path)
    workflow_names = select_workflow_names(
        user_presets, config.matching, config.exclude
    )
    check = make_build_check(config, user_presets)
    if config.jobs <= 1:
        run_sequential(workflow_names, check)
    else:
        groups = group_workflows_by_configure_preset(user_presets, workflow_names)
        run_parallel(groups, config.jobs, check)


def make_build_check(config, user_presets):
    """Return a function that gives a problem message for a workflow, or None."""
    source_dir = config.input_path.resolve().parent

    def check(workflow_name):
        build_dir = build_directory(user_presets, workflow_name, source_dir)
        return single_config_problem(build_dir / "CMakeCache.txt", workflow_name)

    return check


def single_config_problem(cache_file, workflow_name):
    """Return a message if the cache shows a single-configuration generator."""
    if not cache_file.exists():
        return None
    if cache_is_multi_config(cache_file.read_text(encoding="utf-8")):
        return None
    return SINGLE_CONFIG_ERROR.format(workflow=workflow_name, cache_file=cache_file)


def group_workflows_by_configure_preset(user_presets, workflow_names):
    """Group workflow names by their configure preset, preserving order."""
    groups = {}
    for name in workflow_names:
        configure_name = get_configure_step_name(find_workflow(user_presets, name))
        groups.setdefault(configure_name, []).append(name)
    return list(groups.values())


def workflow_banner(name):
    """Return a visually distinct banner for a workflow name."""
    padding = 4
    width = len(name) + padding * 2
    border = "═" * width
    inner = f"║{' ' * padding}{name}{' ' * padding}║"
    return f"╔{border}╗\n{inner}\n╚{border}╝"


def run_sequential(workflow_names, check):
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
        problem = check(workflow_name)
        if problem:
            raise SingleConfigError(problem)


def run_parallel(groups, jobs, check):
    """Run workflow groups in parallel, workflows within a group sequentially."""
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = {
            executor.submit(run_workflow_group, group, check): group for group in groups
        }
        failed = None
        first_problem = None
        for future in as_completed(futures):
            results = future.result()
            for name, result, problem in results:
                print(workflow_banner(name))
                if result.stdout:
                    print(result.stdout, end="")
                if failed is None and result.returncode != 0:
                    failed = result.returncode
                if first_problem is None and problem:
                    first_problem = problem
        if failed is not None:
            raise subprocess.CalledProcessError(failed, "cmake")
        if first_problem is not None:
            raise SingleConfigError(first_problem)


def run_workflow_group(group, check):
    """Run a group of workflows sequentially, capturing output."""
    results = []
    for workflow_name in group:
        result = subprocess.run(
            ["cmake", "--workflow", "--preset", workflow_name],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        problem = check(workflow_name) if result.returncode == 0 else None
        results.append((workflow_name, result, problem))
        if result.returncode != 0 or problem:
            break
    return results


SINGLE_CONFIG_ERROR = """
The workflow '{workflow}' used a single-configuration generator.
See CMAKE_GENERATOR in {cache_file}.
The -devel and -debug workflows need a multi-configuration generator,
for example "Ninja Multi-Config". Correct the configure preset, then
delete the build directory.
"""


if __name__ == "__main__":
    entry_point()
