"""Tests for the resource_monitor module."""

import math
import re
import sys
from types import SimpleNamespace

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from tools.resource_monitor import (
    compute_cpu_percent,
    compute_resource_stats,
    cumulative_cpu_seconds,
    format_bytes,
    format_duration,
    format_resource_table,
    monitor_subprocess,
    process_tree_cpu_seconds,
)

# The child process uses CPU for 1.5 s.
BUSY_LOOP = (
    "import time\n"
    "t = time.monotonic()\n"
    "while time.monotonic() - t < 0.8:\n"
    "    sum(range(10**5))\n"
)

# The parent process starts short CPU-bound child processes one after the other.
SERIAL_CHILDREN = (
    "import subprocess, sys\n"
    "child = (\n"
    "    'import time\\n'\n"
    "    't = time.monotonic()\\n'\n"
    "    'while time.monotonic() - t < 0.5:\\n'\n"
    "    '    sum(range(10**5))\\n'\n"
    ")\n"
    "for _ in range(4):\n"
    "    subprocess.run([sys.executable, '-c', child], check=True)\n"
)

BYTE_UNITS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}

MAX_BYTES = 4 * 1024**4
MAX_SECONDS = 100 * 3600.0

durations = st.floats(min_value=0.0, max_value=MAX_SECONDS, allow_nan=False)
byte_counts = st.integers(min_value=0, max_value=MAX_BYTES)

# Values near a unit boundary, where a rounding defect can show.
byte_counts_near_a_unit = st.builds(
    lambda k, d: max(0, 1024**k + d),
    st.integers(min_value=0, max_value=4),
    st.integers(min_value=-100, max_value=100),
)
durations_near_a_minute = st.builds(
    lambda k, d: 60.0 * k + d,
    st.integers(min_value=1, max_value=120),
    st.floats(min_value=-0.1, max_value=0.1),
)
durations_of_whole_hours = st.builds(
    lambda k: 3600.0 * k, st.integers(min_value=1, max_value=100)
)

boundary_biased_byte_counts = st.one_of(byte_counts, byte_counts_near_a_unit)
boundary_biased_durations = st.one_of(
    durations, durations_near_a_minute, durations_of_whole_hours
)

cpu_times = st.floats(min_value=0.0, max_value=1e6)


# A format_duration string is "[<h>h ][<m>m ]<s.s>s".
DURATION_PATTERN = re.compile(r"(?:(\d+)h )?(?:(\d+)m )?(\d+\.\d)s")


def duration_hours_minutes_seconds(text):
    match = DURATION_PATTERN.fullmatch(text)
    assert match is not None, f"unexpected duration format: {text!r}"
    hours, minutes, seconds = match.groups()
    return int(hours or 0), int(minutes or 0), float(seconds)


def duration_total_seconds(text):
    hours, minutes, seconds = duration_hours_minutes_seconds(text)
    return hours * 3600 + minutes * 60 + seconds


def duration_minutes_and_seconds(text):
    _, minutes, seconds = duration_hours_minutes_seconds(text)
    return minutes, seconds


def bytes_shown_by(text):
    value, unit = text.split(" ")
    return float(value) * BYTE_UNITS[unit]


# --- compute_cpu_percent ---


def test_compute_cpu_percent_half_utilization():
    assert compute_cpu_percent(prev_cpu_time=1.0, cpu_time=3.0, dt=4.0) == 50.0


def test_compute_cpu_percent_full_utilization():
    assert compute_cpu_percent(prev_cpu_time=0.0, cpu_time=2.0, dt=2.0) == 100.0


def test_compute_cpu_percent_zero_dt_returns_zero():
    assert compute_cpu_percent(prev_cpu_time=0.0, cpu_time=1.0, dt=0.0) == 0.0


def test_compute_cpu_percent_multicore_exceeds_100():
    assert compute_cpu_percent(prev_cpu_time=0.0, cpu_time=8.0, dt=2.0) == 400.0


@given(
    prev=st.floats(min_value=0.0, max_value=1e6),
    delta=st.floats(min_value=0.0, max_value=1e6),
    dt=st.floats(min_value=1e-3, max_value=1e3),
)
def test_compute_cpu_percent_is_not_negative_for_non_negative_delta(prev, delta, dt):
    assert compute_cpu_percent(prev, prev + delta, dt) >= 0.0


@given(
    delta=st.floats(min_value=0.0, max_value=1e6),
    dt=st.floats(min_value=1e-3, max_value=1e3),
    factor=st.floats(min_value=1e-3, max_value=1e3),
)
def test_compute_cpu_percent_scales_linearly_with_cpu_time_delta(delta, dt, factor):
    scaled = compute_cpu_percent(0.0, factor * delta, dt)
    expected = factor * compute_cpu_percent(0.0, delta, dt)
    assert math.isclose(scaled, expected, rel_tol=1e-9, abs_tol=1e-9)


