# SJARACNe benchmarking

Dedicated research benchmarks and analysis evidence for [SJARACNe](https://github.com/adamdingliang/SJARACNe). This repository is private during the initial migration and rights/portability review.

## Benchmark index

| Network data | Question | Reference | Benchmark process and results |
| --- | --- | --- | --- |
| DREAM5 Network 1 | How does sampling affect recovery of known directed edges? | [DREAM5 challenge](https://zenodo.org/records/17854236), Marbach et al. (2012): simulated expression and a supplied gold-standard network. [Input provenance](benchmarks/dream5_network1/DATA_LICENSE.md). | [Process](benchmarks/dream5_network1/README.md) · [Results](benchmarks/dream5_network1/RESULTS.md) |
| DREAM5 Network 3 — E. coli | How does sampling affect reference-edge recovery from real expression data? | [DREAM5 challenge](https://zenodo.org/records/17854236): real microarrays and a strong-evidence RegulonDB reference. The reference is incomplete. [Input provenance](benchmarks/dream5_network3/DATA_LICENSE.md). | [Process](benchmarks/dream5_network3/README.md) · [Results](benchmarks/dream5_network3/RESULTS.md) (three seeds, four sampling configurations; raw MI and DPI) |
| THP-1 Perturb-seq | Does sampling improve raw-MI ranking of perturbation-responsive targets? | Yao et al. conventional CRISPRi screen, [GSM6858449](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM6858449): inference from non-targeting-cell metacells; a reconstructed response reference, not direct-edge truth or exact Fig. 6a reproduction. | [Process](benchmarks/thp1_perturbseq/raw_mi/README.md) · [Results](benchmarks/thp1_perturbseq/raw_mi/results_2026-10-15_full100/REPORT.md) (primary, 100 matched pairs) |
| BRCA100 (TF/SIG) | How do bootstrap MI thresholds affect density, driver coverage and topology? | SJARACNe's bundled `BRCA100.exp` and TF/SIG lists; inferred networks with no independent edge-level reference. [Input provenance](benchmarks/brca100_consensus_recurrence_sweep/results_2026-08-20/provenance/design.json). | [Process](benchmarks/brca100_pr67_threshold_sweep/README.md) · [Results](benchmarks/brca100_pr67_threshold_sweep/COMBINED_RESULTS.md) |
| BRCA100 (TF/SIG) | What changes when consensus uses minimum recurrence, including K=6? | Same BRCA100 expression and hub lists; reuses fixed post-DPI bootstrap networks. No independent edge-level reference. | [Process](benchmarks/brca100_consensus_recurrence_sweep/README.md#matched-design) · [Results](benchmarks/brca100_consensus_recurrence_sweep/results_2026-08-20/RESULTS.md) |
| BRCA100 (TF/SIG) | How does hub-list size affect DPI pruning? | Same BRCA100 expression; TF/SIG hub-list sizes varied. No independent edge-level reference. | [Process](benchmarks/brca100_hub_size_dpi_analysis/README.md#evidence-and-provenance) · [Results](benchmarks/brca100_hub_size_dpi_analysis/README.md#matched-100-seed-pilot) |
| BRCA100 (TF/SIG) | How do matched workflow versions differ in network QC? | Same BRCA100 inputs; inferred networks compared using NetBID2 summaries, not biological ground truth. | [Process](benchmarks/brca100_netbid_qc/README.md#matched-workflow) · [Results](benchmarks/brca100_netbid_qc/results_2026-08-17/RESULTS.md) |
| TCGA-LUAD | Acquire validated expression inputs for a future network benchmark. | GDC TCGA-LUAD primary-tumor bulk RNA-seq, STAR - Counts. Expression acquisition only; no network or edge-reference benchmark completed yet. | [Process](benchmarks/tcga_luad_download/README.md#commands) · [Results](benchmarks/tcga_luad_download/README.md#benchmark-results) (pending) |

**Reference** identifies the input-data source and, where available, the edge or
perturbation-response reference used for evaluation. It does not imply that
every dataset has a gold-standard network.

The [E. coli pilot](benchmarks/dream5_network3/RESULTS.md) completed all 60
prospectively specified native jobs. At 80% sampling, median post-DPI Average
Precision increased from 0.042117 to 0.045776 and labeled FPs decreased from 3,242 to
2,134, but TPs decreased slightly from 206 to 200. Raw-MI AUROC barely changed
(0.6400 to 0.6409). This is a small exploratory precision/coverage tradeoff,
not uniform improvement or evidence for a new default.
The [E. coli reference is incomplete](benchmarks/dream5_network3/RESULTS.md#important-limitation-the-biological-reference-is-incomplete):
fewer benchmark-defined FPs does not prove that the removed edges were
biologically false, and the effect on biological precision is not established.

The primary THP-1 result is the **100-pair raw-MI comparison before filtering,
DPI or consensus**. Median TP@5,000 increased from 2,487.50 to 2,624.25 and
full-ranking AUROC from 0.6201 to 0.6659. This describes response-associated
ranking on fixed inputs, not improvement of the entire inference workflow.
The earlier [DPI/consensus comparison](benchmarks/thp1_perturbseq/evidence/author_reconstruction_20261011/sampling_comparison_20261013/REPORT.md)
and [post-DPI bootstrap diagnostic](benchmarks/thp1_perturbseq/evidence/author_reconstruction_20261011/bootstrap_tp_fp_20261013/REPORT.md)
remain unchanged as complementary evidence, including their TP-coverage losses.
The [20-pair pilot](benchmarks/thp1_perturbseq/raw_mi/results_2026-10-15_pilot20/README.md)
is retained as a historical snapshot; the [100-pair extension](benchmarks/thp1_perturbseq/raw_mi/EXTENSION_100.md)
was requested after reviewing it, not an independent validation set.

## Engineering evidence

The [expanded AP-MI null calibration process](benchmarks/apmi_null_m_sweep/expanded_10m/README.md)
and [results](benchmarks/apmi_null_m_sweep/expanded_10m/RESULTS.md) examine synthetic
independent-rank nulls at exact sample counts and the provisional probabilities
0.001 and 0.0005 using 10M fitting and 10M held-out draws at nineteen sizes.
The [earlier 5M study](benchmarks/apmi_null_m_sweep/RESULTS.md) is preserved.
This is estimator calibration, not another biological
network benchmark or a change to SJARACNe defaults.

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

No new scientific runs were part of the original migration. The subsequent
THP-1 raw-MI pilot and its completed 100-pair extension are linked above;
the later DREAM5 E. coli pilot is also linked above. MI-cutoff tuning remains
deferred.
