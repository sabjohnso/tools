"""Tests for the error_policy module."""

import contextlib
import io
import json
import re
import subprocess
import sys

import pytest
from hypothesis import given
from hypothesis import strategies as st

import tools
from tools.error_policy import (
    EXIT_ERROR,
    EXIT_INTERRUPTED,
    EXIT_SOFTWARE,
    STACK_TRACE_OPTION,
    STACK_TRACE_VARIABLE,
    TRUE_VALUES,
    run_tool,
)
from tools.errors import UserError

PROGRAM = "some-tool"


def _raising(error):
    def execute(args):
        raise error

    return execute


def _run(error, *extra_args, environ=None):
    return run_tool(_raising(error), [PROGRAM, *extra_args], environ or {})


# --- expected errors ---


@pytest.mark.parametrize(
    "error",
    [
        UserError("the output file already exists"),
        FileNotFoundError(2, "No such file or directory", "missing.json"),
        json.JSONDecodeError("Expecting value", "", 0),
        re.error("unterminated character set"),
        KeyError("gcc-14"),
    ],
)
def test_expected_error_gives_one_message_and_exit_code_1(error, capsys):
    assert _run(error) == EXIT_ERROR
    err = capsys.readouterr().err
    assert err.startswith(f"{PROGRAM}: ")
    assert "Traceback" not in err


def test_message_of_a_missing_key_names_the_key(capsys):
    _run(KeyError("gcc-14"))
    assert "gcc-14" in capsys.readouterr().err


# --- unexpected errors ---


def test_unexpected_error_gives_type_message_and_hint(capsys):
    assert _run(ZeroDivisionError("division by zero")) == EXIT_SOFTWARE
    err = capsys.readouterr().err
    assert "ZeroDivisionError" in err
    assert "division by zero" in err
    assert STACK_TRACE_OPTION in err
    assert "Traceback" not in err


# --- other exits ---


def test_failed_subprocess_gives_its_return_code_and_no_message(capsys):
    assert _run(subprocess.CalledProcessError(3, "cmake")) == 3
    assert "Traceback" not in capsys.readouterr().err


def test_interrupt_gives_exit_code_130_and_no_stack_trace(capsys):
    assert _run(KeyboardInterrupt()) == EXIT_INTERRUPTED
    assert "Traceback" not in capsys.readouterr().err


def test_command_line_errors_keep_their_exit(capsys):
    with pytest.raises(SystemExit) as exit_info:
        _run(SystemExit(2))
    assert exit_info.value.code == 2


def test_success_gives_the_result_of_the_tool():
    assert run_tool(lambda args: 0, [PROGRAM], {}) == 0


# --- stack trace on request ---


def test_option_shows_the_stack_trace(capsys):
    _run(ZeroDivisionError("division by zero"), STACK_TRACE_OPTION)
    assert "Traceback" in capsys.readouterr().err


@pytest.mark.parametrize("argument", ["--s", "--st", "--stack"])
def test_abbreviation_of_the_option_shows_no_stack_trace(argument, capsys):
    _run(ZeroDivisionError("division by zero"), argument)
    assert "Traceback" not in capsys.readouterr().err


def test_missing_key_with_no_arguments_gives_exit_code_1(capsys):
    assert _run(KeyError()) == EXIT_ERROR
    assert "Traceback" not in capsys.readouterr().err


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_environment_variable_shows_the_stack_trace(value, capsys):
    _run(UserError("bad input"), environ={STACK_TRACE_VARIABLE: value})
    assert "Traceback" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["", "0", "false", "no"])
def test_environment_variable_off_shows_no_stack_trace(value, capsys):
    _run(UserError("bad input"), environ={STACK_TRACE_VARIABLE: value})
    assert "Traceback" not in capsys.readouterr().err


