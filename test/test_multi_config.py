"""Tests for the multi_config module."""

from hypothesis import given
from hypothesis import strategies as st

from tools.multi_config import (
    cache_is_multi_config,
    find_generator,
    is_multi_config_generator,
)

preset_names = st.text(alphabet="abcdefgh", min_size=1, max_size=6)
generators = st.sampled_from(
    ["Ninja", "Unix Makefiles", "Ninja Multi-Config", "Xcode", "Visual Studio 17 2022"]
)


def _presets(*configure_presets):
    return {"version": 6, "configurePresets": list(configure_presets)}


# --- find_generator ---


def test_find_generator_returns_generator_of_the_preset():
    presets = _presets({"name": "default", "generator": "Ninja Multi-Config"})
    assert find_generator(presets, "default") == "Ninja Multi-Config"


def test_find_generator_follows_a_string_inherits():
    presets = _presets(
        {"name": "base", "generator": "Ninja Multi-Config"},
        {"name": "default", "inherits": "base"},
    )
    assert find_generator(presets, "default") == "Ninja Multi-Config"


def test_find_generator_uses_the_first_parent_in_an_inherits_list():
    presets = _presets(
        {"name": "one", "generator": "Ninja"},
        {"name": "two", "generator": "Ninja Multi-Config"},
        {"name": "default", "inherits": ["one", "two"]},
    )
    assert find_generator(presets, "default") == "Ninja"


def test_find_generator_skips_a_parent_with_no_generator():
    presets = _presets(
        {"name": "one"},
        {"name": "two", "generator": "Ninja Multi-Config"},
        {"name": "default", "inherits": ["one", "two"]},
    )
    assert find_generator(presets, "default") == "Ninja Multi-Config"


def test_find_generator_searches_a_grandparent_before_the_second_parent():
    presets = _presets(
        {"name": "grandparent", "generator": "Ninja Multi-Config"},
        {"name": "one", "inherits": "grandparent"},
        {"name": "two", "generator": "Ninja"},
        {"name": "default", "inherits": ["one", "two"]},
    )
    assert find_generator(presets, "default") == "Ninja Multi-Config"


def test_find_generator_returns_none_when_no_preset_sets_a_generator():
    presets = _presets({"name": "default"})
    assert find_generator(presets, "default") is None


def test_find_generator_returns_none_for_an_unknown_preset():
    presets = _presets({"name": "default", "generator": "Ninja"})
    assert find_generator(presets, "other") is None


@given(st.lists(preset_names, min_size=1, max_size=8, unique=True), generators)
def test_find_generator_gets_the_generator_of_the_root_of_a_chain(names, generator):
    root = {"name": names[0], "generator": generator}
    children = [
        {"name": child, "inherits": parent} for parent, child in zip(names, names[1:])
    ]
    presets = _presets(root, *children)
    assert find_generator(presets, names[-1]) == generator


@given(preset_names, generators, generators)
def test_find_generator_prefers_the_own_generator_to_the_parent(name, own, inherited):
    presets = _presets(
        {"name": name + "-parent", "generator": inherited},
        {"name": name, "inherits": name + "-parent", "generator": own},
    )
    assert find_generator(presets, name) == own


# --- is_multi_config_generator ---


def test_multi_config_generators_are_accepted():
    assert is_multi_config_generator("Ninja Multi-Config")
    assert is_multi_config_generator("Xcode")
    assert is_multi_config_generator("Visual Studio 17 2022")


def test_single_config_generators_are_rejected():
    assert not is_multi_config_generator("Ninja")
    assert not is_multi_config_generator("Unix Makefiles")
    assert not is_multi_config_generator(None)


# --- cache_is_multi_config ---


def test_cache_of_a_multi_config_generator_is_multi_config():
    cache = "CMAKE_BUILD_TYPE:STRING=\nCMAKE_GENERATOR:INTERNAL=Ninja Multi-Config\n"
    assert cache_is_multi_config(cache)


def test_cache_of_a_single_config_generator_is_not_multi_config():
    cache = "CMAKE_GENERATOR:INTERNAL=Ninja\n"
    assert not cache_is_multi_config(cache)


def test_configuration_types_entry_does_not_make_a_cache_multi_config():
    cache = (
        "CMAKE_CONFIGURATION_TYPES:UNINITIALIZED=Debug;Release\n"
        "CMAKE_GENERATOR:INTERNAL=Ninja\n"
    )
    assert not cache_is_multi_config(cache)


def test_cache_with_no_generator_is_not_multi_config():
    assert not cache_is_multi_config("CMAKE_BUILD_TYPE:STRING=\n")


@given(generators)
def test_cache_agrees_with_the_generator_rule(generator):
    cache = f"CMAKE_GENERATOR:INTERNAL={generator}\n"
    assert cache_is_multi_config(cache) == is_multi_config_generator(generator)
