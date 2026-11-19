"""Tests for the user_presets module."""

from argparse import ArgumentParser
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st
from preset_strategies import PATTERNS, user_presets

from tools.errors import UserError
from tools.user_presets import (
    add_workflow_selection_options,
    build_directory,
    filter_workflow_names,
    find_workflow,
    get_configure_step_name,
    read_user_presets,
    resolve_binary_dir,
    select_workflow_names,
)

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


def test_read_user_presets_returns_the_content_of_the_file(presets_file, preset_data):
    assert read_user_presets(presets_file) == preset_data


def test_find_workflow_returns_the_workflow_with_the_name():
    workflow = find_workflow(_user_presets(), "gcc-14-devel")
    assert workflow["name"] == "gcc-14-devel"


def test_find_workflow_rejects_an_unknown_name():
    with pytest.raises(UserError, match="clang-18"):
        find_workflow(_user_presets(), "clang-18")


def test_get_configure_step_name_finds_a_configure_step_after_other_steps():
    workflow = find_workflow(_user_presets(), "gcc-14-devel")
    assert get_configure_step_name(workflow) == "gcc-14"


def test_get_configure_step_name_rejects_a_workflow_without_a_configure_step():
    workflow = {"name": "gcc-14", "steps": [{"type": "build", "name": "gcc-14"}]}
    with pytest.raises(UserError, match="No configure step in workflow: gcc-14"):
        get_configure_step_name(workflow)


# --- workflow selection ---


def test_filter_workflow_names_matches_in_the_middle_of_a_name():
    names = ["gcc-14", "clang-18", "gcc-14-devel"]
    result = filter_workflow_names(names, matching="14")
    assert result == ["gcc-14", "gcc-14-devel"]


def test_filter_workflow_names_excludes_in_the_middle_of_a_name():
    names = ["gcc-14", "clang-18", "gcc-14-devel"]
    result = filter_workflow_names(names, exclude="14")
    assert result == ["clang-18"]


def test_filter_workflow_names_keeps_all_names_without_patterns():
    names = ["gcc-14", "clang-18"]
    assert filter_workflow_names(names) == names


def test_filter_workflow_names_returns_a_list_for_a_tuple_of_names():
    names = ("gcc-14", "clang-18")
    assert filter_workflow_names(names) == ["gcc-14", "clang-18"]


def test_filter_workflow_names_result_does_not_share_the_input_list():
    names = ["gcc-14", "clang-18"]
    result = filter_workflow_names(names)
    result.append("msvc")
    assert names == ["gcc-14", "clang-18"]


def test_select_workflow_names_filters_the_workflows_in_file_order(preset_data):
    result = select_workflow_names(preset_data, matching="gcc", exclude="devel")
    assert result == ["gcc-14"]


@given(user_presets(), PATTERNS, PATTERNS)
def test_select_workflow_names_filters_the_names_of_all_workflows(
    presets, matching, exclude
):
    names = [workflow["name"] for workflow in presets["workflowPresets"]]
    expected = filter_workflow_names(names, matching, exclude)
    assert select_workflow_names(presets, matching, exclude) == expected


def test_selection_options_have_the_documented_defaults():
    parser = ArgumentParser()
    add_workflow_selection_options(parser)
    config = parser.parse_args([])
    assert config.input_path == Path("CMakeUserPresets.json")
    assert config.matching is None
    assert config.exclude is None


def test_selection_options_have_short_forms():
    parser = ArgumentParser()
    add_workflow_selection_options(parser)
    config = parser.parse_args(["-i", "p.json", "-m", "gcc", "-e", "devel"])
    assert config.input_path == Path("p.json")
    assert config.matching == "gcc"
    assert config.exclude == "devel"


def test_selection_options_have_long_forms():
    parser = ArgumentParser()
    add_workflow_selection_options(parser)
    config = parser.parse_args(
        ["--input-path", "p.json", "--matching", "gcc", "--exclude", "devel"]
    )
    assert config.input_path == Path("p.json")
    assert config.matching == "gcc"
    assert config.exclude == "devel"
