"""Monitor subprocess resource usage (CPU and RSS)."""

import subprocess
import time
import threading

import psutil


def monitor_subprocess(cmd):
    """Run cmd and sample CPU/RSS for the process tree, return (returncode, samples, elapsed)."""
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
        proc.cpu_percent()
        for child in proc.children(recursive=True):
            child.cpu_percent()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return
    while not stop_event.is_set():
        stop_event.wait(0.5)
        try:
            cpu, rss = _sample_process_tree(proc)
            samples.append((cpu, rss))
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            break


def _sample_process_tree(proc):
    """Return (total_cpu_percent, total_rss_bytes) for a process and its children."""
    cpu = proc.cpu_percent()
    rss = proc.memory_info().rss
    for child in proc.children(recursive=True):
        try:
            cpu += child.cpu_percent()
            rss += child.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return cpu, rss


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
    header_metric = "Metric"
    header_max = "Max".rjust(val_width)
    header_mean = "Mean".rjust(val_width)
    metric_width = max(len(header_metric), len("CPU Load"), len("Elapsed"), len("RSS"))
    col = val_width + 2
    sep = f"├{'─' * (metric_width + 2)}┼{'─' * col}┼{'─' * col}┤"
    top = f"┌{'─' * (metric_width + 2)}┬{'─' * col}┬{'─' * col}┐"
    bot = f"└{'─' * (metric_width + 2)}┴{'─' * col}┴{'─' * col}┘"
    blank = " " * val_width
    lines = [
        top,
        f"│ {header_metric:<{metric_width}} │ {header_max} │ {header_mean} │",
        sep,
        f"│ {'Elapsed':<{metric_width}} │ {elapsed:>{val_width}} │ {blank} │",
        f"│ {'CPU Load':<{metric_width}} │ {max_cpu:>{val_width}} │ {mean_cpu:>{val_width}} │",
        f"│ {'RSS':<{metric_width}} │ {max_rss:>{val_width}} │ {mean_rss:>{val_width}} │",
        bot,
    ]
    return "\n".join(lines)


def format_duration(seconds):
    """Return a human-readable duration string."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{int(minutes)}m {secs:.1f}s"
    hours, minutes = divmod(int(minutes), 60)
    return f"{hours}h {int(minutes)}m {secs:.1f}s"


def format_bytes(n):
    """Return a human-readable byte string."""
    if n >= 1024 * 1024 * 1024:
        return f"{n / (1024 * 1024 * 1024):.1f} GB"
    if n >= 1024 * 1024:
        return f"{n / (1024 * 1024):.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n} B"
