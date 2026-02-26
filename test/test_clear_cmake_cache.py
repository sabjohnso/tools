"""Tests for the clear_cmake_cache module."""

import json
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tools.clear_cmake_cache import (
    get_build_directories,
    main,
    resolve_binary_dir,
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


def _config(input_path, matching=None, exclude=None):
    return SimpleNamespace(input_path=input_path, matching=matching, exclude=exclude)


# --- resolve_binary_dir ---


def test_resolve_binary_dir_replaces_source_dir():
    result = resolve_binary_dir("${sourceDir}/build-gcc-14", Path("/project"))
    assert result == Path("/project/build-gcc-14")


def test_resolve_binary_dir_without_variable():
    result = resolve_binary_dir("/absolute/build", Path("/project"))
    assert result == Path("/absolute/build")


# --- get_build_directories ---


def test_get_build_directories_returns_all_when_no_filter():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        config = _config(path)
        dirs = get_build_directories(config)
        expected = {
            Path(tmpdir) / "build-gcc-14",
            Path(tmpdir) / "build-clang-18",
        }
        assert set(dirs) == expected


def test_get_build_directories_filters_with_matching():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        config = _config(path, matching="gcc")
        dirs = get_build_directories(config)
        assert set(dirs) == {Path(tmpdir) / "build-gcc-14"}


def test_get_build_directories_filters_with_exclude():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        config = _config(path, exclude="clang")
        dirs = get_build_directories(config)
        assert set(dirs) == {Path(tmpdir) / "build-gcc-14"}


def test_get_build_directories_deduplicates():
    """Multiple workflows sharing a configure preset yield one build dir."""
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        config = _config(path, matching="gcc-14")
        dirs = get_build_directories(config)
        assert dirs == [Path(tmpdir) / "build-gcc-14"]


# --- clear_caches (integration via main) ---


def test_main_deletes_existing_cmake_cache():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        build_dir = Path(tmpdir) / "build-gcc-14"
        build_dir.mkdir()
        cache_file = build_dir / "CMakeCache.txt"
        cache_file.write_text("# dummy cache\n")

        result = main(["clear-cmake-cache", "-i", str(path), "-m", "gcc-14"])

        assert result == 0
        assert not cache_file.exists()


def test_main_succeeds_when_cache_does_not_exist():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        result = main(["clear-cmake-cache", "-i", str(path)])
        assert result == 0


def test_main_succeeds_when_build_dir_does_not_exist():
    with tempfile.TemporaryDirectory() as tmpdir:
        path = _write_presets(tmpdir)
        result = main(["clear-cmake-cache", "-i", str(path), "-m", "gcc"])
        assert result == 0


def test_main_returns_zero_on_success():
    with patch("tools.clear_cmake_cache.run"):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write_presets(tmpdir)
            result = main(["clear-cmake-cache", "-i", str(path)])
    assert result == 0
