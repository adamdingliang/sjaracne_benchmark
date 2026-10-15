# SJARACNe benchmarking

Dedicated research benchmarks and analysis evidence for [SJARACNe](https://github.com/adamdingliang/SJARACNe). This repository is private during the initial migration and rights/portability review.

## Benchmark index

| Network data | Question | Reference | Benchmark process and results |
| --- | --- | --- | --- |
| DREAM5 Network 1 | How does sampling affect recovery of known directed edges? | [DREAM5 challenge](https://zenodo.org/records/17854236), Marbach et al. (2012): simulated expression and a supplied gold-standard network. [Input provenance](benchmarks/dream5_network1/DATA_LICENSE.md). | [Process](benchmarks/dream5_network1/README.md) · [Results](benchmarks/dream5_network1/RESULTS.md) |
| THP-1 Perturb-seq | Does sampling improve recovery of perturbation-responsive targets? | Yao et al. conventional CRISPRi screen, [GSM6858449](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM6858449): networks inferred from non-targeting-cell metacells; response labels reconstructed following scMINER, not direct-edge truth or exact Fig. 6a reproduction. | [Process](benchmarks/thp1_perturbseq/author_reconstruction/SAMPLING_COMPARISON.md#matched-design) · [Results](benchmarks/thp1_perturbseq/evidence/author_reconstruction_20261011/sampling_comparison_20261013/REPORT.md) |
| BRCA100 (TF/SIG) | How do bootstrap MI thresholds affect density, driver coverage and topology? | SJARACNe's bundled `BRCA100.exp` and TF/SIG lists; inferred networks with no independent edge-level reference. [Input provenance](benchmarks/brca100_consensus_recurrence_sweep/results_2026-08-20/provenance/design.json). | [Process](benchmarks/brca100_pr67_threshold_sweep/README.md) · [Results](benchmarks/brca100_pr67_threshold_sweep/COMBINED_RESULTS.md) |
| BRCA100 (TF/SIG) | What changes when consensus uses minimum recurrence, including K=6? | Same BRCA100 expression and hub lists; reuses fixed post-DPI bootstrap networks. No independent edge-level reference. | [Process](benchmarks/brca100_consensus_recurrence_sweep/README.md#matched-design) · [Results](benchmarks/brca100_consensus_recurrence_sweep/results_2026-08-20/RESULTS.md) |
| BRCA100 (TF/SIG) | How does hub-list size affect DPI pruning? | Same BRCA100 expression; TF/SIG hub-list sizes varied. No independent edge-level reference. | [Process](benchmarks/brca100_hub_size_dpi_analysis/README.md#evidence-and-provenance) · [Results](benchmarks/brca100_hub_size_dpi_analysis/README.md#matched-100-seed-pilot) |
| BRCA100 (TF/SIG) | How do matched workflow versions differ in network QC? | Same BRCA100 inputs; inferred networks compared using NetBID2 summaries, not biological ground truth. | [Process](benchmarks/brca100_netbid_qc/README.md#matched-workflow) · [Results](benchmarks/brca100_netbid_qc/results_2026-08-17/RESULTS.md) |
| TCGA-LUAD | Acquire validated expression inputs for a future network benchmark. | GDC TCGA-LUAD primary-tumor bulk RNA-seq, STAR - Counts. Expression acquisition only; no network or edge-reference benchmark completed yet. | [Process](benchmarks/tcga_luad_download/README.md#commands) · [Results](benchmarks/tcga_luad_download/README.md#benchmark-results) (pending) |

**Reference** identifies the input-data source and, where available, the edge or
perturbation-response reference used for evaluation. It does not imply that
every dataset has a gold-standard network.

## Engineering evidence

Historical engine timing studies, reusable performance tools and the original
sampling-method evidence are preserved separately in
[Engineering performance and sampling-method archive](engine_performance/README.md).
They are not additional biological network benchmarks. Its
[process/results index](engine_performance/README.md#process-and-results) and
[per-file provenance](provenance/engine_archive_manifest.json) identify the
original measurements and source versions.

## What moved, and what did not

The first migration copies benchmark code, tests, notebooks, compact reports, plots and provenance. Original PR branches/worktrees and local run archives are retained; subsequent source-repository housekeeping is recorded in [source cleanup](docs/SOURCE_CLEANUP.md). Small DREAM5 inputs already bundled with the original benchmark are retained with their separate source-data terms. Large THP-1/TCGA data, expression/reference matrices, native networks, native builds and R environments are not uploaded.

The engine, consensus implementation, calibration implementation and native regression tests remain in SJARACNe. Historical performance tools/evidence now live in `engine_performance/`; the engine retains only the small correctness fixtures needed by its tests. This is not a second implementation of SJARACNe, and the engine has no dependency on this repository.

Historical artifacts retain the commits, paths, hashes and definitions that generated them. Importing a file here does not establish that its historical runner is portable, that the original result has been rerun, or that a missing author intermediate has been recovered. See [migration status and compatibility](docs/MIGRATION.md), [local data policy](docs/DATA.md), and [licensing/attribution status](docs/LICENSING.md).

## Lightweight checks

Use Python 3.11+; dataset-specific requirements remain next to their workflows. Verification and synthetic tests do not launch inference or download data.

```powershell
python scripts/verify_migration.py
python scripts/verify_engine_archive.py
python scripts/check_benchmarks.py
```

The source import is recorded per file in [provenance/import_manifest.json](provenance/import_manifest.json). The report of checks performed during this migration is in [docs/VALIDATION.md](docs/VALIDATION.md).

The later engine archive is recorded separately in
[provenance/engine_archive_manifest.json](provenance/engine_archive_manifest.json);
it does not rewrite the initial scientific migration's frozen records.

The initial migration checks collected 353 distinct tests: 346 passed, six were skipped for compiler/symlink prerequisites, and one pre-existing LUAD parser test fails in both the original and migrated copies. The root check command reports that failure; it is not hidden or treated as a successful validation. LUAD has since been consolidated into one benchmark folder; see the [consolidation and current checks](docs/LUAD_CONSOLIDATION.md).

MI-cutoff tuning and a new THP-1 pre-DPI comparison remain deferred. No new scientific benchmark runs are part of this migration.
