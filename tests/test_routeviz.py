import json
from pathlib import Path

import pytest

from routeviz import ParseError, check, load_instance, load_solution, parse_instance, parse_solution
from routeviz.cli import main

DATA = Path(__file__).parent / "data"

TINY = """NAME : tiny
TYPE : CVRP
DIMENSION : 4
EDGE_WEIGHT_TYPE : EUC_2D
CAPACITY : 10
NODE_COORD_SECTION
1 0 0
2 3 4
3 6 8
4 -3 -4
DEMAND_SECTION
1 0
2 4
3 5
4 6
DEPOT_SECTION
1
-1
EOF
"""


@pytest.fixture
def tiny():
    return parse_instance(TINY)


# --- parsing -----------------------------------------------------------------

def test_parse_real_instance():
    inst = load_instance(DATA / "A-n32-k5.vrp")
    assert inst.name == "A-n32-k5"
    assert inst.n_customers == 31
    assert inst.capacity == 100
    assert inst.coords[0] == (82.0, 76.0)  # depot is node 1
    assert inst.demands[0] == 0


def test_parse_reads_distance_limit():
    inst = load_instance(DATA / "CMT6.vrp")
    assert inst.max_distance == 200.0
    assert inst.service_time == 10.0


def test_depot_not_first_is_moved_to_index_zero():
    text = TINY.replace("DEPOT_SECTION\n1\n", "DEPOT_SECTION\n3\n")
    inst = parse_instance(text)
    assert inst.coords[0] == (6.0, 8.0)
    assert inst.node_ids == [3, 1, 2, 4]


def test_explicit_matrix_rejected_with_clear_message():
    text = "NAME : e\nEDGE_WEIGHT_TYPE : EXPLICIT\nEDGE_WEIGHT_SECTION\n1 2 3\nEOF\n"
    with pytest.raises(ParseError, match="explicit"):
        parse_instance(text)


def test_solution_parsing_handles_empty_route_and_cost():
    sol = parse_solution("Route #1: 1 2\nRoute #2:\nRoute #3: 3\nCost 42.5\n")
    assert sol.routes == [[1, 2], [], [3]]
    assert sol.cost == 42.5


def test_solution_without_routes_is_an_error():
    with pytest.raises(ParseError):
        parse_solution("Cost 10\n")


# --- checking ----------------------------------------------------------------

def test_known_optimum_a_n32_k5():
    r = check(load_instance(DATA / "A-n32-k5.vrp"), load_solution(DATA / "A-n32-k5.sol"))
    assert r.ok and r.computed_cost == 784 and r.n_routes == 5
    assert r.rounding == "nint" and not r.rounding_detected


def test_unrounded_convention_is_detected_for_cmt6():
    r = check(load_instance(DATA / "CMT6.vrp"), load_solution(DATA / "CMT6.sol"))
    assert r.ok
    assert r.rounding == "none" and r.rounding_detected
    assert r.computed_cost == pytest.approx(555.43, abs=0.005)


def test_explicit_rounding_is_not_overridden():
    r = check(load_instance(DATA / "CMT6.vrp"), load_solution(DATA / "CMT6.sol"), rounding="nint")
    assert r.cost_matches is False and not r.ok


def test_edge_lengths_are_nint_rounded(tiny):
    # 0 -> 1 -> 0 is 5 + 5; 0 -> 3 -> 0 is 5 + 5; 0 -> 2 -> 0 is 10 + 10
    r = check(tiny, parse_solution("Route #1: 1\nRoute #2: 2\nRoute #3: 3\nCost 40\n"))
    assert r.ok and r.computed_cost == 40


def test_detects_missing_and_duplicate_and_unknown(tiny):
    r = check(tiny, parse_solution("Route #1: 1 1\nRoute #2: 7\n"))
    assert not r.feasible
    text = " ".join(r.errors)
    assert "unknown customer ids" in text and "7" in text
    assert "more than once: 1" in text
    assert "never visited: 2, 3" in text


