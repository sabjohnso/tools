"""Tests for the run_user_workflows module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from tools.run_user_workflows import (
    main,
    make_command_line_parser,
    process_command_line,
    run,
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
                "steps": [{"type": "configure", "name": "gcc-14"}],
            },
            {
                "name": "clang-18",
                "steps": [{"type": "configure", "name": "clang-18"}],
            },
            {
                "name": "gcc-14-devel",
                "steps": [{"type": "configure", "name": "gcc-14"}],
            },
        ],
    }


def _write_presets(tmpdir, data=None):
    path = Path(tmpdir) / "CMakeUserPresets.json"
    path.write_text(json.dumps(data or _preset_data()), encoding="utf-8")
    return path


# --- CLI parser ---


def test_parser_defaults_jobs_to_one():
    parser = make_command_line_parser("run-user-workflows")
    config = parser.parse_args([])
    assert config.jobs == 1


def test_parser_accepts_jobs_flag():
    parser = make_command_line_parser("run-user-workflows")
    config = parser.parse_args(["-j", "4"])
    assert config.jobs == 4


def test_parser_accepts_long_jobs_flag():
    parser = make_command_line_parser("run-user-workflows")
    config = parser.parse_args(["--jobs", "8"])
    assert config.jobs == 8


# --- sequential run (jobs=1, existing behavior) ---


@patch("tools.run_user_workflows.subprocess.run")
def test_run_sequential_calls_cmake_for_each_workflow(mock_run):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        config = process_command_line(
            ["run-user-workflows", "-i", str(path), "-m", "gcc-14$"]
        )
        run(config)
        mock_run.assert_called_once_with(
            ["cmake", "--workflow", "--preset", "gcc-14"], check=True
        )


# --- parallel run (jobs > 1) ---


@patch("tools.run_user_workflows.subprocess.run")
def test_run_parallel_runs_all_matching_workflows(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        config = process_command_line(
            ["run-user-workflows", "-i", str(path), "-j", "2"]
        )
        run(config)
        workflow_names_called = [c.args[0][3] for c in mock_run.call_args_list]
        assert sorted(workflow_names_called) == [
            "clang-18",
            "gcc-14",
            "gcc-14-devel",
        ]


@patch("tools.run_user_workflows.subprocess.run")
def test_run_parallel_captures_output(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="build ok\n", stderr="")
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        config = process_command_line(
            ["run-user-workflows", "-i", str(path), "-j", "2", "-m", "gcc-14$"]
        )
        run(config)
        mock_run.assert_called_once_with(
            ["cmake", "--workflow", "--preset", "gcc-14"],
            check=True,
            stdout=-1,
            stderr=-2,
            text=True,
        )


@patch("tools.run_user_workflows.subprocess.run")
def test_run_sequential_does_not_capture_output(mock_run):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        config = process_command_line(
            ["run-user-workflows", "-i", str(path), "-j", "1", "-m", "gcc-14$"]
        )
        run(config)
        mock_run.assert_called_once_with(
            ["cmake", "--workflow", "--preset", "gcc-14"], check=True
        )


@patch("tools.run_user_workflows.subprocess.run")
def test_run_parallel_raises_on_failure(mock_run):
    import subprocess as sp

    mock_run.side_effect = sp.CalledProcessError(1, "cmake")
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        config = process_command_line(
            ["run-user-workflows", "-i", str(path), "-j", "2", "-m", "gcc-14$"]
        )
        try:
            run(config)
            assert False, "Expected CalledProcessError"
        except sp.CalledProcessError:
            pass


# --- main integration ---


@patch("tools.run_user_workflows.subprocess.run")
def test_main_returns_zero_on_success(mock_run):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        result = main(["run-user-workflows", "-i", str(path)])
        assert result == 0
