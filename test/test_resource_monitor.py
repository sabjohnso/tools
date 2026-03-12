"""Tests for the resource_monitor module."""

from tools.resource_monitor import (
    compute_resource_stats,
    format_duration,
    format_resource_table,
    format_bytes,
)


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


# --- format_duration ---


def test_format_duration_seconds():
    assert format_duration(45.3) == "45.3s"


def test_format_duration_minutes_and_seconds():
    assert format_duration(125.7) == "2m 5.7s"


def test_format_duration_hours_minutes_seconds():
    assert format_duration(3723.1) == "1h 2m 3.1s"


def test_format_duration_zero():
    assert format_duration(0.0) == "0.0s"


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


def test_format_resource_table_is_multiline():
    stats = {
        "max_cpu": 50.0,
        "mean_cpu": 25.0,
        "max_rss": 1024 * 1024,
        "mean_rss": 1024 * 1024,
        "elapsed": 5.0,
    }
    table = format_resource_table(stats)
    lines = table.strip().split("\n")
    assert len(lines) >= 5, "Table should have header + separator + 3 data rows"
