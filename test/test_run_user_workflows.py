"""Tests for the run_user_workflows module."""

import os
import stat
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.run_user_workflows import (
    group_workflows_by_configure_preset,
    main,
    make_command_line_parser,
    process_command_line,
    run,
    workflow_banner,
)


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


@patch("tools.run_user_workflows.monitor_subprocess")
def test_run_sequential_prints_banner(mock_monitor, presets_file, capsys):
    mock_monitor.return_value = (0, [(10.0, 1000)], 1.0)
    config = process_command_line(
        ["run-user-workflows", "-i", str(presets_file), "-m", "gcc-14$"]
    )
    run(config)
    captured = capsys.readouterr()
    assert "gcc-14" in captured.out


@patch("tools.run_user_workflows.monitor_subprocess")
def test_run_sequential_calls_monitor_for_each_workflow(mock_monitor, presets_file):
    mock_monitor.return_value = (0, [(10.0, 1000)], 1.0)
    config = process_command_line(
        ["run-user-workflows", "-i", str(presets_file), "-m", "gcc-14$"]
    )
    run(config)
    mock_monitor.assert_called_once_with(["cmake", "--workflow", "--preset", "gcc-14"])


@patch("tools.run_user_workflows.monitor_subprocess")
def test_run_sequential_prints_resource_table(mock_monitor, presets_file, capsys):
    mock_monitor.return_value = (0, [(50.0, 1024 * 1024 * 100)], 2.5)
    config = process_command_line(
        ["run-user-workflows", "-i", str(presets_file), "-m", "gcc-14$"]
    )
    run(config)
    captured = capsys.readouterr()
    assert "CPU" in captured.out
    assert "RSS" in captured.out


@patch("tools.run_user_workflows.monitor_subprocess")
def test_run_sequential_raises_on_failure(mock_monitor, presets_file):
    mock_monitor.return_value = (1, [(10.0, 1000)], 0.5)
    config = process_command_line(
        ["run-user-workflows", "-i", str(presets_file), "-m", "gcc-14$"]
    )
    with pytest.raises(subprocess.CalledProcessError):
        run(config)


# --- workflow grouping ---


def test_group_workflows_groups_by_configure_preset(presets_file):
    groups = group_workflows_by_configure_preset(
        presets_file, ["gcc-14", "gcc-14-devel", "clang-18"]
    )
    assert groups == [["gcc-14", "gcc-14-devel"], ["clang-18"]]


def test_group_workflows_preserves_order_within_group(presets_file):
    groups = group_workflows_by_configure_preset(
        presets_file, ["gcc-14-devel", "gcc-14"]
    )
    assert groups == [["gcc-14-devel", "gcc-14"]]


def test_group_workflows_single_workflow(presets_file):
    groups = group_workflows_by_configure_preset(presets_file, ["clang-18"])
    assert groups == [["clang-18"]]


# --- parallel run (jobs > 1) ---


@patch("tools.run_user_workflows.subprocess.run")
def test_run_parallel_runs_all_matching_workflows(mock_run, presets_file):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok\n", stderr="")
    config = process_command_line(
        ["run-user-workflows", "-i", str(presets_file), "-j", "2"]
    )
    run(config)
    workflow_names_called = [c.args[0][3] for c in mock_run.call_args_list]
    assert sorted(workflow_names_called) == [
        "clang-18",
        "gcc-14",
        "gcc-14-devel",
    ]


def _install_fake_cmake(directory: Path, script: str) -> None:
    cmake = directory / "cmake"
    cmake.write_text(f"#!/bin/sh\n{script}\n", encoding="utf-8")
    cmake.chmod(cmake.stat().st_mode | stat.S_IXUSR)


def test_run_parallel_prints_stdout_and_stderr_of_the_workflow(
    presets_file, tmp_path, monkeypatch, capsys
):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _install_fake_cmake(bin_dir, 'echo "build ok $3"\necho "warning $3" >&2')
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    config = process_command_line(
        ["run-user-workflows", "-i", str(presets_file), "-j", "2", "-m", "gcc-14$"]
    )
    run(config)
    captured = capsys.readouterr()
    assert "build ok gcc-14" in captured.out
    assert "warning gcc-14" in captured.out


@patch("tools.run_user_workflows.monitor_subprocess")
def test_run_sequential_uses_monitor(mock_monitor, presets_file):
    mock_monitor.return_value = (0, [(10.0, 1000)], 1.0)
    config = process_command_line(
        ["run-user-workflows", "-i", str(presets_file), "-j", "1", "-m", "gcc-14$"]
    )
    run(config)
    mock_monitor.assert_called_once_with(["cmake", "--workflow", "--preset", "gcc-14"])


