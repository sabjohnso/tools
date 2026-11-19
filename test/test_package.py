"""Tests for the tools package and its entry points."""

import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

HEAVY_MODULES = ["jsonschema", "psutil"]
PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"


def _entry_points():
    scripts = tomllib.loads(PYPROJECT.read_text())["project"]["scripts"]
    return list(scripts.values())


ENTRY_POINTS = _entry_points()


def _run_fresh(program):
    return subprocess.run(
        [sys.executable, "-c", program], capture_output=True, text=True, check=True
    )


def _loaded_modules_after(statement):
    program = f"import sys\n{statement}\nprint('\\n'.join(sorted(sys.modules)))"
    return set(_run_fresh(program).stdout.split())


@pytest.mark.parametrize("module", HEAVY_MODULES)
def test_import_of_the_package_does_not_load_a_heavy_module(module):
    assert module not in _loaded_modules_after("import tools")


@pytest.mark.parametrize("module", HEAVY_MODULES)
def test_import_of_format_cxx_files_does_not_load_a_heavy_module(module):
    assert module not in _loaded_modules_after("import tools.format_cxx_files")


def test_package_docstring_does_not_name_a_specific_project():
    import tools

    assert "Morton" not in tools.__doc__


def test_each_script_in_pyproject_names_the_entry_point_of_a_tool_module():
    for target in ENTRY_POINTS:
        module, function = target.split(":")
        assert module.startswith("tools.")
        assert function == "entry_point"


def test_import_of_the_package_loads_no_tool_module():
    loaded = _loaded_modules_after("import tools")
    modules = {target.split(":")[0] for target in ENTRY_POINTS}
    assert loaded.isdisjoint(modules)


@pytest.mark.parametrize("target", ENTRY_POINTS)
def test_entry_point_runs_its_tool(target):
    module, function = target.split(":")
    _run_fresh(
        f"import sys, importlib\n"
        f"sys.argv = ['{module}', '--help']\n"
        f"entry_point = getattr(importlib.import_module('{module}'), '{function}')\n"
        f"try:\n"
        f"    entry_point()\n"
        f"except SystemExit as error:\n"
        f"    assert error.code == 0, error.code\n"
        f"else:\n"
        f"    raise AssertionError('the entry point did not exit')\n"
    )


TOOL_MODULES = [target.split(":")[0] for target in ENTRY_POINTS]


@pytest.mark.parametrize("module", TOOL_MODULES)
def test_module_run_as_a_program_shows_its_help(module):
    result = subprocess.run(
        [sys.executable, "-m", module, "--help"], capture_output=True, text=True
    )
    assert result.returncode == 0
    assert result.stdout.startswith("usage:")


@pytest.mark.parametrize("module", TOOL_MODULES)
def test_module_run_as_a_program_exits_with_the_code_of_its_tool(module, tmp_path):
    arguments = {
        "tools.make_user_presets": [str(tmp_path / "missing.json")],
        "tools.format_cxx_files": [
            "--source-tree",
            str(tmp_path),
            "--clang-format",
            str(tmp_path / "missing"),
        ],
        "tools.set_cmake_variable": ["-i", str(tmp_path / "missing.json"), "-D", "A=B"],
    }.get(module, ["-i", str(tmp_path / "missing.json")])
    (tmp_path / "main.cpp").write_text("int main(){}\n")
    result = subprocess.run(
        [sys.executable, "-m", module, *arguments], capture_output=True, text=True
    )
    assert result.returncode == 1
