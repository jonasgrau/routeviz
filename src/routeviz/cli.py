"""Command-line interface: routeviz plot | animate | check."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .check import check
from .io import ParseError, load_instance, load_solution

ROUNDING_CHOICES = ("auto", "nint", "ceil", "none")


def _positive_int(value: str) -> int:
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {n}")
    return n


def _add_inputs(p: argparse.ArgumentParser) -> None:
    p.add_argument("instance", help="CVRPLIB instance file (.vrp)")
    p.add_argument("solution", help="CVRPLIB solution file (.sol)")


def _add_style(p: argparse.ArgumentParser) -> None:
    p.add_argument("--dark", action="store_true", help="dark theme")
    p.add_argument("--labels", action="store_true", help="show customer ids")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="routeviz",
        description="Plot, animate and verify vehicle routing (CVRP) solutions.",
    )
    parser.add_argument("--version", action="version", version=f"routeviz {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("plot", help="static image (.svg, .png, .pdf)")
    _add_inputs(p)
    p.add_argument("-o", "--out", help="output file (default: <solution>.svg)")
    p.add_argument("--size", type=float, default=5.5, help="figure height in inches (default 5.5)")
    p.add_argument("--no-load-panel", action="store_true", help="omit panel (b), the capacity utilisation")
    _add_style(p)

    a = sub.add_parser("animate", help="animated GIF, routes drawn edge by edge")
    _add_inputs(a)
    a.add_argument("-o", "--out", help="output file (default: <solution>.gif)")
    a.add_argument("--fps", type=_positive_int, default=12)
    a.add_argument("--max-frames", type=_positive_int, default=240,
                   help="cap on drawing frames; edges are batched for large instances")
    a.add_argument("--size", type=float, default=5.0)
    a.add_argument("--no-load-panel", action="store_true", help="omit panel (b)")
    _add_style(a)

    c = sub.add_parser("check", help="verify feasibility and recompute the cost")
    _add_inputs(c)
    c.add_argument("--rounding", choices=ROUNDING_CHOICES, default="auto",
                   help="distance rounding; auto follows EDGE_WEIGHT_TYPE (EUC_2D -> nint)")
    c.add_argument("--max-vehicles", type=_positive_int, help="fail if more vehicles are used")
    c.add_argument("--json", action="store_true", help="machine-readable output")
    return parser


def _default_out(solution: str, suffix: str) -> Path:
    return Path(solution).with_suffix(suffix)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        instance = load_instance(args.instance)
        solution = load_solution(args.solution)
    except (OSError, ParseError) as exc:
        print(f"routeviz: error: {exc}", file=sys.stderr)
        return 2

    if args.command == "check":
        rounding = None if args.rounding == "auto" else args.rounding
        report = check(instance, solution, rounding=rounding, max_vehicles=args.max_vehicles)
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            _print_report(report)
        return 0 if report.ok else 1

    from . import render  # imported lazily: matplotlib is slow to import

    if args.command == "plot":
        out = Path(args.out) if args.out else _default_out(args.solution, ".svg")
        render.plot(instance, solution, out, dark=args.dark, labels=args.labels, size=args.size,
                    panel_b=not args.no_load_panel)
    else:
        out = Path(args.out) if args.out else _default_out(args.solution, ".gif")
        render.animate(instance, solution, out, dark=args.dark, labels=args.labels,
                       size=args.size, fps=args.fps, max_frames=args.max_frames,
                       panel_b=not args.no_load_panel)
    print(out)
    return 0


def _fmt_cost(x: float) -> str:
    return f"{x:,.0f}" if x == int(x) else f"{x:,.3f}"


def _print_report(r) -> None:
    print(f"{r.instance}: {r.n_customers} customers, {r.n_routes} routes, "
          f"capacity {r.capacity}, rounding {r.rounding}"
          + (" (auto-detected from stated cost)" if r.rounding_detected else ""))
    for rr in r.routes:
        cap = f"/{r.capacity}" if r.capacity is not None else ""
        print(f"  route {rr.index:>3}: {rr.customers:>4} customers  load {rr.load}{cap}"
              f"  cost {_fmt_cost(rr.cost)}")
    print(f"computed cost: {_fmt_cost(r.computed_cost)}")
    if r.stated_cost is not None:
        mark = "matches" if r.cost_matches else "MISMATCH"
        print(f"stated cost:   {_fmt_cost(r.stated_cost)} ({mark})")
    for e in r.errors:
        print(f"error: {e}")
    print("OK" if r.ok else "FAILED")


if __name__ == "__main__":
    raise SystemExit(main())
