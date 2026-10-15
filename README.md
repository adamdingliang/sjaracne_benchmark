# SJARACNe benchmarking

Dedicated research benchmarks and analysis evidence for [SJARACNe](https://github.com/adamdingliang/SJARACNe). This repository is private during the initial migration and rights/portability review.

## Benchmark index

| Work | Question / reference | Entry point |
| --- | --- | --- |
| DREAM5 Network 1 | Direct-edge recovery on a simulated network; sampling with versus without replacement | [Workflow and results](benchmarks/dream5_network1/README.md) |
| THP-1 Perturb-seq | Recovery of reconstructed perturbation responses; not direct-edge ground truth or an exact Fig. 6a reproduction | [Workflow, notebooks and latest evidence](benchmarks/thp1_perturbseq/README.md) |
| BRCA100 threshold sweep | Density, driver coverage and topology across bootstrap MI thresholds | [Combined sweep](benchmarks/brca100_pr67_threshold_sweep/COMBINED_RESULTS.md) |
| BRCA100 consensus recurrence | Evidence for an explicit minimum recurrence rule, including K=6 | [Recurrence analysis](benchmarks/brca100_consensus_recurrence_sweep/README.md) |
| BRCA100 hub-size / DPI | Technical dependence of pruning on the available hub list | [Mechanism and limitations](benchmarks/brca100_hub_size_dpi_analysis/README.md) |
| BRCA100 matched network QC | Matched workflow and NetBID2 summaries | [QC package](benchmarks/brca100_netbid_qc/README.md) |
| TCGA LUAD | One public-expression acquisition workflow; no completed LUAD network benchmark yet | [Downloader and tests](benchmarks/tcga_luad_download/README.md) |

## What moved, and what did not

The first migration copies benchmark code, tests, notebooks, compact reports, plots and provenance. The original repositories/worktrees and local run archives remain intact. Small DREAM5 inputs already bundled with the original benchmark are retained with their separate source-data terms. Large THP-1/TCGA data, expression/reference matrices, native networks, native builds and R environments are not uploaded.

The engine, consensus implementation, calibration implementation, native regression tests and performance microbenchmarks remain in SJARACNe. This is not a second implementation of SJARACNe.

Historical artifacts retain the commits, paths, hashes and definitions that generated them. Importing a file here does not establish that its historical runner is portable, that the original result has been rerun, or that a missing author intermediate has been recovered. See [migration status and compatibility](docs/MIGRATION.md), [local data policy](docs/DATA.md), and [licensing/attribution status](docs/LICENSING.md).

## Lightweight checks

Use Python 3.11+; dataset-specific requirements remain next to their workflows. Verification and synthetic tests do not launch inference or download data.

```powershell
python scripts/verify_migration.py
python scripts/check_benchmarks.py
```

The source import is recorded per file in [provenance/import_manifest.json](provenance/import_manifest.json). The report of checks performed during this migration is in [docs/VALIDATION.md](docs/VALIDATION.md).

The initial migration checks collected 353 distinct tests: 346 passed, six were skipped for compiler/symlink prerequisites, and one pre-existing LUAD parser test fails in both the original and migrated copies. The root check command reports that failure; it is not hidden or treated as a successful validation. LUAD has since been consolidated into one benchmark folder; see the [consolidation and current checks](docs/LUAD_CONSOLIDATION.md).

MI-cutoff tuning and a new THP-1 pre-DPI comparison remain deferred. No new scientific benchmark runs are part of this migration.
