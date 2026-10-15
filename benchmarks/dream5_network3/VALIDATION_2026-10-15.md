# Network 3 execution and scoring validation

This records checks for the prospectively specified three-seed, four-arm,
five-stage pilot. It is computational verification, not independent biological
validation or an official DREAM5 score.

## Frozen protocol and execution

- Protocol and initial runner/scorer committed as `6b45ca1` before inference.
  The runtime data-parser hash pin was added in `b7b9894`, also before inference.
  Reporting/packaging code was committed in `176a276` before cohort scoring.
- The first unused plan was preserved locally as
  `runs/dream5_network3_20261015_pilot3_unused_preflight/plan.json`. It launched
  zero jobs. The executed plan was regenerated after the parser-pin correction.
- Executed plan SHA256:
  `1171d35773bd5ddfde81e9d1317479b247a13f9169272dd563360cfe012733fe`.
  See its [preserved copy](results_2026-10-15_pilot3/provenance/plan.json).
- Source/input/executable/configuration/runtime-code hashes were checked before
  launch and rechecked during scoring and compact packaging. The historical
  source snapshot matches after CRLF-to-LF normalization; this is not a claim
  that working-tree source bytes equal Git blobs without normalization.
- Ten smoke jobs ran with two workers. Independent read-only verification
  checked all 50 artifact hashes, exact native commands, successful exits,
  counts/headers, complete 334-TF traversal, and all shared MI/subset relations.
  No scientific metric direction was used as an expansion gate.
- The full run used 12 workers, hash-verified and reused those ten jobs, and
  executed the other fifty. All **60/60 jobs** exited successfully. Twelve
  arm/seed groups passed exact shared-MI and raw/pre/post subset checks.
- Native elapsed times ranged from **9.41 to 29.55 seconds per job**; their sum
  was 1,083.32 worker-wall seconds, not the overall elapsed benchmark time or
  CPU time. Maximum reported native peak RSS was **135,340 KiB** (~132 MiB).
  Validation/Python/WSL overhead is not included in the native timing fields.
- Native files remain local under
  `runs/dream5_network3_20261015_pilot3/`; the compact package excludes them.

## Tests and preserved historical evidence

- All **54 Network 3 tests** passed: 9 input/preparation, 20 runner, 15 scoring,
  10 reporting/packaging. Tests include deliberate failure injection; printed
  synthetic failure messages are not native benchmark failures.
- All six existing Network 1 tests passed.
- Scientific import-manifest verification passed for 602 historical records
  (599 active, 3 retired). Engine-archive verification passed for 60 files.
  These verify the preserved migration/archive records; they are not fresh
  reruns of the historical scientific experiments.
- The shared SJARACNe checkout was not edited or switched. Inference used the
  separately pinned historical executable, not the shared checkout's HEAD.

## Independent numerical recalculation

A separate read-only calculation imported neither the benchmark gold parser
nor its metric helpers. It read the original labeled gold file and all 60
native adjacency files directly, verified the adjacency SHA256 digests, and
parsed 37,809,626 emitted directed entries across 19,110 nonempty source rows.

- Fixed universe independently confirmed: **152,280 pairs**, 2,066 positives
  and 150,214 negatives. Unlabeled predictions did not become negatives.
- Exact all/labeled/unlabeled counts and TP/FP/FN/TN matched at every stage.
  There were 720 scalar stage comparisons and 144 pruning comparisons.
- Independently computed scikit-learn AP/AUROC matched all 60 stage results:
  maximum absolute AUROC difference `2.220446049250313e-16`, AP difference
  `2.7755575615628914e-17`, specificity difference
  `1.1102230246251565e-16`; pruning differences were zero.
- Independently confirmed primary paired AP changes were +0.0036592090,
  +0.0047313703 and +0.0025681467. This does not turn three computational seeds
  into a significance test.
- Nominal versus common-cutoff post-DPI labeled edge **sets and MI weights**
  matched exactly in all 12 groups. Full-network differences were unlabeled:
  legacy had 14/2/2 extra nominal edges, 64% had 22/24/23 extra fixed-cutoff
  edges, 80% had none, and 90% had 0/1/5 extra nominal edges across seeds 1/2/3.

The [result summary](RESULTS.md) retains the negative and mixed findings,
including TP loss in two of three primary comparisons, minimal 80% raw-AUROC
change and substantial reference-positive loss through DPI. No tuning,
reranking, consensus or outcome-based seed exclusion was performed.

## Compact-package checks

An independent final read-only check verified all 69 copied source artifacts,
all six generated outputs and the reporter/input-metrics hash pins. The
package contains 76 files totaling 4,653,175 bytes, including its manifest.
Exactly 60 distinct completed job records cover the frozen design. All twenty
arm/stage medians were independently reaggregated; the summary tables and
paired changes agree. Local documentation links resolve. No raw adjacencies,
logs, expression, score arrays or native binaries are included; those remain
local. The PNG was also visually inspected for layout and readable labeling.
