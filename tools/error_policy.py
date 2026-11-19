"""Turn the errors of a tool into a short message and an exit code.

A stack trace helps a developer, not a user. The tools therefore show one
only when the command line has --stack-trace or the environment sets
TOOLS_STACK_TRACE to a true value.
"""

import json
import os
import re
import subprocess
import sys
import traceback
from argparse import ArgumentParser
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from tools.errors import UserError

EXIT_ERROR = 1
EXIT_SOFTWARE = 70
EXIT_INTERRUPTED = 130

STACK_TRACE_OPTION = "--stack-trace"
STACK_TRACE_VARIABLE = "TOOLS_STACK_TRACE"
TRUE_VALUES = {"1", "true", "yes", "on"}

UNEXPECTED_ERROR_HINT = f"Run again with {STACK_TRACE_OPTION} and report the output."


# Errors that come from the input or the environment of the user, and not
# from a defect in the tools.
EXPECTED_ERRORS = (
    UserError,
    OSError,
    json.JSONDecodeError,
    re.error,
    KeyError,
)


def run_tool(
    execute: Callable[[Sequence[str]], int],
    args: Sequence[str],
    environ: Mapping[str, str] | None = None,
) -> int:
    """Run execute(args) with the error policy and return the exit code."""
    show_stack_trace = stack_trace_requested(
        args, os.environ if environ is None else environ
    )
    program = Path(args[0]).name
    try:
        return execute(args)
    except subprocess.CalledProcessError as error:
        return error.returncode
    except KeyboardInterrupt:
        return EXIT_INTERRUPTED
    except EXPECTED_ERRORS as error:
        report(program, describe(error), error, show_stack_trace)
        return EXIT_ERROR
    except Exception as error:
        message = f"internal error: {type(error).__name__}: {error}"
        hint = f"{message}\n{UNEXPECTED_ERROR_HINT}"
        report(program, hint, error, show_stack_trace)
        return EXIT_SOFTWARE


def add_stack_trace_option(parser: ArgumentParser) -> None:
    """Add the --stack-trace option to the command line parser of a tool."""
    parser.add_argument(
        STACK_TRACE_OPTION,
        action="store_true",
        help="Show the Python stack trace of an error (for developers)",
    )


def stack_trace_requested(args: Sequence[str], environ: Mapping[str, str]) -> bool:
    """Return True if the command line or the environment asks for a trace."""
    # Only the exact option counts, so that an abbreviation of another option,
    # for example --s for --source-tree, does not turn on stack traces.
    parser = ArgumentParser(add_help=False, allow_abbrev=False)
    add_stack_trace_option(parser)
    known, _ = parser.parse_known_args(args[1:])
    variable = environ.get(STACK_TRACE_VARIABLE, "").strip().lower()
    return known.stack_trace or variable in TRUE_VALUES


def describe(error: BaseException) -> str:
    """Return the message for an expected error."""
    if isinstance(error, KeyError):
        return "missing entry: " + ", ".join(str(argument) for argument in error.args)
    return str(error).strip()


def report(
    program: str, message: str, error: BaseException, show_stack_trace: bool
) -> None:
    """Write the message, and the stack trace of error if requested, to stderr."""
    if show_stack_trace:
        traceback.print_exception(error, file=sys.stderr)
    print(f"{program}: {message}", file=sys.stderr)
