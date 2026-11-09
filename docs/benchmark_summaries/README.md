# DPI epsilon benchmark summaries

Historical exploratory studies of reference-edge recovery and hub-panel
consistency. Their zero-offset, no-consensus designs do not describe the
later native consensus-first workflow.

| Summary | Main question | Evidence boundary |
| --- | --- | --- |
| [1. DREAM5 Networks 1 and 3](https://github.com/adamdingliang/sjaracne_benchmark/blob/2a121d17d0e34c7d1964e05bffb36c1b1d080ccf/docs/benchmark_summaries/dream5_dpi.md) | How do no DPI, fixed epsilon and dynamic epsilon affect precision, recall and reference-negative predictions? | Reference-scored networks; no dynamic-specific accuracy advantage established. |
| [2. Common TF and SIG sources in BRCA100 and LUAD100](https://github.com/adamdingliang/sjaracne_benchmark/blob/81ca0bb1ce7fcb97479e24e82a155e31e45fa383/docs/benchmark_summaries/common_tf_sig_sources.md) | Do the same evaluated sources retain more consistent targets as their surrounding hub panels change? | Common-source context sensitivity, not biological accuracy or whole-source network scoring. |
| [3. Bulk strategy comparison and combined conditional conclusion](bulk_dpi_modes.md) | What balance do no DPI, fixed tolerance and dynamic tolerance offer, interpreted alongside DREAM5? | Reuses summary 2's bulk experiments; it is not independent additional replication. |

Each summary links to its detailed process, results and limitations. The combined conclusion supports an experimental engineering option, not a demonstrated universal accuracy improvement or a new default.

## Later consensus-order study

The [completed consensus-before-DPI study](../../benchmarks/consensus_before_dpi/README.md)
compares five methods across 18 DREAM settings and records an earlier bulk QC
snapshot. It includes supporting-run mean MI, the +0.025 tolerance trial,
weighting sensitivity and native implementation equivalence. It is a separate,
later study rather than another presentation of the three DPI-epsilon summaries
above. The subsequent [native +0.025 bulk batch](../../benchmarks/native_bulk_2026-11-09/README.md)
completed all six arms on November 9; it is outside those frozen tables.
See [bulk cohort definitions](../BULK_DATASETS.md) before comparing studies.
