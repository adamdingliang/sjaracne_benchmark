# Validated TCGA-LUAD expression acquisition

`download_tcga_luad.py` downloads released, open-access TCGA-LUAD primary-tumor
RNA-seq expression quantification files from GDC's **STAR - Counts** workflow.
A GDC token is not required for the selected open files. This is an acquisition
utility, not a completed LUAD benchmark: it does not normalize/build an
expression matrix, choose one file per patient, or invoke SJARACNe.

The script and its synthetic tests were imported from the original SJARACNe
workspace; source-file hashes are recorded in the repository's
[import manifest](../../provenance/import_manifest.json).

## Commands

Use Python 3.9+ and `requests` from the new repository root. Keep downloads
outside Git. For the original workstation, explicitly select `E:\TCGA_data`:

```powershell
Set-Location 'D:\GitHub\sjaracne_benchmark'
python -m pip install requests
python benchmarks/tcga_luad_download/download_tcga_luad.py --outdir 'E:\TCGA_data' --metadata-only
python benchmarks/tcga_luad_download/download_tcga_luad.py --outdir 'E:\TCGA_data' --max-files 1
python benchmarks/tcga_luad_download/download_tcga_luad.py --outdir 'E:\TCGA_data'
python benchmarks/tcga_luad_download/download_tcga_luad.py --outdir 'E:\TCGA_data' --verify-only
```

The actual unchanged CLI default is `downloads/TCGA_LUAD_STAR_Counts` relative
to the working directory, **not** `E:\TCGA_data`. `--metadata-only` and
`--verify-only` are mutually exclusive. `--max-files N` processes the first
N sorted file UUIDs for a smoke test; it is not a biological cohort-selection
rule. `--page-size` defaults to 100 and whole-file `--attempts` to 3.
The commands above are examples, not downloads performed during migration.

## Frozen cohort and validation

The first metadata query validates pagination, uniqueness/order of file
UUIDs and GDC release consistency before publishing `query_snapshot.json`.
Every selected file must match the open/released RNA-seq STAR Counts protocol
and have unambiguous case, primary-tumor sample and aliquot associations.
Subsequent runs reuse the snapshot, checking its schema, protocol and stored
metadata SHA-256. They do not silently re-query a changed cohort. Use a fresh
output directory to acquire a later GDC release.

For each selected expression file, validation checks:

- Exact GDC byte size and MD5, plus a recorded local SHA-256.
- The expected augmented STAR Counts TSV header and well-formed rows.
- Nonnegative integer count fields, finite/nonnegative normalized fields,
  valid unique gene identifiers, and complete STAR `N_*` summary rows.
- Identical gene model, annotation and row order across validated cohort files.

Valid completed downloads are checked before being skipped. In normal
download mode an invalid existing file is replaced only after a newly
downloaded temporary file passes validation. Retries restart whole files;
unchecked partial bytes are not resumed. In `--verify-only` mode, files are
validated offline and never downloaded/replaced. That mode still regenerates
the tool's metadata summaries and validation report, so it is not a
read-only archival audit.

Outputs are `query_snapshot.json`, `metadata.tsv`, `gdc_manifest.tsv`,
`cohort_summary.json`, `validation_report.json`, and count files under
`files/<file_id>/<file_name>`. Metadata-only mode does **not** validate count
files. A smoke subset can pass while `complete_cohort` remains false; failures
are explicit in the validation report and return a nonzero exit code.
The report records script/environment metadata alongside per-file hashes.

Known imported validation gap: the current parser records header comments and
compares the gene-model fingerprint but does not reject a missing gene-model
comment. The synthetic missing-comment test fails identically in the original
workspace and this copy (25 of 26 tests pass). No downloader code was changed
during migration, and this test failure does not establish that any real
downloaded file is invalid. Do not regard the current utility as passing its
entire validation contract until that gap is addressed separately.

All matching files are retained. `cohort_summary.json` flags repeated cases,
samples and aliquots; choose the biological sample policy before constructing
a benchmark input matrix. STAR summary rows are not expression genes.
Normalization, duplicate-gene handling and benchmarking parameters require
separate documented preparation.

## Older downloader archive

The distinct older implementation is preserved at
[archive/tcga_luad_gdc](../../archive/tcga_luad_gdc/README.md), originating from
commit `11554e3df24a9cf4730f5eecf797133efeb26c0c` in the SJARACNe LUAD worktree.
It has a different snapshot/layout and reuse contract. Do not treat these
scripts or their output directories as interchangeable, and do not use both
on the same existing cohort directory.

Run the current utility's offline synthetic tests without downloads:

```powershell
python -m unittest discover -s benchmarks/tcga_luad_download -p 'test_*.py' -v
```

Sources: [GDC Search and Retrieval](https://docs.gdc.cancer.gov/API/Users_Guide/Search_and_Retrieval/),
[Downloading Files](https://docs.gdc.cancer.gov/API/Users_Guide/Downloading_Files/),
and [mRNA pipeline](https://docs.gdc.cancer.gov/Data/Bioinformatics_Pipelines/Expression_mRNA_Pipeline/).
Data/source terms remain separate from this repository's benchmark code;
see [licensing/attribution status](../../docs/LICENSING.md).
