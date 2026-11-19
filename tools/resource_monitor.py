"""Monitor subprocess resource usage (CPU and RSS)."""

import subprocess
import time
import threading

import psutil


def monitor_subprocess(cmd):
    """Run cmd, sample its process tree, and return (returncode, samples, elapsed)."""
    start = time.monotonic()
    process = subprocess.Popen(cmd)
    samples = []
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_sample_loop,
        args=(process.pid, samples, stop_event),
        daemon=True,
    )
    thread.start()
    process.wait()
    elapsed = time.monotonic() - start
    stop_event.set()
    thread.join()
    return process.returncode, samples, elapsed


def _sample_loop(pid, samples, stop_event):
    """Periodically sample CPU and RSS for a process tree."""
    try:
        proc = psutil.Process(pid)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return
    prev_time = time.monotonic()
    prev_cpu_time = process_tree_cpu_seconds(proc)
    while not stop_event.is_set():
        stop_event.wait(0.5)
        try:
            now = time.monotonic()
            cpu_time = process_tree_cpu_seconds(proc)
            rss = _total_rss(proc)
            cpu = compute_cpu_percent(prev_cpu_time, cpu_time, now - prev_time)
            samples.append((cpu, rss))
            prev_time = now
            prev_cpu_time = cpu_time
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            break


def compute_cpu_percent(prev_cpu_time, cpu_time, dt):
    """Return CPU usage as a percentage from cumulative CPU time deltas."""
    if dt <= 0:
        return 0.0
    return ((cpu_time - prev_cpu_time) / dt) * 100.0


def process_tree_cpu_seconds(proc):
    """Return total CPU seconds for a process tree, stopped children included."""
    total = cumulative_cpu_seconds(proc.cpu_times())
    for child in proc.children(recursive=True):
        try:
            total += cumulative_cpu_seconds(child.cpu_times())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return total


def cumulative_cpu_seconds(times):
    """Return the CPU seconds of a process and of the children it waited for.

    When a child process stops and its parent waits for it, the CPU time of
    the child moves into children_user and children_system of the parent.
    Thus this sum does not decrease when a child process stops. On some
    platforms psutil does not give these fields, so they count as 0.
    """
    children = getattr(times, "children_user", 0.0) + getattr(
        times, "children_system", 0.0
    )
    return times.user + times.system + children


def _total_rss(proc):
    """Return total RSS bytes for a process and its children."""
    rss = proc.memory_info().rss
    for child in proc.children(recursive=True):
        try:
            rss += child.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return rss


def compute_resource_stats(samples):
    """Compute max and mean CPU/RSS from a list of (cpu, rss) samples."""
    if not samples:
        return {"max_cpu": 0.0, "mean_cpu": 0.0, "max_rss": 0, "mean_rss": 0.0}
    cpus = [s[0] for s in samples]
    rsss = [s[1] for s in samples]
    return {
        "max_cpu": max(cpus),
        "mean_cpu": sum(cpus) / len(cpus),
        "max_rss": max(rsss),
        "mean_rss": sum(rsss) / len(rsss),
    }


def format_resource_table(stats):
    """Return a formatted table of resource usage statistics."""
    max_rss = format_bytes(int(stats["max_rss"]))
    mean_rss = format_bytes(int(stats["mean_rss"]))
    max_cpu = f"{stats['max_cpu']:.1f} %"
    mean_cpu = f"{stats['mean_cpu']:.1f} %"
    elapsed = format_duration(stats["elapsed"])
    val_width = max(
        len(max_rss), len(mean_rss), len(max_cpu), len(mean_cpu), len(elapsed), 4
    )
    metric_width = max(len("Metric"), len("CPU Load"), len("Elapsed"), len("RSS"))
    col = val_width + 2

    def row(metric, first, second):
        cells = [
            f"{metric:<{metric_width}}",
            f"{first:>{val_width}}",
            f"{second:>{val_width}}",
        ]
        return "│ " + " │ ".join(cells) + " │"

    def rule(left, middle, right):
        widths = [metric_width + 2, col, col]
        return left + middle.join("─" * width for width in widths) + right

    lines = [
        rule("┌", "┬", "┐"),
        row("Metric", "Max", "Mean"),
        rule("├", "┼", "┤"),
        row("Elapsed", elapsed, ""),
        row("CPU Load", max_cpu, mean_cpu),
        row("RSS", max_rss, mean_rss),
        rule("└", "┴", "┘"),
    ]
    return "\n".join(lines)


TENTHS_PER_MINUTE = 600


def format_duration(seconds):
    """Return a human-readable duration string."""
    tenths = round(seconds * 10)
    if tenths < TENTHS_PER_MINUTE:
        return f"{tenths / 10:.1f}s"
    minutes, tenths = divmod(tenths, TENTHS_PER_MINUTE)
    if minutes < 60:
        return f"{minutes}m {tenths / 10:.1f}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m {tenths / 10:.1f}s"


def format_bytes(n):
    """Return a human-readable byte string."""
    if n < 1024:
        return f"{n} B"
    for unit_name, unit_size in (("KB", 1024), ("MB", 1024**2)):
        shown = round(n / unit_size, 1)
        if shown < 1024:
            return f"{shown:.1f} {unit_name}"
    return f"{n / 1024**3:.1f} GB"
