# BRCA100 study guide

BRCA100 is one reused, 100-observation expression dataset. The studies below
change methods, parameters or hub panels; they are not independent cohorts.
They assess network coverage and topology without an edge-level gold standard.

## Current comparison

- [Completed native bulk batch, finalized 2026-11-09](../native_bulk_2026-11-09/README.md).
- [Dataset and cohort definitions](../../docs/BULK_DATASETS.md#brca100).
- [SJARACNe2 workflow defaults](https://github.com/adamdingliang/SJARACNe2/blob/develop/SJARACNe/wdl/README.md#default-parameter-values).

## Historical studies

| Date | Study | Report |
| --- | --- | --- |
| 2026-08-17 | Sampling/MI versions and NetBID2 QC | [Matched workflow](../brca100_netbid_qc/README.md#matched-workflow) and [results](../brca100_netbid_qc/results_2026-08-17/RESULTS.md) |
| 2026-08-19 | Per-resample MI threshold sweep | [Combined 13-point results](../brca100_pr67_threshold_sweep/COMBINED_RESULTS.md) |
| 2026-08-20 | Post-DPI recurrence K=6..20 with historical cutoffs | [Frozen sweep package](../brca100_consensus_recurrence_sweep/README.md) |
| 2026-08-25/26 | Hub-panel size and DPI witnesses | [Frozen analysis](../brca100_hub_size_dpi_analysis/README.md) and [interpretation notes](hub_dpi_notes.md) |
| 2026-10-17 | PCHIP refresh with per-resample DPI and probability consensus | [Process](../brca100_pchip_refresh/README.md) and [results](../brca100_pchip_refresh/results_2026-10-17/RESULTS.md) |
| 2026-10-18 | K6 versus probability consensus on fixed PCHIP post-DPI graphs | [Process](../brca100_pchip_recurrence/README.md) and [results](../brca100_pchip_recurrence/results_2026-10-18/RESULTS.md) |
| Imported 2026-11-08 | Earlier BRCA100/LUAD517/BLCA406 consensus-order comparison | [Historical study](../consensus_before_dpi/README.md) |

## Reading the archived records

Labels such as "current PCHIP", "proposed K6" and software defaults describe the
recorded date, not today's workflow. The August studies use pre-PCHIP cutoffs;
the October PCHIP studies still apply DPI before consensus. The frozen
18-row bulk comparison predates the native +0.025 batch linked above.

Recorded tables, protocols, source pins and checksums remain unchanged. Some
entry READMEs are themselves included in migration or package manifests, so
this guide supplies current navigation without rebinding historical evidence.
Absolute paths and commands in those records describe their original runtimes;
they are not portable installation instructions.
