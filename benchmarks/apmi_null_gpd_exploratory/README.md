# Historical GPD null calibration (exploratory)

This archive records the GPD route explored before the empirical PCHIP surface.
Current [SJARACNe2](https://github.com/adamdingliang/SJARACNe2) workflows use the
later [frozen PCHIP calibration](../apmi_null_m_sweep/broad_grid_10m/README.md).
The initial [engine PR #1](https://github.com/adamdingliang/SJARACNe2/pull/1)
was a historical integration step; its opt-in policy is not the current default.

## Process

- [Original calibrator and BRCA100 validation](legacy_pr1/benchmarks/apmi_null_calibration/README.md).
- [Eleven-size, 5M + 5M protocol](../apmi_null_m_sweep/PLAN_2026-10-15.md).
- [Nineteen-size, 10M + 10M protocol](../apmi_null_m_sweep/expanded_10m/PLAN_2026-10-15.md).

These studies use independent rank pairs and the shared AP-MI estimator.
The original `p=1e-7` stability rule differs from the later moderate-probability
rule; acceptance labels remain specific to each protocol.

## Results

| Study | Original acceptance result |
| --- | --- |
| [Six-size sweep](legacy_pr1/benchmarks/apmi_null_calibration/calibration_results_2026-08-12/calibration_summary.csv) | Only `m=80` and `90` accepted |
| [Eleven sizes](../apmi_null_m_sweep/RESULTS.md) | 3 accepted, 8 rejected |
| [Nineteen sizes](../apmi_null_m_sweep/expanded_10m/RESULTS.md) | 5 accepted, 14 rejected |

The fixed GPD procedures did not reliably generalize across the tested sizes.
This motivated the separate empirical study; it does not invalidate historical
acceptance under its own gates or prove that every GPD approach fails.
These are null-calibration results, not biological edge-accuracy evidence.

## Archive provenance

`legacy_pr1/` remains a byte-preserving copy of the original PR source and compact
evidence. Its [manifest](legacy_pr1_manifest.json) retains source commits, sizes,
SHA-256 values and Git blob identities. Internal paths and runtime claims describe
that snapshot. Raw simulation payloads, builds and expression matrices stay local.
