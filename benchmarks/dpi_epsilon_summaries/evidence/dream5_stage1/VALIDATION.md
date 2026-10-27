> Publication copy of a frozen local report/process. Scientific text and numbers are unchanged; relative links are adapted to this compact package. See [publication provenance](PUBLICATION.json) for original hashes and [local artifacts](README.md#local-artifacts) for omitted sidecars.

# Stage 1 validation and provenance

All reported inference uses frozen design fingerprint
`69dd3dc91b7e4b210bd40788853d5b17dba9682ad0420b1fc1fd3983fb50f330`.
The frozen analysis SHA256 is
`82de2cf236646fee1c14628138c1c3f029c25226fc4a056b8fd781323905a2c8`.

## Completed evidence

- 30/30 expected unique jobs, no failed or additional native jobs in this run.
  Ten seed-1 smoke jobs passed and were revalidated/reused, not rerun.
- Both full candidate lists matched with zero missing TFs; complete 195/334
  source traversals and all 1,643/4,511 genes in the 644-observation rank cache.
- Exactly 644 unique sorted actual native observation indices per job. All
  five modes within each seed used identical ordered indices. Both datasets
  select the same column numbers because both have 805 columns, not because
  those columns are biologically matched.
- All 30 native cutoff decimals/hex values and model identities agree.
  Native cutoff `0.021543205318573955` equals the frozen Python callable here.
- Global pre=pruned+post; emitted counts=post; pre-counts equal across modes.
  No-DPI applied no pruning. Strict and relaxed DPI were actually applied.
- All six dataset/seed families satisfy the exact serialized-weight chain
  E0 subset E.05 subset E.10 subset E.15 subset E1. There were no missing or
  changed shared serialized MI tokens.
- Original source hashes, engine archive/source/model hashes, compiler/binary,
  frozen harness and artifact identities are retained in the external design
  and per-job records. No engine source or default was changed.

The exact family/subset check results are in [analysis.json](README.md#local-artifacts).
These are engineering consistency checks, not biological validation or a
full-precision pre-DPI MI fingerprint.

## Lightweight tests and controller corrections

[34 tests passed](README.md#local-artifacts), zero skips/failures/errors,
on the workstation's Python 3.13/scikit-learn environment. The inference
controller also passed its unit tests in WSL/Python 3.12.

Coverage includes frozen command/grid parameters, immutable artifact checks,
read-existing validation that cannot launch inference, mandatory revalidation
of smoke artifacts before full-batch workers, native sampling/completion/header
validation, explicit labels, tied AP/AUROC, independent synthetic score checks,
incremental counts, undefined metrics, graph nesting and report aggregation.

An initial preparation-only directory was retained after source review found
two orchestration guard gaps: a read-existing validation path could launch a
missing job, and a full run trusted a smoke-summary flag without first
revalidating its artifacts. Both were fixed and regression-tested **before any
native inference was launched**. All reported jobs use the subsequent frozen
`20261025-r2` directory. No old or failed inference results were overwritten.

## Independent actual-output audit

An [independent helper](README.md#local-artifacts), without importing the
pilot scorer, reparsed original labeled pairs and all 30 actual adjacencies.
It verified reference and adjacency hashes, all six serialized-MI nesting
families and all 24 versus-strict comparisons, including no-DPI controls.

Scikit-learn 1.8.0 independently reproduced AP and AUROC; count-derived
precision/recall/TP/FP and paired changes also matched. Absolute metric
tolerance was 1e-12. [Audit JSON](README.md#local-artifacts): passed,
no failures. Helper SHA256:
`f56e003c7209e8736aaec07fd62e6d879335a8654dfc678ae3af49c79e1183f0`.

The helper checked data read-only and wrote a separate audit JSON; it did not
run inference, change labels or modify the original outputs.

## Report and plot checks

The reporter independently validates all 30 metric rows, the complete relaxed
comparison grid, count-derived rates and paired deltas before producing
medians/ranges. It does not pool networks or drop undefined seed values.
Source/data/artifact hashes are in [report provenance](original_report_provenance.json).
Both generated SVG figures were rendered in headless Chrome and visually
inspected; titles, axes, seed traces, medians and the reference caveat are visible.

The independent audit confirms the important aggregation distinction:
Network 1 epsilon 0.05 has a higher separate median AP but negative paired
AP changes in two seeds. The conditional conclusion uses those paired changes,
not subtraction of group medians or an apparent one-cell maximum.

Compact evidence is stored here. Native graphs, inputs/builds and full logs
remain outside Git; no data download, consensus or Stage 2 experiment occurred.