def test_detects_capacity_violation(tiny):
    r = check(tiny, parse_solution("Route #1: 1 2 3\n"))
    assert any("exceeds capacity: load 15 > 10" in e for e in r.errors)


def test_detects_cost_mismatch(tiny):
    r = check(tiny, parse_solution("Route #1: 1\nRoute #2: 2\nRoute #3: 3\nCost 39\n"))
    assert r.feasible and r.cost_matches is False and not r.ok


def test_vehicle_limit(tiny):
    sol = parse_solution("Route #1: 1\nRoute #2: 2\nRoute #3: 3\n")
    assert check(tiny, sol, max_vehicles=3).ok
    assert not check(tiny, sol, max_vehicles=2).ok


def test_distance_limit_includes_service_time():
    inst = load_instance(DATA / "CMT6.vrp")
    inst.max_distance = 50.0
    r = check(inst, load_solution(DATA / "CMT6.sol"))
    assert any("length limit" in e and "service time" in e for e in r.errors)


# --- CLI ---------------------------------------------------------------------

def test_cli_check_exit_codes(tmp_path, capsys):
    vrp, sol = DATA / "A-n32-k5.vrp", DATA / "A-n32-k5.sol"
    assert main(["check", str(vrp), str(sol)]) == 0
    bad = tmp_path / "bad.sol"
    bad.write_text(sol.read_text().replace("Cost 784", "Cost 700"))
    assert main(["check", str(vrp), str(bad)]) == 1
    assert main(["check", str(vrp), str(tmp_path / "missing.sol")]) == 2


def test_cli_check_json(capsys):
    main(["check", "--json", str(DATA / "A-n32-k5.vrp"), str(DATA / "A-n32-k5.sol")])
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True and out["computed_cost"] == 784 and len(out["routes"]) == 5


@pytest.mark.parametrize("suffix", [".svg", ".png"])
def test_cli_plot(tmp_path, suffix):
    out = tmp_path / f"a{suffix}"
    assert main(["plot", str(DATA / "A-n32-k5.vrp"), str(DATA / "A-n32-k5.sol"), "-o", str(out)]) == 0
    assert out.stat().st_size > 1000


def test_cli_animate(tmp_path):
    out = tmp_path / "a.gif"
    args = ["animate", str(DATA / "A-n32-k5.vrp"), str(DATA / "A-n32-k5.sol"), "-o", str(out),
            "--max-frames", "10", "--fps", "5", "--size", "3"]
    assert main(args) == 0
    assert out.read_bytes()[:6] in (b"GIF87a", b"GIF89a")


def test_solver_metadata_lines_are_tolerated():
    sol = parse_solution("Route #1: 1 2\nCost 10\nTime 0.52\n")
    assert sol.cost == 10 and sol.extra == {"Time": "0.52"}


@pytest.mark.parametrize("n_routes", [9, 17, 26])
def test_no_colour_collision_between_angular_neighbours(n_routes):
    import math
    from routeviz.render import LIGHT, route_colors
    from routeviz.io import Instance

    coords = [(0.0, 0.0)] + [(math.cos(2 * math.pi * i / n_routes), math.sin(2 * math.pi * i / n_routes))
                             for i in range(n_routes)]
    inst = Instance("ring", coords, [0] * len(coords), None, "EUC_2D", list(range(len(coords))))
    routes = [[i] for i in range(1, n_routes + 1)]
    colors = route_colors(inst, routes, LIGHT)
    order = sorted(range(n_routes), key=lambda i: math.atan2(coords[i + 1][1], coords[i + 1][0]))
    ring = [colors[i] for i in order]
    assert all(ring[j] != ring[(j + 1) % n_routes] for j in range(n_routes))


def test_cli_rejects_zero_frames(tmp_path):
    with pytest.raises(SystemExit):
        main(["animate", str(DATA / "A-n32-k5.vrp"), str(DATA / "A-n32-k5.sol"), "--max-frames", "0"])
