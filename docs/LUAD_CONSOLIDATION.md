# One LUAD benchmark entry point — 2026-10-14

Use [benchmarks/tcga_luad_download](../benchmarks/tcga_luad_download/README.md).
The separate `archive/tcga_luad_gdc` folder and its duplicate downloader/test
entry points have been removed from the active repository tree.

## What was integrated

- The current downloader, command-line interface and primary-tumor protocol
  remain unchanged. Its original 26 tests are unchanged.
- The useful frozen-query safety coverage from the earlier utility is now
  exercised against the current implementation by 11 new offline tests in
  `test_query_snapshot.py`: snapshot creation/reuse, no-network offline reuse,
  digest tampering, protocol incompatibility, duplicate IDs, association
  validation, release consistency and refusal to implicitly import a legacy
  snapshot in offline mode.
- The root test launcher now has only one `luad` group, covering both current
  test modules. It no longer offers a separate archive group, and the import
  helper no longer recreates the duplicate archive.
- The original three import records and their SHA-256/size/source metadata
  remain in `provenance/import_manifest.json`, explicitly marked retired and
  mapped to their canonical counterparts. The original SJARACNe worktree is
  untouched. No downloaded data or scientific evidence was removed.

The retired files are recoverable from this repository's immutable import
commit [`55f9745`](https://github.com/adamdingliang/sjaracne_benchmark/tree/55f974555cb02eef53d7b1802c3b4e2e8c7d9b9e/archive/tcga_luad_gdc).
The migration verifier validates those bytes directly from that Git snapshot;
only these three exact retirements are permitted. A full Git clone/history is
therefore required for that verification, not a source ZIP or shallow checkout
that omits the recovery commit. Historical scientific-result guards are not
relaxed.

## Compatibility

The earlier utility's `query.json` / `metadata.tsv` output format is not the
current `query_snapshot.json` format. Use a fresh output directory for current
acquisition. This cleanup does not migrate or overwrite an existing cohort.
The canonical utility remains primary-tumor-only; the older general
`--sample-type` option and fail-immediately corrupt-file behavior are not
silently added to its protocol. Its existing validated-replacement behavior
is documented in the benchmark README.

## Checks performed

| Check | Result |
| --- | --- |
| New frozen-query tests | 11/11 passed |
| Combined current LUAD suite | 36/37 passed; one known pre-existing failure |
| Migration/provenance tests | 16/16 passed |
| Imported-file/source verification | 599 active files verified; three retired imports recovered and verified from Git |

The remaining LUAD failure is still
`StarValidationTests.test_requires_gene_model_and_all_summary_rows`, subtest
`removed_index=0`: a missing gene-model comment is not rejected. It predates
this consolidation and was not fixed or hidden as part of a folder cleanup.
The `luad` check group continues to return a nonzero status for that failure.

```powershell
python scripts/check_benchmarks.py --group migration --group luad
python scripts/verify_migration.py
```

Tests used tiny synthetic inputs, fake network sessions and temporary output
directories. No GDC request, real data download, new inference, MI-cutoff change
or scientific rescoring was performed.
