# Data and artifact policy

Git holds code, compact reports/tables, plots and provenance. Raw data, large
expression/reference matrices, native graphs, builds and environments remain
external. Write new outputs under ignored `runs/` or an external directory.

DREAM5 Networks 1 and 3 are explicit bundling exceptions: approximately
28.4 MiB and 37 MiB respectively. N1 includes its historical expression
conversion; N3 conversion is generated locally. Their `DATA_LICENSE.md`
files retain the source terms; this is not a general redistribution policy.

## Recorded local archives

| Content | Current location |
| --- | --- |
| THP-1 public source data and source-data workbook | `E:\SpaGRN\SJARACNe\Perturb-seq\THP1_GSM6858449` |
| THP-1 prepared matrices/reference, 200 native networks and completed scoring | `D:\GitHub\SJARACNe\benchmarks\thp1_perturbseq\results\author_reconstruction_20261011` |
| THP-1 pinned sources/builds and R/toolchain environment | `D:\GitHub\_datasets\THP1_reconstruction` |
| DREAM5 original acquisition/pilot archive | `D:\GitHub\_datasets\DREAM5_Network1` |
| DREAM5 yeast Network 4 raw source members, prepared expression and audit | `D:\GitHub\_datasets\DREAM5_Network4` |
| DREAM5 Systems Genetics A sources, 15 prepared expression inputs and validation receipts | `D:\GitHub\_datasets\DREAM5_SysGenA` |
| TCGA-LUAD prepared cohort root | `E:\TCGA\LUAD` |
| TCGA-BLCA prepared cohort root | `E:\TCGA\BLCA` |
| Historical LUAD download destination | `E:\TCGA_data` (verify the snapshot before reuse) |

These workstation paths identify recorded archives, not public downloads or
portable defaults. Imported manifests retain additional original paths and
hashes. Cohort identities are summarized in [Bulk datasets](BULK_DATASETS.md).

For larger datasets, record source URL/accession, version, retrieval time,
checksums, eligibility and preprocessing alongside external immutable data.
No new data-hosting service is configured here.

## DREAM5 acquisition records (2026-11-07)

The [N4](../benchmarks/dream5_network4/README.md) and
[Systems Genetics A](../benchmarks/dream5_systems_genetics_a/README.md) guides
record source hashes and value-preserving preparation. Their raw sources and
generated matrices remain external. The [later consensus-order study](../benchmarks/consensus_before_dpi/README.md)
completed inference for both; acquisition-only status labels describe November 7.

N4 retains seven checksum-verified challenge members and the full 333-TF
candidate panel. SysGenA retains 15 validated expression/genotype/reference
sets, with positional sample-order mappings because source sample IDs are
absent. Expression-only scoring omits the genotype information available in
the original challenge. Source and archival access URLs remain distinguished.

The N1/N3 source-bundling exceptions above are unchanged. The two new datasets do not introduce a new raw-data redistribution exception or relicense their source materials.

## Completed native bulk batch

The [November 9 summary](../benchmarks/native_bulk_2026-11-09/README.md) records all
six BRCA100/LUAD517/BLCA406 TF/SIG outputs. Networks, raw MI and QC HTMLs remain
in the two documented local run roots; only aggregate results and recorded
network hashes are summarized here. Original run receipts are unchanged.
