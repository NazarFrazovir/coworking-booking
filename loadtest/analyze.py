"""Turn Locust CSVs + resource samples into report tables and charts.

    python -m loadtest.analyze            # reads/writes loadtest/results/

Produces:
* ``summary.md``            — tables used in docs/lab4-load-testing.md
* ``baseline_timeline.png`` — users, RPS, latency over the baseline run
* ``stress_timeline.png``   — users, RPS, errors, latency, CPU (stress run)
* ``stress_stages.png``     — p95 latency and error rate per load stage
* ``baseline_endpoints.png``— average vs p95 latency per endpoint
"""

import csv
import statistics
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

RESULTS = Path(__file__).parent / "results"

# Categorical slots (fixed order) + reserved "critical" status color.
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
RED = "#e34948"
INK, INK_2, GRID = "#1d2330", "#5f6a64", "#e3e6eb"

plt.rcParams.update(
    {
        "font.family": "DejaVu Sans",
        "font.size": 10,
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK_2,
        "axes.titlecolor": INK,
        "axes.titlesize": 11,
        "axes.titleweight": "bold",
        "axes.titlelocation": "left",
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "xtick.color": INK_2,
        "ytick.color": INK_2,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "lines.linewidth": 2,
    }
)


# ---------------------------------------------------------------- loading


def _num(value: str) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class Tick:
    t: float  # seconds since start
    users: int
    rps: float
    fps: float
    p50: float | None
    p95: float | None
    total: int
    failures: int


def load_history(name: str) -> list[Tick]:
    rows = list(csv.DictReader(open(RESULTS / f"{name}_stats_history.csv")))
    rows = [r for r in rows if r["Name"] == "Aggregated"]
    t0 = float(rows[0]["Timestamp"])
    return [
        Tick(
            t=float(r["Timestamp"]) - t0,
            users=int(r["User Count"]),
            rps=float(r["Requests/s"]),
            fps=float(r["Failures/s"]),
            p50=_num(r["50%"]),
            p95=_num(r["95%"]),
            total=int(r["Total Request Count"]),
            failures=int(r["Total Failure Count"]),
        )
        for r in rows
    ]


def load_resources(name: str, t0: float) -> list[dict[str, float]]:
    out = []
    for r in csv.DictReader(open(RESULTS / f"{name}_resources.csv")):
        row = {k: float(v) for k, v in r.items()}
        row["t"] = row["timestamp"] - t0
        # Load generator and OS share the same 2 vCPU machine.
        row["other_cpu"] = max(row["system_cpu"] - row["app_cpu"] - row["db_cpu"], 0)
        out.append(row)
    return out


def load_endpoints(name: str) -> list[dict[str, str]]:
    return list(csv.DictReader(open(RESULTS / f"{name}_stats.csv")))


def history_t0(name: str) -> float:
    rows = csv.DictReader(open(RESULTS / f"{name}_stats_history.csv"))
    return float(next(rows)["Timestamp"])


# ---------------------------------------------------------------- tables


def ms(value: str | float) -> str:
    v = float(value)
    if v >= 1000:
        return f"{v / 1000:.1f} с"
    return f"{v:.0f} мс" if v >= 10 else f"{v:.1f} мс"


