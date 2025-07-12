# pylint: disable=missing-module-docstring
# pylint: disable=missing-function-docstring
# pylint: disable=redefined-outer-name
import pytest


from tools.script import Script


@pytest.fixture
def derived_script_class():
    class FakeArgumentParser:
        """
        This is a fake argument parser. It doen't realy parse arguments.
        """

        def parse_args(self, args):
            """
            Return the string "runtime_config" as the output of fake parsing dfdfdffdfd fdfafdfa
            the command line arguments.
            """
            assert isinstance(args, list)
            return "runtime_config"

    class ExampleScript(Script):
        """
        This is a derived class used to test the `Script`
        class
        """

        def make_command_line_parser(self, prog):
            return FakeArgumentParser()

        def execute(self):
            pass

    return ExampleScript


def empty_list():
    return []


def cmdline(additional_arguments=()):
    return ["program"] + additional_arguments


@pytest.fixture
def good_cmdline():
    return cmdline(["--arg", "argument"])


def test_script_accepts_arguments(derived_script_class, good_cmdline):
    script = derived_script_class(args=good_cmdline)
    assert script.args == good_cmdline


def test_script_accepts_stdin():
    pass


def test_script_stdin_is_sys_stdin_as_default():
    pass


def test_script_accepts_stdout():
    pass


def test_script_stdout_is_sys_stdout_as_default():
    pass


def test_script_accepts_stderr():
    pass


def test_script_stderr_is_sys_stderr_as_default():
    pass
