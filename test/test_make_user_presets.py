"""Tests for the CMake user presets generator."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from jsonschema import ValidationError

from tools.make_user_presets import (
    main,
    make_build_presets,
    make_configure_preset,
    make_test_presets,
    validate_schema,
)


def _compiler_with_add_paths():
    return {
        "name": "gcc-14",
        "root": "/usr/local/gcc-14",
        "cc": "gcc",
        "cxx": "g++",
        "addPaths": True,
    }


def _config(**overrides):
    defaults = {"shared_build_directory": False, "test_jobs": 1, "inherits": "default"}
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_cpath_has_separator_before_penv():
    preset = make_configure_preset(_config(), _compiler_with_add_paths())
    cpath = preset["environment"]["CPATH"]
    assert cpath == "/usr/local/gcc-14/include:$penv{CPATH}"


def test_main_returns_zero_on_success():
    with (
        patch("tools.make_user_presets.validate_input"),
        patch("tools.make_user_presets.run"),
    ):
        result = main(["make-user-presets", "/dev/null"])
    assert result == 0


def _valid_compiler():
    return {"name": "gcc-14", "root": "/usr/local/gcc-14", "cc": "gcc", "cxx": "g++"}


def test_valid_input_passes_validation():
    validate_schema([_valid_compiler()])


def test_missing_required_key_raises():
    compiler = _valid_compiler()
    del compiler["cc"]
    with pytest.raises(ValidationError):
        validate_schema([compiler])


def test_wrong_type_raises():
    compiler = _valid_compiler()
    compiler["name"] = 42
    with pytest.raises(ValidationError):
        validate_schema([compiler])


def test_unknown_key_raises():
    compiler = _valid_compiler()
    compiler["nme"] = "typo"
    with pytest.raises(ValidationError):
        validate_schema([compiler])


def test_configure_preset_sets_custom_build_type_flags():
    preset = make_configure_preset(_config(), _valid_compiler())
    cache_vars = preset["cacheVariables"]
    assert cache_vars["CMAKE_C_FLAGS_RELWITHDEBINFO"] == "-O3 -g -DNDEBUG"
    assert cache_vars["CMAKE_CXX_FLAGS_RELWITHDEBINFO"] == "-O3 -g -DNDEBUG"
    assert cache_vars["CMAKE_C_FLAGS_RELWITHASSERTS"] == "-O3"
    assert cache_vars["CMAKE_CXX_FLAGS_RELWITHASSERTS"] == "-O3"


def test_devel_build_preset_uses_rel_with_asserts():
    compilers = [_valid_compiler()]
    presets = make_build_presets(_config(), compilers)
    devel = [p for p in presets if p["name"] == "gcc-14-devel"][0]
    assert devel["configuration"] == "RelWithAsserts"


def test_devel_test_preset_uses_rel_with_asserts():
    compilers = [_valid_compiler()]
    presets = make_test_presets(_config(), compilers)
    devel = [p for p in presets if p["name"] == "gcc-14-devel"][0]
    assert devel["configuration"] == "RelWithAsserts"


def test_configure_preset_inherits_default_by_default():
    preset = make_configure_preset(_config(), _valid_compiler())
    assert preset["inherits"] == "default"


def test_configure_preset_inherits_from_option():
    preset = make_configure_preset(_config(inherits="multi"), _valid_compiler())
    assert preset["inherits"] == "multi"


def test_base_build_preset_uses_inherits_as_configure_preset():
    compilers = [_valid_compiler()]
    presets = make_build_presets(_config(inherits="multi"), compilers)
    base = presets[0]
    assert base["configurePreset"] == "multi"


def test_base_test_preset_uses_inherits_as_configure_preset():
    compilers = [_valid_compiler()]
    presets = make_test_presets(_config(inherits="multi"), compilers)
    base = presets[0]
    assert base["configurePreset"] == "multi"
