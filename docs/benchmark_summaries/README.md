# DPI epsilon benchmark summaries

These three summaries separate reference-edge recovery from engineering consistency across hub panels. They document exploratory benchmarks, not a change to SJARACNe's engine or defaults.

| Summary | Main question | Evidence boundary |
| --- | --- | --- |
| [1. DREAM5 Networks 1 and 3](https://github.com/adamdingliang/sjaracne_benchmark/blob/f4770ff52416e5d4c95a387c8b85b07f0237a885/docs/benchmark_summaries/dream5_dpi.md) | How do no DPI, fixed epsilon and dynamic epsilon affect precision, recall and reference-negative predictions? | Reference-scored networks; no dynamic-specific accuracy advantage established. |
| [2. Common TF/SIG sources in BRCA100 and LUAD100](https://github.com/adamdingliang/sjaracne_benchmark/blob/4b7a643135ffb6e754d7c59d677aafb9c555dce2/docs/benchmark_summaries/common_tf_sig_sources.md) | Do the same evaluated sources retain more consistent targets as their surrounding hub panels change? | Common-source context sensitivity, not biological accuracy or whole-source network scoring. |
| [3. Bulk strategy comparison and combined conditional conclusion](bulk_dpi_modes.md) | What balance do no DPI, fixed tolerance and dynamic tolerance offer, interpreted alongside DREAM5? | Reuses summary 2's bulk experiments; it is not independent additional replication. |

Each summary links to its detailed process, results and limitations. The combined conclusion supports an experimental engineering option, not a demonstrated universal accuracy improvement or a new default.