def endpoint_table(name: str) -> str:
    rows = load_endpoints(name)
    lines = [
        "| Ендпоінт | Запитів | RPS | Avg | Min | Max | p95 | Помилки |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    rows.sort(key=lambda r: (r["Name"] == "Aggregated", -int(r["Request Count"])))
    for r in rows:
        n, f = int(r["Request Count"]), int(r["Failure Count"])
        label = "**Усього**" if r["Name"] == "Aggregated" else f"`{r['Name']}`"
        lines.append(
            f"| {label} | {n} | {float(r['Requests/s']):.1f} | "
            f"{ms(r['Average Response Time'])} | {ms(r['Min Response Time'])} | "
            f"{ms(r['Max Response Time'])} | {ms(r['95%'])} | "
            f"{f / n * 100 if n else 0:.2f}% |"
        )
    return "\n".join(lines)


@dataclass
class Stage:
    users: int
    rps: float
    p50: float
    p95: float
    p95_peak: float
    err: float
    app_cpu: float
    db_cpu: float
    other_cpu: float
    app_mem: float


def stages(name: str, settle: float = 10) -> list[Stage]:
    """Steady part of each load level (drop the first `settle` s)."""
    hist = load_history(name)
    res = load_resources(name, history_t0(name))
    levels = sorted({h.users for h in hist if h.users and h.users % 50 == 0})
    out = []
    for level in levels:
        ticks = [h for h in hist if h.users == level]
        start = ticks[0].t + settle
        steady = [h for h in ticks if h.t >= start] or ticks
        end = steady[-1].t
        requests = steady[-1].total - steady[0].total
        failures = steady[-1].failures - steady[0].failures
        rs = [r for r in res if start <= r["t"] <= end]
        out.append(
            Stage(
                users=level,
                rps=statistics.mean(h.rps for h in steady),
                p50=statistics.median(h.p50 for h in steady if h.p50 is not None),
                p95=statistics.median(h.p95 for h in steady if h.p95 is not None),
                p95_peak=max(h.p95 for h in steady if h.p95 is not None),
                err=failures / requests * 100 if requests else 0,
                app_cpu=statistics.mean(r["app_cpu"] for r in rs),
                db_cpu=statistics.mean(r["db_cpu"] for r in rs),
                other_cpu=statistics.mean(r["other_cpu"] for r in rs),
                app_mem=max(r["app_mem_mb"] for r in rs),
            )
        )
    return out


def stage_table(items: list[Stage]) -> str:
    lines = [
        "| VUsers | RPS | p50 | p95 (типово) | p95 (пік) | Помилки "
        "| CPU застосунку | CPU БД | CPU інше (Locust, ОС) | RAM застосунку |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s in items:
        lines.append(
            f"| {s.users} | {s.rps:.1f} | {ms(s.p50)} | {ms(s.p95)} | "
            f"{ms(s.p95_peak)} | "
            f"{s.err:.2f}% | {s.app_cpu:.0f}% | {s.db_cpu:.0f}% | "
            f"{s.other_cpu:.0f}% | {s.app_mem:.0f} MB |"
        )
    return "\n".join(lines)


def resource_summary(name: str) -> str:
    res = load_resources(name, history_t0(name))
    busy = [r for r in res if r["app_cpu"] > 5] or res

    def avg_max(key: str) -> str:
        values = [r[key] for r in busy]
        return f"{statistics.mean(values):.0f} / {max(values):.0f}"

    return (
        "| Ресурс | Середнє / пік |\n|---|---:|\n"
        f"| CPU застосунку (2 воркери uvicorn), % ядра | {avg_max('app_cpu')} |\n"
        f"| CPU PostgreSQL, % ядра | {avg_max('db_cpu')} |\n"
        f"| CPU інше (Locust, ОС), % ядра | {avg_max('other_cpu')} |\n"
        f"| CPU усієї машини (2 vCPU = 200%), % | {avg_max('system_cpu')} |\n"
        f"| RAM застосунку, MB | {avg_max('app_mem_mb')} |\n"
        f"| RAM PostgreSQL, MB | {avg_max('db_mem_mb')} |\n"
        f"| RAM усієї машини (з 8 GB), MB | {avg_max('system_mem_used_mb')} |"
    )


# ---------------------------------------------------------------- charts


def _ms_axis(ax) -> None:
    ax.set_yscale("log")
    ax.yaxis.set_major_formatter(
        FuncFormatter(lambda v, _: f"{v / 1000:g} с" if v >= 1000 else f"{v:g} мс")
    )


def _stage_bands(ax, hist: list[Tick]) -> None:
    """Light vertical guides where a new load level starts."""
    prev = 0
    for h in hist:
        if h.users and h.users % 50 == 0 and h.users != prev:
            ax.axvline(h.t, color=GRID, linewidth=1, zorder=0)
            prev = h.users


def chart_timeline(name: str, title: str, with_cpu: bool) -> Path:
    hist = load_history(name)
    t = [h.t for h in hist]
    panels = 4 if with_cpu else 3
    fig, axes = plt.subplots(
        panels, 1, figsize=(10, 2.3 * panels + 0.6), sharex=True,
        gridspec_kw={"hspace": 0.45},
    )  # fmt: skip
    fig.suptitle(title, x=0.06, ha="left", fontsize=13, fontweight="bold", color=INK)

    ax = axes[0]
    ax.plot(t, [h.users for h in hist], color=BLUE)
    ax.set_title("Віртуальні користувачі (VUsers)")
    ax.set_ylim(bottom=0)

    ax = axes[1]
    ax.plot(t, [h.rps for h in hist], color=BLUE, label="Запити/с (RPS)")
    ax.plot(t, [h.fps for h in hist], color=RED, label="Помилки/с")
    ax.set_title("Пропускна здатність")
    ax.set_ylim(bottom=0)
    ax.legend(loc="lower right", bbox_to_anchor=(1, 1.0), ncols=2, fontsize=9)

    ax = axes[2]
    p50 = [(h.t, h.p50) for h in hist if h.p50]
    p95 = [(h.t, h.p95) for h in hist if h.p95]
    ax.plot(*zip(*p50, strict=True), color=BLUE, label="Медіана (p50)")
    ax.plot(*zip(*p95, strict=True), color=ORANGE, label="95-й перцентиль (p95)")
    _ms_axis(ax)
    ax.set_title("Час відповіді (логарифмічна шкала)")
    ax.legend(loc="lower right", bbox_to_anchor=(1, 1.0), ncols=2, fontsize=9)

    if with_cpu:
        res = load_resources(name, history_t0(name))
        ax = axes[3]
        rt = [r["t"] for r in res]
        ax.plot(rt, [r["app_cpu"] for r in res], color=BLUE, label="Застосунок")
        ax.plot(rt, [r["other_cpu"] for r in res], color=ORANGE,
                label="Інше (Locust, ОС)")  # fmt: skip
        ax.plot(rt, [r["db_cpu"] for r in res], color=AQUA, label="PostgreSQL")
        ax.axhline(200, color=INK_2, linewidth=1, linestyle="--")
        ax.text(2, 192, "межа 2 vCPU", ha="left", va="top",
                color=INK_2, fontsize=9)  # fmt: skip
        ax.set_title("CPU, % одного ядра")
        ax.set_ylim(0, 230)
        ax.legend(loc="lower right", bbox_to_anchor=(1, 1.0), ncols=3, fontsize=9)

    for ax in axes:
        if name == "stress":
            _stage_bands(ax, hist)
    axes[-1].set_xlabel("Час від початку тесту, с")
    out = RESULTS / f"{name}_timeline.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def chart_stages(items: list[Stage]) -> Path:
    labels = [str(s.users) for s in items]
    fig, (a1, a2, a3) = plt.subplots(1, 3, figsize=(12, 4.0),
                                     gridspec_kw={"wspace": 0.35})  # fmt: skip
    fig.suptitle(
        "Стрес-тест: показники на кожному рівні навантаження",
        x=0.06, ha="left", fontsize=13, fontweight="bold", color=INK,
    )  # fmt: skip

    bars = a1.bar(labels, [s.rps for s in items], color=BLUE, width=0.6)
    a1.bar_label(bars, fmt="%.0f", color=INK, fontsize=9, padding=2)
    a1.set_title("RPS")

    bars = a2.bar(labels, [s.p95_peak for s in items], color=ORANGE, width=0.6)
    a2.bar_label(bars, labels=[ms(s.p95_peak) for s in items], color=INK,
                 fontsize=9, padding=2)  # fmt: skip
    a2.set_title("Пікове p95 (найгірші 10 с)")
    a2.set_yscale("log")
    a2.yaxis.set_major_formatter(
        FuncFormatter(lambda v, _: f"{v / 1000:g} с" if v >= 1000 else f"{v:g} мс")
    )

    bars = a3.bar(labels, [s.err for s in items], color=RED, width=0.6)
    a3.bar_label(bars, fmt="%.1f%%", color=INK, fontsize=9, padding=2)
    a3.set_title("Відсоток помилок")

    for ax in (a1, a2, a3):
        ax.set_xlabel("VUsers")
        ax.grid(axis="x", visible=False)
        ax.margins(y=0.18)
    fig.subplots_adjust(top=0.78)
    out = RESULTS / "stress_stages.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def chart_endpoints(name: str) -> Path:
    rows = [r for r in load_endpoints(name) if r["Name"] != "Aggregated"]
    rows.sort(key=lambda r: float(r["95%"]))
    labels = [r["Name"] for r in rows]
    avg = [float(r["Average Response Time"]) for r in rows]
    p95 = [float(r["95%"]) for r in rows]
    y = range(len(rows))
    fig, ax = plt.subplots(figsize=(10, 4.2))
    ax.barh([i + 0.2 for i in y], p95, height=0.38, color=ORANGE, label="p95")
    ax.barh([i - 0.2 for i in y], avg, height=0.38, color=BLUE, label="Середнє")
    for i, p in enumerate(p95):
        ax.text(p * 1.08, i + 0.2, ms(p), va="center", fontsize=8.5, color=INK)
    ax.set_yticks(list(y), labels, fontsize=9)
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(
        FuncFormatter(lambda v, _: f"{v / 1000:g} с" if v >= 1000 else f"{v:g} мс")
    )
    ax.grid(axis="y", visible=False)
    ax.set_title("Baseline (50 VUsers): час відповіді за ендпоінтами")
    ax.legend(loc="lower right", bbox_to_anchor=(1, 1.0), ncols=2, fontsize=9)
    ax.set_xlim(right=max(p95) * 3)
    out = RESULTS / "baseline_endpoints.png"
    fig.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return out


def main() -> int:
    stress_stages = stages("stress")
    paths = [
        chart_timeline("baseline", "Baseline: 50 VUsers, розгін 60 с, 4 хв", False),
        chart_timeline("stress", "Стрес-тест: +50 VUsers щохвилини, 50 → 300", True),
        chart_stages(stress_stages),
        chart_endpoints("baseline"),
    ]
    summary = [
        "## Baseline — метрики за ендпоінтами\n",
        endpoint_table("baseline"),
        "\n\n## Baseline — ресурси сервера\n",
        resource_summary("baseline"),
        "\n\n## Стрес-тест — за рівнями навантаження\n",
        stage_table(stress_stages),
        "\n\n## Стрес-тест — метрики за ендпоінтами\n",
        endpoint_table("stress"),
        "\n\n## Стрес-тест — ресурси сервера\n",
        resource_summary("stress"),
        "\n",
    ]
    (RESULTS / "summary.md").write_text("\n".join(summary))
    for p in paths:
        print("wrote", p.relative_to(RESULTS.parent.parent))
    print("wrote loadtest/results/summary.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
