# TCGA-LUAD expression download for PR #70/#71 benchmarks

`download_luad_star_counts.py` retrieves public TCGA-LUAD RNA-Seq gene
expression quantification files produced by GDC's **STAR - Counts** workflow.
It selects files linked to **Primary Tumor** samples by default. A GDC token
is not required for these open-access files.

From the repository root, with Python 3.9+ and `requests` installed:

```bash
python -m pip install requests
python benchmarks/tcga_luad_gdc/download_luad_star_counts.py --metadata-only
python benchmarks/tcga_luad_gdc/download_luad_star_counts.py --max-files 1
python benchmarks/tcga_luad_gdc/download_luad_star_counts.py
python benchmarks/tcga_luad_gdc/download_luad_star_counts.py --verify-only
```

The default destination is `downloads/TCGA_LUAD_STAR_Counts/`, which Git
ignores. `--outdir` chooses another location. `--metadata-only` queries GDC
without downloading counts; `--max-files 1` downloads one file as a smoke test.
The unrestricted command later downloads the remaining files and verifies any
previously downloaded files before skipping them. An incomplete `.part` file
is restarted on the next attempt. A corrupt completed file causes an error
instead of being silently overwritten.

The directory contains `metadata.tsv` (one row per selected GDC file) and
`query.json` (filters and retrieval time). Count files are saved under
`files/<file_id>/<file_name>`. The script checks GDC pagination, that each
selected file is open-access and linked to exactly one case and sample, and
each downloaded file's byte size and MD5 checksum. It refuses to reuse the
same output directory if a later GDC query returns different metadata. Use a
new `--outdir` to preserve the earlier benchmark snapshot.

Each row retains its case and sample barcode. Multiple files can share a
sample barcode; the downloader keeps all of them. Choose a single file per
biological sample and an expression transform separately when constructing
the SJARACNe input matrix. This script downloads per-file STAR Counts TSVs;
it does not build or normalize a matrix.

In a live query on 2026-09-23, GDC returned 601 matching open files, of which
540 were linked to Primary Tumor samples (529 distinct sample barcodes across
517 cases; approximately 2.13 GiB in total). One file was downloaded and
checksum-verified as a smoke test. GDC's file selection can change with later
data releases.

The GDC API details are documented in [Search and Retrieval](https://docs.gdc.cancer.gov/API/Users_Guide/Search_and_Retrieval/),
[Downloading Files](https://docs.gdc.cancer.gov/API/Users_Guide/Downloading_Files/),
and the [mRNA analysis pipeline](https://docs.gdc.cancer.gov/Data/Bioinformatics_Pipelines/Expression_mRNA_Pipeline/).
