"""Property tests for workflow selection in each tool that selects workflows."""

import importlib
import re
from types import SimpleNamespace

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from preset_strategies import (
    NAMES,
    PATTERNS,
    expected_directory_sequence,
    expected_names,
    is_subsequence,
    user_presets,
    write_json,
)

# The tools package has functions with the same names as these modules, so
# "tools.<module>" gives the function. Thus import the modules by name.
RUN_USER_WORKFLOWS = importlib.import_module("tools.run_user_workflows")
CLEAR_CMAKE_CACHE = importlib.import_module("tools.clear_cmake_cache")
SET_CMAKE_VARIABLE = importlib.import_module("tools.set_cmake_variable")

# Each of these modules has its own copy of filter_workflow_names.
FILTER_MODULES = [RUN_USER_WORKFLOWS, CLEAR_CMAKE_CACHE, SET_CMAKE_VARIABLE]

# Each of these modules has its own copy of get_build_directories.
BUILD_DIRECTORY_MODULES = [CLEAR_CMAKE_CACHE, SET_CMAKE_VARIABLE]

with_each_filter = pytest.mark.parametrize(
    "filter_workflow_names",
    [module.filter_workflow_names for module in FILTER_MODULES],
    ids=[module.__name__ for module in FILTER_MODULES],
)

with_each_build_directory_function = pytest.mark.parametrize(
    "get_build_directories",
    [module.get_build_directories for module in BUILD_DIRECTORY_MODULES],
    ids=[module.__name__ for module in BUILD_DIRECTORY_MODULES],
)


def _config(input_path=None, matching=None, exclude=None):
    return SimpleNamespace(input_path=input_path, matching=matching, exclude=exclude)


# --- filter_workflow_names ---


@with_each_filter
@given(names=st.lists(NAMES), matching=PATTERNS, exclude=PATTERNS)
def test_filter_workflow_names_keeps_exactly_the_selected_names(
    filter_workflow_names, names, matching, exclude
):
    result = filter_workflow_names(_config(None, matching, exclude), names)
    assert result == expected_names(names, matching, exclude)


@with_each_filter
@given(names=st.lists(NAMES), matching=PATTERNS, exclude=PATTERNS)
def test_filter_workflow_names_returns_subsequence_of_input(
    filter_workflow_names, names, matching, exclude
):
    result = filter_workflow_names(_config(None, matching, exclude), names)
    assert is_subsequence(result, names)


@with_each_filter
@given(names=st.lists(NAMES), matching=PATTERNS, exclude=PATTERNS)
def test_filter_workflow_names_returns_no_excluded_name(
    filter_workflow_names, names, matching, exclude
):
    result = filter_workflow_names(_config(None, matching, exclude), names)
    if exclude:
        assert not any(re.search(exclude, name) for name in result)


@with_each_filter
@given(names=st.lists(NAMES), matching=PATTERNS, exclude=PATTERNS)
def test_filter_workflow_names_is_idempotent(
    filter_workflow_names, names, matching, exclude
):
    config = _config(None, matching, exclude)
    once = filter_workflow_names(config, names)
    assert filter_workflow_names(config, once) == once


# --- get_build_directories ---


@with_each_build_directory_function
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(user_presets=user_presets(), matching=PATTERNS, exclude=PATTERNS)
def test_get_build_directories_gives_each_selected_directory_once_in_first_order(
    get_build_directories, tmp_path, user_presets, matching, exclude
):
    path = write_json(tmp_path / "CMakeUserPresets.json", user_presets)
    dirs = get_build_directories(_config(path, matching, exclude))
    sequence = expected_directory_sequence(
        user_presets, matching, exclude, tmp_path.resolve()
    )
    assert len(dirs) == len(set(dirs))
    assert dirs == list(dict.fromkeys(sequence))
    assert set(dirs) == set(sequence)