# Each error type with the exit code that the policy must give for it.
_ERRORS_WITH_CODES = st.sampled_from(
    [
        (UserError, EXIT_ERROR),
        (OSError, EXIT_ERROR),
        (FileNotFoundError, EXIT_ERROR),
        (PermissionError, EXIT_ERROR),
        (KeyError, EXIT_ERROR),
        (ValueError, EXIT_SOFTWARE),
        (TypeError, EXIT_SOFTWARE),
        (RuntimeError, EXIT_SOFTWARE),
        (IndexError, EXIT_SOFTWARE),
    ]
)
_ERROR_ARGUMENTS = st.lists(st.text(max_size=10) | st.integers(), max_size=3)
# Command-line arguments that are not the option.
_OTHER_ARGUMENTS = st.lists(
    # "--" ends the options, so an option after it is a positional argument.
    st.text(max_size=10).filter(
        lambda a: a != "--" and not a.startswith(STACK_TRACE_OPTION)
    ),
    max_size=4,
)
_FALSE_VALUES = st.none() | st.text(max_size=8).filter(
    lambda v: v.strip().lower() not in TRUE_VALUES
)


def _run_captured(error, arguments, environ):
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        code = run_tool(_raising(error), [PROGRAM, *arguments], environ)
    return code, stderr.getvalue()


def _environment(value):
    return {} if value is None else {STACK_TRACE_VARIABLE: value}


@given(_ERRORS_WITH_CODES, _ERROR_ARGUMENTS, _OTHER_ARGUMENTS, _FALSE_VALUES)
def test_no_error_shows_a_stack_trace_without_a_request(
    error_and_code, error_arguments, arguments, value
):
    error_type, expected_code = error_and_code
    error = error_type(*error_arguments)
    code, stderr = _run_captured(error, arguments, _environment(value))
    assert code == expected_code
    assert stderr.startswith(f"{PROGRAM}: ")
    assert "Traceback" not in stderr


# A true value of the variable, in any case and with spaces around it.
_TRUE_VALUES = st.tuples(
    st.sampled_from(sorted(TRUE_VALUES)), st.text(" \t", max_size=2)
).flatmap(
    lambda pair: st.lists(st.booleans(), min_size=len(pair[0]), max_size=len(pair[0]))
    .map(lambda upper: "".join(c.upper() if u else c for c, u in zip(pair[0], upper)))
    .map(lambda value: pair[1] + value + pair[1])
)


@given(
    _ERRORS_WITH_CODES,
    _ERROR_ARGUMENTS,
    _OTHER_ARGUMENTS,
    st.integers(min_value=0, max_value=4),
    _TRUE_VALUES,
)
def test_a_request_adds_the_stack_trace_and_keeps_the_rest(
    error_and_code, error_arguments, arguments, position, value
):
    error_type, _ = error_and_code

    # Each run raises a new exception, because a raise adds to the traceback.
    def error():
        return error_type(*error_arguments)

    code, plain = _run_captured(error(), arguments, {})
    with_option = list(arguments)
    with_option.insert(min(position, len(arguments)), STACK_TRACE_OPTION)
    traced_code, traced = _run_captured(error(), with_option, {})
    variable_code, by_variable = _run_captured(error(), arguments, _environment(value))
    assert traced_code == code == variable_code
    assert "Traceback" in traced
    assert traced.endswith(plain)
    assert by_variable == traced


# --- the five tools ---


def _tool_cases(tmp_path):
    missing = str(tmp_path / "missing.json")
    source = tmp_path / "src"
    source.mkdir()
    (source / "main.cpp").write_text("int main(){}\n")
    return {
        "make_user_presets": ["make-user-presets", missing],
        "run_user_workflows": ["run-user-workflows", "-i", missing],
        "clear_cmake_cache": ["clear-cmake-cache", "-i", missing],
        "set_cmake_variable": ["set-cmake-variable", "-i", missing, "-D", "A=B"],
        "format_cxx_files": [
            "format-cxx-files",
            "--source-tree",
            str(source),
            "--clang-format",
            str(tmp_path / "no-such-clang-format"),
        ],
    }


TOOLS = [
    "make_user_presets",
    "run_user_workflows",
    "clear_cmake_cache",
    "set_cmake_variable",
    "format_cxx_files",
]


def _run_entry_point(name, argv, monkeypatch):
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.delenv(STACK_TRACE_VARIABLE, raising=False)
    with pytest.raises(SystemExit) as exit_info:
        getattr(tools, name)()
    return exit_info.value.code