@given(
    delta=st.floats(min_value=0.0, max_value=1e6),
    dt=st.floats(min_value=1e-3, max_value=1e3),
    factor=st.floats(min_value=1e-3, max_value=1e3),
)
def test_compute_cpu_percent_is_unchanged_when_delta_and_dt_scale_together(
    delta, dt, factor
):
    scaled = compute_cpu_percent(0.0, factor * delta, factor * dt)
    expected = compute_cpu_percent(0.0, delta, dt)
    assert math.isclose(scaled, expected, rel_tol=1e-9, abs_tol=1e-9)


@given(prev=cpu_times, cpu_time=cpu_times, dt=st.floats(max_value=0.0))
def test_compute_cpu_percent_is_zero_when_dt_is_not_positive(prev, cpu_time, dt):
    assert compute_cpu_percent(prev, cpu_time, dt) == 0.0


@given(
    prev=cpu_times,
    delta=st.floats(min_value=0.0, max_value=1e6),
    offset=cpu_times,
    dt=st.floats(min_value=1e-3, max_value=1e3),
)
def test_compute_cpu_percent_is_unchanged_when_both_times_move_together(
    prev, delta, offset, dt
):
    moved = compute_cpu_percent(prev + offset, prev + delta + offset, dt)
    # The addition of the offset changes the difference by a rounding error of
    # the floats. The tolerance is that error, divided by dt, as a percentage.
    tolerance = 4 * math.ulp(prev + delta + offset) / dt * 100.0
    assert moved == pytest.approx(
        compute_cpu_percent(prev, prev + delta, dt), rel=1e-9, abs=tolerance
    )


# --- monitor_subprocess ---


def test_monitor_subprocess_reports_nonzero_cpu():
    # Use CPU for 0.8 s, so that the monitor takes one sample or more.
    _, samples, _ = monitor_subprocess([sys.executable, "-c", BUSY_LOOP])
    stats = compute_resource_stats(samples)
    assert stats["max_cpu"] > 0.0, "CPU load should be non-zero for a busy process"


# One run of SERIAL_CHILDREN serves both tests. The xdist group keeps both
# tests on one worker, so the run occurs once.
serial_children_run = pytest.mark.xdist_group("serial-children")


@pytest.fixture(scope="module")
def serial_children_monitoring():
    _, samples, elapsed = monitor_subprocess([sys.executable, "-c", SERIAL_CHILDREN])
    return samples, elapsed


@serial_children_run
def test_cumulative_cpu_time_does_not_decrease_with_short_children(
    serial_children_monitoring,
):
    # A sample is (change of cumulative CPU time) / dt, and dt is more than 0.
    # Thus a negative sample shows that the cumulative CPU time decreased.
    samples, _ = serial_children_monitoring
    negative = [cpu for cpu, _ in samples if cpu < 0.0]
    assert negative == []


@serial_children_run
def test_monitor_counts_the_cpu_time_of_short_children(serial_children_monitoring):
    # The four children use about 2.0 s of CPU time in all. The last interval
    # after the final sample is not measured, so expect 1.0 s or more.
    samples, elapsed = serial_children_monitoring
    mean_cpu = compute_resource_stats(samples)["mean_cpu"]
    assert mean_cpu / 100.0 * elapsed >= 1.0


_CPU_SECONDS = st.floats(min_value=0.0, max_value=1e6)


# A fake process for process_tree_cpu_seconds. It has the psutil methods that
# the function uses: cpu_times() and children(recursive=True).
class _FakeProcess:
    def __init__(self, user, system, children=()):
        self.times = SimpleNamespace(
            user=user, system=system, children_user=0.0, children_system=0.0
        )
        self.live_children = list(children)

    def cpu_times(self):
        return self.times

    def children(self, recursive=False):
        descendants = []
        for child in self.live_children:
            descendants.append(child)
            if recursive:
                descendants.extend(child.children(recursive=True))
        return descendants


# The operating system adds the CPU time of a stopped child, and of the
# children that it waited for, to the parent when the parent waits for it.
def _wait_for(parent, child):
    parent.times.children_user += child.times.user + child.times.children_user
    parent.times.children_system += child.times.system + child.times.children_system
    parent.live_children.remove(child)


