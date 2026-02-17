"""Tests for the C++ file formatter."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import subprocess
import tempfile

from tools.format_cxx_files import main, make_command_line_parser, get_source_files


def test_parser_prog_is_full_program_name():
    parser = make_command_line_parser("format-cxx-files")
    assert parser.prog == "format-cxx-files"


def test_clang_format_defaults_to_clang_format():
    parser = make_command_line_parser("format-cxx-files")
    config = parser.parse_args([])
    assert config.clang_format == Path("clang-format")


def test_main_returns_returncode_on_subprocess_failure():
    error = subprocess.CalledProcessError(returncode=2, cmd=["clang-format"])
    with patch("tools.format_cxx_files.run", side_effect=error):
        result = main(["format-cxx-files"])
    assert result == 2


def test_get_source_files_does_not_change_cwd():
    with tempfile.TemporaryDirectory() as tmpdir:
        (Path(tmpdir) / "hello.cpp").touch()
        config = SimpleNamespace(source_tree=Path(tmpdir))
        original_cwd = Path.cwd()
        get_source_files(config)
        assert Path.cwd() == original_cwd
