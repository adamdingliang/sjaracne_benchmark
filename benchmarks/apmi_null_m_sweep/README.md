# AP-MI null-calibration studies

This directory contains the October 2026 calibration sequence. The selected
[broad-grid PCHIP study](broad_grid_10m/README.md) supplies the frozen surface now
used by [SJARACNe2 workflows](https://github.com/adamdingliang/SJARACNe2/blob/develop/SJARACNe/wdl/README.md#default-parameter-values).
Calibration uses simulated independent ranks, not expression datasets or
biological reference edges. Runtime adoption did not reopen the final evaluation.

| Study | Scope | Results |
| --- | --- | --- |
| [Original exact-m GPD](PLAN_2026-10-15.md) | Eleven sizes, 5M fitting + 5M validation draws per size | [3 accepted, 8 rejected](RESULTS.md) |
| [Expanded exact-m GPD](expanded_10m/README.md) | Nineteen sizes, 10M + 10M per size | [5 accepted, 14 rejected](expanded_10m/RESULTS.md) |
| [Smooth feasibility](smooth_feasibility/README.md) | Reuse the nineteen-size streams; no new draws | [Quadratic surface within 10% in 34 main checks, with wider-p failures](smooth_feasibility/RESULTS.md) |
| [Probability-axis refinement](p_axis_refinement/README.md) | Denser p knots on the same streams | [Quadratic 261/272; PCHIP 265/272 within 10% on off-knot probes](p_axis_refinement/RESULTS.md) |
| [Broad-grid PCHIP](broad_grid_10m/README.md) | 200 sizes, 10M + 10M; separate selection and final validation | [6599/6600 moderate observed errors within 10%](broad_grid_10m/RESULTS.md) |

The broad-grid simultaneous-interval assessment did not confirm the complete
core grid. Larger GPD/hybrid/spline candidate searches remain deferred. Earlier
plans, result packages and acceptance labels retain their original scope.

## Stages

The original eleven-size [protocol](PLAN_2026-10-15.md) used Npar=40 and fresh
**5,000,000 fitting plus 5,000,000 validation draws** at each exact sample count:

1. Time 200,000-draw pilots at m=30, 300 and 1000; exclude them from calibration.
2. Calibrate anchors m=30, 50, 80, 90, 100, 150, 300 and 1000.
3. Calibrate the exact DREAM5 counts m=644, 516 and 725.

The primary GPD uses strict exceedances above q=0.995. Valid fits at
q=0.9925/0.995/0.9975 must agree within 10% at p=0.0005. Both p=0.001 and 0.0005
must pass conservative 99.9% pointwise Clopper-Pearson checks. Only m=90, 100
and 150 passed both gates. Rejected cutoffs remain diagnostic; there is no
nearest-size substitution or held-out-data rescue.

These provisional TF/SIG probabilities are not biological FDR controls or
universal optima. Ties, zero inflation and dependent observations require
additional assessment beyond independent unique ranks.

## Runtime-first pilot

```powershell
python benchmarks/apmi_null_m_sweep/time_generator.py --generator PATH_TO_PINNED_GENERATOR --out runs/FRESH_TIMING_DIRECTORY
```

The October 15 sequential pilot took 0.11 s at m=30, 0.71 s at m=300 and 2.22 s
at m=1000. These are generator timings, excluding fitting, sorting, hashing and
parallel contention. [Timing provenance](timing_2026-10-15/timing_results.json)
records commands and hashes; binary streams remain under ignored `runs/`.

## Reproduce the staged run

Historical reproduction uses the pinned generator/source with Windows Python
3.13, NumPy 2.4.4, SciPy 1.17.1 and WSL Ubuntu. Numerical-library threads are
limited to one per child. Replace local paths with verified equivalents and use
fresh output directories; current engine defaults are not a substitute for the
recorded runtime.

```powershell
python benchmarks/apmi_null_m_sweep/run_staged.py plan --engine-root D:/GitHub/SJARACNe --generator D:/GitHub/SJARACNe/SJARACNe/bin/apmi_null_generator.exe --engine-commit 7633ebb4a0d966dbda15a4e32d0efa492fb71aeb --python C:/Users/adamd/miniconda3/python.exe --distro Ubuntu --protocol benchmarks/apmi_null_m_sweep/PLAN_2026-10-15.md --out runs/FRESH_CALIBRATION_DIRECTORY
python benchmarks/apmi_null_m_sweep/run_staged.py run --plan runs/FRESH_CALIBRATION_DIRECTORY/plan.json --m 80 --workers 1
python benchmarks/apmi_null_m_sweep/run_staged.py run --plan runs/FRESH_CALIBRATION_DIRECTORY/plan.json --stage anchors --workers 8
python benchmarks/apmi_null_m_sweep/run_staged.py run --plan runs/FRESH_CALIBRATION_DIRECTORY/plan.json --stage dream --workers 3
python benchmarks/apmi_null_m_sweep/summarize.py --run runs/FRESH_CALIBRATION_DIRECTORY --out benchmarks/apmi_null_m_sweep/FRESH_RESULT_DIRECTORY
python scripts/check_benchmarks.py --group apmi_null_m_sweep
```

The m=80 smoke uses full draw counts. Later stages verify and reuse completed
attempts regardless of scientific acceptance. Failures are preserved rather than
silently retried. Only newly generated, verified streams enter `--reuse-raw`.

The legacy CSV label `cutoff_p1e-7` contains the configured default-p cutoff
(0.0005 here); newer summaries label both probabilities explicitly. Fit-stream
quantiles are diagnostics, not fallback models. Raw streams remain local.