@given(st.lists(_CPU_SECONDS, min_size=6, max_size=6))
def test_process_tree_cpu_seconds_does_not_change_when_children_stop(seconds):
    grandchild = _FakeProcess(seconds[0], seconds[1])
    child = _FakeProcess(seconds[2], seconds[3], [grandchild])
    parent = _FakeProcess(seconds[4], seconds[5], [child])
    before = process_tree_cpu_seconds(parent)
    _wait_for(child, grandchild)
    assert process_tree_cpu_seconds(parent) == pytest.approx(before)
    _wait_for(parent, child)
    assert process_tree_cpu_seconds(parent) == pytest.approx(before)


@given(_CPU_SECONDS, _CPU_SECONDS, _CPU_SECONDS, _CPU_SECONDS)
def test_cumulative_cpu_seconds_adds_the_children_that_the_process_waited_for(
    user, system, children_user, children_system
):
    times = SimpleNamespace(
        user=user,
        system=system,
        children_user=children_user,
        children_system=children_system,
    )
    expected = user + system + children_user + children_system
    assert cumulative_cpu_seconds(times) == pytest.approx(expected)


@given(_CPU_SECONDS, _CPU_SECONDS)
def test_cumulative_cpu_seconds_counts_missing_children_fields_as_zero(user, system):
    times = SimpleNamespace(user=user, system=system)
    assert cumulative_cpu_seconds(times) == user + system


# --- compute_resource_stats ---


def test_compute_resource_stats_from_samples():
    samples = [(10.0, 1000), (50.0, 3000), (30.0, 2000)]
    stats = compute_resource_stats(samples)
    assert stats["max_cpu"] == 50.0
    assert stats["mean_cpu"] == 30.0
    assert stats["max_rss"] == 3000
    assert stats["mean_rss"] == 2000.0


def test_compute_resource_stats_single_sample():
    samples = [(42.0, 5000)]
    stats = compute_resource_stats(samples)
    assert stats["max_cpu"] == 42.0
    assert stats["mean_cpu"] == 42.0
    assert stats["max_rss"] == 5000
    assert stats["mean_rss"] == 5000.0


def test_compute_resource_stats_empty_returns_zeros():
    stats = compute_resource_stats([])
    assert stats["max_cpu"] == 0.0
    assert stats["mean_cpu"] == 0.0
    assert stats["max_rss"] == 0
    assert stats["mean_rss"] == 0.0


# --- format_bytes ---


def test_format_bytes_megabytes():
    assert format_bytes(100 * 1024 * 1024) == "100.0 MB"


def test_format_bytes_gigabytes():
    assert format_bytes(2 * 1024 * 1024 * 1024) == "2.0 GB"


def test_format_bytes_kilobytes():
    assert format_bytes(512 * 1024) == "512.0 KB"


def test_format_bytes_small():
    assert format_bytes(500) == "500 B"


def test_format_bytes_zero():
    assert format_bytes(0) == "0 B"


@given(a=boundary_biased_byte_counts, b=boundary_biased_byte_counts)
def test_format_bytes_is_monotonic(a, b):
    low, high = sorted((a, b))
    assert bytes_shown_by(format_bytes(low)) <= bytes_shown_by(format_bytes(high))


@given(n=byte_counts)
def test_format_bytes_shows_a_value_near_the_input(n):
    # The output has one decimal digit, so the error is half of 0.1 unit or less.
    shown = bytes_shown_by(format_bytes(n))
    unit = BYTE_UNITS[format_bytes(n).split(" ")[1]]
    assert abs(shown - n) <= 0.05 * unit + 1e-6 * n


@given(n=st.integers(min_value=0, max_value=1023 * 1024))
def test_format_bytes_value_is_below_1024_up_to_1023_kb(n):
    value, _ = format_bytes(n).split(" ")
    assert float(value) < 1024


@given(n=st.integers(min_value=0, max_value=1024**3 - 1))
@example(n=1024**2 - 1)
def test_format_bytes_value_is_below_1024_below_one_gigabyte(n):
    value, _ = format_bytes(n).split(" ")
    assert float(value) < 1024


def test_format_bytes_just_below_one_megabyte_shows_megabytes():
    assert format_bytes(1024**2 - 1) == "1.0 MB"


def test_format_bytes_just_below_one_gigabyte_shows_gigabytes():
    assert format_bytes(1024**3 - 1) == "1.0 GB"


@given(n=boundary_biased_byte_counts)
def test_format_bytes_shows_a_value_near_the_input_at_a_unit_boundary(n):
    # The error is half of the last shown digit or less.
    text = format_bytes(n)
    unit = BYTE_UNITS[text.split(" ")[1]]
    last_digit = 1 if unit == 1 else 0.1
    assert abs(bytes_shown_by(text) - n) <= last_digit / 2 * unit + 1e-6 * n


# --- format_duration ---


def test_format_duration_seconds():
    assert format_duration(45.3) == "45.3s"


def test_format_duration_minutes_and_seconds():
    assert format_duration(125.7) == "2m 5.7s"


