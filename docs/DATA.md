# Data and artifact policy

Keep code, tests, compact tables/reports, plots and provenance in Git. Keep raw or large data, derived expression/reference matrices, bootstrap/consensus edge files, native builds and environments outside Git. New run outputs go under ignored `runs/` or an explicit external directory.

The DREAM5 source-data bundles are explicit exceptions. Network 1 retains approximately 28.4 MiB including its historical expression-format conversion. Network 3 adds approximately 37 MiB of unmodified source files and metadata; its expression-format conversion is generated locally rather than duplicated in Git. See each benchmark's `DATA_LICENSE.md`; bundled status is not a general permission to redistribute other datasets.

## Existing local archives (unchanged)

| Content | Current location |
| --- | --- |
| THP-1 public source data and source-data workbook | `E:\SpaGRN\SJARACNe\Perturb-seq\THP1_GSM6858449` |
| THP-1 prepared matrices/reference, 200 native networks and completed scoring | `D:\GitHub\SJARACNe\benchmarks\thp1_perturbseq\results\author_reconstruction_20261011` |
| THP-1 pinned sources/builds and R/toolchain environment | `D:\GitHub\_datasets\THP1_reconstruction` |
| DREAM5 original acquisition/pilot archive | `D:\GitHub\_datasets\DREAM5_Network1` |
| DREAM5 yeast Network 4 raw source members, prepared expression and audit | `D:\GitHub\_datasets\DREAM5_Network4` |
| DREAM5 Systems Genetics A source archives and acquisition receipts | `D:\GitHub\_datasets\DREAM5_SysGenA` |
| LUAD download destination used previously | `E:\TCGA_data` (verify the intended snapshot before reuse) |

These are local-location notes, not instructions to move or delete anything. Imported manifests may refer to additional original BRCA100 paths. Their recorded paths/hashes are preserved. Compact evidence has a separate import record; its existence here does not mean all dependencies of an original manifest were uploaded.

For future larger benchmark datasets, store immutable releases externally and record source URLs, accession/version, retrieval time, checksums, eligibility and preprocessing. Choose GitHub Releases, an institutional store, or a data repository only after reviewing size, license and privacy constraints. No new external data service is configured during this migration.

## New DREAM5 data additions (2026-11-07)

Network 4 and Systems Genetics A follow the existing source-member/provenance conventions, with large raw sources and generated expression matrices stored externally. The repository contains acquisition/preparation instructions, source hashes, reference definitions and validation code or receipts; no new inference results are claimed.

Network 4 was acquired from the same checksum-verified challenge archive used for Networks 1 and 3. Its seven source files remain byte-identical, and its locally prepared expression preserves the original numeric strings. The full 333-TF candidate list is retained independently of the smaller scored reference. See [Network 4](../benchmarks/dream5_network4/README.md).

Systems Genetics A is a separate DREAM5 subchallenge. Its 15 gold networks have been recovered from an archived original public ZIP, with receipts that distinguish the original URL from the archival retrieval URL. The three expression/genotype ZIPs still require an authenticated Synapse download; they are not marked acquired. Its simulated truth is complete within the specified model; expression-only SJARACNe evaluation would omit genotype information available to original challenge participants. See [Systems Genetics A](../benchmarks/dream5_systems_genetics_a/README.md) for the actual download and validation status.

The N1/N3 source-bundling exceptions above are unchanged. The two new datasets do not introduce a new raw-data redistribution exception or relicense their source materials.
