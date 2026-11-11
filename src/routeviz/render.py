"""Static plots and animations of CVRP solutions (matplotlib).

Figure layout, in the style of a journal figure:
  (a) the routes on the instance's coordinate plane, with travel direction,
      depot (square) and customers (circle area proportional to demand);
  (b) the load of every route as a share of vehicle capacity Q.
"""

from __future__ import annotations

import math
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import matplotlib.ticker as mticker  # noqa: E402
from matplotlib.animation import FuncAnimation, PillowWriter  # noqa: E402
from matplotlib.patches import FancyArrowPatch  # noqa: E402

from .check import CheckReport, check, distance  # noqa: E402
from .io import Instance, Solution  # noqa: E402


@dataclass(frozen=True)
class Theme:
    surface: str
    text: str
    muted: str
    grid: str
    node_fill: str
    alert: str
    palette: tuple[str, ...]


# Eight categorical hues, validated for colour-vision deficiency (adjacent pairs)
# in light and dark mode. Assigned in fixed order.
LIGHT = Theme(
    surface="#ffffff",
    text="#111111",
    muted="#5a5a5a",
    grid="#e8e8e8",
    node_fill="#ffffff",
    alert="#c62828",
    palette=("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"),
)
DARK = Theme(
    surface="#1a1a19",
    text="#f0efec",
    muted="#a9a89f",
    grid="#2e2e2c",
    node_fill="#1a1a19",
    alert="#ff6b6b",
    palette=("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"),
)

ARROW_EDGE_LIMIT = 160  # above this many edges, direction arrows become clutter


@contextmanager
def _paper_style(theme: Theme):
    """Serif typesetting (STIX, ships with matplotlib) and inward ticks on all sides."""
    with plt.rc_context({
        "font.family": "STIXGeneral",
        "mathtext.fontset": "stix",
        "font.size": 10,
        "axes.edgecolor": theme.text,
        "axes.labelcolor": theme.text,
        "axes.linewidth": 0.8,
        "xtick.color": theme.text,
        "ytick.color": theme.text,
        "xtick.direction": "in",
        "ytick.direction": "in",
        "xtick.top": True,
        "ytick.right": True,
        "xtick.major.size": 3.5,
        "ytick.major.size": 3.5,
        "xtick.minor.visible": True,
        "ytick.minor.visible": True,
        "xtick.minor.size": 1.8,
        "ytick.minor.size": 1.8,
        "xtick.labelsize": 8.5,
        "ytick.labelsize": 8.5,
        "text.color": theme.text,
    }):
        yield


def route_colors(instance: Instance, routes: list[list[int]], theme: Theme) -> list[str]:
    """Colour per route.

    Up to eight routes: palette slots in route order, so colour follows the route.
    More routes: palette slots assigned in angular order around the depot (by route
    centroid), so routes adjacent in that order never share a colour. Routes that
    overlap but are not angular neighbours can still coincide; identity is carried
    by position, not by a legend.
    """
    k = len(theme.palette)
    if len(routes) <= k:
        return [theme.palette[i] for i in range(len(routes))]
    dx, dy = instance.coords[0]

    def angle(route: list[int]) -> float:
        if not route:
            return 0.0
        cx = sum(instance.coords[c][0] for c in route) / len(route)
        cy = sum(instance.coords[c][1] for c in route) / len(route)
        return math.atan2(cy - dy, cx - dx)

    order = sorted(range(len(routes)), key=lambda i: angle(routes[i]))
    colors = [""] * len(routes)
    slots = [rank % k for rank in range(len(order))]
    if slots[-1] == slots[0]:  # angular order is circular: last route borders the first
        slots[-1] = next(s for s in range(k) if s not in (slots[0], slots[-2]))
    for i, slot in zip(order, slots):
        colors[i] = theme.palette[slot]
    return colors


# --- building blocks -----------------------------------------------------------

@dataclass
class _Figure:
    fig: object
    ax_map: object
    bars: object | None
    subtitle: object
    report: CheckReport
    colors: list[str]
    routes: list[list[int]]  # valid customer ids only
    theme: Theme


def _fmt_cost(x: float) -> str:
    s = f"{x:,.0f}" if x == int(x) else f"{x:,.2f}"
    return s.replace(",", r"\,")


def _subtitle_text(inst: Instance, report: CheckReport, z: float | None = None) -> str:
    parts = [f"$n = {inst.n_customers}$"]
    if inst.capacity is not None:
        parts.append(f"$Q = {inst.capacity}$")
    parts.append(f"$K = {report.n_routes}$")
    parts.append(f"$z = {_fmt_cost(report.computed_cost if z is None else z)}$")
    return ",    ".join(parts)


