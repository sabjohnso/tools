#!/usr/bin/env python
"""Generate CMakeUserPresets.json from a compiler specification file."""

import os
import sys
import json
import importlib.resources
from argparse import ArgumentParser
from pathlib import Path

import jsonschema

from tools.error_policy import add_stack_trace_option, run_tool
from tools.errors import UserError
from tools.multi_config import (
    SingleConfigError,
    find_generator,
    is_multi_config_generator,
)


def main(args):
    """Run the tool with the error policy and return the exit code."""
    return run_tool(execute, args)


def execute(args):
    """Run the preset generator and return 0."""
    config = process_command_line(args)
    run(config)
    return 0


def process_command_line(args):
    """Process the command line arguments and return the runtime configuration."""
    parser = make_command_line_parser(Path(args[0]).name)
    config = parser.parse_args(args[1:])
    validate_input(config)
    return config


def make_command_line_parser(prog):
    """Return the command line parser."""
    parser = ArgumentParser(prog=prog)
    parser.add_argument("filename", type=Path)
    parser.add_argument(
        "--output-file", "-o", type=Path, default=Path("CMakeUserPresets.json")
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        default=False,
        help="Dump the user presets to stdout instead of a file",
    )
    parser.add_argument(
        "--replace-existing",
        action="store_true",
        default=False,
        help="""Overwrite the output file if it exists.
        Otherwise, it is an error if the output file
        already exists""",
    )

    parser.add_argument(
        "--test-jobs",
        type=int,
        default=1,
        help="The number of jobs to use when running the tests",
    )

    parser.add_argument(
        "--inherits",
        default="default",
        help="The configure preset to inherit from (default: 'default')",
    )
    add_stack_trace_option(parser)
    return parser


def validate_input(config):
    """Validate that the input file exists and the output file is writable."""
    if not config.filename.exists():
        raise UserError(MISSING_INPUT_ERROR.format(input_file=config.filename))
    if (
        config.output_file.exists()
        and not config.replace_existing
        and not config.stdout
    ):
        raise UserError(EXISTING_OUTPUT_ERROR.format(output_file=config.output_file))


def run(config):
    """Read, validate, transform, and write the user presets."""
    input_data = read_input_data(config)
    validate_input_data(input_data)
    validate_project_generator(config)
    output_data = make_output_data(config, input_data, os.environ)
    write_output_data(config, output_data)


def validate_project_generator(config):
    """Raise SingleConfigError unless the inherited preset is multi-config."""
    project_presets = read_project_presets(config)
    generator = find_generator(project_presets, config.inherits)
    if not is_multi_config_generator(generator):
        raise SingleConfigError(
            SINGLE_CONFIG_ERROR.format(preset=config.inherits, generator=generator)
        )


def read_project_presets(config):
    """Read and return the CMakePresets.json next to the output file."""
    path = config.output_file.parent / "CMakePresets.json"
    if not path.exists():
        raise UserError(MISSING_PROJECT_PRESETS_ERROR.format(path=path))
    with open(path, "r", encoding="utf-8") as inp:
        return json.load(inp)


def validate_input_data(input_data):
    """Raise UserError if the input data does not match the compiler schema."""
    try:
        validate_schema(input_data)
    except jsonschema.ValidationError as error:
        raise UserError(f"invalid compiler list: {error.message}") from error


def validate_schema(input_data):
    """Validate the input data against the compiler JSON schema."""
    schema_file = importlib.resources.files("tools").joinpath("compilers.schema.json")
    schema = json.loads(schema_file.read_text(encoding="utf-8"))
    jsonschema.validate(input_data, schema)


def read_input_data(config):
    """Read and return the JSON input data from disk."""
    with open(config.filename, "r", encoding="utf-8") as inp:
        return json.load(inp)


def write_output_data(config, output_data):
    """Write the output data to a file or stdout."""
    if config.stdout:
        print(json.dumps(output_data))
    else:
        with open(config.output_file, "w", encoding="utf-8") as out:
            json.dump(output_data, out, indent=4)


def make_output_data(config, input_data, parent_environment):
    """Assemble the complete CMakeUserPresets output structure."""
    return {
        "version": 6,
        "cmakeMinimumRequired": {"major": 3, "minor": 21, "patch": 0},
        "configurePresets": make_configure_presets(
            config, input_data, parent_environment
        ),
        "buildPresets": make_build_presets(config, input_data),
        "testPresets": make_test_presets(config, input_data),
        "workflowPresets": make_workflow_presets(config, input_data),
    }


def make_configure_presets(config, input_data, parent_environment):
    """Return configure presets for all compilers."""
    return [
        make_configure_preset(config, compiler, parent_environment)
        for compiler in input_data
    ]


def make_build_presets(config, input_data):
    """Return build presets for all compilers and build types."""
    return (
        [{"name": "baseBuild", "jobs": 16, "configurePreset": config.inherits}]
        + [
            make_build_preset(compiler["name"], "", "Release")
            for compiler in input_data
        ]
        + [
            make_build_preset(compiler["name"], "-devel", "RelWithAsserts")
            for compiler in input_data
        ]
        + [
            make_build_preset(compiler["name"], "-debug", "Debug")
            for compiler in input_data
        ]
    )


