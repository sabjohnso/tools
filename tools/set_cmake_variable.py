"""Set CMake variables in build directories associated with workflow presets."""

import json
import re
import subprocess
import sys
from argparse import ArgumentParser
from pathlib import Path


def main(args):
    """Set cmake variables and return 0 on success, or returncode on failure."""
    try:
        config = process_command_line(args)
        validate_definitions(config)
        run(config)
        return 0
    except subprocess.CalledProcessError as e:
        return e.returncode


def process_command_line(args):
    """Process command line arguments and return the runtime configuration."""
    parser = make_command_line_parser(args[0])
    return parser.parse_args(args[1:])


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
        "-D",
        dest="definitions",
        action="append",
        default=[],
        help="CMake variable definition (VAR=VALUE)",
    )
    return parser


def validate_definitions(config):
    """Raise SystemExit if no definitions were provided."""
    if not config.definitions:
        raise SystemExit("error: at least one -D definition is required")


def run(config):
    """Reconfigure each matched build directory with the given definitions."""
    build_directories = get_build_directories(config)
    set_variables(build_directories, config.definitions)


def set_variables(build_directories, definitions):
    """Reconfigure each build directory with the given definitions."""
    for build_directory in build_directories:
        reconfigure(build_directory, definitions)


def reconfigure(build_directory, definitions):
    """Run cmake to reconfigure a build directory with the given definitions."""
    command = make_cmake_command(build_directory, definitions)
    print(f"Reconfiguring {build_directory}")
    subprocess.run(command, check=True)


def make_cmake_command(build_directory, definitions):
    """Return the cmake command to reconfigure a build directory."""
    return ["cmake", str(build_directory)] + [f"-D{d}" for d in definitions]


# --- Build directory discovery (copied from clear_cmake_cache.py) ---


def get_build_directories(config):
    """Return deduplicated build directories for matched workflow presets."""
    user_presets = read_user_presets(config)
    source_dir = config.input_path.resolve().parent
    workflow_names = get_workflow_names(config, user_presets)
    configure_presets = {p["name"]: p for p in user_presets["configurePresets"]}

    seen = set()
    directories = []
    for name in workflow_names:
        workflow = find_workflow(name, user_presets)
        configure_name = get_configure_step_name(workflow)
        binary_dir = configure_presets[configure_name]["binaryDir"]
        resolved = resolve_binary_dir(binary_dir, source_dir)
        if resolved not in seen:
            seen.add(resolved)
            directories.append(resolved)
    return directories


def resolve_binary_dir(binary_dir, source_dir):
    """Replace ${sourceDir} with the actual source directory path."""
    return Path(binary_dir.replace("${sourceDir}", str(source_dir)))


def read_user_presets(config):
    """Read and return the user presets JSON."""
    with open(config.input_path, "r", encoding="utf-8") as inp:
        return json.load(inp)


def get_workflow_names(config, user_presets):
    """Return filtered workflow names."""
    all_names = [wp["name"] for wp in user_presets["workflowPresets"]]
    return filter_workflow_names(config, all_names)


def filter_workflow_names(config, all_workflow_names):
    """Filter workflow names by matching and exclude patterns."""
    names = all_workflow_names
    if config.matching:
        names = [
            n for n in names if isinstance(re.search(config.matching, n), re.Match)
        ]
    if config.exclude:
        names = [
            n for n in names if not isinstance(re.search(config.exclude, n), re.Match)
        ]
    return names


def find_workflow(name, user_presets):
    """Find a workflow preset by name."""
    for workflow in user_presets["workflowPresets"]:
        if workflow["name"] == name:
            return workflow
    raise KeyError(f"Workflow preset not found: {name}")


def get_configure_step_name(workflow):
    """Return the name of the configure step in a workflow."""
    for step in workflow["steps"]:
        if step["type"] == "configure":
            return step["name"]
    raise KeyError(f"No configure step in workflow: {workflow['name']}")


if __name__ == "__main__":
    sys.exit(main(sys.argv))