@patch("tools.run_user_workflows.subprocess.run")
def test_run_parallel_does_not_run_same_preset_concurrently(mock_run, presets_file):
    # Workflows that share a configure preset must not run at the same time.
    active = {}
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
        time.sleep(0.05)
        with lock:
            active[preset] -= 1
        return MagicMock(returncode=0, stdout="ok\n", stderr="")

    mock_run.side_effect = fake_run
    config = process_command_line(
        ["run-user-workflows", "-i", str(presets_file), "-j", "4"]
    )
    run(config)
    assert violations == [], f"Concurrent violations: {violations}"


@patch("tools.run_user_workflows.subprocess.run")
def test_run_parallel_raises_on_failure(mock_run, presets_file):
    mock_run.return_value = MagicMock(returncode=1, stdout="fail\n")
    config = process_command_line(
        ["run-user-workflows", "-i", str(presets_file), "-j", "2", "-m", "gcc-14$"]
    )
    with pytest.raises(subprocess.CalledProcessError):
        run(config)


@patch("tools.run_user_workflows.subprocess.run")
def test_run_parallel_prints_output_from_failed_workflow(
    mock_run, presets_file, capsys
):
    mock_run.return_value = MagicMock(returncode=1, stdout="error: build failed\n")
    config = process_command_line(
        ["run-user-workflows", "-i", str(presets_file), "-j", "2", "-m", "gcc-14$"]
    )
    with pytest.raises(subprocess.CalledProcessError):
        run(config)
    captured = capsys.readouterr()
    assert "error: build failed" in captured.out


# --- main integration ---


@patch("tools.run_user_workflows.monitor_subprocess")
def test_main_returns_zero_on_success(mock_monitor, presets_file):
    mock_monitor.return_value = (0, [(10.0, 1000)], 1.0)
    result = main(["run-user-workflows", "-i", str(presets_file)])
    assert result == 0


SINGLE_CONFIG_CACHE = (
    "CMAKE_CONFIGURATION_TYPES:STRING=Debug\nCMAKE_GENERATOR:INTERNAL=Ninja\n"
)
MULTI_CONFIG_CACHE = "CMAKE_GENERATOR:INTERNAL=Ninja Multi-Config\n"


def _write_cache(source_dir: Path, text: str) -> None:
    build_dir = source_dir / "build-gcc-14"
    build_dir.mkdir()
    (build_dir / "CMakeCache.txt").write_text(text)


@patch("tools.run_user_workflows.monitor_subprocess")
def test_main_fails_after_a_single_config_sequential_workflow(
    mock_monitor, presets_file, capsys
):
    mock_monitor.return_value = (0, [(10.0, 1000)], 1.0)
    _write_cache(presets_file.parent, SINGLE_CONFIG_CACHE)
    result = main(["run-user-workflows", "-i", str(presets_file), "-m", "gcc"])
    assert result == 1
    assert mock_monitor.call_count == 1
    assert "multi-configuration" in capsys.readouterr().err


@patch("tools.run_user_workflows.monitor_subprocess")
def test_main_accepts_a_multi_config_sequential_workflow(mock_monitor, presets_file):
    mock_monitor.return_value = (0, [(10.0, 1000)], 1.0)
    _write_cache(presets_file.parent, MULTI_CONFIG_CACHE)
    result = main(["run-user-workflows", "-i", str(presets_file), "-m", "gcc"])
    assert result == 0
    assert mock_monitor.call_count == 2


@patch("tools.run_user_workflows.subprocess.run")
def test_main_fails_after_a_single_config_parallel_workflow(
    mock_run, presets_file, capsys
):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok\n")
    _write_cache(presets_file.parent, SINGLE_CONFIG_CACHE)
    result = main(
        ["run-user-workflows", "-i", str(presets_file), "-j", "2", "-m", "gcc"]
    )
    assert result == 1
    assert "multi-configuration" in capsys.readouterr().err


@patch("tools.run_user_workflows.subprocess.run")
def test_parallel_cmake_failure_wins_over_a_single_config_problem(
    mock_run, presets_file
):
    def fake_run(cmd, **kwargs):
        return MagicMock(returncode=2 if cmd[3] == "clang-18" else 0, stdout="")

    mock_run.side_effect = fake_run
    _write_cache(presets_file.parent, SINGLE_CONFIG_CACHE)
    result = main(["run-user-workflows", "-i", str(presets_file), "-j", "2"])
    assert result == 2


@patch("tools.run_user_workflows.subprocess.run")
def test_parallel_group_stops_after_a_single_config_workflow(mock_run, presets_file):
    mock_run.return_value = MagicMock(returncode=0, stdout="ok\n")
    _write_cache(presets_file.parent, SINGLE_CONFIG_CACHE)
    main(["run-user-workflows", "-i", str(presets_file), "-j", "2", "-m", "gcc"])
    ran = [c.args[0][3] for c in mock_run.call_args_list]
    assert ran == ["gcc-14"]
