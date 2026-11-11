# routeviz

Plot, animate and **verify** vehicle routing (CVRP) solutions from the command line.
Reads the standard [CVRPLIB](http://vrp.galgos.inf.puc-rio.br/index.php/en/) formats (`.vrp`, `.sol`).

<p align="center">
  <img src="docs/A-n32-k5.gif" width="640" alt="Animated optimal solution of CVRPLIB instance A-n32-k5">
</p>

## Usage

```bash
pip install git+https://github.com/jonasgrau/routeviz

routeviz check   A-n32-k5.vrp A-n32-k5.sol            # feasibility + recomputed cost
routeviz plot    A-n32-k5.vrp A-n32-k5.sol -o out.svg # also .png / .pdf
routeviz animate A-n32-k5.vrp A-n32-k5.sol -o out.gif
```

`check` verifies that every customer is visited exactly once, that capacity and
route-length limits hold, and that the stated cost matches the recomputed one.
Exit code `0` = OK, `1` = violation, `2` = unreadable input; `--json` for scripts and CI.

**Distance convention:** `EUC_2D` is rounded to the nearest integer, as in TSPLIB. Some
classic sets (CMT, Golden, Li, Taillard) are scored unrounded despite the header;
routeviz detects this from the stated cost. Verified against the published solutions
of 10 CVRPLIB instances.

Limitations: coordinates required (no explicit distance matrices), single depot, no time windows.

MIT licensed · `pip install -e ".[dev]" && pytest`
