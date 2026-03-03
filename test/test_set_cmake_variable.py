"""Tests for the set_cmake_variable module."""

import json
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.set_cmake_variable import (
    main,
    make_cmake_command,
    make_command_line_parser,
    run,
    validate_definitions,
)


def _preset_data():
    return {
        "version": 6,
        "configurePresets": [
            {"name": "gcc-14", "binaryDir": "${sourceDir}/build-gcc-14"},
            {"name": "clang-18", "binaryDir": "${sourceDir}/build-clang-18"},
        ],
        "workflowPresets": [
            {
                "name": "gcc-14",
                "steps": [
                    {"type": "configure", "name": "gcc-14"},
                    {"type": "build", "name": "gcc-14"},
                    {"type": "test", "name": "gcc-14"},
                ],
            },
            {
                "name": "gcc-14-devel",
                "steps": [
                    {"type": "configure", "name": "gcc-14"},
                    {"type": "build", "name": "gcc-14-devel"},
                    {"type": "test", "name": "gcc-14-devel"},
                ],
            },
            {
                "name": "clang-18",
                "steps": [
                    {"type": "configure", "name": "clang-18"},
                    {"type": "build", "name": "clang-18"},
                    {"type": "test", "name": "clang-18"},
                ],
            },
        ],
    }


def _write_presets(tmpdir, data=None):
    path = Path(tmpdir) / "CMakeUserPresets.json"
    path.write_text(json.dumps(data or _preset_data()), encoding="utf-8")
    return path


def _config(input_path, matching=None, exclude=None, definitions=None):
    return SimpleNamespace(
        input_path=input_path,
        matching=matching,
        exclude=exclude,
        definitions=definitions or [],
    )


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
    try:
        validate_definitions(config)
        assert False, "Expected SystemExit"
    except SystemExit:
        pass


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


def test_run_calls_cmake_for_each_build_directory():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        config = _config(
            path, definitions=["CMAKE_BUILD_TYPE=Debug"], matching="gcc-14$"
        )
        with patch("tools.set_cmake_variable.subprocess") as mock_sub:
            run(config)
            assert mock_sub.run.call_count == 1


def test_run_passes_definitions_to_cmake():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        config = _config(
            path,
            definitions=["CMAKE_BUILD_TYPE=Debug", "ENABLE_TESTS=ON"],
            matching="gcc-14$",
        )
        with patch("tools.set_cmake_variable.subprocess") as mock_sub:
            run(config)
            call_args = mock_sub.run.call_args[0][0]
            assert "-DCMAKE_BUILD_TYPE=Debug" in call_args
            assert "-DENABLE_TESTS=ON" in call_args


# --- main ---


def test_main_returns_zero_on_success():
    with patch("tools.set_cmake_variable.run"):
        with patch("tools.set_cmake_variable.validate_definitions"):
            with tempfile.TemporaryDirectory() as tmpdir:
                path = _write_presets(tmpdir)
                result = main(
                    [
                        "set-cmake-variable",
                        "-i",
                        str(path),
                        "-D",
                        "CMAKE_BUILD_TYPE=Debug",
                    ]
                )
    assert result == 0


def test_main_returns_returncode_on_failure():
    with patch(
        "tools.set_cmake_variable.run",
        side_effect=subprocess.CalledProcessError(2, "cmake"),
    ):
        with patch("tools.set_cmake_variable.validate_definitions"):
            with tempfile.TemporaryDirectory() as tmpdir:
                path = _write_presets(tmpdir)
                result = main(
                    [
                        "set-cmake-variable",
                        "-i",
                        str(path),
                        "-D",
                        "CMAKE_BUILD_TYPE=Debug",
                    ]
                )
    assert result == 2


def test_main_with_matching_filter():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        with patch("tools.set_cmake_variable.subprocess") as mock_sub:
            result = main(
                [
                    "set-cmake-variable",
                    "-i",
                    str(path),
                    "-m",
                    "clang",
                    "-D",
                    "CMAKE_BUILD_TYPE=Debug",
                ]
            )
            assert result == 0
            assert mock_sub.run.call_count == 1
            call_args = mock_sub.run.call_args[0][0]
            build_dir = str(Path(tmpdir) / "build-clang-18")
            assert call_args[1] == build_dir