def test_format_duration_hours_minutes_seconds():
    assert format_duration(3723.1) == "1h 2m 3.1s"


def test_format_duration_zero():
    assert format_duration(0.0) == "0.0s"


@given(a=boundary_biased_durations, b=boundary_biased_durations)
def test_format_duration_is_monotonic(a, b):
    low, high = sorted((a, b))
    assert duration_total_seconds(format_duration(low)) <= duration_total_seconds(
        format_duration(high)
    )


@given(seconds=durations)
def test_format_duration_shows_a_value_near_the_input(seconds):
    # The output has one decimal digit, so the error is 0.05 s or less.
    shown = duration_total_seconds(format_duration(seconds))
    assert abs(shown - seconds) <= 0.05 + 1e-9 * seconds


@given(seconds=st.floats(min_value=0.0, max_value=59.9))
def test_format_duration_seconds_field_is_below_60_up_to_59_9_seconds(seconds):
    _, secs = duration_minutes_and_seconds(format_duration(seconds))
    assert secs < 60


@given(seconds=durations)
@example(seconds=59.97)
@example(seconds=3599.97)
def test_format_duration_minute_and_second_fields_are_below_60(seconds):
    minutes, secs = duration_minutes_and_seconds(format_duration(seconds))
    assert minutes < 60
    assert secs < 60


def test_format_duration_just_below_one_minute_shows_one_minute():
    assert format_duration(59.97) == "1m 0.0s"


def test_format_duration_just_below_one_hour_shows_one_hour():
    assert format_duration(3599.97) == "1h 0m 0.0s"


@given(seconds=boundary_biased_durations)
def test_format_duration_shows_a_value_near_the_input_at_a_unit_boundary(seconds):
    # The last shown digit is 0.1 s, so the error is 0.05 s or less.
    shown = duration_total_seconds(format_duration(seconds))
    assert abs(shown - seconds) <= 0.05 + 1e-9 * seconds


# --- format_resource_table ---


def test_format_resource_table_contains_all_metrics():
    stats = {
        "max_cpu": 95.2,
        "mean_cpu": 45.1,
        "max_rss": 512 * 1024 * 1024,
        "mean_rss": 256 * 1024 * 1024,
        "elapsed": 12.5,
    }
    table = format_resource_table(stats)
    assert "CPU" in table
    assert "RSS" in table
    assert "Max" in table
    assert "Mean" in table
    assert "Elapsed" in table


def test_format_resource_table_contains_values():
    stats = {
        "max_cpu": 95.2,
        "mean_cpu": 45.1,
        "max_rss": 512 * 1024 * 1024,
        "mean_rss": 256 * 1024 * 1024,
        "elapsed": 12.5,
    }
    table = format_resource_table(stats)
    assert "95.2" in table
    assert "45.1" in table
    assert "512.0 MB" in table
    assert "256.0 MB" in table
    assert "12.5s" in table


def test_format_resource_table_gives_the_exact_table():
    stats = {
        "max_cpu": 95.2,
        "mean_cpu": 45.1,
        "max_rss": 512 * 1024 * 1024,
        "mean_rss": 256 * 1024 * 1024,
        "elapsed": 12.5,
    }
    assert format_resource_table(stats) == "\n".join(
        [
            "┌──────────┬──────────┬──────────┐",
            "│ Metric   │      Max │     Mean │",
            "├──────────┼──────────┼──────────┤",
            "│ Elapsed  │    12.5s │          │",
            "│ CPU Load │   95.2 % │   45.1 % │",
            "│ RSS      │ 512.0 MB │ 256.0 MB │",
            "└──────────┴──────────┴──────────┘",
        ]
    )


_CPU_PERCENTS = st.floats(min_value=0.0, max_value=1e5)


@given(
    _CPU_PERCENTS,
    _CPU_PERCENTS,
    boundary_biased_byte_counts,
    boundary_biased_byte_counts,
    boundary_biased_durations,
)
def test_format_resource_table_lines_have_one_width_and_aligned_columns(
    max_cpu, mean_cpu, max_rss, mean_rss, elapsed
):
    stats = {
        "max_cpu": max_cpu,
        "mean_cpu": mean_cpu,
        "max_rss": max_rss,
        "mean_rss": mean_rss,
        "elapsed": elapsed,
    }
    lines = format_resource_table(stats).split("\n")
    assert len(lines) == 7
    assert len({len(line) for line in lines}) == 1
    columns = [
        [index for index, char in enumerate(line) if char in "│┌┬┐├┼┤└┴┘"]
        for line in lines
    ]
    assert all(positions == columns[0] for positions in columns)
    assert len(columns[0]) == 4
