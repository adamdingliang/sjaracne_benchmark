# Expanded 19-size AP-MI calibration: 10M + 10M

This is a separate, prospective extension of the
[original 11-size 5M + 5M study](../RESULTS.md), requested after reviewing its
results. Both original code and evidence are preserved. The expanded scripts
are versioned copies with an explicit new schema, larger fixed draw counts,
fresh seed namespace and a larger grid, not edits to the earlier frozen run.

The [completed results](RESULTS.md) include all nineteen sizes and the
[descriptive 5M/10M comparison](comparison_5m_10m_2026-10-15/REPORT.md).
Five exact-m GPD models passed; fourteen were rejected. Engine defaults
remain unchanged.

The [protocol](PLAN_2026-10-15.md) fixes nineteen exact observation counts:
30, 50, 80, 90, 100, 150, 200, 250, 300, 400, 500, 516, 600, 644, 700,
725, 800, 900 and 1000. Every size uses **10 million fitting draws and
10 million independent validation draws** with Npar=40 and the same shared
AP-MI kernel. No biological expression or reference edges enter calibration.

The GPD fitting and acceptance criteria are unchanged. More simulation
reduces Monte Carlo uncertainty; it does not fix a systematically inaccurate
GPD, and narrower held-out intervals can increase rejections. Only accepted
exact-m models are packaged; no models are installed as engine defaults.

## Execution

Use the pinned generator and unchanged engine checkout with Windows Python
3.13, NumPy 2.4.4, SciPy 1.17.1 and WSL Ubuntu. Child numerical-library threads
are capped at one. The full m=1000 run measures runtime before the sweep;
the anchor stage verifies/reuses that same attempt regardless of acceptance.

```powershell
python benchmarks/apmi_null_m_sweep/expanded_10m/run_staged.py plan --engine-root D:/GitHub/SJARACNe --generator D:/GitHub/SJARACNe/SJARACNe/bin/apmi_null_generator.exe --engine-commit 7633ebb4a0d966dbda15a4e32d0efa492fb71aeb --python C:/Users/adamd/miniconda3/python.exe --distro Ubuntu --protocol benchmarks/apmi_null_m_sweep/expanded_10m/PLAN_2026-10-15.md --out runs/FRESH_10M_RUN
python benchmarks/apmi_null_m_sweep/expanded_10m/run_staged.py run --plan runs/FRESH_10M_RUN/plan.json --m 1000 --workers 1
python benchmarks/apmi_null_m_sweep/expanded_10m/run_staged.py run --plan runs/FRESH_10M_RUN/plan.json --stage anchors --workers 8
python benchmarks/apmi_null_m_sweep/expanded_10m/run_staged.py run --plan runs/FRESH_10M_RUN/plan.json --stage expanded --workers 8
python benchmarks/apmi_null_m_sweep/expanded_10m/run_staged.py run --plan runs/FRESH_10M_RUN/plan.json --stage dream --workers 3
python benchmarks/apmi_null_m_sweep/expanded_10m/summarize.py --run runs/FRESH_10M_RUN --out benchmarks/apmi_null_m_sweep/expanded_10m/FRESH_RESULTS
python benchmarks/apmi_null_m_sweep/expanded_10m/compare.py --previous benchmarks/apmi_null_m_sweep/results_2026-10-15 --current benchmarks/apmi_null_m_sweep/expanded_10m/FRESH_RESULTS --out benchmarks/apmi_null_m_sweep/expanded_10m/FRESH_COMPARISON
python scripts/check_benchmarks.py --group apmi_null_m_sweep_10m
```

Replace local paths with verified equivalents. The runner checks the exact
generator SHA256, source/protocol/code/environment pins, seeds, raw metadata,
lengths, finite support, hashes and provenance before fitting. Raw files stay
under ignored runs/; the new raw payload totals 3.04 GB (decimal).

## Interpretation

Model support is requested at p=0.0005 through 0.001; endpoint checks are not
proof of accuracy throughout that interval. p=0.001 and p=0.0005 remain
provisional TF/SIG operating choices, not biological probabilities or FDR.
Confidence is per model with .999 pointwise Clopper-Pearson intervals, not
simultaneous coverage over all nineteen m values. No interpolation is used.

Fit-stream empirical quantiles are diagnostic only. Held-out data cannot
select/refit a model or rescue a rejection. Original calibrator reports retain
their legacy `cutoff_p1e-7` label byte-for-byte; new summaries explicitly use
p=0.001 and p=0.0005. Descriptive comparison with the earlier experiment must
acknowledge that both draw counts and seeds changed.
