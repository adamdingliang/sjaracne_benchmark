# Historical GPD null calibration (exploratory)

This entry preserves the GPD route explored before the empirical PCHIP surface.
It is **not the current SJARACNe runtime proposal** and is not evidence for a
generally calibrated GPD function across sample sizes.
The revised [engine PR #1](https://github.com/adamdingliang/SJARACNe/pull/1)
instead proposes an experimental, opt-in bundled PCHIP callable while retaining
legacy defaults. This archive does not claim that proposal is merged.

## Process

- [Original PR #1 calibrator, exact-size models, tests and BRCA100 validation](legacy_pr1/benchmarks/apmi_null_calibration/README.md).
- [Eleven-size, 5M fitting + 5M validation protocol](../apmi_null_m_sweep/PLAN_2026-10-15.md).
- [Nineteen-size, 10M fitting + 10M validation protocol](../apmi_null_m_sweep/expanded_10m/PLAN_2026-10-15.md).

All calibrations use independent rank pairs with the shared AP-MI estimator,
not biological edge labels. The original PR's stability requirement at
`p=1e-7` differs from the later moderate-probability stability requirement;
their acceptance labels must not be pooled or retroactively relabeled.

## Results

- [Original six-size sweep](legacy_pr1/benchmarks/apmi_null_calibration/calibration_results_2026-08-12/calibration_summary.csv):
  the original gates accepted only `m=80` and `90`.
- [Eleven-size results](../apmi_null_m_sweep/RESULTS.md): 3 accepted, 8 rejected.
- [Nineteen-size results](../apmi_null_m_sweep/expanded_10m/RESULTS.md): 5 accepted, 14 rejected.

A fitted GPD did not reliably generalize across the tested sizes under those
fixed procedures. This motivated the separate [empirical PCHIP study](../apmi_null_m_sweep/broad_grid_10m/RESULTS.md),
not a claim that every possible GPD model fails. Historical accepted fits remain
accepted under their original tests; they are not biological validation or
direct proof of accuracy at `p=1e-7`.

## Archive provenance

`legacy_pr1/` is a byte-preserving copy of the original PR #1 source files and
compact evidence, made before removing GPD from its revised runtime proposal.
The [archive manifest](legacy_pr1_manifest.json) records the source commit,
per-file byte counts, working-copy SHA256 and Git blob identities. No raw
simulation payloads, build products or expression matrices are copied.
Historical documentation inside the archive retains its original paths and
runtime claims; it describes that snapshot, not the current implementation.
