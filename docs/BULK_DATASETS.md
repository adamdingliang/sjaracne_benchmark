# Bulk datasets and study snapshots

The bulk index has one row per dataset. Parameter sweeps, TF/SIG panels and
workflow comparisons reuse those data; they are not additional independent
benchmark datasets. Bulk studies report coverage, stability and topology,
without independent edge-level truth.

## BRCA100

The bundled 100-profile expression matrix has 28,278 feature rows. The full
panels contain 2,608 TF and 10,680 SIG source IDs. TF and SIG use the same
expression cohort. Historical descriptions of a "current PCHIP" workflow
refer to their recorded October 2026 versions.

- [Latest completed native TF/SIG networks](../benchmarks/native_bulk_2026-11-09/README.md)
- [Dated BRCA100 study catalog](../benchmarks/brca100_studies/README.md)
- [Earlier consensus-order comparison](../benchmarks/consensus_before_dpi/README.md)

## TCGA-LUAD

Keep the two preparations distinct:

| Preparation | Profiles | Purpose |
| --- | ---: | --- |
| LUAD100 | 100 patient-distinct tumors | Common-source TF/SIG panel and DPI-tolerance studies; 477 shared sources. |
| LUAD517 | 517 primary-tumor profiles | Full-cohort TF/SIG consensus-order and native workflow studies. |

The LUAD517 matrix has 29,841 gene rows, 1,929 TF and 9,464 SIG sources.
LUAD100 is a subset analysis, not a second independent dataset. Its feature
selection used the prepared 517-patient cohort.

- [Latest native LUAD517 results](../benchmarks/native_bulk_2026-11-09/README.md)
- [LUAD100 panel/tolerance results](benchmark_summaries/common_tf_sig_sources.md)
- [Acquisition utility and protocol](../benchmarks/tcga_luad_download/README.md)

## TCGA-BLCA

BLCA406 is the prepared primary-tumor cohort used in the bulk benchmark: 406
profiles, 29,778 gene rows, 1,920 TF and 9,428 SIG sources. The separate
T2-T4 MIBC372 preparation is **not** the cohort used in these tables.

- [Latest native BLCA406 results](../benchmarks/native_bulk_2026-11-09/README.md)
- [Earlier BLCA406 consensus-order results](../benchmarks/consensus_before_dpi/README.md)

## Comparing studies

Match cohort, expression representation, hub list, sampling, cutoff, consensus
order/K and DPI settings before comparing topology numbers. Probe-level
BRCA100 and gene-level TCGA source counts are not interchangeable. The
[historical DPI summaries](benchmark_summaries/README.md) used zero-offset,
pre-consensus designs; they do not describe the later native +0.025 batch.
