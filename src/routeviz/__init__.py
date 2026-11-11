"""routeviz: plot, animate and verify vehicle routing solutions."""

__version__ = "0.1.0"

from .check import CheckReport, check  # noqa: E402
from .io import Instance, ParseError, Solution, load_instance, load_solution, parse_instance, parse_solution  # noqa: E402

__all__ = [
    "CheckReport",
    "Instance",
    "ParseError",
    "Solution",
    "check",
    "load_instance",
    "load_solution",
    "parse_instance",
    "parse_solution",
]