def _marker_sizes(inst: Instance) -> list[float]:
    """Circle area proportional to demand; mean area ~ 28 pt^2, floor 5 pt^2."""
    d = inst.demands[1:]
    mean = (sum(d) / len(d)) if d and sum(d) > 0 else 1.0
    base = 28.0 if inst.n_customers <= 150 else 12.0
    return [max(5.0, base * q / mean) for q in d]


def _setup(inst: Instance, sol: Solution, theme: Theme, size: float, panel_b: bool) -> _Figure:
    report = check(inst, sol)
    n = inst.n_customers
    routes = [[c for c in r if 1 <= c <= n] for r in sol.routes]
    colors = route_colors(inst, sol.routes, theme)

    show_b = panel_b and inst.capacity is not None and any(routes)
    width = size * (1.45 if show_b else 1.0)
    fig = plt.figure(figsize=(width, size * 1.1), dpi=110)
    fig.patch.set_facecolor(theme.surface)
    left = 0.085 if show_b else 0.12
    right = 0.97 if show_b else 0.95
    if show_b:
        gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 0.36], wspace=0.1,
                              left=left, right=right, bottom=0.12, top=0.82)
        ax_map, ax_load = fig.add_subplot(gs[0]), fig.add_subplot(gs[1])
    else:
        ax_map, ax_load = fig.add_axes([left, 0.12, right - left, 0.70]), None

    # (a) coordinate plane, square window around the instance
    ax_map.set_facecolor(theme.surface)
    ax_map.set_aspect("equal", adjustable="box")
    xs = [p[0] for p in inst.coords]
    ys = [p[1] for p in inst.coords]
    span = max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    half = span / 2 * 1.08
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    ax_map.set_xlim(cx - half, cx + half)
    ax_map.set_ylim(cy - half, cy + half)
    ax_map.grid(True, color=theme.grid, lw=0.5)
    ax_map.set_axisbelow(True)
    ax_map.set_xlabel("$x$")
    ax_map.set_ylabel("$y$", rotation=0, labelpad=8)

    ax_map.scatter(xs[1:], ys[1:], s=_marker_sizes(inst), c=theme.node_fill,
                   edgecolors=theme.text, linewidths=0.7, zorder=4)
    ax_map.scatter([xs[0]], [ys[0]], s=64, marker="s", c=theme.text,
                   edgecolors=theme.surface, linewidths=1.2, zorder=5)

    # header, flush with the drawn axes (equal aspect shrinks the map box)
    ax_map.apply_aspect()
    left = ax_map.get_position().x0
    if ax_load is not None:
        right = ax_load.get_position().x1
    else:
        right = ax_map.get_position().x1
    fig.text(left, 0.965, inst.name, fontsize=14, fontweight="bold", va="top")
    subtitle = fig.text(left, 0.91, _subtitle_text(inst, report), fontsize=10.5, va="top")
    if report.feasible:
        status, color = "feasible", theme.muted
    else:
        k = len(report.errors)
        status, color = f"infeasible ({k} violation{'s' if k != 1 else ''})", theme.alert
    fig.text(right, 0.965, status, fontsize=10, ha="right", va="top", color=color, style="italic")
    metric = {"nint": "Euclidean, rounded (nint)", "ceil": "Euclidean, rounded up",
              "none": "Euclidean, unrounded"}[report.rounding]
    fig.text(right, 0.91, f"$d_{{ij}}$: {metric}", fontsize=8.5, ha="right", va="top",
             color=theme.muted)

    ax_map.text(0.0, 1.02, "(a)  routes", transform=ax_map.transAxes, fontsize=10, va="bottom")
    ax_map.text(1.0, -0.1, "■ depot    ○ customer, area ∝ demand",
                transform=ax_map.transAxes, ha="right", va="top", fontsize=8, color=theme.muted)

    bars = _setup_load_panel(ax_load, inst, routes, colors, theme) if ax_load is not None else None
    return _Figure(fig, ax_map, bars, subtitle, report, colors, routes, theme)


def _setup_load_panel(ax, inst: Instance, routes, colors, theme: Theme):
    k = len(routes)
    loads = [sum(inst.demands[c] for c in r) / inst.capacity for r in routes]
    ax.set_facecolor(theme.surface)
    ax.set_xlim(0, max(1.1, max(loads) * 1.05))
    ax.set_ylim(k - 0.5, -0.5)
    ax.axvline(1.0, color=theme.text, lw=0.8, ls=(0, (4, 3)), zorder=3)
    ax.grid(True, axis="x", color=theme.grid, lw=0.5)
    ax.set_axisbelow(True)
    ax.set_xlabel(r"$q_k \,/\, Q$")
    ax.set_xticks([0, 0.5, 1.0])
    ax.xaxis.set_major_formatter(mticker.PercentFormatter(1.0, decimals=0))
    ax.yaxis.set_minor_locator(mticker.NullLocator())
    step = 1 if k <= 16 else math.ceil(k / 16)
    ax.set_yticks(range(0, k, step))
    ax.set_yticklabels([str(i + 1) for i in range(0, k, step)], fontsize=8)
    ax.set_ylabel("route $k$", fontsize=9)
    ax.tick_params(axis="y", which="both", right=False)
    ax.text(0.0, 1.02, "(b)  load", transform=ax.transAxes, fontsize=10, va="bottom")
    total = sum(inst.demands[1:])
    ax.text(1.0, -0.1, rf"$\bar{{u}} = {100 * total / (k * inst.capacity):.1f}\,\%$",
            transform=ax.transAxes, ha="right", va="top", fontsize=8.5, color=theme.muted)
    height = 0.45 if k <= 8 else (0.66 if k <= 30 else 0.85)
    return ax.barh(range(k), [0] * k, height=height, color=colors, zorder=2)