def make_build_preset(workflow_name, suffix, configuration):
    """Return a single build preset for the given name and configuration."""
    return {
        "name": workflow_name + suffix,
        "inherits": "baseBuild",
        "configuration": configuration,
        "configurePreset": workflow_name,
    }


def make_test_presets(config, input_data):
    """Return test presets for all compilers and build types."""
    return (
        [
            {
                "name": "baseTest",
                "output": {"outputOnFailure": True},
                "configurePreset": config.inherits,
                "execution": {"jobs": config.test_jobs},
            }
        ]
        + [make_test_preset(compiler["name"], "", "Release") for compiler in input_data]
        + [
            make_test_preset(compiler["name"], "-devel", "RelWithAsserts")
            for compiler in input_data
        ]
        + [
            make_test_preset(compiler["name"], "-debug", "Debug")
            for compiler in input_data
        ]
    )


def make_test_preset(workflow_name, suffix, configuration):
    """Return a single test preset for the given name and configuration."""
    return {
        "name": workflow_name + suffix,
        "inherits": "baseTest",
        "configuration": configuration,
        "configurePreset": workflow_name,
    }


def make_configure_preset(config, compiler, parent_environment):
    """Return a single configure preset for the given compiler."""
    return {
        "name": compiler["name"],
        "inherits": config.inherits,
        "hidden": False,
        "binaryDir": binary_directory(compiler),
        "cacheVariables": custom_build_type_flags(),
        "environment": compiler_environment(compiler, parent_environment),
    }


def compiler_environment(compiler, parent_environment):
    """Return the environment variables that select the compiler."""
    if compiler.get("addPaths", False):
        return add_paths_environment(compiler, parent_environment)
    return {
        "CC": f"{compiler['root']}/bin/{compiler['cc']}",
        "CXX": f"{compiler['root']}/bin/{compiler['cxx']}",
    }


def add_paths_environment(compiler, parent_environment):
    """Return an environment that puts the compiler directories first."""
    root = compiler["root"]
    search_paths = {
        variable: search_path(
            [f"{root}/{directory}" for directory in directories],
            variable,
            parent_environment,
        )
        for variable, directories in COMPILER_SEARCH_DIRECTORIES.items()
    }
    return search_paths | {"CC": compiler["cc"], "CXX": compiler["cxx"]}


def search_path(directories, variable, parent_environment):
    """Return the directories, then the parent variable if it has a value.

    An empty element in a search path means the current directory, so the
    parent variable is added only when the parent environment gives it a value.
    """
    if parent_environment.get(variable):
        return ":".join([*directories, f"$penv{{{variable}}}"])
    return ":".join(directories)


def custom_build_type_flags():
    """Return cache variables defining compiler flags for custom build types."""
    return {
        "CMAKE_C_FLAGS_RELWITHDEBINFO": "-O3 -g -DNDEBUG",
        "CMAKE_CXX_FLAGS_RELWITHDEBINFO": "-O3 -g -DNDEBUG",
        "CMAKE_C_FLAGS_RELWITHASSERTS": "-O3",
        "CMAKE_CXX_FLAGS_RELWITHASSERTS": "-O3",
    }


def make_workflow_presets(config, input_data):
    """Return workflow presets for all compilers and build types."""
    return (
        [make_workflow_preset(compiler["name"], "") for compiler in input_data]
        + [make_workflow_preset(compiler["name"], "-devel") for compiler in input_data]
        + [make_workflow_preset(compiler["name"], "-debug") for compiler in input_data]
    )


def make_workflow_preset(workflow_name, suffix):
    """Return a single workflow preset for the given name and suffix."""
    return {
        "name": workflow_name + suffix,
        "steps": [
            {"type": "configure", "name": workflow_name},
            {"type": "build", "name": workflow_name + suffix},
            {"type": "test", "name": workflow_name + suffix},
        ],
    }


def binary_directory(compiler):
    """Return the build directory path for the given compiler."""
    return "${sourceDir}/build-" + compiler["name"]


COMPILER_SEARCH_DIRECTORIES = {
    "PATH": ["bin"],
    "LIBRARY_PATH": ["lib", "lib64"],
    "LD_LIBRARY_PATH": ["lib", "lib64"],
    "CPATH": ["include"],
}

MISSING_INPUT_ERROR = """
Could not find input file: {input_file}
"""

EXISTING_OUTPUT_ERROR = """
The output file ({output_file}) already exists.  To
overwrite it, provide the switch --replace-existing.
"""

MISSING_PROJECT_PRESETS_ERROR = """
Could not find the project presets file: {path}
"""

SINGLE_CONFIG_ERROR = """
The configure preset '{preset}' uses the generator {generator}.
The -devel and -debug workflows need a multi-configuration generator,
for example "Ninja Multi-Config". Set it in CMakePresets.json, or
select a different preset with --inherits.
"""

if __name__ == "__main__":
    sys.exit(main(sys.argv))
