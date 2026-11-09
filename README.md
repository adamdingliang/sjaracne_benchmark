# SJARACNe2 benchmarks

Research benchmarks, dataset preparation and analysis evidence for
[SJARACNe2](https://github.com/adamdingliang/SJARACNe2). The engine is maintained
separately and does not depend on this repository.

## SJARACNe versus SJARACNe2

Matched-input comparisons cover 18 DREAM settings and the TF/SIG networks of
BRCA100, TCGA-LUAD517 and TCGA-BLCA406. The baseline is legacy SJARACNe before
the sampling change; SJARACNe2 uses the consensus-first develop workflow.

| Guide | Contents |
| --- | --- |
| [Comparison report](benchmarks/legacy_vs_sjaracne2_2026-11-09/README.md) | Workflow definitions, accuracy, target coverage, topology and provenance. |
| [ROC figures and AUROC tables](benchmarks/legacy_vs_sjaracne2_2026-11-09/roc/README.md) | DREAM final-network ROC curves, full-range AUROC and low-FPR zooms. |
| [Four bar plots](benchmarks/legacy_vs_sjaracne2_2026-11-09/bars/README.md) | DREAM precision/F1 and bulk median targets/adjusted scale-free R². |

Figures are available as PNG, PDF and SVG, with exact values in linked tables.

## Benchmark index

Rows identify datasets; linked studies describe their experiments. Reusing a
dataset for parameter sweeps does not add independent benchmark evidence.

### DREAM

| Dataset | Reference and scope | Guides and results |
| --- | --- | --- |
| DREAM5 Network 1 | Simulated expression with a supplied directed gold network. | [Data and sampling study](benchmarks/dream5_network1/README.md); [consensus-order comparison](benchmarks/consensus_before_dpi/README.md). |
| DREAM5 Network 3 (E. coli) | Real expression; incomplete strong-evidence RegulonDB reference. | [Data and sampling study](benchmarks/dream5_network3/README.md); [consensus-order comparison](benchmarks/consensus_before_dpi/README.md). |
| DREAM5 Network 4 (yeast) | Real expression; incomplete binding/conservation reference. | [Data preparation](benchmarks/dream5_network4/README.md); [completed consensus-order comparison](benchmarks/consensus_before_dpi/README.md). |
| DREAM5 Systems Genetics A | Fifteen distinct 1,000-gene simulations with model-defined gold networks. | [Data and evaluation scope](benchmarks/dream5_systems_genetics_a/README.md); [completed comparison](benchmarks/consensus_before_dpi/README.md). |

### Bulk

| Dataset | Cohorts and evaluation scope | Guides and results |
| --- | --- | --- |
| BRCA100 | One 100-profile dataset; TF/SIG coverage and topology QC, without edge-level truth. | [Cohort](docs/BULK_DATASETS.md#brca100); [latest native results](benchmarks/native_bulk_2026-11-09/README.md); [historical study catalog](benchmarks/brca100_studies/README.md). |
| TCGA-LUAD | LUAD100 subset and LUAD517 full-cohort studies; descriptive network QC. | [Cohorts](docs/BULK_DATASETS.md#tcga-luad); [latest LUAD517 results](benchmarks/native_bulk_2026-11-09/README.md); [LUAD100 DPI study](docs/benchmark_summaries/common_tf_sig_sources.md). |
| TCGA-BLCA | BLCA406 primary-tumor cohort; separate from MIBC372; descriptive network QC. | [Cohort](docs/BULK_DATASETS.md#tcga-blca); [latest BLCA406 results](benchmarks/native_bulk_2026-11-09/README.md); [earlier comparison](benchmarks/consensus_before_dpi/README.md). |

### Single-cell

| Dataset | Reference and scope | Guides and results |
| --- | --- | --- |
| THP-1 Perturb-seq | Historical non-targeting-cell metacells evaluated against a reconstructed perturbation-response reference. | [Study](benchmarks/thp1_perturbseq/raw_mi/README.md); [100-pair results](benchmarks/thp1_perturbseq/raw_mi/results_2026-10-15_full100/REPORT.md). |

No established single-cell direct-edge gold-standard benchmark is included.
THP-1 response-associated ranking is exploratory evidence for a different task.

## Engineering studies

| Study | Scope | Guide |
| --- | --- | --- |
| AP-MI/PCHIP calibration | Independent-rank nulls; cutoff calibration, not biological edge accuracy. | [Broad-grid process and results](benchmarks/apmi_null_m_sweep/broad_grid_10m/README.md). |
| Earlier calibration candidates | GPD, quadratic and probability-axis explorations. | [Calibration history](benchmarks/apmi_null_m_sweep/README.md); [GPD archive](benchmarks/apmi_null_gpd_exploratory/README.md). |
| DPI context sensitivity | Historical fixed/dynamic/no-DPI comparisons and common-source consistency. | [DPI summaries](docs/benchmark_summaries/README.md). |
| Engine performance | Historical timing, memory and sampling-method evidence. | [Archive index](engine_performance/README.md). |

## Documentation

| Guide | What it covers |
| --- | --- |
| [Bulk datasets](docs/BULK_DATASETS.md) | Cohorts, reused studies and comparison boundaries. |
| [Data and artifacts](docs/DATA.md) | Distributed inputs, local archives and provenance. |
| [Licensing and attribution](docs/LICENSING.md) | Source notices and dataset-specific terms. |
| [Migration and portability](docs/MIGRATION.md) | Original imports, integrity guards and external-engine paths. |
| [Validation](docs/VALIDATION.md) | Integrity checks, synthetic tests and known gaps. |
| [BRCA100 compatibility](docs/BRCA100_COMPATIBILITY.md) | Historical runner assumptions and external fixtures. |
| [LUAD utility history](docs/LUAD_CONSOLIDATION.md) | Downloader consolidation and validation limits. |
| [Source cleanup history](docs/SOURCE_CLEANUP.md) | Dated engine/archive separation. |

## Repository checks

Verify archive preservation without launching inference:

```powershell
python scripts/verify_migration.py
python scripts/verify_engine_archive.py
python scripts/check_benchmarks.py --group migration
```

The [validation guide](docs/VALIDATION.md) records full-group status and the
known LUAD downloader test failure.

Large raw data, generated expression matrices, native graphs and environments
remain external. Frozen reports retain their original definitions, paths and
hashes; current guides provide navigation without rewriting those records.
