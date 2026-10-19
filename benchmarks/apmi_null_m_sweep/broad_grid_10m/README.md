# Broad-grid AP-MI calibration: process and results

**Completed October 17, 2026.** See the [results and defensible conclusion](RESULTS.md)
and [full evidence package with plots](results_2026-10-17/RESULTS.md).
PCHIP was selected on development data; 6599/6600 moderate observed-rate checks
were within 10%. The complete core grid was not confirmed under the stricter
simultaneous-interval rule. The benchmark itself made no engine/default change.
The execution history below preserves both interruptions and the final-scoring continuation.

**Terminology:** one evaluation case is one sample-size/probability pair (m,p).
The development selection score uses 80 cases: 20 development sample sizes ×
four probabilities. These are not biological cells or 80 individual samples.
The historical, hash-frozen specifications use "cell" for the same table entry;
their original wording is preserved to keep provenance hashes unchanged.

## Benchmark process

The goal is to map an actual sample count m and requested independence-null
tail probability p to an MI cutoff, then measure whether independent null
draws exceed that cutoff at the requested rate. No expression dataset or
biological edge reference supplies the calibration labels.

1. Simulate independent rank pairs with the production-shared AP-MI estimator:
   200 sizes m=50,100,...,10000, with 10M fitting and 10M validation draws each.
2. Construct empirical quadratic and PCHIP cutoff surfaces from 160 sizes;
   select between them on 20 development sizes at four fixed probabilities.
3. Refit the selected procedure once on 180 sizes, freeze it, then evaluate
   independent validation draws at all 200 sizes. Twenty sizes never train
   the final surfaces and test sample-size interpolation.
4. Report observed null-rate errors separately from simultaneous-interval
   confirmation; retain all planned cases, including unfavorable ones.

PCHIP interpolates empirical MI quantiles from independent-rank null draws
evaluated with the shared AP-MI estimator; no parametric tail distribution
is fitted.
The [summary results](RESULTS.md) show PCHIP-only rate trajectories; the
[full report and plots](results_2026-10-17/RESULTS.md) preserve both models,
comparators, diagnostic probabilities, numerical corrections and audit details.

## Frozen function and provenance

