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

## Completed develop cleanup

The engine branch `chore/separate-research-benchmarks` was based on
`develop` at `1638e8f4eb3d7ffe5057922fa9f9bd1043d466ac`. Its cleanup removes only
the 11 migrated files under `benchmarks/dream5_network1/`, removes their
obsolete `.gitattributes`/`.gitignore` rules, and replaces the engine README's
local DREAM5 link with a link to this private repository.
At the user's explicit request on 2026-10-14, the branch was pushed and
fast-forward merged into `adamdingliang/SJARACNe:develop` at
`edf7a2fdf3c5ff866f4fea30fe1ca010c00e6a3a`. Both remote branch heads were
verified at that commit. No force-push, branch-protection bypass, old-PR
rewrite, or change to `master` was performed. The cleanup branch is retained.
Original DREAM5 files remain recoverable from both this repository and the
engine's existing Git history/worktree.

Engine code, consensus/calibration implementation, native regression fixtures,
performance microbenchmarks, other PR branches/worktrees, external/large raw
datasets and local scientific run outputs are outside this cleanup. The
removed DREAM5 package does include its migrated expression/reference inputs;
their copies here and in the original DREAM5 worktree remain intact. At this
first cleanup stage, `benchmarks/rank_cache` remained engine-owned and was used
by engine tests. The later retirement below supersedes that location.

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

## Second cleanup: remaining engine benchmark tree

The user subsequently authorized moving the remaining engineering evidence and
tools here, retaining only engine correctness support in SJARACNe, and removing
the engine's root `benchmarks/` directory. The separate branch is
`chore/archive-engine-benchmarks`, based on `edf7a2f`.
The engine cleanup commit is `9f4959c5a0a083bc13c9dede62d9ba49be5c8dfa`.
After the verified archive was published here at `984f48b`, the branch was
pushed and fast-forward merged into `adamdingliang/SJARACNe:develop` on
2026-10-14. Both remote branch heads were verified at that engine commit.
There is no tracked root `benchmarks/` tree on `develop`; no force-push or
history rewrite was used. Other working branches and their local archives
are deliberately unaffected.

All 60 remaining benchmark files (nine folders; 2,004,300 bytes) are preserved
byte for byte from pinned Git objects under `engine_performance/`. The original
mixed generator/native-test module is retained as a 9,656-byte text snapshot.
See the [engineering process/results index](../engine_performance/README.md)
and [strict archive manifest](../provenance/engine_archive_manifest.json).
The initial 602-record scientific migration manifest is not modified.

Six synthetic fixtures are relocated byte for byte into the engine's
`tests/fixtures/rank_cache/`. Its two tied/conditional rank-cache tests and
three adaptive-partition workspace tests remain engine-owned; none of their
test bodies or assertions changes. The generator-only test moves with the
generator and keeps its complete original class body/assertions. Engine code,
build/package/CI configuration, raw datasets, old PR branches/worktrees and
the path-bound THP-1 archive are unchanged. SJARACNe needs no external
benchmark-repository checkout to build, infer networks or run its tests.

Validation for this second cleanup:

- Fresh WSL `g++`/glibc build: passed, with existing compiler warnings.
- Six native/workflow-wiring modules: all 56 tests passed, including the five
  directly affected native regression tests.
- Benchmark migration/verifier and generator tests: 33 collected, 32 passed,
  one skipped because Windows lacks symlink-creation privileges.
- All 16 new archive-verifier tests additionally passed under WSL, including
  the symlink-rejection case skipped on Windows.
- Archive verification: source Git objects and staged bytes/modes checked;
  all 60 files plus the original test snapshot match.
- Clean Windows engine discovery: 81 tests, 24 passed, 53 skipped and four
  existing environment errors (three temporary-file reopen errors and missing
  `cwltool`). Bare WSL Python cannot run full workflow acceptance because
  NumPy is unavailable. No full-suite or end-to-end success is claimed.

The passing native command, after building in the isolated cleanup checkout,
was run from its `tests/` directory:

```sh
python3 -m unittest test_sjaracne_adaptive_partition_workspace \
  test_sjaracne_adjacency_input test_sjaracne_expression_validation \
  test_sjaracne_rank_cache test_sjaracne_sampling \
  test_sjaracne_subnetwork_resolution -q
```

This is a preservation and test-layout cleanup, not a rerun of the historical
timing studies or a new scientific benchmark. Native timing tools retain their
old path/version assumptions and require explicit external inputs/adapters.
