# Bounded source-repository cleanup: 2026-10-14

This follow-up is separately authorized cleanup, not a scientific rerun or a
claim that every historical workflow is portable from this repository.

## Checks before removal

`scripts/verify_migration.py --source-workspace D:\GitHub` passed for all 602
historical import records before cleanup: 599 active files and three retired
LUAD archive records. The private remote `main` was confirmed at
`1876f5c9f9de14ae9b04e3b2f4ae1e9be4810e50`. All 11 DREAM5 Git blobs on engine
`develop` (`1638e8f4eb3d7ffe5057922fa9f9bd1043d466ac`) matched the source blobs
recorded in the import manifest.

## Local engine checkout

- Removed the duplicate, previously untracked
  `benchmarks/tcga_luad_download/download_tcga_luad.py` and
  `test_download_tcga_luad.py`, plus one generated Python cache file and their
  now-empty directories. Both source files matched their committed copies in
  this repository byte for byte. Recover the scripts from
  `benchmarks/tcga_luad_download/` here; no downloaded LUAD data was removed.
- Retained `D:\GitHub\SJARACNe\benchmarks\thp1_perturbseq` at its original
  location. It includes roughly 2.66 GiB of local results, prepared inputs,
  native networks, hash-bound helpers and a deliberately unimported native
  sampling patch. Existing manifests bind these original paths. It is a
  frozen local archive, not the location for new benchmark development.
- Added only `/benchmarks/thp1_perturbseq/` to the engine's local
  `.git/info/exclude`. This does not change tracked ignore rules, relocate
  files or create a dependency on this repository.
- Kept the engine checkout on `feat/estimator-matched-apmi-null` at
  `7633ebb4a0d966dbda15a4e32d0efa492fb71aeb`.

## Prepared develop cleanup

The separate local engine branch `chore/separate-research-benchmarks` starts
from `develop` at `1638e8f4eb3d7ffe5057922fa9f9bd1043d466ac`. It removes only
the 11 migrated files under `benchmarks/dream5_network1/`, removes their
obsolete `.gitattributes`/`.gitignore` rules, and replaces the engine README's
local DREAM5 link with a link to this private repository.
Preparing this branch does not merge it into `develop` or rewrite old PRs.
The prepared local cleanup commit is
`edf7a2fdf3c5ff866f4fea30fe1ca010c00e6a3a`; it has not been pushed or merged.
Original DREAM5 files remain recoverable from both this repository and the
engine's existing Git history/worktree.

Engine code, consensus/calibration implementation, native regression fixtures,
performance microbenchmarks, other PR branches/worktrees, external/large raw
datasets and local scientific run outputs are outside this cleanup. The
removed DREAM5 package does include its migrated expression/reference inputs;
their copies here and in the original DREAM5 worktree remain intact. In
particular,
`benchmarks/rank_cache` remains engine-owned and is used by engine tests.

## Verification after cleanup

Run `python scripts/verify_migration.py` to verify the imported artifacts and
the fixed Git recovery snapshots. The optional `--source-workspace` mode
expects every original import source to remain present and will now report
the intentionally removed local LUAD scripts as missing. Do not modify the
frozen import records or bypass integrity checks to hide that source cleanup.

The engine's Python test discovery was attempted after the DREAM5 removal:
82 tests, with 25 passed, 53 skipped and four errors. Three errors are Windows
`NamedTemporaryFile` reopen failures in line-ending tests; the acceptance
test cannot launch the missing `cwltool` executable. Native test prerequisites
are unavailable in this Windows environment. This is not a fully passing
engine test suite or a successful end-to-end workflow run. A Git comparison
confirmed that engine implementation, tests, workflow configuration and
`benchmarks/rank_cache` are unchanged from the `develop` base.

Imported-artifact verification and all 16 synthetic migration-verifier tests
pass after cleanup. No THP-1 or DREAM5 scientific inference was run.
