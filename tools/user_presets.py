"""Find facts about workflows in a CMakeUserPresets.json structure."""

from pathlib import Path


def build_directory(user_presets, workflow_name, source_dir):
    """Return the build directory of the configure step of a workflow."""
    workflow = find_workflow(user_presets, workflow_name)
    configure_name = get_configure_step_name(workflow)
    configure_preset = find_configure_preset(user_presets, configure_name)
    return resolve_binary_dir(configure_preset["binaryDir"], source_dir)


def find_workflow(user_presets, name):
    """Return the workflow preset with the given name."""
    return _find_by_name(user_presets["workflowPresets"], name)


def find_configure_preset(user_presets, name):
    """Return the configure preset with the given name."""
    return _find_by_name(user_presets["configurePresets"], name)


def get_configure_step_name(workflow):
    """Return the name of the configure step in a workflow."""
    for step in workflow["steps"]:
        if step["type"] == "configure":
            return step["name"]
    raise KeyError(f"No configure step in workflow: {workflow['name']}")


def resolve_binary_dir(binary_dir, source_dir):
    """Replace ${sourceDir} with the actual source directory path."""
    return Path(binary_dir.replace("${sourceDir}", str(source_dir)))


def _find_by_name(presets, name):
    """Return the preset with the given name from a list of presets."""
    for preset in presets:
        if preset["name"] == name:
            return preset
    raise KeyError(f"Preset not found: {name}")
