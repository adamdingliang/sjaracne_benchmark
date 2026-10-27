> Publication copy of a frozen local report/process. Scientific text and numbers are unchanged; relative links are adapted to this compact package. See [publication provenance](PUBLICATION.json) for original hashes and [local artifacts](README.md#local-artifacts) for omitted sidecars.

# TCGA-LUAD gene-level TPM preparation

Protocol recorded 2026-10-26 before matrix construction and IQR outcome inspection.
The user requested direct log transformation and the NetBID2 IQR rules, without
calling `SJAracne.prepare()`, with outputs under `E:\TCGA\LUAD\`.

## Scope

Prepare expression inputs only. No SJARACNe inference, network benchmarking,
dynamic-epsilon anchor selection, consensus, calibration, new downloads,
annotation refresh, Git staging/commit/push or PR update is included.
Preserve all original downloads at `E:\TCGA\_data\` unchanged.

## Inputs and cohort

- Use the existing open-access TCGA-LUAD primary-tumor STAR augmented count files
  and frozen `metadata.tsv` / `query.json` download snapshot.
- Validate all 540 metadata files, not just the eventual selected cohort:
  safe paths, byte sizes and GDC MD5, recorded SHA-256, expected nine columns,
  mandatory consistent gene-model comment, four STAR `N_*` summary rows,
  valid nonnegative count/abundance values, unique ordered gene IDs and identical
  annotation/row order across files. Fail on mismatch, never replace downloads.
- Choose ONE file per patient to avoid overweighting repeated patient samples.
  Sort within each patient by `(sample_id, file_name, file_id)` and select the
  first. This is deterministic selection, not a biological/technical quality
  ranking. Save all 540 records, selected/excluded decisions and the 517-patient
  mapping. Input inspection identifies 517 distinct patients/529 sample IDs;
  selected barcodes are 514 type 01A and three type 01B.
- Use all 517 selected patients; do NOT choose a 100-patient pilot or resample.
  Future inference on a subset needs a separately documented design. This full-
  cohort feature selection is not held-out validation of patient subsets.

## Gene IDs and regulator annotations

- Use `tpm_unstranded`, already provided at gene level. Discard the four `N_*`
  summary rows from expression, not biological gene rows.
- Keep one row per stable Ensembl gene identifier. Strip only its numeric version,
  preserving `_PAR_Y` suffixes. Fail if this creates collisions; do not average
  distinct gene IDs that share a symbol. Keep source versioned ID, symbol and
  gene type in a separate annotation table.
- Use the installed, frozen NetBID2 human gene-level lists:
  `HUMAN_TF_ensembl_gene_id.txt` and `HUMAN_SIG_ensembl_gene_id.txt`, from the
  pinned 2.2.0 environment. Record/copy their contents and hashes. No network
  lookup or opportunistic remapping. Record absent IDs and each mapping outcome.
- Do not introduce a protein-coding-only restriction. Retain the input gene types
  subject only to the explicit all-zero/IQR rules below.

## Transform and filter once

1. Assemble the gene-by-patient TPM matrix in one common gene order. Save it and
   `log2(TPM + 1)` for all gene rows, including all-zero genes for traceability.
2. Exclude all-zero genes from the population used to calculate IQR thresholds.
   Removing zeros before versus after `log2(TPM + 1)` is equivalent here.
3. For each remaining gene calculate `Q75 - Q25` across all 517 patients on the
   LOG-TRANSFORMED values. Use R type-7 / NumPy `method='linear'` quantiles.
4. Calculate two GLOBAL quantiles over those per-gene IQRs: q50 and q10.
   Retain a gene if `IQR > q50`, OR if it belongs to the full TF/SIG union and
   `IQR > q10`. Both comparisons are strictly greater; tied values may change
   the nominal retained fractions. These are not separately calculated TF/SIG
   quantiles and q10 does not mean retaining only the top 10% of regulators.
5. Save every gene's zero flag, IQR, regulator membership, filter flags and final
   retained/excluded decision. Do not additionally apply the tutorial's separate
   bottom-5%-expression rule: the user asked for log transformation plus IQR.
6. Export one fixed filtered matrix and intersect BOTH full regulator lists with
   its row IDs. Save TF, SIG and shared-source lists in expression-row order.
   Never repeat filtering for different hub subsets; that would change the
   regulator-aware filter and confound subsequent DPI comparisons.

No quantile normalization, count renormalization, transcript aggregation,
symbol collapsing, imputation or additional expression threshold is applied.
The log transform preserves within-gene ranks in exact arithmetic but changes
IQR-based feature selection. Retain binary64 precision in exports (17 significant
digits) and verify serialized matrices, not just in-memory results.

## Outputs, provenance and validation

Write only into a NEW `E:\TCGA\LUAD\` output directory. Refuse any existing
directory; incomplete outputs must remain visible with a failed/incomplete status
instead of being overwritten or presented as complete. Copy the protocol,
preparation code/tests and regulator lists into output provenance.

Primary outputs: compressed unfiltered TPM and log2(TPM+1) matrices,
`LUAD_filtered.exp` with `isoformId`, `geneSymbol` and patient columns, retained
TF/SIG/shared lists, gene annotations, complete gene-filter decisions, raw-file
validation records and sample selection. The legacy `isoformId` header is a
SJARACNe format convention; these rows represent genes.

Record source and output hashes, timestamps, software versions, exact numeric
cutoffs, shapes and retained gene/regulator counts. A complete preparation is
not a completed network analysis. An independent validator must re-read all
exported numeric cells, recompute log/IQR/strict cutoffs and list intersections,
verify hashes and patient uniqueness, and compare original TPM values for
predeclared first/middle/last selected patients. Its raw-content spot-check
coverage must be explicit; the preparer separately checks all 540 raw files.

## References

- NetBID2 network reconstruction tutorial:
  https://jyyulab.github.io/NetBID/docs/network_reconstruction
- GDC gene-level STAR/TPM pipeline:
  https://docs.gdc.cancer.gov/Data/Bioinformatics_Pipelines/Expression_mRNA_Pipeline/
- Installed NetBID2 2.2.0 source inspection, commit
  `5defa454d600b94f5dd6d1f9f4428f99759a6821`, confirms all-zero exclusion,
  strict global IQR quantiles and regulator-aware filtering. This preparation
  reimplements those numeric rules; it does not invoke NetBID2 or its old shell
  command generator.
