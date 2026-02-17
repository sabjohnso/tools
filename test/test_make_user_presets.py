from types import SimpleNamespace
from unittest.mock import patch

from tools.make_user_presets import main, make_configure_preset


def _compiler_with_add_paths():
    return {
        "name": "gcc-14",
        "root": "/usr/local/gcc-14",
        "cc": "gcc",
        "cxx": "g++",
        "addPaths": True,
    }


def _config(**overrides):
    defaults = {"shared_build_directory": False}
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_cpath_has_separator_before_penv():
    preset = make_configure_preset(_config(), _compiler_with_add_paths())
    cpath = preset["environment"]["CPATH"]
    assert cpath == "/usr/local/gcc-14/include:$penv{CPATH}"


def test_main_returns_zero_on_success():
    with patch("tools.make_user_presets.run"):
        result = main(["make-user-presets", "/dev/null"])
    assert result == 0
