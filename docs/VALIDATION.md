# Initial migration validation — 2026-10-13

This validates the copied artifacts and synthetic checks, not a new end-to-end scientific benchmark run. No inference, download, calibration, R execution, package installation or native build was performed.

This is the historical initial-migration report. On 2026-10-14 the redundant
LUAD archive was consolidated into the current benchmark; the active tree no
longer includes that archived test suite. See [LUAD consolidation and current
checks](LUAD_CONSOLIDATION.md) for the follow-up status. The initial counts
below are not rewritten as if those later changes had already occurred.

## Artifact integrity

- 602 imported files were checked against the originals using SHA-256 and byte size; the originals remain unchanged.
- 599 imported files remain byte-identical. Three navigation documents were deliberately adapted: DREAM5 `README.md`, THP-1 `README.md` and THP-1 `AUTHOR_RECONSTRUCTION.md`. Their original hashes and adapted hashes are both recorded.
- Dated evidence, existing output manifests/checksums, Python/R scientific helpers and notebooks were not rewritten.
- Imported content is approximately 69.5 MiB, including the existing small DREAM5 bundle. No individual file exceeds 50 MiB. Large THP-1/TCGA data and native networks/builds remain external.
- A lightweight selected-file check found no obvious credential/private-key signatures. This was not a comprehensive security audit.

```powershell
python scripts/verify_migration.py
# Optional on the original workstation: also verify the unchanged sources.
python scripts/verify_migration.py --source-workspace 'D:\GitHub'
```

## Synthetic tests

Checks used `C:\Users\adamd\miniconda3\python.exe` on Windows. Native/R invocations inside the THP-1 integration fixtures are mocked; those test names do not mean a real network was inferred.

| Suite | Collected | Passed | Skipped | Failed |
| --- | ---: | ---: | ---: | ---: |
| DREAM5 | 6 | 6 | 0 | 0 |
| THP-1 top-level metrics/preparation/notebook/runner | 44 | 44 | 0 | 0 |
| THP-1 author reconstruction Python helpers | 221 | 221 | 0 | 0 |
| BRCA100 threshold/package/QC helpers | 15 | 15 | 0 | 0 |
| BRCA100 recurrence | 18 | 12 | 6 | 0 |
| BRCA100 hub-size, external fixture binding | 6 | 6 | 0 | 0 |
| BRCA100 witness screen | 9 | 9 | 0 | 0 |
| Current LUAD utility | 26 | 25 | 0 | 1 |
| Archived earlier LUAD utility | 4 | 4 | 0 | 0 |
| New import verifier | 4 | 4 | 0 | 0 |
| **Total distinct tests** | **353** | **346** | **6** | **1** |

The root check command runs a faster subset of the THP-1 author suite (78 tests rather than 221) plus the other listed groups:

```powershell
python scripts/check_benchmarks.py --engine-repo 'D:\GitHub\SJARACNe'
# Full copied author-reconstruction Python suite:
python -m unittest discover -s benchmarks/thp1_perturbseq/author_reconstruction -p 'test_*.py' -v
```

The external engine option binds only the existing real-input panel test to its original BRCA100 fixtures in memory. Without it, that one fixture test is explicitly skipped. It does not adapt or run the inference workflows. See [BRCA100 compatibility](BRCA100_COMPATIBILITY.md).

Five recurrence tests were skipped because `g++` was unavailable in the invoked Windows environment; one was skipped because directory-symlink creation requires unavailable Windows privileges. The machine was not reconfigured to enable them.

## Known pre-existing LUAD failure

`StarValidationTests.test_requires_gene_model_and_all_summary_rows`, subtest `removed_index=0`, expects the parser to reject a missing gene-model comment. The unchanged parser does not raise `ValueError` in that case. The same 25/26 result was independently reproduced in the original SJARACNe checkout.

This is a real validation-contract gap, not introduced by migration. It was not fixed or hidden. Consequently, the root check command currently exits nonzero for the `luad` group. This failure alone does not establish that any real downloaded file is invalid. A separate change should resolve the validator/test contract before describing the current utility as fully validated.

## Remaining limits

Fresh BRCA100/THP-1 end-to-end portability is not established. Existing absolute-path/hash-bound archives remain unchanged and external; engine adapters and fresh output provenance are follow-up work. The code has not been relicensed, and public release remains subject to explicit rights/attribution review.
