"""Tests for the set_cmake_variable module."""

import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tools.errors import UserError

from tools.set_cmake_variable import (
    filter_workflow_names,
    main,
    make_cmake_command,
    make_command_line_parser,
    run,
    validate_definitions,
)


def _config(input_path, matching=None, exclude=None, definitions=None):
    return SimpleNamespace(
        input_path=input_path,
        matching=matching,
        exclude=exclude,
        definitions=definitions or [],
    )


# Replace the cmake subprocess. Record each command and give the exit status.
class _FakeCMake:
    def __init__(self, returncode=0):
        self.commands = []
        self.returncode = returncode

    def __call__(self, command, check=False, **kwargs):
        self.commands.append(list(command))
        if check and self.returncode != 0:
            raise subprocess.CalledProcessError(self.returncode, command)
        return subprocess.CompletedProcess(command, self.returncode)


def _run_main_with_fake_cmake(args, fake_cmake=None):
    fake_cmake = fake_cmake or _FakeCMake()
    with patch("tools.set_cmake_variable.subprocess.run", fake_cmake):
        result = main(["set-cmake-variable", *args])
    return result, fake_cmake.commands


# --- make_cmake_command ---


def test_make_cmake_command_single_definition():
    result = make_cmake_command(Path("/build"), ["CMAKE_BUILD_TYPE=Debug"])
    assert result == ["cmake", "/build", "-DCMAKE_BUILD_TYPE=Debug"]


def test_make_cmake_command_multiple_definitions():
    result = make_cmake_command(
        Path("/build"), ["CMAKE_BUILD_TYPE=Debug", "ENABLE_TESTS=ON"]
    )
    assert result == [
        "cmake",
        "/build",
        "-DCMAKE_BUILD_TYPE=Debug",
        "-DENABLE_TESTS=ON",
    ]


# --- validate_definitions ---


def test_validate_definitions_raises_when_none():
    config = _config(Path("dummy"), definitions=[])
    with pytest.raises(UserError, match="-D"):
        validate_definitions(config)


def test_validate_definitions_passes_with_definitions():
    config = _config(Path("dummy"), definitions=["CMAKE_BUILD_TYPE=Debug"])
    validate_definitions(config)


# --- parser ---


def test_parser_parses_single_definition():
    parser = make_command_line_parser("set-cmake-variable")
    config = parser.parse_args(["-D", "CMAKE_BUILD_TYPE=Debug"])
    assert config.definitions == ["CMAKE_BUILD_TYPE=Debug"]


def test_parser_parses_multiple_definitions():
    parser = make_command_line_parser("set-cmake-variable")
    config = parser.parse_args(
        ["-D", "CMAKE_BUILD_TYPE=Debug", "-D", "ENABLE_TESTS=ON"]
    )
    assert config.definitions == ["CMAKE_BUILD_TYPE=Debug", "ENABLE_TESTS=ON"]


# --- filter_workflow_names ---


def test_filter_workflow_names_matches_in_the_middle_of_a_name():
    names = ["gcc-14", "clang-18", "gcc-14-devel"]
    result = filter_workflow_names(_config(None, matching="14"), names)
    assert result == ["gcc-14", "gcc-14-devel"]


def test_filter_workflow_names_excludes_in_the_middle_of_a_name():
    names = ["gcc-14", "clang-18", "gcc-14-devel"]
    result = filter_workflow_names(_config(None, exclude="14"), names)
    assert result == ["clang-18"]


# --- run ---


def test_run_calls_cmake_for_each_build_directory(presets_file):
    config = _config(
        presets_file, definitions=["CMAKE_BUILD_TYPE=Debug"], matching="gcc-14$"
    )
    fake_cmake = _FakeCMake()
    with patch("tools.set_cmake_variable.subprocess.run", fake_cmake):
        run(config)
    assert len(fake_cmake.commands) == 1


def test_run_passes_definitions_to_cmake(presets_file):
    config = _config(
        presets_file,
        definitions=["CMAKE_BUILD_TYPE=Debug", "ENABLE_TESTS=ON"],
        matching="gcc-14$",
    )
    fake_cmake = _FakeCMake()
    with patch("tools.set_cmake_variable.subprocess.run", fake_cmake):
        run(config)
    assert "-DCMAKE_BUILD_TYPE=Debug" in fake_cmake.commands[0]
    assert "-DENABLE_TESTS=ON" in fake_cmake.commands[0]


# --- main ---


def test_main_returns_zero_on_success(presets_file):
    result, _ = _run_main_with_fake_cmake(
        ["-i", str(presets_file), "-D", "CMAKE_BUILD_TYPE=Debug"]
    )
    assert result == 0


def test_main_reconfigures_each_distinct_build_directory_once(tmp_path, presets_file):
    _, commands = _run_main_with_fake_cmake(
        ["-i", str(presets_file), "-D", "CMAKE_BUILD_TYPE=Debug"]
    )
    assert sorted(commands) == sorted(
        [
            ["cmake", str(tmp_path / "build-gcc-14"), "-DCMAKE_BUILD_TYPE=Debug"],
            ["cmake", str(tmp_path / "build-clang-18"), "-DCMAKE_BUILD_TYPE=Debug"],
        ]
    )


def test_main_returns_returncode_on_failure(presets_file):
    result, _ = _run_main_with_fake_cmake(
        ["-i", str(presets_file), "-D", "CMAKE_BUILD_TYPE=Debug"],
        _FakeCMake(returncode=2),
    )
    assert result == 2


def test_main_reports_missing_definitions_without_cmake_call(presets_file, capsys):
    fake_cmake = _FakeCMake()
    with patch("tools.set_cmake_variable.subprocess.run", fake_cmake):
        result = main(["set-cmake-variable", "-i", str(presets_file)])
    assert result == 1
    assert capsys.readouterr().err.startswith("set-cmake-variable: ")
    assert fake_cmake.commands == []


def test_main_with_matching_filter(tmp_path, presets_file):
    result, commands = _run_main_with_fake_cmake(
        ["-i", str(presets_file), "-m", "clang", "-D", "CMAKE_BUILD_TYPE=Debug"]
    )
    assert result == 0
    assert len(commands) == 1
    assert commands[0][1] == str(tmp_path / "build-clang-18")


def test_main_with_matching_filter_in_the_middle_of_a_name(tmp_path, presets_file):
    result, commands = _run_main_with_fake_cmake(
        ["-i", str(presets_file), "-m", "14", "-D", "CMAKE_BUILD_TYPE=Debug"]
    )
    assert result == 0
    assert commands == [
        ["cmake", str(tmp_path / "build-gcc-14"), "-DCMAKE_BUILD_TYPE=Debug"]
    ]
