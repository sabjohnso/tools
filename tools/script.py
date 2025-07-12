"""
This module contains the definition of a class (`Script`) that provides
a base class for scripts, to reduce code duplication.
"""

import sys
from pathlib import Path
from abc import ABC, abstractmethod
from argparse import ArgumentParser

__all__ = ["Script"]


class Script(ABC):
    """
    A base class for scripts. Derived classes must provide the methods
    `make_command_line_parser()` and `execute()`, where the former returns
    a command line parser and the latter executes the main logic of the
    script.

    This class provides the following properties for script execution:
      - `args`: the command line arguments
      - `stdin` :  a port to use as standard input
      - `stdout` : a port to use as standard output
      - `stderr` : a port to use as standard error
      - `runtime_config` : the runtime configuration
    """

    __slots__ = [
        "__args",
        "__stdin",
        "__stdout",
        "__stderr",
        "__parser",
        "__runtime_config",
        "__return_code",
    ]

    @property
    def args(self) -> list[str]:
        """
        Return the command line used to invoke the script.
        """
        return self.__args

    @property
    def stdin(self):
        """
        Return the input stream for this script
        """
        return self.__stdin

    @property
    def stdout(self):
        """
        Return the output stream for this script
        """
        return self.__stdout

    @property
    def stderr(self):
        """
        Return the error stream for this script
        """
        return self.__stderr

    @property
    def parser(self):
        """
        Return the command line parser
        """
        return self.__parser

    @property
    def runtime_config(self):
        """
        Return the runtime configuration produced by parsing the command
        line arguments with the command line parser.
        """
        return self.__runtime_config

    @property
    def return_code(self):
        """
        Return the return code for the script, indicating success or failure
        """
        return self.__return_code

    @abstractmethod
    def make_command_line_parser(self, prog: str) -> ArgumentParser:
        """
        An abstract method to return a command line parser
        """

    @abstractmethod
    def execute(self):
        """
        An abstract method to execute the script logic. The runtime configuration
        is available at the time this method is executed
        """

    def handle_exceptions(self, err):
        """
        A method to handle exceptions caught at the end of the script
        execution. As the default, this function prints the error and
        sets the return code to 1.  This will prevent the stack from
        being displayed to the user, which is usually the desired behavior.
        Override this function for different behavior that will be desired
        during debugging.
        """
        print(err)

    def __init__(
        self,
        args=sys.argv,
        stdin=sys.stdin,
        stdout=sys.stdout,
        stderr=sys.stderr,
    ):
        self.__return_code = 1
        self.__args = args
        self.__stdin = stdin
        self.__stdout = stdout
        self.__stderr = stderr
        self.__parser = self.make_command_line_parser(Path(self.args[0]).name)
        self.__runtime_config = self.__process_command_line()
        try:
            self.execute()
            self.__return_code = 0
        except SystemExit:
            raise
        except Exception as err:
            self.handle_exceptions(err)

    def __process_command_line(self):
        runtime_config = self.parser.parse_args(self.args[1:])
        return runtime_config