@pytest.mark.parametrize("name", TOOLS)
def test_tool_reports_a_missing_file_without_a_stack_trace(
    name, tmp_path, monkeypatch, capsys
):
    argv = _tool_cases(tmp_path)[name]
    assert _run_entry_point(name, argv, monkeypatch) == EXIT_ERROR
    err = capsys.readouterr().err
    assert err.startswith(f"{argv[0]}: ")
    assert "Traceback" not in err


@pytest.mark.parametrize("name", TOOLS)
def test_tool_shows_the_stack_trace_on_request(name, tmp_path, monkeypatch, capsys):
    argv = _tool_cases(tmp_path)[name] + [STACK_TRACE_OPTION]
    assert _run_entry_point(name, argv, monkeypatch) == EXIT_ERROR
    assert "Traceback" in capsys.readouterr().err


def test_invalid_compiler_list_gives_one_message_and_exit_code_1(
    tmp_path, monkeypatch, capsys
):
    compilers = tmp_path / "compilers.json"
    compilers.write_text('[{"name": "gcc-14"}]')
    argv = ["make-user-presets", str(compilers), "-o", str(tmp_path / "out.json")]
    assert _run_entry_point("make_user_presets", argv, monkeypatch) == EXIT_ERROR
    err = capsys.readouterr().err
    assert err.startswith("make-user-presets: ")
    assert "Traceback" not in err


def test_environment_of_the_process_shows_the_stack_trace(
    tmp_path, monkeypatch, capsys
):
    argv = _tool_cases(tmp_path)["clear_cmake_cache"]
    monkeypatch.setattr(sys, "argv", argv)
    monkeypatch.setenv(STACK_TRACE_VARIABLE, "1")
    with pytest.raises(SystemExit):
        tools.clear_cmake_cache()
    assert "Traceback" in capsys.readouterr().err


_PRESET_TOOLS = ["run_user_workflows", "clear_cmake_cache", "set_cmake_variable"]


def _preset_tool_argv(name, presets):
    argv = [name.replace("_", "-"), "-i", str(presets)]
    return argv + ["-D", "A=B"] if name == "set_cmake_variable" else argv


# run-user-workflows gives such a workflow to cmake, which reports the error.
@pytest.mark.parametrize("name", ["clear_cmake_cache", "set_cmake_variable"])
def test_tool_reports_a_workflow_without_a_configure_step(
    name, tmp_path, monkeypatch, capsys
):
    presets = tmp_path / "CMakeUserPresets.json"
    workflow = {"name": "gcc-14", "steps": [{"type": "build", "name": "gcc-14"}]}
    presets.write_text(
        json.dumps({"configurePresets": [], "workflowPresets": [workflow]})
    )
    argv = _preset_tool_argv(name, presets)
    assert _run_entry_point(name, argv, monkeypatch) == EXIT_ERROR
    err = capsys.readouterr().err
    assert "No configure step in workflow: gcc-14" in err
    assert "missing entry" not in err


@pytest.mark.parametrize("name", _PRESET_TOOLS)
def test_tool_reports_a_presets_file_without_workflows(
    name, tmp_path, monkeypatch, capsys
):
    presets = tmp_path / "CMakeUserPresets.json"
    presets.write_text("{}")
    argv = _preset_tool_argv(name, presets)
    assert _run_entry_point(name, argv, monkeypatch) == EXIT_ERROR
    assert "missing entry: workflowPresets" in capsys.readouterr().err


def test_option_after_end_of_options_shows_no_stack_trace(capsys):
    _run(ZeroDivisionError("division by zero"), "--", STACK_TRACE_OPTION)
    assert "Traceback" not in capsys.readouterr().err


def test_message_starts_with_the_name_of_the_program_without_its_path(capsys):
    run_tool(_raising(UserError("bad input")), ["/usr/local/bin/some-tool"], {})
    assert capsys.readouterr().err.startswith("some-tool: bad input")


@given(st.integers(min_value=1, max_value=255))
def test_failed_subprocess_gives_its_return_code(returncode):
    error = subprocess.CalledProcessError(returncode, "cmake")
    assert _run_captured(error, [], {}) == (returncode, "")
