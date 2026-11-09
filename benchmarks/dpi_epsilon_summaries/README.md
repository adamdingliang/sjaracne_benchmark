# Historical DPI tolerance evidence

These compact packages record the October 2026 DPI studies summarized in the
[benchmark guides](../../docs/benchmark_summaries/README.md). Their reports,
protocols, tables and publication manifests retain the original measurements.

| Package | Scope |
| --- | --- |
| [DREAM5 Stage 1](evidence/dream5_stage1/README.md) | Per-resample strict/relaxed DPI recovery on Networks 1 and 3; three seeds. |
| [DREAM5 controls](evidence/dream5_controls/README.md) | Fixed-budget and matched-recall controls on the same challenge references. |
| [BRCA100 fixed grid](evidence/brca100_fixed_grid/README.md) | Shared fixed/dynamic tolerances over nested hub panels. |
| [BRCA100 source benefits](evidence/brca100_source_benefits/README.md) | Degree-stratified agreement and rescued-edge descriptions from existing outputs. |
| [LUAD preparation](evidence/luad_preparation/README.md) | Gene-level inputs for 517 patient-distinct primary tumors. |
| [LUAD100 transfer](evidence/luad100_common/README.md) | A 100-patient subset with 477 common TF/SIG sources; panel/pruning consistency. |

These studies concern individual resample graphs and the recorded zero-offset
DPI schedules; they do not measure the later K20-before-DPI workflow with offset
0.025. See the [bulk cohort overview](../../docs/BULK_DATASETS.md) and
[completed native bulk batch](../native_bulk_2026-11-09/README.md) for that work.
LUAD100 and LUAD517 are different cohort sizes; their results are not interchangeable.

DREAM5 scoring uses its documented reference universes; experimental references
are incomplete. BRCA100/LUAD agreement and topology metrics have no independent
edge-level ground truth. Multiple panels or resamples of one cohort are not new
biological datasets.

Each package's `PUBLICATION.json` identifies its original evidence and omitted
local artifacts. Frozen process text can contain obsolete status/default wording;
interpret it at the stated date. Current implementation guidance lives in
[SJARACNe2](https://github.com/adamdingliang/SJARACNe2).
