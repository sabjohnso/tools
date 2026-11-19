"""Read a CMakeUserPresets.json file and find facts about its workflows."""

import json
import re
from argparse import ArgumentParser
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from tools.errors import UserError

DEFAULT_INPUT_PATH = Path("CMakeUserPresets.json")

# A JSON object, for example a presets file or one preset in it.
# Other modules import this alias, so define it here only.
JsonObject = Mapping[str, Any]


def add_workflow_selection_options(parser: ArgumentParser) -> None:
    """Add the options that select the presets file and its workflows."""
    parser.add_argument(
        "--input-path",
        "-i",
        type=Path,
        default=DEFAULT_INPUT_PATH,
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


def read_user_presets(input_path: str | Path) -> Any:
    """Read and return the user presets JSON."""
    with open(input_path, "r", encoding="utf-8") as inp:
        return json.load(inp)


def select_workflow_names(
    user_presets: JsonObject, matching: str | None = None, exclude: str | None = None
) -> list[str]:
    """Return the names of the selected workflows in file order."""
    all_names = [workflow["name"] for workflow in user_presets["workflowPresets"]]
    return filter_workflow_names(all_names, matching, exclude)


def filter_workflow_names(
    names: Sequence[str], matching: str | None = None, exclude: str | None = None
) -> list[str]:
    """Return a new list of the names that match and are not excluded (re.search)."""
    if matching:
        names = [name for name in names if re.search(matching, name) is not None]
    if exclude:
        names = [name for name in names if re.search(exclude, name) is None]
    return list(names)


def build_directory(
    user_presets: JsonObject, workflow_name: str, source_dir: str | Path
) -> Path:
    """Return the build directory of the configure step of a workflow."""
    workflow = find_workflow(user_presets, workflow_name)
    configure_name = get_configure_step_name(workflow)
    configure_preset = find_configure_preset(user_presets, configure_name)
    return resolve_binary_dir(configure_preset["binaryDir"], source_dir)


def find_workflow(user_presets: JsonObject, name: str) -> JsonObject:
    """Return the workflow preset with the given name."""
    return _find_by_name(user_presets["workflowPresets"], name)


def find_configure_preset(user_presets: JsonObject, name: str) -> JsonObject:
    """Return the configure preset with the given name."""
    return _find_by_name(user_presets["configurePresets"], name)


def get_configure_step_name(workflow: JsonObject) -> str:
    """Return the name of the configure step in a workflow."""
    for step in workflow["steps"]:
        if step["type"] == "configure":
            return step["name"]
    raise UserError(f"No configure step in workflow: {workflow['name']}")


def resolve_binary_dir(binary_dir: str, source_dir: str | Path) -> Path:
    """Replace ${sourceDir} with the actual source directory path."""
    return Path(binary_dir.replace("${sourceDir}", str(source_dir)))


def _find_by_name(presets: Sequence[JsonObject], name: str) -> JsonObject:
    """Return the preset with the given name from a list of presets."""
    for preset in presets:
        if preset["name"] == name:
            return preset
    raise UserError(f"Preset not found: {name}")
