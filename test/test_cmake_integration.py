"""Integration tests that run generated user presets through CMake."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.make_user_presets import main
from tools.user_presets import build_directory

COMPILER_NAME = "system"

# Each row: workflow suffix, expected configuration, expected NDEBUG state.
WORKFLOWS = [
    ("", "Release", "NDEBUG=on"),
    ("-devel", "RelWithAsserts", "NDEBUG=off"),
    ("-debug", "Debug", "NDEBUG=off"),
]

CMAKE_LISTS = """\
cmake_minimum_required(VERSION 3.21)
project(show_config LANGUAGES CXX)
enable_testing()

add_executable(show_config show_config.cpp)
target_compile_definitions(show_config PRIVATE BUILD_CONFIG="$<CONFIG>")
add_test(NAME show_config COMMAND show_config)

add_executable(failed_assert failed_assert.cpp)
"""

SHOW_CONFIG_SOURCE = """\
#include <iostream>

int main() {
  std::cout << "CONFIG=" << BUILD_CONFIG << "\\n";
#ifdef NDEBUG
  std::cout << "NDEBUG=on\\n";
#else
  std::cout << "NDEBUG=off\\n";
#endif
  return 0;
}
"""

FAILED_ASSERT_SOURCE = """\
#include <cassert>

int main(int argc, char**) {
  assert(argc == 0);
  return 0;
}
"""

CONFIGURATION_TYPES = "Debug;Release;RelWithDebInfo;RelWithAsserts"


def _find_first(*names):
    """Return the first program name that is on PATH, or None."""
    return next((name for name in names if shutil.which(name)), None)


CXX = _find_first("g++", "c++")
CC = _find_first("gcc", "cc")

pytestmark = [
    pytest.mark.cmake,
    pytest.mark.skipif(
        shutil.which("cmake") is None
        or shutil.which("ninja") is None
        or CXX is None
        or CC is None,
        reason="cmake, ninja or a C/C++ compiler is not on PATH",
    ),
    # Run all tests of this module on one xdist worker, so that the module
    # fixture builds the project one time only.
    pytest.mark.xdist_group("cmake"),
]


@pytest.fixture(scope="module")
def built_project(tmp_path_factory):
    project = tmp_path_factory.mktemp("project")
    _write_project(project, "Ninja Multi-Config")
    status = main(
        [
            "make-user-presets",
            str(project / "compilers.json"),
            "-o",
            str(project / "CMakeUserPresets.json"),
        ]
    )
    assert status == 0
    results = {
        suffix: _run(
            ["cmake", "--workflow", "--preset", COMPILER_NAME + suffix], project
        )
        for suffix, _, _ in WORKFLOWS
    }
    return project, results


@pytest.mark.parametrize("suffix", [suffix for suffix, _, _ in WORKFLOWS])
def test_workflow_succeeds(built_project, suffix):
    _, results = built_project
    result = results[suffix]
    assert result.returncode == 0, result.stdout


@pytest.mark.parametrize("suffix, configuration, ndebug", WORKFLOWS)
def test_workflow_builds_its_configuration(
    built_project, suffix, configuration, ndebug
):
    project, _ = built_project
    workflow = COMPILER_NAME + suffix
    result = _run(
        [str(_executable(project, workflow, configuration, "show_config"))], project
    )
    assert result.returncode == 0, result.stdout
    assert f"CONFIG={configuration}" in result.stdout.splitlines(), result.stdout
    assert ndebug in result.stdout.splitlines(), result.stdout


def test_rel_with_asserts_build_stops_at_a_failed_assert(built_project):
    project, _ = built_project
    workflow = COMPILER_NAME + "-devel"
    result = _run(
        [str(_executable(project, workflow, "RelWithAsserts", "failed_assert"))],
        project,
    )
    assert result.returncode != 0, result.stdout


def _write_project(directory, generator):
    """Write a small C++ project and a compiler file for the system compiler."""
    (directory / "CMakeLists.txt").write_text(CMAKE_LISTS, encoding="utf-8")
    (directory / "show_config.cpp").write_text(SHOW_CONFIG_SOURCE, encoding="utf-8")
    (directory / "failed_assert.cpp").write_text(FAILED_ASSERT_SOURCE, encoding="utf-8")
    _write_json(directory / "CMakePresets.json", _project_presets(generator))
    _write_json(directory / "compilers.json", [_system_compiler()])


def _project_presets(generator):
    """Return project presets whose hidden default preset uses the generator."""
    return {
        "version": 6,
        "configurePresets": [
            {
                "name": "default",
                "hidden": True,
                "generator": generator,
                "cacheVariables": {"CMAKE_CONFIGURATION_TYPES": CONFIGURATION_TYPES},
            }
        ],
    }


def _system_compiler():
    """Return the compiler entry for the C and C++ compilers on PATH."""
    root = Path(shutil.which(CXX)).parent.parent
    return {"name": COMPILER_NAME, "root": str(root), "cc": CC, "cxx": CXX}


def _write_json(path, data):
    """Write the data to the path as JSON."""
    path.write_text(json.dumps(data, indent=4), encoding="utf-8")


def _executable(project, workflow, configuration, target):
    """Return the path of a target that the Ninja Multi-Config generator built."""
    user_presets = json.loads(
        (project / "CMakeUserPresets.json").read_text(encoding="utf-8")
    )
    # Ninja Multi-Config puts each target in <build directory>/<config>/<target>.
    return build_directory(user_presets, workflow, project) / configuration / target


def _run(command, cwd):
    """Run the command and return the result with stderr merged into stdout."""
    return subprocess.run(
        command,
        cwd=cwd,
        env=dict(os.environ),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
