"""Sample server CPU and RAM once a second during a load test.

Process groups:

* ``app``    — the uvicorn master and ALL its descendants (the workers are
               started via multiprocessing and don't have "uvicorn" in
               their command line, so they are found as children);
* ``db``     — every postgres process;
* ``locust`` — the load generator itself. When it runs on the same
               machine it competes for the same CPU, so it is recorded too.

CPU is in percent of ONE core (200 % = two cores fully busy), like `top`.
Memory is summed as PSS where the OS provides it (Linux), so memory shared
between postgres processes is not counted many times; otherwise RSS.

    python -m loadtest.monitor --out loadtest/results/baseline_resources.csv \
        --duration 250
"""

import argparse
import csv
import time

import psutil

GROUPS = ("app", "db", "locust")
FIELDS = ["timestamp"]
for _g in GROUPS:
    FIELDS += [f"{_g}_cpu", f"{_g}_mem_mb"]
FIELDS += ["system_cpu", "system_mem_used_mb"]


def _discover() -> dict[int, tuple[str, psutil.Process]]:
    """Find tracked processes. Processes may exit at any moment (postgres
    forks a backend per connection), so every psutil call is guarded."""
    found: dict[int, tuple[str, psutil.Process]] = {}
    for proc in psutil.process_iter():
        try:
            name = proc.name()
            cmd = " ".join(proc.cmdline())
            is_python = "python" in name or "uvicorn" in name
            if is_python and "uvicorn" in cmd and "app.main" in cmd:
                found[proc.pid] = ("app", proc)
                for child in proc.children(recursive=True):
                    found[child.pid] = ("app", child)
            elif name.startswith("postgres"):
                found.setdefault(proc.pid, ("db", proc))
            elif "locust" in name or (is_python and "locust" in cmd):
                found.setdefault(proc.pid, ("locust", proc))
        except psutil.Error:
            continue
    return found


def _memory_mb(proc: psutil.Process) -> float:
    try:
        info = proc.memory_full_info()
        return getattr(info, "pss", info.rss) / 2**20
    except psutil.AccessDenied:
        return proc.memory_info().rss / 2**20


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--duration", type=float, default=600)
    parser.add_argument("--interval", type=float, default=1.0)
    args = parser.parse_args(argv)

    tracked: dict[int, tuple[str, psutil.Process]] = {}
    psutil.cpu_percent(None)
    started = time.time()
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        try:
            while time.time() - started < args.duration:
                for pid, (group, proc) in _discover().items():
                    if pid not in tracked:
                        try:
                            proc.cpu_percent(None)  # prime the counter
                        except psutil.Error:
                            continue
                        tracked[pid] = (group, proc)
                time.sleep(args.interval)
                row: dict[str, float] = dict.fromkeys(FIELDS[1:-2], 0.0)
                for pid, (group, proc) in list(tracked.items()):
                    try:
                        row[f"{group}_cpu"] += proc.cpu_percent(None)
                        row[f"{group}_mem_mb"] += _memory_mb(proc)
                    except psutil.Error:
                        tracked.pop(pid, None)
                vm = psutil.virtual_memory()
                row["system_cpu"] = psutil.cpu_percent(None) * psutil.cpu_count()
                row["system_mem_used_mb"] = (vm.total - vm.available) / 2**20
                out = {k: round(v, 1) for k, v in row.items()}
                out["timestamp"] = round(time.time(), 1)
                writer.writerow(out)
                f.flush()
        except KeyboardInterrupt:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
