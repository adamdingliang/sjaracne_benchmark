# Expanded exact-m moderate-tail calibration: 10M + 10M draws

Recorded q=0.995 GPD fits at 19 predeclared exact m values; default/minimum p=0.0005, supported through p=0.001; independent 10M fitting and 10M validation draws per exact m, using fresh base seeds 20261017 and 20261018 with the fixed per-m/validation offsets.

Synthetic independent uniform rank-permutation nulls only; Npar=40 and unique ordinal ranks. Exact m only: no interpolation or nearest-neighbor lookup. Acceptance does not establish biological accuracy, biological FDR, or an optimal network setting. Confidence is the predeclared 99% family setting per model with ten comparisons (99.9% per point), not simultaneous 99% coverage across all m. Empirical thresholds are fit-stream diagnostics evaluated on held-out draws, not replacement runtime models or a model-selection rule.

Original engine CSV cutoff_p1e-7 and report p=1e-7 prose are stale labels. Original evidence remains unchanged; corrected cutoffs here are explicitly p=0.0005 and p=0.001.

| m | Stage | Status |
|---:|:---|:---|
| 30 | anchors | rejected |
| 50 | anchors | rejected |
| 80 | anchors | rejected |
| 90 | anchors | rejected |
| 100 | anchors | accepted |
| 150 | anchors | rejected |
| 300 | anchors | accepted |
| 1000 | anchors | rejected |
| 200 | expanded | accepted |
| 250 | expanded | accepted |
| 400 | expanded | accepted |
| 500 | expanded | rejected |
| 600 | expanded | rejected |
| 700 | expanded | rejected |
| 800 | expanded | rejected |
| 900 | expanded | rejected |
| 644 | dream | rejected |
| 516 | dream | rejected |
| 725 | dream | rejected |

See summary.json for verified provenance and diagnostics, summary.csv for GPD parameters/cutoffs, and heldout.csv for independent exceedance counts and intervals. Original compact reports/logs are in evidence/. Raw streams are excluded.
