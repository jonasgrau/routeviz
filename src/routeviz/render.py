"""Static plots and animations of CVRP solutions (matplotlib)."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.animation import FuncAnimation, PillowWriter  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402

from .check import check  # noqa: E402
from .io import Instance, Solution  # noqa: E402


@dataclass(frozen=True)
class Theme:
    surface: str
    text: str
    muted: str
    node_fill: str
    palette: tuple[str, ...]


# Eight categorical hues, validated for colour-vision deficiency (adjacent pairs)
# in light and dark mode. Assigned in fixed order.
LIGHT = Theme(
    surface="#fcfcfb",
    text="#0b0b0b",
    muted="#52514e",
    node_fill="#fcfcfb",
    palette=("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"),
)
DARK = Theme(
    surface="#1a1a19",
    text="#f0efec",
    muted="#c3c2b7",
    node_fill="#1a1a19",
    palette=("#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"),
)


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


def _segments(instance: Instance, route: list[int]) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    path = [0, *route, 0]
    c = instance.coords
    return [(c[i], c[j]) for i, j in zip(path, path[1:])]


def _setup_axes(instance: Instance, theme: Theme, size: float):
    fig, ax = plt.subplots(figsize=(size, size), dpi=100)
    fig.patch.set_facecolor(theme.surface)
    ax.set_facecolor(theme.surface)
    ax.set_aspect("equal")
    ax.axis("off")
    xs = [p[0] for p in instance.coords]
    ys = [p[1] for p in instance.coords]
    pad = 0.04 * max(max(xs) - min(xs), max(ys) - min(ys), 1.0)
    ax.set_xlim(min(xs) - pad, max(xs) + pad)
    ax.set_ylim(min(ys) - pad, max(ys) + pad)
    return fig, ax


def _marker_size(n: int) -> float:
    # markers stay >= ~5 pt across; shrink gently for large instances
    return max(25.0, 70.0 - 0.05 * n)


def _draw_nodes(ax, instance: Instance, theme: Theme, labels: bool) -> None:
    n = instance.n_customers
    cx = [p[0] for p in instance.coords[1:]]
    cy = [p[1] for p in instance.coords[1:]]
    ax.scatter(cx, cy, s=_marker_size(n), c=theme.node_fill, edgecolors=theme.muted,
               linewidths=1.2, zorder=3)
    dx, dy = instance.coords[0]
    ax.scatter([dx], [dy], s=_marker_size(n) * 2.2, marker="s", c=theme.text,
               edgecolors=theme.surface, linewidths=2, zorder=4)
    if labels:
        for i, (x, y) in enumerate(instance.coords[1:], start=1):
            ax.annotate(str(i), (x, y), xytext=(4, 4), textcoords="offset points",
                        fontsize=7, color=theme.muted, zorder=5)


def _title(ax, instance: Instance, solution: Solution, theme: Theme) -> None:
    report = check(instance, solution)
    cost = report.computed_cost
    cost_s = f"{cost:,.0f}" if cost == int(cost) else f"{cost:,.2f}"
    status = "feasible" if report.feasible else "INFEASIBLE"
    ax.set_title(f"{instance.name}", loc="left", fontsize=13, color=theme.text,
                 fontweight="bold", pad=22)
    ax.text(0, 1.012, f"{report.n_routes} routes · cost {cost_s} · {status}",
            transform=ax.transAxes, fontsize=9.5, color=theme.muted, va="bottom")


def _legend(ax, colors: list[str], theme: Theme) -> None:
    if len(colors) > 8:
        return
    handles = [Line2D([0], [0], color=c, lw=2.5) for c in colors]
    leg = ax.legend(handles, [f"Route {i}" for i in range(1, len(colors) + 1)],
                    loc="upper left", bbox_to_anchor=(1.0, 1.0), frameon=False,
                    fontsize=8.5, labelcolor=theme.text, handlelength=1.6)
    leg.set_zorder(6)


def plot(instance: Instance, solution: Solution, out: str | Path, *, dark: bool = False,
         labels: bool = False, size: float = 7.0) -> Path:
    theme = DARK if dark else LIGHT
    fig, ax = _setup_axes(instance, theme, size)
    colors = route_colors(instance, solution.routes, theme)
    for route, color in zip(solution.routes, colors):
        valid = [c for c in route if 1 <= c <= instance.n_customers]
        if not valid:
            continue
        path = [instance.coords[i] for i in [0, *valid, 0]]
        ax.plot([p[0] for p in path], [p[1] for p in path], color=color, lw=2,
                solid_capstyle="round", solid_joinstyle="round", zorder=2)
    _draw_nodes(ax, instance, theme, labels)
    _title(ax, instance, solution, theme)
    _legend(ax, colors, theme)
    out = Path(out)
    fig.savefig(out, facecolor=theme.surface, bbox_inches="tight")
    plt.close(fig)
    return out


def animate(instance: Instance, solution: Solution, out: str | Path, *, dark: bool = False,
            labels: bool = False, size: float = 6.0, fps: int = 12, max_frames: int = 240,
            hold_seconds: float = 2.0) -> Path:
    """Draw the routes edge by edge, route after route, and save as GIF."""
    theme = DARK if dark else LIGHT
    fig, ax = _setup_axes(instance, theme, size)
    colors = route_colors(instance, solution.routes, theme)
    edges: list[tuple[tuple[float, float], tuple[float, float], str]] = []
    for route, color in zip(solution.routes, colors):
        valid = [c for c in route if 1 <= c <= instance.n_customers]
        if valid:
            edges.extend((a, b, color) for a, b in _segments(instance, valid))

    _draw_nodes(ax, instance, theme, labels)
    _title(ax, instance, solution, theme)
    _legend(ax, colors, theme)

    per_frame = max(1, math.ceil(len(edges) / max_frames))
    n_draw = math.ceil(len(edges) / per_frame)
    hold = max(1, int(round(hold_seconds * fps)))

    def update(frame: int):
        artists = []
        if frame < n_draw:
            for a, b, color in edges[frame * per_frame:(frame + 1) * per_frame]:
                (line,) = ax.plot([a[0], b[0]], [a[1], b[1]], color=color, lw=2,
                                  solid_capstyle="round", zorder=2)
                artists.append(line)
        return artists

    anim = FuncAnimation(fig, update, frames=n_draw + hold, blit=False, repeat=False)
    out = Path(out)
    fig.tight_layout()
    anim.save(out, writer=PillowWriter(fps=fps), savefig_kwargs={"facecolor": theme.surface})
    plt.close(fig)
    return out
