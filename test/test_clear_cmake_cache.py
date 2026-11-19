"""Tests for the clear_cmake_cache module."""

import inspect
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.clear_cmake_cache import (
    get_build_directories,
    main,
)


def _config(input_path, matching=None, exclude=None):
    return SimpleNamespace(input_path=input_path, matching=matching, exclude=exclude)


# --- get_build_directories ---


def test_get_build_directories_returns_all_when_no_filter(tmp_path, presets_file):
    dirs = get_build_directories(_config(presets_file))
    assert set(dirs) == {tmp_path / "build-gcc-14", tmp_path / "build-clang-18"}


def test_get_build_directories_filters_with_matching(tmp_path, presets_file):
    dirs = get_build_directories(_config(presets_file, matching="gcc"))
    assert set(dirs) == {tmp_path / "build-gcc-14"}


def test_get_build_directories_filters_with_exclude(tmp_path, presets_file):
    dirs = get_build_directories(_config(presets_file, exclude="clang"))
    assert set(dirs) == {tmp_path / "build-gcc-14"}


def test_get_build_directories_matches_in_the_middle_of_a_name(tmp_path, presets_file):
    dirs = get_build_directories(_config(presets_file, matching="18"))
    assert dirs == [tmp_path / "build-clang-18"]


def test_get_build_directories_deduplicates(tmp_path, presets_file):
    # Two workflows use the same configure preset. Expect one build directory.
    dirs = get_build_directories(_config(presets_file, matching="gcc-14"))
    assert dirs == [tmp_path / "build-gcc-14"]


# --- clear_cache and remove_cmake_files (integration via main) ---


def test_main_deletes_existing_cmake_cache(tmp_path, presets_file):
    build_dir = tmp_path / "build-gcc-14"
    build_dir.mkdir()
    cache_file = build_dir / "CMakeCache.txt"
    cache_file.write_text("# dummy cache\n")

    result = main(["clear-cmake-cache", "-i", str(presets_file), "-m", "gcc-14"])

    assert result == 0
    assert not cache_file.exists()


def test_main_keeps_cmake_cache_of_excluded_workflow(tmp_path, presets_file):
    cache_files = {}
    for name in ["gcc-14", "clang-18"]:
        build_dir = tmp_path / f"build-{name}"
        build_dir.mkdir()
        cache_files[name] = build_dir / "CMakeCache.txt"
        cache_files[name].write_text("# dummy cache\n")

    result = main(["clear-cmake-cache", "-i", str(presets_file), "-e", "clang"])

    assert result == 0
    assert not cache_files["gcc-14"].exists()
    assert cache_files["clang-18"].exists()


def test_main_keeps_files_other_than_cmake_cache(tmp_path, presets_file):
    build_dir = tmp_path / "build-gcc-14"
    build_dir.mkdir()
    other_file = build_dir / "build.ninja"
    other_file.write_text("# dummy build file\n")
    (build_dir / "CMakeCache.txt").write_text("# dummy cache\n")

    main(["clear-cmake-cache", "-i", str(presets_file), "-m", "gcc-14"])

    assert other_file.exists()


def test_main_succeeds_when_cache_does_not_exist(tmp_path, presets_file):
    for name in ["gcc-14", "clang-18"]:
        (tmp_path / f"build-{name}").mkdir()
    result = main(["clear-cmake-cache", "-i", str(presets_file)])
    assert result == 0


def test_main_succeeds_when_build_dir_does_not_exist(presets_file):
    result = main(["clear-cmake-cache", "-i", str(presets_file), "-m", "gcc"])
    assert result == 0


# --- --remove-cmake-files ---


def _make_build_directory(tmp_path, name):
    build_dir = tmp_path / f"build-{name}"
    (build_dir / "CMakeFiles" / "3.30.0").mkdir(parents=True)
    (build_dir / "CMakeFiles" / "3.30.0" / "CMakeCCompiler.cmake").write_text("#\n")
    (build_dir / "CMakeCache.txt").write_text("# dummy cache\n")
    return build_dir


