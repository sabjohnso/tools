"""Tests for the user_presets module."""

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tools.errors import UserError
from tools.user_presets import build_directory, resolve_binary_dir

path_parts = st.text(alphabet="abcdefgh-_", min_size=1, max_size=8)


def _user_presets():
    return {
        "configurePresets": [
            {"name": "gcc-14", "binaryDir": "${sourceDir}/build-gcc-14"},
        ],
        "workflowPresets": [
            {
                "name": "gcc-14-devel",
                "steps": [
                    {"type": "build", "name": "gcc-14-devel"},
                    {"type": "configure", "name": "gcc-14"},
                ],
            },
        ],
    }


def test_build_directory_uses_the_configure_step_of_the_workflow():
    result = build_directory(_user_presets(), "gcc-14-devel", Path("/project"))
    assert result == Path("/project/build-gcc-14")


def test_build_directory_rejects_an_unknown_workflow():
    with pytest.raises(UserError, match="clang-18"):
        build_directory(_user_presets(), "clang-18", Path("/project"))


@given(path_parts, path_parts)
def test_resolve_binary_dir_puts_the_source_dir_in_place_of_the_macro(source, build):
    source_dir = Path("/") / source
    result = resolve_binary_dir("${sourceDir}/" + build, source_dir)
    assert result == source_dir / build


@given(path_parts, path_parts)
def test_resolve_binary_dir_keeps_a_path_with_no_macro(source, build):
    binary_dir = "/" + build
    assert resolve_binary_dir(binary_dir, Path("/") / source) == Path(binary_dir)
