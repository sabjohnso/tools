"""Hypothesis strategies and test oracles for workflow selection tests."""

import json
import re
from pathlib import Path

from hypothesis import strategies as st

# The alphabet has the characters that REGEX_PATTERNS look for, so that
# generated names can match each of these patterns.
NAME_ALPHABET = "abcg4-"

REGEX_PATTERNS = ["a|b", "c+", "^a.*c$", "[ab]-", "(?!a)", "4$", "^g"]

NAMES = st.text(alphabet=NAME_ALPHABET, max_size=5)

LITERAL_PATTERNS = st.builds(
    lambda prefix, body, suffix: prefix + re.escape(body) + suffix,
    st.sampled_from(["", "^"]),
    st.text(alphabet=NAME_ALPHABET, min_size=1, max_size=3),
    st.sampled_from(["", "$"]),
)

PATTERNS = st.one_of(st.none(), LITERAL_PATTERNS, st.sampled_from(REGEX_PATTERNS))

# Few binary directories, so that configure presets can share one.
BINARY_DIRS = ["${sourceDir}/build-x", "${sourceDir}/build-y", "/abs"]


@st.composite
def user_presets(draw):
    """Return a CMakeUserPresets.json structure with workflow presets."""
    configure_names = draw(st.lists(NAMES, min_size=1, max_size=4, unique=True))
    binary_dirs = draw(_lists_of_length(st.sampled_from(BINARY_DIRS), configure_names))
    workflow_names = draw(st.lists(NAMES, max_size=6, unique=True))
    configure_of_workflow = draw(
        _lists_of_length(st.sampled_from(configure_names), workflow_names)
    )
    return {
        "version": 6,
        "configurePresets": [
            {"name": name, "binaryDir": binary_dir}
            for name, binary_dir in zip(configure_names, binary_dirs)
        ],
        "workflowPresets": [
            {"name": name, "steps": [{"type": "configure", "name": configure}]}
            for name, configure in zip(workflow_names, configure_of_workflow)
        ],
    }


def _lists_of_length(elements, other):
    """Return a strategy for lists with the same length as the other list."""
    return st.lists(elements, min_size=len(other), max_size=len(other))


def is_subsequence(candidate, sequence):
    """Return True if the candidate items occur in the sequence in that order."""
    remaining = iter(sequence)
    return all(item in remaining for item in candidate)


# The oracles below calculate the expected results without the production
# code, so that a defect in the production code cannot also change the
# expected result.


def expected_names(names, matching, exclude):
    """Return the names that match and that are not excluded."""
    return [
        name
        for name in names
        if (not matching or re.search(matching, name))
        and not (exclude and re.search(exclude, name))
    ]


def expected_directory_sequence(user_presets, matching, exclude, source_dir):
    """Return the build directory of each selected workflow, in workflow order."""
    binary_dirs = {p["name"]: p["binaryDir"] for p in user_presets["configurePresets"]}
    configure_of = {
        w["name"]: w["steps"][0]["name"] for w in user_presets["workflowPresets"]
    }
    selected = expected_names(list(configure_of), matching, exclude)
    return [
        Path(binary_dirs[configure_of[name]].replace("${sourceDir}", str(source_dir)))
        for name in selected
    ]


def write_json(path, data):
    """Write the data to the path as JSON and return the path."""
    path.write_text(json.dumps(data), encoding="utf-8")
    return path