The [full report's design section](results_2026-10-17/RESULTS.md#design-numerical-policy-and-opening-order)
defines the empirical quantiles, log-coordinate interpolation and probability-scope
split. Exact training-size/probability knot queries return the stored binary64
cutoff without a log/exp round trip. The selected [frozen primary](results_2026-10-17/primary.json)
has SHA256 `8b4104be3f3ffe0a476a4dd7c8f7f6d95f00f1a51fa467c7194edf3806d427f5`.

SJARACNe's [offline exporter](https://github.com/adamdingliang/SJARACNe/blob/fdbc69c281d57f3b6e175d2ecd4d8e9e1e2280ee/tools/export_apmi_pchip.py)
represents this same frozen surface as bundled observations and interpolation
coefficients; it does not refit, reselect or generate new null draws. The
[bundled JSON](https://github.com/adamdingliang/SJARACNe/blob/fdbc69c281d57f3b6e175d2ecd4d8e9e1e2280ee/SJARACNe/config/apmi_pchip.json)
has SHA256 `5ae44f3ec251282b242e1e25e5695fe8c6d80a0e7a3f156170dbb72c29e09f59`.
The Python cutoff callable uses only the standard library; the corresponding
native evaluator embeds the same data. Neither cutoff evaluator needs this
benchmark checkout, raw simulations, SciPy interpolation or network access.
The full workflow and consensus analysis retain their usual dependencies.

The [results](RESULTS.md#evidence-and-limitations) distinguish runtime-port
representation checks from the original statistical calibration.

## SJARACNe runtime policy

The later, experimental opt-in integration at
[SJARACNe `86f8729`](https://github.com/adamdingliang/SJARACNe/tree/86f8729087b3a6d22bdce128649b4e49d725fb9e)
uses this frozen surface; it does not refit the model or reopen the benchmark's
final evaluation. Legacy defaults remain unchanged.

- Active PCHIP requires actual selected integer `m=50..10000`, `Npar=40`,
  matching kernel schema and `p=1e-7..0.05`. Workflow opt-in (`-M pchip`)
  requires explicit `-pb`; it does not select a TF/SIG probability.
- All supported probabilities are accepted without a separate acknowledgment
  flag. Alongside the experimental warning, `p<0.0005` warns about being outside
  the principal assessment range; `p<=1e-5` additionally warns about limited
  extreme-tail Monte Carlo precision. Neither warning rejects the request or
  establishes an accuracy guarantee. See the
  [statistical limitations](RESULTS.md#evidence-and-limitations).
- Off-grid sample counts such as `m=80` are interpolated and produce a warning;
  representation checks do not provide new statistical calibration at those sizes.
- Unsupported inputs, crossed cutoff knots and estimator-configuration
  mismatches fail rather than extrapolating, repairing knots or silently falling
  back. Active PCHIP rejects native replacement sampling (`-r`) and adjacency
  replay (`-j`). Explicit native `-t`, including zero, overrides probability
  conversion; native `-p 1` also bypasses cutoff evaluation.
- Native network headers record the primary/data/summary SHA256 hashes, kernel
  schema, actual `m`, `Npar`, experimental and principal-range/extreme-tail/off-grid
  status, requested probability, and round-trippable decimal/hex binary64 MI cutoff.

## Reproduce the summary plots

To regenerate only the PCHIP presentation plots from the committed score table
(no raw draws, fitting or selection), use a fresh output directory:

```powershell
python benchmarks/apmi_null_m_sweep/broad_grid_10m/plot_pchip_summary.py --csv benchmarks/apmi_null_m_sweep/broad_grid_10m/results_2026-10-17/final_scores.csv --out runs/FRESH_PCHIP_SUMMARY_PLOTS
```

## Corrected numerical-zero analysis

The first October17 attempt stopped at09:50 EDT during internal scoring,
before selection or final access: reporting rejected tiny negatives that the
original integrity checker already permitted. See the explicit
[numerical-zero correction and restart history](CORRECTION_2026-10-17.md).
The corrected analysis treats only MI in [-64 binary64 epsilon,0) as positive
zero, preserves every positive value and all original raw files, and retains
material-negative errors. All161 tests pass, including regression and
restart/sealing tests.

The fresh corrected run uses12 workers and the same existing simulations:
`runs/apmi_null_broad_fits_20261017_zero_corrected/`. The first failed run is
preserved unchanged. No new draws or model/selection/default changes are made.
Check the corrected run's `status.json`, `stdout.log` and `stderr.log` rather
than interpreting the failed run's last progress heartbeat as a live process.

The corrected freeze command requires
`--restart-from runs/apmi_null_broad_fits_20261017` to pin the failed-run evidence
and acknowledge prior training/development access. A new request is frozen
before selection/refitting/final evaluation; the untouched final streams stay
sealed until primary freeze. The historical launch description below refers
to the original attempt, not successful completion.

## Final-scoring continuation

The corrected run subsequently selected PCHIP, froze its180-size refit and
completed all200 validation and20 test-size extraction tasks. A Windows
progress-file replacement failure interrupted test-size index bookkeeping,
before final scoring. The [final-scoring continuation](CORRECTION_STATUS_IO_2026-10-17.md)
uses the same complete caches and frozen models, with no repeated extraction,
selection or refitting. Its fresh local output directory is
`runs/apmi_null_broad_fits_20261017_zero_corrected_final_recovery/`.

## Original October17 attempt (failed, preserved)

**Focused fitting/selection/final evaluation launched October 17 at 9:46 AM
EDT with 12 workers.** All400 generation streams completed. The
[prospective focused-analysis amendment](AMENDMENT_2026-10-17.md) replaces the
104-candidate selection with empirical quadratic versus PCHIP for this pass;
the broader GPD/hybrid/spline analysis is deferred. Code was frozen at
`481ac20` before statistical access; all132 tests passed (90 new fitting tests).
This is not a claim that either function has passed final calibration.

The automatic pipeline constructs from160 sizes, selects on20 development
sizes, refits once on180 sizes, freezes its primary and only then opens the
200 independent validation streams and20 held-out-size fitting streams.
No runner-up fallback or engine/default change is allowed. Local artifacts:
`runs/apmi_null_broad_fits_20261017/`; request SHA256:
`1a0a8af9927d9f0b0735f2470b58701e163e1c75f2d649b2824c3a8b1bf2b313`.
`status.json`, `stdout.log`, `stderr.log` and (if needed) `failure.json` record
execution. Raw data and sorted caches remain ignored, outside Git history.

For a new authorized analysis directory, the implementation entry points are
`fit_pipeline.py freeze --plan <generation-plan> --out <fresh-run-directory> --restart-from <failed-run-directory>`
then `fit_pipeline.py run --request <fresh-run-directory>/request.json`.
The controller refuses a second run of an already-started request. Do not
rerun final evaluation to select a favorable result.

**Launched October 16, 2026 at 2:07 PM EDT with 12 workers.** See the
[launch record and status commands](LAUNCH_2026-10-16.md), not a final-result
or continuously updated status report. The new
[execution amendment](EXECUTION_2026-10-16.md) and
[frozen analysis choices](ANALYSIS_SPEC_2026-10-16.md) govern the launch.
Generation is checkpointed and separate from model fitting; validation stays
statistically sealed. No engine/default change or automatic model promotion.

On October 15, 2026, the user requested a prospective grid
of m=50..10000 in steps of 50 with 10M fitting plus 10M validation draws,
then explicitly chose to stop after timing and the detailed protocol.
That original stop was superseded by the explicit October 16 launch request,
again specifying **12 workers**.
Measured twelve-worker throughput projects to roughly **9-10 hours of
generation**, with fitting and analysis additional; this is not a guarantee.

- [Detailed prospective protocol](PROTOCOL.md): 200 sizes, eight probability
  levels through 1e-7, user-approved 10% relative null-rate error target,
  sealed validation/test-m design and candidate function families.
- [Measured runtime and capacity](TIMING.md): small timing draws only, excluded
  from scientific calibration. Full sweep storage would be 32 GB decimal.
- The [completed 19-size study](../expanded_10m/RESULTS.md) remains separate
  and unchanged. No new accepted models, smooth functions or engine defaults
  have been produced by this planning work.

The existing fixed q=0.995 GPD tail cannot cover p=0.05 or 0.01. A single
GPD across this broader range is a hypothesis to test, alongside empirical
body/tail and quantile-surface alternatives. At 10M validation draws,
p=1e-7 yields only one expected event and cannot establish 10% accuracy.

## Generation commands

Use Windows Python and WSL Ubuntu. Planning, raw generation and subsequent
statistical analysis are separate phases. Replace paths only after verifying
the source/executable pins. Never reuse another plan's output directory.

```powershell
python scripts/check_benchmarks.py --group apmi_broad_generation
python benchmarks/apmi_null_m_sweep/broad_grid_10m/generate.py plan --engine-root D:/GitHub/SJARACNe --generator D:/GitHub/SJARACNe/SJARACNe/bin/apmi_null_generator.exe --python C:/Users/adamd/miniconda3/python.exe --distro Ubuntu --out runs/FRESH_BROAD_GRID --protocol benchmarks/apmi_null_m_sweep/broad_grid_10m/EXECUTION_2026-10-16.md --analysis-spec benchmarks/apmi_null_m_sweep/broad_grid_10m/ANALYSIS_SPEC_2026-10-16.md
python benchmarks/apmi_null_m_sweep/broad_grid_10m/generate.py run --plan runs/FRESH_BROAD_GRID/plan.json --workers 12 --only-m 50
.\benchmarks\apmi_null_m_sweep\broad_grid_10m\start_generation.ps1 -PlanPath runs/FRESH_BROAD_GRID/plan.json
python benchmarks/apmi_null_m_sweep/broad_grid_10m/generate.py status --plan runs/FRESH_BROAD_GRID/plan.json
```

The hidden launcher resumes only verified completed streams and uses twelve
workers for the remaining largest-m-first tasks. The bounded m=50 smoke is
part of the same 400 streams, not extra draws. Failed or incomplete attempts
block automatic resume; they are never overwritten or retried until favorable.
Read-only status does not assert process liveness: also verify the controller
PID, recent heartbeat and native processes.

To stop new launches while allowing active streams to finish and checkpoint:

```powershell
python benchmarks/apmi_null_m_sweep/broad_grid_10m/generate.py stop --plan runs/FRESH_BROAD_GRID/plan.json
```

Keep the workstation powered and awake, and do not modify the pinned engine,
controller, test, launcher or protocol/specification files during generation.
Source/pin drift stops new launches and preserves failed evidence. No machine
power settings are changed by the launcher.