def test_main_keeps_cmake_files_by_default(tmp_path, presets_file):
    build_dir = _make_build_directory(tmp_path, "gcc-14")
    main(["clear-cmake-cache", "-i", str(presets_file), "-m", "gcc-14"])
    assert (build_dir / "CMakeFiles").is_dir()


def test_main_removes_cmake_files_on_request(tmp_path, presets_file):
    build_dir = _make_build_directory(tmp_path, "gcc-14")
    result = main(
        [
            "clear-cmake-cache",
            "-i",
            str(presets_file),
            "-m",
            "gcc-14",
            "--remove-cmake-files",
        ]
    )
    assert result == 0
    assert not (build_dir / "CMakeFiles").exists()
    assert not (build_dir / "CMakeCache.txt").exists()


def test_main_removes_only_cmake_files_of_selected_workflows(tmp_path, presets_file):
    gcc_dir = _make_build_directory(tmp_path, "gcc-14")
    clang_dir = _make_build_directory(tmp_path, "clang-18")
    main(
        [
            "clear-cmake-cache",
            "-i",
            str(presets_file),
            "-e",
            "clang",
            "--remove-cmake-files",
        ]
    )
    assert not (gcc_dir / "CMakeFiles").exists()
    assert (clang_dir / "CMakeFiles").is_dir()


def test_main_prints_one_line_for_each_removed_item(tmp_path, presets_file, capsys):
    build_dir = _make_build_directory(tmp_path, "gcc-14")
    main(
        [
            "clear-cmake-cache",
            "-i",
            str(presets_file),
            "-m",
            "gcc-14",
            "--remove-cmake-files",
        ]
    )
    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        f"Cleared {build_dir / 'CMakeCache.txt'}",
        f"Removed {build_dir / 'CMakeFiles'}",
    ]


def test_main_accepts_a_missing_cmake_files_directory(tmp_path, presets_file, capsys):
    build_dir = tmp_path / "build-gcc-14"
    build_dir.mkdir()
    (build_dir / "CMakeCache.txt").write_text("# dummy cache\n")
    result = main(
        [
            "clear-cmake-cache",
            "-i",
            str(presets_file),
            "-m",
            "gcc-14",
            "--remove-cmake-files",
        ]
    )
    assert result == 0
    assert capsys.readouterr().out.splitlines() == [
        f"Cleared {build_dir / 'CMakeCache.txt'}"
    ]


def test_main_removes_a_cmake_files_symlink_but_keeps_its_target(
    tmp_path, presets_file, capsys
):
    build_dir = tmp_path / "build-gcc-14"
    build_dir.mkdir()
    target = tmp_path / "elsewhere"
    target.mkdir()
    (target / "keep.txt").write_text("keep\n")
    (build_dir / "CMakeFiles").symlink_to(target, target_is_directory=True)
    result = main(
        [
            "clear-cmake-cache",
            "-i",
            str(presets_file),
            "-m",
            "gcc-14",
            "--remove-cmake-files",
        ]
    )
    assert result == 0
    assert not (build_dir / "CMakeFiles").is_symlink()
    assert (target / "keep.txt").exists()
    assert capsys.readouterr().out.splitlines()[-1] == (
        f"Removed {build_dir / 'CMakeFiles'}"
    )


# --- program name and script ---


def test_usage_names_the_program_without_its_directory(capsys):
    with pytest.raises(SystemExit):
        main(["/usr/local/bin/clear-cmake-cache", "--help"])
    assert capsys.readouterr().out.startswith("usage: clear-cmake-cache ")


def test_module_file_runs_as_a_script():
    script = Path(inspect.getfile(main))
    result = subprocess.run(
        [script, "--help"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    assert result.stdout.startswith("usage: clear_cmake_cache.py ")
