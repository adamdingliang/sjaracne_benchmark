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
