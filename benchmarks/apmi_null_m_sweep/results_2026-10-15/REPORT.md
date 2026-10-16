# Exact-m moderate-tail calibration

Recorded q=0.995 GPD fits; default/minimum p=0.0005, supported through p=0.001; independent 5M fitting and 5M validation draws per exact m.

Synthetic independent uniform rank-permutation nulls only; Npar=40 and unique ordinal ranks. Exact m only: no interpolation or nearest-neighbor lookup. Acceptance does not establish biological accuracy, biological FDR, or an optimal network setting. Confidence is the predeclared 99% family setting per model with ten comparisons (99.9% per point), not simultaneous 99% coverage across all m. Empirical thresholds are fit-stream diagnostics evaluated on held-out draws, not replacement runtime models or a model-selection rule.

Original engine CSV cutoff_p1e-7 and report p=1e-7 prose are stale labels. Original evidence remains unchanged; corrected cutoffs here are explicitly p=0.0005 and p=0.001.

| m | Stage | Status |
|---:|:---|:---|
| 30 | anchors | rejected |
| 50 | anchors | rejected |
| 80 | anchors | rejected |
| 90 | anchors | accepted |
| 100 | anchors | accepted |
| 150 | anchors | accepted |
| 300 | anchors | rejected |
| 1000 | anchors | rejected |
| 644 | dream | rejected |
| 516 | dream | rejected |
| 725 | dream | rejected |

See summary.json for verified provenance and diagnostics, summary.csv for GPD parameters/cutoffs, and heldout.csv for independent exceedance counts and intervals. Original compact reports/logs are in evidence/. Raw streams are excluded.
