# Authorized broad-grid execution: October 16, 2026

The user explicitly requested launching the expensive sweep with **12 workers**
on October 16. This supersedes the stop-after-timing instruction for the grid
specified here. The [October 15 prospective protocol](PROTOCOL.md) and prior
calibration/refinement evidence remain preserved. This document and the
[analysis implementation specification](ANALYSIS_SPEC_2026-10-16.md) resolve
execution choices before opening new statistical summaries.

## Generation phase launched now

- Exactly 200 sizes: m=50,100,...,10000; Npar=40.
- Exactly 10,000,000 fresh fitting and 10,000,000 fresh validation draws per m.
  There are 400 stream tasks, 4 billion null rank pairs and 32,000,000,000 raw
  payload bytes (29.80 GiB). No old or timing draws enter these streams.
- Fit seed = 20261019 + m; validation seed = 20261020 + 1000000000 + m.
  Verify uniqueness and disjointness from the original 5M and expanded 10M
  scientific streams before planning. Seeds are RNG identifiers, not dates.
- Production-shared AP-MI generator SHA256:
  `08224b6b20e29628be6d89d22eb7e355f8c6a05623e06f801fae5347a70a7f18`.
  Verify engine/source identity and preserve an immutable plan and executable
  identity. No engine rebuilds, modifications or default changes.
- At most twelve native CPU tasks across the controller, with numerical
  library threads capped at one per task. Schedule expensive large-m tasks
  first after a bounded full-draw smoke at m=50. The two smoke streams belong
  to these 400 tasks; never regenerate them for the main launch.

Generation is separate from model fitting. It may perform only raw-integrity
operations (metadata, exit status, byte lengths, SHA256, finite MI support).
Do not compute CDFs, quantiles, cutoffs, tail counts, tie/unique summaries or
statistical fits during this phase. In particular, new final-validation streams
and the 20 interpolation-test fitting streams remain statistically sealed.
This is a protocol/access discipline, not a claim that raw files are encrypted.

## Checkpoints and process lifetime

Use a new ignored run directory. Each stream has an immutable command, task
identity, seed, logs, resource timing, raw metadata, provenance and last-written
completion record. Native generator output can truncate an existing file:
therefore only fresh stream-attempt targets may be passed to it. Existing raw,
partial or failed attempts must never be overwritten or silently retried.

Resume only hash-verified completed streams from the same frozen plan. Preserve
all failures. Use an exclusive OS-owned controller lock, durable status and
heartbeat, controller/child process IDs, and cooperative stop-after-current-
stream behavior. A stop request prevents new launches but allows current
streams to finish and checkpoint. An interrupted incomplete stream is not a
verified completed result and requires explicit recovery rather than auto-retry.

Launch the Windows-owned Python controller with a hidden window and separate
stdout/stderr logs. Verify actual controller identity and native generator
processes before reporting the batch running. Product/tool-session persistence
is not a process-lifetime guarantee. The workstation must remain powered and
awake; no power settings are changed automatically.

## Statistical freeze and subsequent work

The new analysis specification fixes the finite families, m-smoother grid,
probability knots/probes, loss, tie breaking, numerical convention, refit-failure
policy and supported-domain evaluation before generation begins. Analysis
implementation may be completed and tested while generation runs, but must be
hash-frozen before ANY new fitting/development statistical summaries are opened.
Generation cannot select or modify the model based on incoming raw streams.

Final interpolation-test m=350,850,...,9850 and all final-validation streams
remain unavailable to model selection. Freeze the selected procedure, once-only
full-data refit, primary function artifact and claimed domain before opening
those streams for final evaluation. Do not tune until held-out gates pass.
Failures and unresolved calibration remain outcomes, not reasons for retrying
favorable draws, switching to nearby m or shrinking the claimed domain.

The immediate launch is the expensive **generation phase**. It stops after
verified generation; no automatic unreviewed model selection, final evaluation
or runtime promotion is attached to the background controller. Analysis follows
under the sealed-data rules once its tested implementation is frozen. User
authorization to launch this study does not authorize an engine/default change.

## Timing and interpretation

The 12-worker capacity pilot projects roughly **9-10 hours of generation**,
not a completion guarantee. Fitting, selection, integrity checks and reporting
add time; long-run contention/thermal behavior may change throughput. Update
estimates from actual completed streams rather than extrapolating raw byte
growth as scientific completion.

At 10M validation draws, rare p=1e-5,1e-6,1e-7 have only 100,10,1 expected
events. The study cannot strongly establish 10% relative accuracy there.
Preserve the +/-10% target and simultaneous intervals, and retain unresolved
results. Unique-rank independence null calibration is not biological FDR,
direct-edge truth, optimal density or a generally validated TF/SIG default.
