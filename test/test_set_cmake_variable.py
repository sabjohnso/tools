"""Tests for the set_cmake_variable module."""

import inspect
import subprocess
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from preset_strategies import PATTERNS, expected_names, user_presets, write_json

from tools.errors import UserError

from tools.set_cmake_variable import (
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


# Replace the cmake subprocess. Record each command and its working directory,
# and give the exit status.
class _FakeCMake:
    def __init__(self, returncode=0):
        self.commands = []
        self.working_directories = []
        self.returncode = returncode

    def __call__(self, command, check=False, cwd=None, **kwargs):
        self.commands.append(list(command))
        self.working_directories.append(cwd)
        if check and self.returncode != 0:
            raise subprocess.CalledProcessError(self.returncode, command)
        return subprocess.CompletedProcess(command, self.returncode)


def _run_with_fake_cmake(config):
    fake_cmake = _FakeCMake()
    with patch("tools.set_cmake_variable.subprocess.run", fake_cmake):
        run(config)
    return fake_cmake


# Calculate the expected configure presets without the production code.
def _expected_configure_names(user_presets, matching, exclude):
    configure_of = {
        w["name"]: w["steps"][0]["name"] for w in user_presets["workflowPresets"]
    }
    selected = expected_names(list(configure_of), matching, exclude)
    return list(dict.fromkeys(configure_of[name] for name in selected))


def _run_main_with_fake_cmake(args, fake_cmake=None):
    fake_cmake = fake_cmake or _FakeCMake()
    with patch("tools.set_cmake_variable.subprocess.run", fake_cmake):
        result = main(["set-cmake-variable", *args])
    return result, fake_cmake.commands


# --- make_cmake_command ---


def test_make_cmake_command_single_definition():
    result = make_cmake_command("gcc-14", ["CMAKE_BUILD_TYPE=Debug"])
    assert result == ["cmake", "--preset", "gcc-14", "-DCMAKE_BUILD_TYPE=Debug"]


def test_make_cmake_command_multiple_definitions():
    result = make_cmake_command("gcc-14", ["CMAKE_BUILD_TYPE=Debug", "ENABLE_TESTS=ON"])
    assert result == [
        "cmake",
        "--preset",
        "gcc-14",
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


# --- run ---


def test_run_calls_cmake_once_for_a_configure_preset_of_two_workflows(presets_file):
    config = _config(
        presets_file, definitions=["CMAKE_BUILD_TYPE=Debug"], matching="gcc-14"
    )
    fake_cmake = _run_with_fake_cmake(config)
    assert fake_cmake.commands == [
        ["cmake", "--preset", "gcc-14", "-DCMAKE_BUILD_TYPE=Debug"]
    ]


def test_run_calls_cmake_in_the_directory_of_the_presets_file(
    tmp_path, presets_file, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    config = _config(
        presets_file.relative_to(tmp_path), definitions=["CMAKE_BUILD_TYPE=Debug"]
    )
    fake_cmake = _run_with_fake_cmake(config)
    assert fake_cmake.working_directories == [tmp_path.resolve()] * 2


def test_run_reports_a_workflow_without_a_configure_step(tmp_path):
    presets = {
        "configurePresets": [],
        "workflowPresets": [{"name": "gcc-14", "steps": []}],
    }
    path = write_json(tmp_path / "CMakeUserPresets.json", presets)
    config = _config(path, definitions=["CMAKE_BUILD_TYPE=Debug"])
    with pytest.raises(UserError, match="No configure step in workflow: gcc-14"):
        _run_with_fake_cmake(config)


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    user_presets=user_presets(),
    matching=PATTERNS,
    exclude=PATTERNS,
    definitions=st.lists(st.sampled_from(["A=1", "B=OFF", "C="]), min_size=1),
)
def test_run_calls_cmake_once_for_each_selected_configure_preset_in_first_order(
    tmp_path, user_presets, matching, exclude, definitions
):
    path = write_json(tmp_path / "CMakeUserPresets.json", user_presets)
    config = _config(path, matching, exclude, definitions)
    fake_cmake = _run_with_fake_cmake(config)
    assert fake_cmake.commands == [
        ["cmake", "--preset", name, *[f"-D{d}" for d in definitions]]
        for name in _expected_configure_names(user_presets, matching, exclude)
    ]
    assert set(fake_cmake.working_directories) <= {tmp_path.resolve()}


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


def test_main_reconfigures_each_distinct_configure_preset_once(presets_file):
    _, commands = _run_main_with_fake_cmake(
        ["-i", str(presets_file), "-D", "CMAKE_BUILD_TYPE=Debug"]
    )
    assert commands == [
        ["cmake", "--preset", "gcc-14", "-DCMAKE_BUILD_TYPE=Debug"],
        ["cmake", "--preset", "clang-18", "-DCMAKE_BUILD_TYPE=Debug"],
    ]


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


def test_main_with_matching_filter(presets_file):
    result, commands = _run_main_with_fake_cmake(
        ["-i", str(presets_file), "-m", "clang", "-D", "CMAKE_BUILD_TYPE=Debug"]
    )
    assert result == 0
    assert commands == [["cmake", "--preset", "clang-18", "-DCMAKE_BUILD_TYPE=Debug"]]


def test_main_with_matching_filter_in_the_middle_of_a_name(presets_file):
    result, commands = _run_main_with_fake_cmake(
        ["-i", str(presets_file), "-m", "14", "-D", "CMAKE_BUILD_TYPE=Debug"]
    )
    assert result == 0
    assert commands == [["cmake", "--preset", "gcc-14", "-DCMAKE_BUILD_TYPE=Debug"]]


def test_main_with_exclude_filter(presets_file):
    result, commands = _run_main_with_fake_cmake(
        ["-i", str(presets_file), "-e", "gcc", "-D", "CMAKE_BUILD_TYPE=Debug"]
    )
    assert result == 0
    assert commands == [["cmake", "--preset", "clang-18", "-DCMAKE_BUILD_TYPE=Debug"]]


# --- program name and script ---


def test_usage_names_the_program_without_its_directory(capsys):
    with pytest.raises(SystemExit):
        main(["/usr/local/bin/set-cmake-variable", "--help"])
    assert capsys.readouterr().out.startswith("usage: set-cmake-variable ")


def test_module_file_runs_as_a_script():
    script = Path(inspect.getfile(main))
    result = subprocess.run(
        [script, "--help"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    assert result.stdout.startswith("usage: set_cmake_variable.py ")
