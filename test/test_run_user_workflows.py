"""Tests for the run_user_workflows module."""

import json
import tempfile
from pathlib import Path
import threading
from unittest.mock import patch, MagicMock

from tools.run_user_workflows import (
    group_workflows_by_configure_preset,
    main,
    make_command_line_parser,
    process_command_line,
    run,
    workflow_banner,
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


# --- workflow banner ---


def test_workflow_banner_contains_workflow_name():
    banner = workflow_banner("gcc-14")
    assert "gcc-14" in banner


def test_workflow_banner_is_visually_distinct():
    banner = workflow_banner("gcc-14")
    lines = banner.strip().split("\n")
    assert len(lines) >= 3, "Banner should have at least 3 lines for visibility"
    assert len(lines[0]) == len(lines[-1]), (
        "Top and bottom borders should be same width"
    )


def test_workflow_banner_width_adapts_to_name():
    short = workflow_banner("a")
    long = workflow_banner("a-very-long-workflow-name")
    short_width = len(short.strip().split("\n")[0])
    long_width = len(long.strip().split("\n")[0])
    assert long_width > short_width


# --- sequential run (jobs=1, existing behavior) ---


@patch("tools.run_user_workflows.subprocess.run")
def test_run_sequential_prints_banner(mock_run, capsys):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        config = process_command_line(
            ["run-user-workflows", "-i", str(path), "-m", "gcc-14$"]
        )
        run(config)
        captured = capsys.readouterr()
        assert "gcc-14" in captured.out
        lines = captured.out.strip().split("\n")
        assert len(lines) >= 3, "Banner should be printed before the workflow"


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


# --- workflow grouping ---


def test_group_workflows_groups_by_configure_preset():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        groups = group_workflows_by_configure_preset(
            path, ["gcc-14", "gcc-14-devel", "clang-18"]
        )
        assert groups == [["gcc-14", "gcc-14-devel"], ["clang-18"]]


def test_group_workflows_preserves_order_within_group():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        groups = group_workflows_by_configure_preset(path, ["gcc-14-devel", "gcc-14"])
        assert groups == [["gcc-14-devel", "gcc-14"]]


def test_group_workflows_single_workflow():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        groups = group_workflows_by_configure_preset(path, ["clang-18"])
        assert groups == [["clang-18"]]


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
def test_run_parallel_does_not_run_same_preset_concurrently(mock_run):
    """Workflows sharing a configure preset must not overlap in time."""
    active = {}  # configure_preset -> count of concurrent runs
    violations = []
    lock = threading.Lock()

    preset_for_workflow = {
        "gcc-14": "gcc-14",
        "gcc-14-devel": "gcc-14",
        "clang-18": "clang-18",
    }

    def fake_run(cmd, **kwargs):
        name = cmd[3]
        preset = preset_for_workflow[name]
        with lock:
            active[preset] = active.get(preset, 0) + 1
            if active[preset] > 1:
                violations.append(f"{preset} had {active[preset]} concurrent runs")
        import time

        time.sleep(0.05)
        with lock:
            active[preset] -= 1
        return MagicMock(returncode=0, stdout="ok\n", stderr="")

    mock_run.side_effect = fake_run
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        config = process_command_line(
            ["run-user-workflows", "-i", str(path), "-j", "4"]
        )
        run(config)
    assert violations == [], f"Concurrent violations: {violations}"


@patch("tools.run_user_workflows.subprocess.run")
def test_run_parallel_raises_on_failure(mock_run):
    import subprocess as sp

    mock_run.return_value = MagicMock(returncode=1, stdout="fail\n")
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


@patch("tools.run_user_workflows.subprocess.run")
def test_run_parallel_prints_output_from_failed_workflow(mock_run, capsys):
    import subprocess as sp

    mock_run.return_value = MagicMock(returncode=1, stdout="error: build failed\n")
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        config = process_command_line(
            ["run-user-workflows", "-i", str(path), "-j", "2", "-m", "gcc-14$"]
        )
        try:
            run(config)
        except sp.CalledProcessError:
            pass
        captured = capsys.readouterr()
        assert "error: build failed" in captured.out


# --- main integration ---


@patch("tools.run_user_workflows.subprocess.run")
def test_main_returns_zero_on_success(mock_run):
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        result = main(["run-user-workflows", "-i", str(path)])
        assert result == 0
