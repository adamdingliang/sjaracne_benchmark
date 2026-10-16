# Denser probability-axis refinement

This is a separate exploratory follow-up to the
[first smooth-cutoff feasibility analysis](../smooth_feasibility/README.md).
It reuses the same nineteen sizes and 38 existing streams, replacing the
sparse p knots with a frozen denser grid. No new null draws, sorting,
GPD fitting, engine changes or broad-grid sweep are involved.

[Analysis plan](PLAN.md) fixes 25 p knots, 21 separate geometric-midpoint probes
and 49 total queries. The main comparison leaves entire m values out and
tests new off-knot p values. Old probes that become knots are regression
checks, not new p-interpolation tests. Exact-m p-only baselines separate
p-axis errors from m-axis interpolation errors.

All validation data were previously inspected. This is development evidence,
not fresh confirmation or a generally accepted runtime cutoff function.

The [completed results](RESULTS.md) improved the quadratic surface from
187/272 to 261/272 observed errors within 10% on new off-knot probes. PCHIP
reached 265/272, but some small-m errors remained large. Computation took
9.89 seconds; the expensive sweep remains stopped.

## Reproduce

Use the same Python/NumPy/SciPy/matplotlib environment and existing local raw
streams/caches as the first analysis. Output directories must be new.

```powershell
python scripts/check_benchmarks.py --group apmi_p_axis_refinement
python benchmarks/apmi_null_m_sweep/p_axis_refinement/run.py --source runs/apmi_null_smooth_feasibility_20261015 --out runs/FRESH_P_AXIS_REFINEMENT --workers 12
python benchmarks/apmi_null_m_sweep/p_axis_refinement/package.py --run runs/FRESH_P_AXIS_REFINEMENT --out benchmarks/apmi_null_m_sweep/p_axis_refinement/FRESH_RESULTS
```
