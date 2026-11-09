# Historical smooth-cutoff feasibility (October 15, 2026)

This exploratory analysis reused nineteen completed 10M fitting + 10M validation
null distributions. It compared smooth GPD parameters and empirical quantile
surfaces without new simulations. The [denser-p refinement](../p_axis_refinement/README.md)
and later [200-size PCHIP study](../broad_grid_10m/README.md) have separate scope
and results; the original records here remain unchanged.

[Results](RESULTS.md): 29.69 s of computation; the quadratic empirical surface
was within 10% observed null-rate error in all 34 main interior checks but failed
wider-p interpolation checks. This supported further investigation, not a generally
validated function or an engine-default change at that date.

The [design](PLAN.md) fixes six candidates, eight p knots, eight extra p probes,
endpoint handling, tie counts and invalid predictions. GPD candidates reuse every
q=0.995 primary fit, including rejected fits. PCHIP is a shape-preserving comparator;
loglinear/logquadratic models have fewer parameters.

## Reproduce

Use the recorded Windows Python 3.13/NumPy/SciPy/matplotlib environment and frozen
expanded-study streams. Outputs must be new children of ignored `runs/`; only
sorted copies are written. Twelve workers use one numerical-library thread each.

```powershell
python scripts/check_benchmarks.py --group apmi_smooth_feasibility
python benchmarks/apmi_null_m_sweep/smooth_feasibility/analyze.py --source-run runs/apmi_null_m_sweep_10m_20261015 --out runs/FRESH_SMOOTH_FEASIBILITY --workers 12
python benchmarks/apmi_null_m_sweep/smooth_feasibility/package.py --run runs/FRESH_SMOOTH_FEASIBILITY --out benchmarks/apmi_null_m_sweep/smooth_feasibility/FRESH_COMPACT_RESULTS
```

The primary comparison covers seventeen interior sizes at p=0.001 and 0.0005.
Tables separate fit/validation streams, interpolation/extrapolation, knots/probes,
and exact-m/leave-size-out baselines. Evaluate null-rate error rather than cutoff
closeness. Pointwise intervals omit fitting and post-selection uncertainty.

Previously inspected streams are not fresh confirmation. Rare probabilities have
limited event counts; this study does not support m>1000 or arbitrary untested p.
The later broad-grid experiment supplies the separate validation evidence.
