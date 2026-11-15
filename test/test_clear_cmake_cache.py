"""Tests for the clear_cmake_cache module."""

from types import SimpleNamespace

from tools.clear_cmake_cache import (
    filter_workflow_names,
    get_build_directories,
    main,
)


def _config(input_path, matching=None, exclude=None):
    return SimpleNamespace(input_path=input_path, matching=matching, exclude=exclude)


# --- filter_workflow_names ---


def test_filter_workflow_names_matches_in_the_middle_of_a_name():
    names = ["gcc-14", "clang-18", "gcc-14-devel"]
    result = filter_workflow_names(_config(None, matching="14"), names)
    assert result == ["gcc-14", "gcc-14-devel"]


def test_filter_workflow_names_excludes_in_the_middle_of_a_name():
    names = ["gcc-14", "clang-18", "gcc-14-devel"]
    result = filter_workflow_names(_config(None, exclude="14"), names)
    assert result == ["clang-18"]


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


# --- clear_caches (integration via main) ---


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
