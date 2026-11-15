"""Tests for the CMake user presets generator."""

import json
from types import SimpleNamespace

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from jsonschema import ValidationError

from tools.make_user_presets import (
    binary_directory,
    main,
    make_build_presets,
    make_command_line_parser,
    make_configure_preset,
    make_output_data,
    make_test_presets,
    make_workflow_presets,
    validate_input,
    validate_schema,
    write_output_data,
)


# A parent environment that sets each search path variable.
PARENT_ENVIRONMENT = {
    "PATH": "/usr/bin",
    "LIBRARY_PATH": "/opt/lib",
    "LD_LIBRARY_PATH": "/opt/lib",
    "CPATH": "/opt/include",
}


def _compiler_with_add_paths():
    return {
        "name": "gcc-14",
        "root": "/usr/local/gcc-14",
        "cc": "gcc",
        "cxx": "g++",
        "addPaths": True,
    }


def _config(**overrides):
    defaults = {"test_jobs": 1, "inherits": "default"}
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_cpath_has_separator_before_penv():
    preset = make_configure_preset(
        _config(), _compiler_with_add_paths(), PARENT_ENVIRONMENT
    )
    cpath = preset["environment"]["CPATH"]
    assert cpath == "/usr/local/gcc-14/include:$penv{CPATH}"


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
    preset = make_configure_preset(_config(), _valid_compiler(), PARENT_ENVIRONMENT)
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
    preset = make_configure_preset(_config(), _valid_compiler(), PARENT_ENVIRONMENT)
    assert preset["inherits"] == "default"


def test_configure_preset_inherits_from_option():
    preset = make_configure_preset(
        _config(inherits="multi"), _valid_compiler(), PARENT_ENVIRONMENT
    )
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


def _write_project(tmp_path, generator, compilers=None):
    preset = {"name": "default", "hidden": True}
    if generator is not None:
        preset["generator"] = generator
    project = {"version": 6, "configurePresets": [preset]}
    (tmp_path / "CMakePresets.json").write_text(json.dumps(project))
    input_file = tmp_path / "compilers.json"
    if compilers is None:
        compilers = [_valid_compiler()]
    input_file.write_text(json.dumps(compilers))
    return input_file


def _run_main(tmp_path, compilers):
    output = tmp_path / "CMakeUserPresets.json"
    return main(["make-user-presets", str(compilers), "-o", str(output)])


def test_main_accepts_a_multi_config_generator(tmp_path):
    compilers = _write_project(tmp_path, "Ninja Multi-Config")
    assert _run_main(tmp_path, compilers) == 0
    assert (tmp_path / "CMakeUserPresets.json").exists()


def test_main_rejects_a_single_config_generator(tmp_path, capsys):
    compilers = _write_project(tmp_path, "Ninja")
    assert _run_main(tmp_path, compilers) == 1
    assert "Ninja" in capsys.readouterr().err
    assert not (tmp_path / "CMakeUserPresets.json").exists()


def test_main_rejects_a_preset_with_no_generator(tmp_path):
    compilers = _write_project(tmp_path, None)
    assert _run_main(tmp_path, compilers) == 1


def test_main_rejects_a_missing_project_presets_file(tmp_path, capsys):
    compilers = _write_project(tmp_path, "Ninja Multi-Config")
    (tmp_path / "CMakePresets.json").unlink()
    assert _run_main(tmp_path, compilers) == 1
    assert "CMakePresets.json" in capsys.readouterr().err


# The names in this alphabet have no "-" and are not reserved names.
# Thus no generated name can collide with a different generated name.
_SAFE_NAMES = st.lists(
    st.text(alphabet="ab", min_size=1, max_size=4), min_size=1, max_size=5, unique=True
)

# These names collide with a different compiler name, with a generated
# name, with a base preset name or with the inherited preset name.
_COLLIDING_NAMES = st.lists(
    st.sampled_from(["a", "a-devel", "a-debug", "baseBuild", "baseTest", "default"]),
    min_size=1,
    max_size=5,
)

_PRESET_TYPES = ["configurePresets", "buildPresets", "testPresets", "workflowPresets"]

_STEP_PRESET_TYPES = {
    "configure": "configurePresets",
    "build": "buildPresets",
    "test": "testPresets",
}


