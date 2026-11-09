# Expanded 19-size AP-MI calibration: 10M + 10M

This completed October 15, 2026 experiment extends the
[eleven-size study](../RESULTS.md) with fresh seeds and larger draw counts.
Original code, plans and evidence remain unchanged. The later
[broad-grid PCHIP study](../broad_grid_10m/README.md) is a separate experiment.

[Results](RESULTS.md): five exact-m GPD models passed and fourteen were rejected.
The [5M/10M comparison](comparison_5m_10m_2026-10-15/REPORT.md) is descriptive:
both seeds and draw counts changed. The additional
[GPD-or-empirical display](RESULTS.md#additional-mi-cutoff-table-gpd-or-empirical)
and [CSV](cutoffs_gpd_or_empirical.csv) substitute fit-only empirical quantiles
for rejected GPDs; this retrospective table is not a validated runtime fallback.

The [protocol](PLAN_2026-10-15.md) fixes nineteen exact m values:
30, 50, 80, 90, 100, 150, 200, 250, 300, 400, 500, 516, 600, 644, 700,
725, 800, 900 and 1000. Each uses **10M fitting plus 10M independent validation
draws**, Npar=40 and the shared AP-MI kernel. No biological expression or
reference edges enter calibration. Only accepted exact-m models are packaged;
this study did not install GPDs as engine defaults.

## Execution

Historical reproduction uses the pinned generator/source, Windows Python 3.13,
NumPy 2.4.4, SciPy 1.17.1 and WSL Ubuntu. Each child uses one numerical-library
thread. The full m=1000 runtime gate is reused by later stages regardless of
scientific acceptance. Replace paths with verified equivalents and use new outputs.

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

The runner verifies source/protocol/environment, seeds, generator SHA-256,
raw metadata, lengths, finite support, hashes and provenance. The 3.04-GB decimal
raw payload remains local under ignored `runs/`.

## Interpretation

More draws reduce Monte Carlo uncertainty without repairing a misspecified GPD;
narrower validation intervals can increase rejection. Support at the tested
p=0.0005 and 0.001 endpoints is not proof throughout that interval. These remain
provisional TF/SIG settings, not biological probabilities or FDR controls.

The .999 pointwise Clopper-Pearson checks are per model, not simultaneous over
nineteen m values; no interpolation is used. Held-out data cannot select/refit a
model or rescue a rejection. Fit quantiles remain diagnostic. Original reports
retain their legacy `cutoff_p1e-7` column; new summaries label both probabilities.
