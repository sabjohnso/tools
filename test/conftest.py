"""Shared pytest fixtures for the CMake user preset tests."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def preset_data() -> dict:
    return {
        "version": 6,
        "configurePresets": [
            _configure_preset("gcc-14"),
            _configure_preset("clang-18"),
        ],
        "workflowPresets": [
            _workflow_preset("gcc-14", configure="gcc-14"),
            _workflow_preset("clang-18", configure="clang-18"),
            _workflow_preset("gcc-14-devel", configure="gcc-14"),
        ],
    }


@pytest.fixture
def presets_file(tmp_path: Path, preset_data: dict) -> Path:
    path = tmp_path / "CMakeUserPresets.json"
    path.write_text(json.dumps(preset_data), encoding="utf-8")
    return path


def _configure_preset(name: str) -> dict:
    return {"name": name, "binaryDir": f"${{sourceDir}}/build-{name}"}


def _workflow_preset(name: str, configure: str) -> dict:
    return {
        "name": name,
        "steps": [
            {"type": "configure", "name": configure},
            {"type": "build", "name": name},
            {"type": "test", "name": name},
        ],
    }