def _compilers(names):
    return [
        {"name": name, "root": f"/opt/{name}", "cc": "gcc", "cxx": "g++"}
        for name in names
    ]


def _preset_names(output_data, preset_type):
    return [preset["name"] for preset in output_data[preset_type]]


def _assert_unique_names(output_data):
    for preset_type in _PRESET_TYPES:
        names = _preset_names(output_data, preset_type)
        assert len(names) == len(set(names)), preset_type


# Vary the options that change the output of make_output_data.
_OUTPUT_CONFIGS = st.builds(
    _config,
    inherits=st.sampled_from(["default", "base"]),
)

# The fields that refer to a different preset, and the preset type of the
# preset that they refer to, for each preset type.
_REFERENCE_FIELDS = {
    "configurePresets": {"inherits": "configurePresets"},
    "buildPresets": {"inherits": "buildPresets", "configurePreset": "configurePresets"},
    "testPresets": {"inherits": "testPresets", "configurePreset": "configurePresets"},
}


def _existing_names(config, output_data, preset_type):
    names = set(_preset_names(output_data, preset_type))
    if preset_type == "configurePresets":
        # config.inherits names a configure preset in CMakePresets.json of the
        # project. Thus the output does not contain it.
        names.add(config.inherits)
    return names


@given(_OUTPUT_CONFIGS, _SAFE_NAMES)
def test_output_preset_names_are_unique_in_each_preset_type(config, names):
    output_data = make_output_data(config, _compilers(names), PARENT_ENVIRONMENT)
    _assert_unique_names(output_data)


@given(_OUTPUT_CONFIGS, _SAFE_NAMES)
def test_each_workflow_step_refers_to_an_existing_preset(config, names):
    output_data = make_output_data(config, _compilers(names), PARENT_ENVIRONMENT)
    for workflow in output_data["workflowPresets"]:
        for step in workflow["steps"]:
            preset_type = _STEP_PRESET_TYPES[step["type"]]
            assert step["name"] in _existing_names(config, output_data, preset_type)


@given(_OUTPUT_CONFIGS, _SAFE_NAMES)
def test_each_preset_reference_refers_to_an_existing_preset(config, names):
    output_data = make_output_data(config, _compilers(names), PARENT_ENVIRONMENT)
    for preset_type, fields in _REFERENCE_FIELDS.items():
        for preset in output_data[preset_type]:
            for field, target_type in fields.items():
                if field in preset:
                    existing = _existing_names(config, output_data, target_type)
                    assert preset[field] in existing, (preset_type, field)


@given(_OUTPUT_CONFIGS, _SAFE_NAMES)
def test_output_has_three_workflows_for_each_compiler(config, names):
    output_data = make_output_data(config, _compilers(names), PARENT_ENVIRONMENT)
    expected = {name + suffix for name in names for suffix in ["", "-devel", "-debug"]}
    assert set(_preset_names(output_data, "workflowPresets")) == expected