def _add_edge(f: _Figure, a, b, color, arrows: bool) -> None:
    f.ax_map.plot([a[0], b[0]], [a[1], b[1]], color=color, lw=1.4,
                  solid_capstyle="round", zorder=2)
    if arrows and math.dist(a, b) > 0:
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        tip = (mid[0] + (b[0] - a[0]) * 0.02, mid[1] + (b[1] - a[1]) * 0.02)
        f.ax_map.add_patch(FancyArrowPatch(mid, tip, arrowstyle="-|>", mutation_scale=8,
                                           color=color, lw=0, zorder=3))


def _edges(f: _Figure, inst: Instance):
    out = []
    for k, (route, color) in enumerate(zip(f.routes, f.colors)):
        if not route:
            continue
        path = [0, *route, 0]
        for i, j in zip(path, path[1:]):
            out.append((k, j, inst.coords[i], inst.coords[j], color))
    return out


def _labels(f: _Figure, inst: Instance) -> None:
    for i, (x, y) in enumerate(inst.coords[1:], start=1):
        f.ax_map.annotate(str(i), (x, y), xytext=(3.5, 3.5), textcoords="offset points",
                          fontsize=7, color=f.theme.muted, zorder=6)


# --- public API ----------------------------------------------------------------

def plot(instance: Instance, solution: Solution, out: str | Path, *, dark: bool = False,
         labels: bool = False, size: float = 5.5, panel_b: bool = True) -> Path:
    theme = DARK if dark else LIGHT
    with _paper_style(theme):
        f = _setup(instance, solution, theme, size, panel_b)
        edges = _edges(f, instance)
        arrows = len(edges) <= ARROW_EDGE_LIMIT
        for _, _, a, b, color in edges:
            _add_edge(f, a, b, color, arrows)
        if labels:
            _labels(f, instance)
        if f.bars is not None:
            for bar, route in zip(f.bars, f.routes):
                bar.set_width(sum(instance.demands[c] for c in route) / instance.capacity)
        out = Path(out)
        f.fig.savefig(out, facecolor=theme.surface)
        plt.close(f.fig)
    return out


def animate(instance: Instance, solution: Solution, out: str | Path, *, dark: bool = False,
            labels: bool = False, size: float = 5.0, fps: int = 12, max_frames: int = 240,
            hold_seconds: float = 2.5, panel_b: bool = True) -> Path:
    """Draw the routes edge by edge; z and the load bars update as the tours grow."""
    theme = DARK if dark else LIGHT
    with _paper_style(theme):
        f = _setup(instance, solution, theme, size, panel_b)
        if labels:
            _labels(f, instance)
        edges = _edges(f, instance)
        arrows = len(edges) <= ARROW_EDGE_LIMIT
        per_frame = max(1, math.ceil(len(edges) / max_frames))
        n_draw = math.ceil(len(edges) / per_frame)
        hold = max(1, int(round(hold_seconds * fps)))
        state = {"z": 0.0, "load": [0] * len(f.routes)}
        f.subtitle.set_text(_subtitle_text(instance, f.report, 0.0))

        done: set[int] = set()

        def update(frame: int):
            # FuncAnimation calls the first frame twice (as init); draw each frame once
            if frame >= n_draw or frame in done:
                return []
            done.add(frame)
            for k, j, a, b, color in edges[frame * per_frame:(frame + 1) * per_frame]:
                _add_edge(f, a, b, color, arrows)
                state["z"] += distance(a, b, f.report.rounding)
                if j != 0:
                    state["load"][k] += instance.demands[j]
                    if f.bars is not None:
                        f.bars[k].set_width(state["load"][k] / instance.capacity)
            z = f.report.computed_cost if frame == n_draw - 1 else state["z"]
            f.subtitle.set_text(_subtitle_text(instance, f.report, z))
            return []

        anim = FuncAnimation(f.fig, update, frames=n_draw + hold, blit=False, repeat=False)
        out = Path(out)
        anim.save(out, writer=PillowWriter(fps=fps), savefig_kwargs={"facecolor": theme.surface})
        plt.close(f.fig)
    return out
