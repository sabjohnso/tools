"""Property tests for workflow selection."""

import importlib
import re
from types import SimpleNamespace

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

from tools.user_presets import filter_workflow_names

# The tools package has functions with the same names as these modules, so
# "tools.<module>" gives the function. Thus import the module by name.
CLEAR_CMAKE_CACHE = importlib.import_module("tools.clear_cmake_cache")


def _config(input_path=None, matching=None, exclude=None):
    return SimpleNamespace(input_path=input_path, matching=matching, exclude=exclude)


# --- filter_workflow_names ---


@given(names=st.lists(NAMES), matching=PATTERNS, exclude=PATTERNS)
def test_filter_workflow_names_keeps_exactly_the_selected_names(
    names, matching, exclude
):
    result = filter_workflow_names(names, matching, exclude)
    assert result == expected_names(names, matching, exclude)


@given(names=st.lists(NAMES), matching=PATTERNS, exclude=PATTERNS)
def test_filter_workflow_names_returns_subsequence_of_input(names, matching, exclude):
    result = filter_workflow_names(names, matching, exclude)
    assert is_subsequence(result, names)


@given(names=st.lists(NAMES), matching=PATTERNS, exclude=PATTERNS)
def test_filter_workflow_names_returns_no_excluded_name(names, matching, exclude):
    result = filter_workflow_names(names, matching, exclude)
    if exclude:
        assert not any(re.search(exclude, name) for name in result)


@given(names=st.lists(NAMES), matching=PATTERNS, exclude=PATTERNS)
def test_filter_workflow_names_is_idempotent(names, matching, exclude):
    once = filter_workflow_names(names, matching, exclude)
    assert filter_workflow_names(once, matching, exclude) == once


# --- get_build_directories ---


@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(user_presets=user_presets(), matching=PATTERNS, exclude=PATTERNS)
def test_get_build_directories_gives_each_selected_directory_once_in_first_order(
    tmp_path, user_presets, matching, exclude
):
    path = write_json(tmp_path / "CMakeUserPresets.json", user_presets)
    dirs = CLEAR_CMAKE_CACHE.get_build_directories(_config(path, matching, exclude))
    sequence = expected_directory_sequence(
        user_presets, matching, exclude, tmp_path.resolve()
    )
    assert len(dirs) == len(set(dirs))
    assert dirs == list(dict.fromkeys(sequence))
    assert set(dirs) == set(sequence)
