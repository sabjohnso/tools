"""Tests for the C++ file formatter."""

import math
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tools.format_cxx_files import (
    CXX_EXTENSIONS,
    format_files,
    get_source_files,
    main,
    make_command_line_parser,
)

CLANG_FORMAT = shutil.which("clang-format")

needs_clang_format = pytest.mark.skipif(
    CLANG_FORMAT is None, reason="clang-format is not installed"
)

BAD_SOURCE = "int  main( ){return 0;}\n"
OTHER_EXTENSIONS = [".h", ".c", ".txt", ".py", ".cmake"]


def test_parser_prog_is_the_given_program_name():
    parser = make_command_line_parser("format-cxx-files")
    assert parser.prog == "format-cxx-files"


def test_usage_shows_the_program_name_without_its_directory(capsys):
    with pytest.raises(SystemExit):
        main(["/usr/local/bin/format-cxx-files", "--help"])
    usage = capsys.readouterr().out.splitlines()[0]
    assert usage.startswith("usage: format-cxx-files ")


def test_clang_format_defaults_to_clang_format():
    parser = make_command_line_parser("format-cxx-files")
    config = parser.parse_args([])
    assert config.clang_format == Path("clang-format")


@given(returncode=st.integers(min_value=1, max_value=125))
def test_main_returns_returncode_of_failed_formatter(tmp_path_factory, returncode):
    tree = tmp_path_factory.mktemp("tree")
    _write(tree / "hello.cpp", BAD_SOURCE)
    formatter = _failing_formatter(tmp_path_factory.mktemp("bin"), returncode)
    assert main(_command_line(tree, clang_format=formatter)) == returncode


def test_get_source_files_does_not_change_cwd(tmp_path):
    (tmp_path / "hello.cpp").touch()
    original_cwd = Path.cwd()
    get_source_files(tmp_path)
    assert Path.cwd() == original_cwd


# A stem can contain dots, and a part of a stem can be an extension name.
# This gives names such as "a.cpp.txt" and "a.b.cpp".
STEM_PARTS = st.text(alphabet="abcxyz_", min_size=1, max_size=5) | st.sampled_from(
    [extension.lstrip(".") for extension in CXX_EXTENSIONS + OTHER_EXTENSIONS]
)
STEMS = st.lists(STEM_PARTS, min_size=1, max_size=3).map(".".join)


# Directories for files, and directories that can hold a CMakeCache.txt.
DIRECTORIES = [
    "",
    "src",
    "src/detail",
    "include",
    "build",
    "build/_deps/x",
    "src/build",
]


@given(
    names=st.sets(
        st.tuples(
            st.sampled_from(DIRECTORIES),
            STEMS,
            st.sampled_from(CXX_EXTENSIONS + OTHER_EXTENSIONS),
        ),
        max_size=12,
    ),
    build_directories=st.sets(st.sampled_from(DIRECTORIES), max_size=3),
)
def test_get_source_files_finds_cxx_files_outside_build_directories(
    tmp_path_factory, names, build_directories
):
    tree = tmp_path_factory.mktemp("tree")
    files = {
        _touch(tree / directory / f"{stem}{suffix}")
        for directory, stem, suffix in names
    }
    for directory in build_directories:
        _touch(tree / directory / "CMakeCache.txt")
    expected = sorted(
        path
        for path in files
        if path.suffix in CXX_EXTENSIONS
        and not _below_build_directory(path, tree, build_directories)
    )
    assert sorted(get_source_files(tree)) == expected


# A file is below a build directory if one of its directories, other than the
# root of the tree, holds a CMakeCache.txt.
def _below_build_directory(path, tree, build_directories):
    directories = path.relative_to(tree).parents
    return any(
        directory != Path(".") and str(directory) in build_directories
        for directory in directories
    )


@needs_clang_format
def test_format_files_formats_only_the_given_files(tmp_path):
    given_file = tmp_path / "given.cpp"
    other_file = tmp_path / "other.cpp"
    _write(given_file, BAD_SOURCE)
    _write(other_file, BAD_SOURCE)
    format_files(Path(CLANG_FORMAT), [given_file])
    assert given_file.read_text() != BAD_SOURCE
    assert other_file.read_text() == BAD_SOURCE


@needs_clang_format
def test_main_formats_cxx_files_in_source_tree(tmp_path):
    sources = [tmp_path / "main.cpp", tmp_path / "src" / "lib.hpp"]
    for source in sources:
        _write(source, BAD_SOURCE)
    assert main(_command_line(tmp_path)) == 0
    assert all(source.read_text() != BAD_SOURCE for source in sources)


@needs_clang_format
def test_main_does_not_change_files_with_other_extensions(tmp_path):
    _write(tmp_path / "main.cpp", BAD_SOURCE)
    others = [tmp_path / f"other{suffix}" for suffix in OTHER_EXTENSIONS]
    for other in others:
        _write(other, BAD_SOURCE)
    assert main(_command_line(tmp_path)) == 0
    assert all(other.read_text() == BAD_SOURCE for other in others)


@needs_clang_format
def test_main_keeps_formatted_files_unchanged(tmp_path):
    source = tmp_path / "main.cpp"
    _write(source, BAD_SOURCE)
    main(_command_line(tmp_path))
    formatted = source.read_text()
    assert main(_command_line(tmp_path)) == 0
    assert source.read_text() == formatted


def test_main_returns_zero_for_empty_source_tree(tmp_path):
    assert main(_command_line(tmp_path)) == 0


@needs_clang_format
def test_main_does_not_format_files_in_build_directories(tmp_path):
    _write(tmp_path / "main.cpp", BAD_SOURCE)
    # A CMakeCache.txt file marks a CMake build directory.
    _touch(tmp_path / "build-gcc" / "CMakeCache.txt")
    dependency = tmp_path / "build-gcc" / "_deps" / "fmt-src" / "format.cc"
    _write(dependency, BAD_SOURCE)
    main(_command_line(tmp_path))
    assert dependency.read_text() == BAD_SOURCE


def test_main_reports_a_missing_formatter(tmp_path, capsys):
    _write(tmp_path / "main.cpp", BAD_SOURCE)
    missing = tmp_path / "no-such-clang-format"
    assert main(_command_line(tmp_path, missing)) != 0
    assert str(missing) in capsys.readouterr().err


@given(
    st.integers(min_value=1, max_value=5).flatmap(
        lambda size: st.tuples(st.just(size), st.integers(0, 4 * size))
    )
)
def test_format_files_runs_the_formatter_on_consecutive_batches(size_and_count):
    batch_size, count = size_and_count
    files = [Path(f"f{index}.cpp") for index in range(count)]
    with patch("tools.format_cxx_files.subprocess.run") as run:
        format_files(Path("clang-format"), files, batch_size)
    commands = [call.args[0] for call in run.call_args_list]
    assert all(command[:2] == [Path("clang-format"), "-i"] for command in commands)
    assert all(0 < len(command[2:]) <= batch_size for command in commands)
    assert [file for command in commands for file in command[2:]] == files
    assert len(commands) == math.ceil(count / batch_size)


def _command_line(source_tree, clang_format=CLANG_FORMAT):
    return [
        "format-cxx-files",
        "--source-tree",
        str(source_tree),
        "--clang-format",
        str(clang_format),
    ]


def _failing_formatter(directory, returncode):
    script = _write(directory / "clang-format", f"#!/bin/sh\nexit {returncode}\n")
    script.chmod(0o755)
    return script


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _touch(path):
    return _write(path, "")