@pytest.mark.xfail(
    strict=True,
    reason="Review.org: Duplicate compiler names or reserved names make an "
    "invalid presets file",
)
@settings(suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(names=_COLLIDING_NAMES)
def test_main_rejects_colliding_names_or_writes_unique_names(tmp_path, names):
    input_file = _write_project(tmp_path, "Ninja Multi-Config", _compilers(names))
    output = tmp_path / "CMakeUserPresets.json"
    # Hypothesis runs all examples in one tmp_path. Remove the output of
    # the previous example.
    output.unlink(missing_ok=True)
    if _run_main(tmp_path, input_file) == 0:
        output_data = json.loads(output.read_text())
        _assert_unique_names(output_data)
        assert "default" not in _preset_names(output_data, "configurePresets")


def test_configure_preset_with_add_paths_prepends_bin_to_path():
    preset = make_configure_preset(
        _config(), _compiler_with_add_paths(), PARENT_ENVIRONMENT
    )
    assert preset["environment"]["PATH"] == "/usr/local/gcc-14/bin:$penv{PATH}"


def test_configure_preset_with_add_paths_prepends_lib_dirs_to_library_path():
    preset = make_configure_preset(
        _config(), _compiler_with_add_paths(), PARENT_ENVIRONMENT
    )
    assert preset["environment"]["LIBRARY_PATH"] == (
        "/usr/local/gcc-14/lib:/usr/local/gcc-14/lib64:$penv{LIBRARY_PATH}"
    )


def test_configure_preset_with_add_paths_prepends_lib_dirs_to_ld_library_path():
    preset = make_configure_preset(
        _config(), _compiler_with_add_paths(), PARENT_ENVIRONMENT
    )
    assert preset["environment"]["LD_LIBRARY_PATH"] == (
        "/usr/local/gcc-14/lib:/usr/local/gcc-14/lib64:$penv{LD_LIBRARY_PATH}"
    )


def test_configure_preset_with_add_paths_uses_bare_compiler_names():
    environment = make_configure_preset(
        _config(), _compiler_with_add_paths(), PARENT_ENVIRONMENT
    )["environment"]
    assert (environment["CC"], environment["CXX"]) == ("gcc", "g++")


def test_configure_preset_without_add_paths_uses_full_compiler_paths():
    environment = make_configure_preset(
        _config(), _valid_compiler(), PARENT_ENVIRONMENT
    )["environment"]
    assert environment == {
        "CC": "/usr/local/gcc-14/bin/gcc",
        "CXX": "/usr/local/gcc-14/bin/g++",
    }


def test_workflow_presets_chain_configure_build_and_test_for_each_build_type():
    workflows = make_workflow_presets(_config(), [_valid_compiler()])
    assert workflows == [
        {
            "name": name,
            "steps": [
                {"type": "configure", "name": "gcc-14"},
                {"type": "build", "name": name},
                {"type": "test", "name": name},
            ],
        }
        for name in ["gcc-14", "gcc-14-devel", "gcc-14-debug"]
    ]


def test_binary_directory_contains_the_compiler_name():
    directory = binary_directory(_valid_compiler())
    assert directory == "${sourceDir}/build-gcc-14"


def _io_config(tmp_path, **overrides):
    defaults = {
        "filename": tmp_path / "compilers.json",
        "output_file": tmp_path / "CMakeUserPresets.json",
        "replace_existing": False,
        "stdout": False,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_validate_input_rejects_a_missing_input_file(tmp_path):
    with pytest.raises(RuntimeError, match="compilers.json"):
        validate_input(_io_config(tmp_path))


def test_validate_input_rejects_an_existing_output_file(tmp_path):
    config = _io_config(tmp_path)
    config.filename.write_text("[]")
    config.output_file.write_text("{}")
    with pytest.raises(RuntimeError, match="--replace-existing"):
        validate_input(config)


def test_validate_input_accepts_an_existing_output_file_with_replace_existing(
    tmp_path,
):
    config = _io_config(tmp_path, replace_existing=True)
    config.filename.write_text("[]")
    config.output_file.write_text("{}")
    validate_input(config)


def test_validate_input_accepts_an_existing_output_file_with_stdout(tmp_path):
    config = _io_config(tmp_path, stdout=True)
    config.filename.write_text("[]")
    config.output_file.write_text("{}")
    validate_input(config)


def test_write_output_data_writes_json_to_the_output_file(tmp_path):
    config = _io_config(tmp_path)
    write_output_data(config, {"version": 6})
    assert json.loads(config.output_file.read_text()) == {"version": 6}


def test_write_output_data_with_stdout_prints_json_and_writes_no_file(tmp_path, capsys):
    config = _io_config(tmp_path, stdout=True)
    write_output_data(config, {"version": 6})
    assert json.loads(capsys.readouterr().out) == {"version": 6}
    assert not config.output_file.exists()


def _configure_preset_named(output_data, name):
    return [p for p in output_data["configurePresets"] if p["name"] == name][0]


def test_main_writes_presets_for_each_compiler_from_input_to_output_file(tmp_path):
    compilers = _compilers(["gcc-14", "clang-18"])
    input_file = _write_project(tmp_path, "Ninja Multi-Config", compilers)
    assert _run_main(tmp_path, input_file) == 0
    output_data = json.loads((tmp_path / "CMakeUserPresets.json").read_text())
    assert _preset_names(output_data, "workflowPresets") == [
        "gcc-14",
        "clang-18",
        "gcc-14-devel",
        "clang-18-devel",
        "gcc-14-debug",
        "clang-18-debug",
    ]
    clang = _configure_preset_named(output_data, "clang-18")
    assert clang["binaryDir"] == "${sourceDir}/build-clang-18"
    assert clang["environment"]["CXX"] == "/opt/clang-18/bin/g++"


SEARCH_PATH_VARIABLES = ["PATH", "LIBRARY_PATH", "LD_LIBRARY_PATH", "CPATH"]

# Each variable of the parent environment is missing, empty, or set.
_PARENT_ENVIRONMENTS = st.dictionaries(
    st.sampled_from(SEARCH_PATH_VARIABLES), st.sampled_from(["", "/parent"])
)


@given(_PARENT_ENVIRONMENTS)
def test_search_paths_have_no_empty_element(parent_environment):
    preset = make_configure_preset(
        _config(), _compiler_with_add_paths(), parent_environment
    )
    for variable in SEARCH_PATH_VARIABLES:
        value = _expand_penv(preset["environment"][variable], parent_environment)
        assert "" not in value.split(":")


# Replace each $penv{VAR} with its parent value, as CMake does.
def _expand_penv(value, parent_environment):
    for variable in SEARCH_PATH_VARIABLES:
        value = value.replace(
            f"$penv{{{variable}}}", parent_environment.get(variable, "")
        )
    return value


# The compiler directories of each search path variable, from the README.
EXPECTED_DIRECTORIES = {
    "PATH": ["bin"],
    "LIBRARY_PATH": ["lib", "lib64"],
    "LD_LIBRARY_PATH": ["lib", "lib64"],
    "CPATH": ["include"],
}

_ROOTS = st.text(alphabet="abc_-", min_size=1, max_size=8).map(lambda s: "/opt/" + s)


@given(_ROOTS, _PARENT_ENVIRONMENTS)
def test_search_path_is_compiler_directories_then_parent_value_if_set(
    root, parent_environment
):
    compiler = _compiler_with_add_paths() | {"root": root}
    environment = make_configure_preset(_config(), compiler, parent_environment)[
        "environment"
    ]
    for variable, directories in EXPECTED_DIRECTORIES.items():
        expected = [f"{root}/{directory}" for directory in directories]
        if parent_environment.get(variable):
            expected.append(f"$penv{{{variable}}}")
        assert environment[variable] == ":".join(expected)


@given(_PARENT_ENVIRONMENTS, _PARENT_ENVIRONMENTS)
def test_environment_without_add_paths_does_not_depend_on_the_parent(first, second):
    environment = make_configure_preset(_config(), _valid_compiler(), first)[
        "environment"
    ]
    other = make_configure_preset(_config(), _valid_compiler(), second)["environment"]
    assert environment == other
    assert set(environment) == {"CC", "CXX"}


def test_main_uses_the_search_paths_of_the_real_parent_environment(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("LD_LIBRARY_PATH", "/parent/lib")
    monkeypatch.delenv("CPATH", raising=False)
    compilers = _write_project(
        tmp_path, "Ninja Multi-Config", [_compiler_with_add_paths()]
    )
    assert _run_main(tmp_path, compilers) == 0
    output = json.loads((tmp_path / "CMakeUserPresets.json").read_text())
    environment = output["configurePresets"][0]["environment"]
    assert environment["LD_LIBRARY_PATH"].endswith(":$penv{LD_LIBRARY_PATH}")
    assert "$penv" not in environment["CPATH"]


@pytest.mark.parametrize(
    "removed_option", ["--shared-build-directory", "--shared-devel-build-directory"]
)
def test_parser_rejects_removed_build_directory_options(removed_option):
    parser = make_command_line_parser("make-user-presets")
    with pytest.raises(SystemExit):
        parser.parse_args(["compilers.json", removed_option])


@given(_OUTPUT_CONFIGS, _SAFE_NAMES)
def test_each_compiler_has_its_own_build_directory_for_all_its_workflows(config, names):
    output_data = make_output_data(config, _compilers(names), PARENT_ENVIRONMENT)
    binary_dirs = {
        preset["name"]: preset["binaryDir"]
        for preset in output_data["configurePresets"]
    }
    assert len(set(binary_dirs.values())) == len(names)
    for workflow in output_data["workflowPresets"]:
        compiler = next(
            name
            for name in names
            if workflow["name"] in {name, name + "-devel", name + "-debug"}
        )
        configure_step = workflow["steps"][0]["name"]
        assert binary_dirs[configure_step] == "${sourceDir}/build-" + compiler
