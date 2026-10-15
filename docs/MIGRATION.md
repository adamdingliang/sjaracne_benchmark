# Migration status and compatibility

The first stage is an additive migration of scientific workflows and compact evidence. Originals are not deleted, relocated or rewritten. Per-file source paths, source checkout commits, tracked/untracked status and SHA-256 values are retained in `provenance/import_manifest.json`. For previously untracked THP-1/LUAD code, the source checkout commit is context only: the recorded file hash, not that commit, identifies the imported code.

## Sources

| Package | Source snapshot |
| --- | --- |
| DREAM5 | `SJARACNe-dream5-benchmark`, `b4b35ca711be1f1112dc8fb8e2811094afca9648` |
| BRCA100 thresholds and matched QC | `SJARACNe-pr68-develop`, `32fe12c168ef80291e487dbf4045f430b9c5d90a` |
| BRCA100 recurrence evidence | `SJARACNe-min-recurrence-develop`, `c7cdd45bda7bb2cba1fef3f6e7953d474382a06e` |
| BRCA100 hub-size and witness evidence | `SJARACNe-hub-dpi-analysis`, `b3f9a83a27c994370c2b54eef48dcb5d4e735fa9` |
| Current THP-1 and validated LUAD utility | Previously untracked files in the active `SJARACNe` checkout, recorded individually |
| Earlier LUAD utility | `SJARACNe-luad-gdc`, `11554e3df24a9cf4730f5eecf797133efeb26c0c`; original import retained in Git history, now consolidated into the current LUAD benchmark |

The package-source commits above identify the imported presentation/code snapshots. Historical run manifests may identify earlier inference commits; those original values remain authoritative for the historical results.

## Stage 1: preserved archive and browseable evidence

Import the selected packages, preserve original result manifests/checksums, distinguish THP-1 pilot from full reconstructed baseline/after comparison, reconcile stale navigation documentation, and verify imported bytes plus lightweight synthetic tests. No inference, downloads, or rescoring of the scientific evidence is performed.

Dated result folders and `evidence/` are historical snapshots. Root documentation and workflow navigation may be adapted for the new repository; every adaptation is marked in the import manifest. Do not edit frozen result JSON to make old paths appear portable.

On 2026-10-14 the duplicate LUAD archive was consolidated into
`benchmarks/tcga_luad_download`. Its three original import records are retained
as explicitly retired entries, verified against their immutable initial Git
snapshot. Active files and retired records are reported separately. See
[LUAD consolidation](LUAD_CONSOLIDATION.md). No historical scientific result
was retired or edited.

## Stage 2: operational portability

Historical scripts are not automatically portable:

- THP-1 guards bind helper files, prepared inputs, native builds and completed runs to absolute paths and hashes. Existing runs should continue using their original archive/code paths. Moving them requires a separately documented relocation strategy, not a silent manifest rewrite.
- DREAM5 accepts explicit `--binary`, `--config`, `--data-root` and `--out`; the engine must be built in a separate SJARACNe checkout. The old README's in-repository `make -C SJARACNe` example no longer describes this repository.
- Some BRCA100 runners assume an engine Git checkout, its native fixtures, or the consensus Python module. They need explicit engine-checkout adapters before a fresh end-to-end run from this repository can be claimed. Imported analysis and compact result browsing remain available.
- Native sampling changes and DPI instrumentation stay engine-owned. The native sampling backport patch is not vendored here; use the recorded external source/build archive when revisiting that historical protocol.

Future adapters should take explicit external engine/build/data paths, enforce source/version pins, create fresh output directories, and record new provenance without mutating the historical packages.

Some preserved BRCA100 sweep-history filenames contain two full SHA-256 values
and exceed traditional Windows path limits. On Windows, clone with
`git -c core.longpaths=true clone ...` or set `git config core.longpaths true`
in this repository. The original filenames are retained rather than shortened,
because historical manifests identify them.

## Stage 3: source-repository retirement and publication

Only after equivalent migrated workflows are validated should we replace source-repository benchmark folders with links or remove duplicate working copies. No deletion, SJARACNe commit/PR changes, or public visibility change is authorized by this initial migration. Rights/attribution review and a deliberate data-hosting decision precede public release.

On 2026-10-14 the user separately authorized bounded source cleanup. The
standalone duplicate LUAD utility was removed from the active engine checkout;
the path-bound THP-1 archive remains in place and is locally excluded from Git
status. At the user's subsequent explicit request, engine cleanup commit
`edf7a2f` was pushed and fast-forward merged into `develop`, removing the
already migrated DREAM5 package and replacing its README link with a link
here. No legacy PR
branch or worktree is retired, no scientific result is recomputed, and this
does not assert end-to-end portability. See [source cleanup](SOURCE_CLEANUP.md).

The same day, the user authorized a second cleanup to retire the remaining
engine `benchmarks/` tree. Its 60 files are preserved from pinned Git objects
under `engine_performance/`, with a separate
`provenance/engine_archive_manifest.json` and strict integrity verifier. The
original mixed test module is retained as source text; its generator-only test
moves with the tool, while all five native numerical regression tests remain
engine-owned with the six fixtures relocated under `tests/fixtures/rank_cache/`.
This separates historical evidence from required test support without making
the engine depend on this repository. Historical native timing runners remain
version-bound snapshots, not newly validated portable workflows.
