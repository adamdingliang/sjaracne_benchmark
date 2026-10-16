# Smooth AP-MI cutoff feasibility (no new simulations)

This exploratory analysis reuses the nineteen completed 10M fitting + 10M
validation null distributions. It compares leave-entire-size-out smooth GPD
parameters with direct empirical quantile surfaces. It does not run the proposed
200-size sweep, install models, change engine defaults or claim fresh validation.

The [completed results](RESULTS.md) took 29.69 seconds of computation. The
quadratic empirical surface stayed within 10% observed null-rate error in all
34 main interior checks, but failed some wider-p interpolation checks. This
is promising limited-scope feasibility, not a generally validated function.

[Frozen analysis design](PLAN.md) specifies six candidates, endpoint handling,
eight probability knots, eight additional probability probes, exact tie counts
and all unavailable/invalid predictions. The GPD candidates reuse every existing
q=0.995 primary parameter set, including rejected fits; no new GPDs are optimized.
Loglinear/logquadratic curves are low-parameter candidates; PCHIP is the more
flexible shape-preserving piecewise-cubic interpolation comparator.

## Reproduce

Use Windows Python 3.13 with NumPy, SciPy and matplotlib. Original streams must
match the expanded study's frozen hashes. Output must be a new child of ignored
`runs/`. The script uses twelve workers by default, with numerical threads capped
at one each, and refuses overwrites. Only sorted copies are written locally.

```powershell
python scripts/check_benchmarks.py --group apmi_smooth_feasibility
python benchmarks/apmi_null_m_sweep/smooth_feasibility/analyze.py --source-run runs/apmi_null_m_sweep_10m_20261015 --out runs/FRESH_SMOOTH_FEASIBILITY --workers 12
python benchmarks/apmi_null_m_sweep/smooth_feasibility/package.py --run runs/FRESH_SMOOTH_FEASIBILITY --out benchmarks/apmi_null_m_sweep/smooth_feasibility/FRESH_COMPACT_RESULTS
```

The evaluation table distinguishes fitting and validation streams, interior
interpolation and endpoint extrapolation, p knots and extra p probes, and exact-m
baselines from leave-size-out candidates. The primary comparison covers seventeen
interior sizes at p=0.001 and 0.0005. Null-rate error is the metric of interest,
not simply closeness of MI cutoffs. Pointwise intervals are descriptive and do
not cover function-fitting or post-selection uncertainty.

Previously inspected validation streams are not new confirmation. Rare p levels
have limited event counts. There is no support for m>1000 or arbitrary untested
probabilities. An attractive function still needs a frozen method and fresh
validation before any runtime promotion.
