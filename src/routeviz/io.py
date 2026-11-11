"""Parsers for CVRPLIB / TSPLIB-style instance (.vrp) and solution (.sol) files.

Internal convention: index 0 is the depot, indices 1..n are the customers in the
order they appear in the instance file. This matches the CVRPLIB solution format,
where routes list customers numbered 1..n and the depot is implicit.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED_EDGE_WEIGHT_TYPES = {"EUC_2D", "CEIL_2D"}


class ParseError(ValueError):
    """Raised when an instance or solution file cannot be parsed."""


@dataclass
class Instance:
    name: str
    coords: list[tuple[float, float]]  # coords[0] is the depot
    demands: list[int]  # demands[0] is the depot (normally 0)
    capacity: int | None
    edge_weight_type: str
    node_ids: list[int]  # original node id from the file for each internal index
    max_distance: float | None = None  # DISTANCE: route length limit (incl. service time)
    service_time: float = 0.0  # SERVICE_TIME per customer

    @property
    def n_customers(self) -> int:
        return len(self.coords) - 1


@dataclass
class Solution:
    routes: list[list[int]]  # customer indices, depot excluded
    cost: float | None = None
    extra: dict[str, str] = field(default_factory=dict)


_HEADER_RE = re.compile(r"^\s*([A-Z_]+)\s*:\s*(.*?)\s*$")
_SECTIONS = {
    "NODE_COORD_SECTION",
    "DEMAND_SECTION",
    "DEPOT_SECTION",
    "EDGE_WEIGHT_SECTION",
    "DISPLAY_DATA_SECTION",
}


def parse_instance(text: str, name_hint: str = "instance") -> Instance:
    header: dict[str, str] = {}
    coords: dict[int, tuple[float, float]] = {}
    demands: dict[int, int] = {}
    depots: list[int] = []
    section: str | None = None

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        token = line.split()[0].rstrip(":")
        if token == "EOF":
            break
        if token in _SECTIONS:
            section = token
            continue
        if section is None:
            m = _HEADER_RE.match(line)
            if m:
                header[m.group(1)] = m.group(2)
                continue
            raise ParseError(f"line {lineno}: unexpected header line: {raw!r}")
        parts = line.split()
        try:
            if section in ("NODE_COORD_SECTION", "DISPLAY_DATA_SECTION"):
                node = int(parts[0])
                if section == "NODE_COORD_SECTION" or node not in coords:
                    coords[node] = (float(parts[1]), float(parts[2]))
            elif section == "DEMAND_SECTION":
                demands[int(parts[0])] = int(parts[1])
            elif section == "DEPOT_SECTION":
                value = int(parts[0])
                if value == -1:
                    section = None
                else:
                    depots.append(value)
            elif section == "EDGE_WEIGHT_SECTION":
                continue  # explicit matrices are not supported; coords are required
        except (IndexError, ValueError) as exc:
            raise ParseError(f"line {lineno}: cannot parse {section} entry {raw!r}") from exc

    if not coords:
        raise ParseError(
            "instance has no NODE_COORD_SECTION; explicit distance matrices are not supported"
        )
    ewt = header.get("EDGE_WEIGHT_TYPE", "EUC_2D").upper()
    if ewt not in SUPPORTED_EDGE_WEIGHT_TYPES:
        raise ParseError(
            f"EDGE_WEIGHT_TYPE {ewt} is not supported "
            f"(supported: {', '.join(sorted(SUPPORTED_EDGE_WEIGHT_TYPES))})"
        )

    nodes = sorted(coords)
    depot = depots[0] if depots else nodes[0]
    if len(depots) > 1:
        raise ParseError("multi-depot instances are not supported")
    if depot not in coords:
        raise ParseError(f"depot {depot} has no coordinates")

    order = [depot] + [n for n in nodes if n != depot]
    capacity = header.get("CAPACITY")
    return Instance(
        name=header.get("NAME", name_hint),
        coords=[coords[n] for n in order],
        demands=[demands.get(n, 0) for n in order],
        capacity=int(float(capacity)) if capacity else None,
        edge_weight_type=ewt,
        node_ids=order,
        max_distance=float(header["DISTANCE"]) if header.get("DISTANCE") else None,
        service_time=float(header.get("SERVICE_TIME") or 0.0),
    )


_ROUTE_RE = re.compile(r"^\s*Route\s*#?\s*\d+\s*:(.*)$", re.IGNORECASE)
_COST_RE = re.compile(r"^\s*Cost\s*:?\s*([-+0-9.eE]+)\s*$", re.IGNORECASE)


def parse_solution(text: str) -> Solution:
    routes: list[list[int]] = []
    cost: float | None = None
    extra: dict[str, str] = {}
    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if m := _ROUTE_RE.match(line):
            try:
                routes.append([int(tok) for tok in m.group(1).split()])
            except ValueError as exc:
                raise ParseError(f"line {lineno}: non-integer customer in {raw!r}") from exc
        elif m := _COST_RE.match(line):
            cost = float(m.group(1))
        elif ":" in line:
            key, _, value = line.partition(":")
            extra[key.strip()] = value.strip()
        else:
            # solver metadata such as "Time 0.52" (HGS-CVRP, PyVRP): keep, don't fail
            key, _, value = line.partition(" ")
            extra[key.strip()] = value.strip()
    if not routes:
        raise ParseError("solution contains no 'Route #k:' lines")
    return Solution(routes=routes, cost=cost, extra=extra)


def load_instance(path: str | Path) -> Instance:
    p = Path(path)
    return parse_instance(p.read_text(), name_hint=p.stem)


def load_solution(path: str | Path) -> Solution:
    return parse_solution(Path(path).read_text())
