# Historical probability-axis refinement (October 15, 2026)

This exploratory follow-up reused the nineteen sizes and 38 streams from the
[first smooth-cutoff analysis](../smooth_feasibility/README.md). It added no draws,
sorting or GPD fits. The later [broad-grid study](../broad_grid_10m/README.md)
completed separately; the old "sweep stopped" status does not describe it.

The [plan](PLAN.md) fixes 25 p knots, 21 geometric-midpoint probes and 49 total
queries. It leaves whole m values out and separates exact-m p-only errors from
m-axis interpolation. Probes promoted to knots are regression checks, not fresh
p-interpolation tests. Previously inspected validation streams remain development
evidence.

[Results](RESULTS.md): quadratic observed errors within 10% improved from
187/272 to 261/272 on new off-knot probes; PCHIP reached 265/272. Some small-m
failures remained large, with a numerical/tie caveat. Computation took 9.89 s.
These results do not independently validate a general runtime cutoff function.

## Reproduce

Use the recorded Python/NumPy/SciPy/matplotlib environment and existing raw
streams/caches from the first analysis. Output directories must be new.

```powershell
python scripts/check_benchmarks.py --group apmi_p_axis_refinement
python benchmarks/apmi_null_m_sweep/p_axis_refinement/run.py --source runs/apmi_null_smooth_feasibility_20261015 --out runs/FRESH_P_AXIS_REFINEMENT --workers 12
python benchmarks/apmi_null_m_sweep/p_axis_refinement/package.py --run runs/FRESH_P_AXIS_REFINEMENT --out benchmarks/apmi_null_m_sweep/p_axis_refinement/FRESH_RESULTS
```
