# Broad-grid AP-MI calibration: process and results

**Completed October 17, 2026.** The [summary](RESULTS.md) and
[full report with plots](results_2026-10-17/RESULTS.md) retain the measured results.
PCHIP was selected on development data; 6599/6600 moderate observed-rate checks
were within 10%. The stricter simultaneous-interval rule did not confirm the
complete core grid. This is estimator calibration, not biological FDR validation.

The benchmark did not itself change engine defaults. Its frozen surface was
adopted later by [SJARACNe2](https://github.com/adamdingliang/SJARACNe2);
[current workflow settings](https://github.com/adamdingliang/SJARACNe2/blob/develop/SJARACNe/wdl/README.md#default-parameter-values)
are documented in the software repository.

## Benchmark process

1. Simulate independent rank pairs at 200 sizes m=50,100,...,10000, with
   10M fitting and 10M independent validation draws per size, Npar=40.
2. Construct empirical quadratic and PCHIP surfaces on 160 sizes; select on
   20 development sizes at four probabilities (80 evaluation cases).
3. Refit once on 180 sizes, freeze the selected procedure, then evaluate all
   200 validation streams. Twenty sample sizes never train the final surface.
4. Retain every planned case and separate observed-rate errors from
   simultaneous-interval confirmation.

PCHIP interpolates empirical MI quantiles; it does not fit a parametric tail.
The frozen specifications call an (m,p) evaluation case a "cell"; this is a table
entry, not a biological cell or an independent dataset. Their wording is unchanged.
The [full report](results_2026-10-17/RESULTS.md) preserves both surfaces,
comparators, diagnostic probabilities and corrections.

## Frozen function and provenance

The [design section](results_2026-10-17/RESULTS.md#design-numerical-policy-and-opening-order)
defines quantiles, log-coordinate interpolation and probability scope. Exact
training-knot queries return the stored binary64 cutoff without a log/exp round trip.

- [Frozen primary](results_2026-10-17/primary.json): SHA-256
  `8b4104be3f3ffe0a476a4dd7c8f7f6d95f00f1a51fa467c7194edf3806d427f5`.
- [Historical exporter](https://github.com/adamdingliang/SJARACNe2/blob/fdbc69c281d57f3b6e175d2ecd4d8e9e1e2280ee/tools/export_apmi_pchip.py)
  represents that surface without refitting, reselection or new draws.
- [Bundled JSON at that port](https://github.com/adamdingliang/SJARACNe2/blob/fdbc69c281d57f3b6e175d2ecd4d8e9e1e2280ee/SJARACNe/config/apmi_pchip.json):
  SHA-256 `5ae44f3ec251282b242e1e25e5695fe8c6d80a0e7a3f156170dbb72c29e09f59`.

Python and native cutoff evaluators use the bundled data without this repository,
raw simulations or SciPy interpolation. The full workflow retains its normal
dependencies. [Representation checks](RESULTS.md#evidence-and-limitations) verify
the port, not new statistical calibration.

## SJARACNe runtime policy

The initial [opt-in integration at `86f8729`](https://github.com/adamdingliang/SJARACNe2/tree/86f8729087b3a6d22bdce128649b4e49d725fb9e)
is historical. Current workflows use PCHIP by default, with TF `pb=0.001` and
SIG `pb=0.0005`; the explicit legacy profile uses affine conversion.

For a PCHIP cutoff lookup (`pb != 1`), the selected integer `m` must be
50..10000, Npar must be 40, and p must be 1e-7..0.05 with matching kernel schema
and sampling without replacement. Native `-p 1` bypasses cutoff evaluation;
an explicit native `-t`, including zero, overrides probability conversion.

- `p<0.0005` warns about the principal assessment range; `p<=1e-5` also warns
  about limited extreme-tail Monte Carlo precision. Warnings do not reject
  supported requests or certify accuracy.
- Off-grid m, such as 80, is interpolated and warned; representation checks do
  not add statistical calibration there.
- Invalid inputs, crossed knots, estimator mismatches and unsupported PCHIP
  replacement/replay combinations fail without repair, extrapolation or fallback.
- Native headers record model hashes, schema, actual m/Npar, warning status,
  requested probability and round-trippable decimal/hex binary64 cutoffs.

The current [software guide](https://github.com/adamdingliang/SJARACNe2/blob/develop/SJARACNe/wdl/README.md#interpretation-and-calibration-limits)
separates supported inputs from the statistical evidence limits.

## Reproduce the summary plots

This command regenerates presentation plots from the committed score table;
it does not generate draws, fit or select a model:

```powershell
python benchmarks/apmi_null_m_sweep/broad_grid_10m/plot_pchip_summary.py --csv benchmarks/apmi_null_m_sweep/broad_grid_10m/results_2026-10-17/final_scores.csv --out runs/FRESH_PCHIP_SUMMARY_PLOTS
```

## Corrected numerical-zero analysis

The first October 17 scoring attempt stopped at 09:50 EDT before selection or
final access. The [recorded correction](CORRECTION_2026-10-17.md) treats only MI
in [-64 binary64 epsilon,0) as positive zero, preserves positive values/raw files
and rejects material negatives. All 161 checks passed at that revision.

The corrected run used 12 workers and existing simulations at
`runs/apmi_null_broad_fits_20261017_zero_corrected/`; the failed attempt remains
unchanged. Restart required `--restart-from runs/apmi_null_broad_fits_20261017`
to acknowledge earlier training/development access. This is dated history,
not a live status report.

## Final-scoring continuation

PCHIP selection, the 180-size refit, all 200 validation extractions and 20 test-size
extractions completed before a Windows progress-file replacement error interrupted
bookkeeping. The [continuation](CORRECTION_STATUS_IO_2026-10-17.md) reused complete
caches and frozen models without extraction, reselection or refitting, at
`runs/apmi_null_broad_fits_20261017_zero_corrected_final_recovery/`.

## Original October17 attempt (failed, preserved)

The focused analysis launched at 9:46 AM EDT after all 400 generation streams
completed. Its [amendment](AMENDMENT_2026-10-17.md) narrowed the original
104-candidate plan to quadratic versus PCHIP; broader GPD/hybrid/spline searches
remain deferred. Source was frozen at `481ac20`, with 132 checks passed.

The original request SHA-256 was
`1a0a8af9927d9f0b0735f2470b58701e163e1c75f2d649b2824c3a8b1bf2b313`.
The [October 16 launch](LAUNCH_2026-10-16.md),
[execution amendment](EXECUTION_2026-10-16.md),
[frozen analysis choices](ANALYSIS_SPEC_2026-10-16.md),
[protocol](PROTOCOL.md) and [timing record](TIMING.md) preserve the full history,
including the superseded stop-after-timing decision and 9-10-hour projection.
They are not current completion estimates.

## Generation commands

Historical re-execution requires the recorded generator, source and environment
pins, Windows Python and WSL Ubuntu. Use a fresh output directory. These commands
launch generation; reading the completed report requires no rerun:

```powershell
python scripts/check_benchmarks.py --group apmi_broad_generation
python benchmarks/apmi_null_m_sweep/broad_grid_10m/generate.py plan --engine-root D:/GitHub/SJARACNe --generator D:/GitHub/SJARACNe/SJARACNe/bin/apmi_null_generator.exe --python C:/Users/adamd/miniconda3/python.exe --distro Ubuntu --out runs/FRESH_BROAD_GRID --protocol benchmarks/apmi_null_m_sweep/broad_grid_10m/EXECUTION_2026-10-16.md --analysis-spec benchmarks/apmi_null_m_sweep/broad_grid_10m/ANALYSIS_SPEC_2026-10-16.md
python benchmarks/apmi_null_m_sweep/broad_grid_10m/generate.py run --plan runs/FRESH_BROAD_GRID/plan.json --workers 12 --only-m 50
.\benchmarks\apmi_null_m_sweep\broad_grid_10m\start_generation.ps1 -PlanPath runs/FRESH_BROAD_GRID/plan.json
python benchmarks/apmi_null_m_sweep/broad_grid_10m/generate.py status --plan runs/FRESH_BROAD_GRID/plan.json
```

The m=50 smoke belongs to the same 400 streams. The hidden launcher reused only
verified complete streams and used twelve workers for the remaining tasks.
Failures block automatic resume; read-only status alone does not prove liveness.
Verify process identity and heartbeat before treating an old PID as active.

To stop new launches while active streams finish and checkpoint:

```powershell
python benchmarks/apmi_null_m_sweep/broad_grid_10m/generate.py stop --plan runs/FRESH_BROAD_GRID/plan.json
```

Keep the pinned source, launchers and protocols unchanged during an execution.
New analyses require new frozen requests; final evaluation must not be rerun to
select a favorable outcome. Raw streams and sorted caches remain local.
