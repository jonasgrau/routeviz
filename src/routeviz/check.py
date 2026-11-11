"""Feasibility and cost checks for CVRP solutions."""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass, field

from .io import Instance, Solution

# Stated costs of integer-rounded instances must match exactly; unrounded costs are
# conventionally reported with two decimals, so allow half a cent of slack there.
COST_TOLERANCE = {"nint": 1e-6, "ceil": 1e-6, "none": 0.005}


def distance(a: tuple[float, float], b: tuple[float, float], rounding: str) -> float:
    """Edge length following TSPLIB conventions.

    rounding: "nint" (EUC_2D, CVRPLIB default), "ceil" (CEIL_2D) or "none" (exact).
    """
    d = math.hypot(a[0] - b[0], a[1] - b[1])
    if rounding == "nint":
        return float(int(d + 0.5))
    if rounding == "ceil":
        return float(math.ceil(d))
    return d


def default_rounding(instance: Instance) -> str:
    return {"EUC_2D": "nint", "CEIL_2D": "ceil"}.get(instance.edge_weight_type, "none")


def route_cost(instance: Instance, route: list[int], rounding: str) -> float:
    if not route:
        return 0.0
    path = [0, *route, 0]
    c = instance.coords
    return sum(distance(c[i], c[j], rounding) for i, j in zip(path, path[1:]))


@dataclass
class RouteReport:
    index: int  # 1-based, as in the solution file
    customers: int
    load: int
    cost: float


@dataclass
class CheckReport:
    instance: str
    n_customers: int
    n_routes: int
    capacity: int | None
    rounding: str
    rounding_detected: bool
    computed_cost: float
    stated_cost: float | None
    feasible: bool
    cost_matches: bool | None
    errors: list[str] = field(default_factory=list)
    routes: list[RouteReport] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.feasible and self.cost_matches is not False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ok"] = self.ok
        return d


def check(
    instance: Instance,
    solution: Solution,
    rounding: str | None = None,
    max_vehicles: int | None = None,
) -> CheckReport:
    """Verify a solution against an instance.

    If ``rounding`` is None it follows EDGE_WEIGHT_TYPE. Several CVRPLIB sets
    (CMT, Golden, Li, Taillard) declare EUC_2D but are scored with unrounded
    distances; when the header rounding does not reproduce the stated cost but
    unrounded distances do, the unrounded convention is used and flagged as detected.
    """
    detected = False
    if rounding is None:
        rounding = default_rounding(instance)
        if solution.cost is not None and rounding != "none":
            if not _matches(_total(instance, solution, rounding), solution.cost, rounding) and _matches(
                _total(instance, solution, "none"), solution.cost, "none"
            ):
                rounding, detected = "none", True

    n = instance.n_customers
    errors: list[str] = []

    visits = Counter(c for r in solution.routes for c in r)
    unknown = sorted(c for c in visits if not 1 <= c <= n)
    if unknown:
        errors.append(f"unknown customer ids (valid: 1..{n}): {_fmt(unknown)}")
    dupes = sorted(c for c, k in visits.items() if k > 1 and 1 <= c <= n)
    if dupes:
        errors.append(f"customers visited more than once: {_fmt(dupes)}")
    missing = [c for c in range(1, n + 1) if c not in visits]
    if missing:
        errors.append(f"customers never visited: {_fmt(missing)}")

    route_reports: list[RouteReport] = []
    for i, route in enumerate(solution.routes, start=1):
        valid = [c for c in route if 1 <= c <= n]
        load = sum(instance.demands[c] for c in valid)
        cost = route_cost(instance, valid, rounding)
        route_reports.append(RouteReport(i, len(route), load, cost))
        if instance.capacity is not None and load > instance.capacity:
            errors.append(f"route {i} exceeds capacity: load {load} > {instance.capacity}")
        if instance.max_distance is not None:
            duration = cost + instance.service_time * len(valid)
            if duration > instance.max_distance + 1e-6:
                errors.append(
                    f"route {i} exceeds length limit: {duration:.2f} > {instance.max_distance:g}"
                    + (" (incl. service time)" if instance.service_time else "")
                )

    used = sum(1 for r in solution.routes if r)
    if max_vehicles is not None and used > max_vehicles:
        errors.append(f"uses {used} vehicles, limit is {max_vehicles}")

    computed = sum(r.cost for r in route_reports)
    cost_matches = None if solution.cost is None else _matches(computed, solution.cost, rounding)

    return CheckReport(
        instance=instance.name,
        n_customers=n,
        n_routes=used,
        capacity=instance.capacity,
        rounding=rounding,
        rounding_detected=detected,
        computed_cost=computed,
        stated_cost=solution.cost,
        feasible=not errors,
        cost_matches=cost_matches,
        errors=errors,
        routes=route_reports,
    )


def _total(instance: Instance, solution: Solution, rounding: str) -> float:
    n = instance.n_customers
    return sum(route_cost(instance, [c for c in r if 1 <= c <= n], rounding) for r in solution.routes)


def _matches(computed: float, stated: float, rounding: str) -> bool:
    return abs(computed - stated) <= COST_TOLERANCE[rounding]


def _fmt(ids: list[int], limit: int = 15) -> str:
    shown = ", ".join(map(str, ids[:limit]))
    return shown + (f", ... ({len(ids)} total)" if len(ids) > limit else "")
