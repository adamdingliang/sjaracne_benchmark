# Cheap smooth-cutoff feasibility analysis

Prospective analysis specification, October 15, 2026. This analysis reuses
already inspected evidence. It is exploratory, not a new calibration gate or
fresh independent confirmation. The separate 200-size broad-grid protocol
remains unexecuted. No null generation, engine changes or default changes.

## Inputs and concurrency

Use all nineteen exact sizes from the expanded 10M fitting + 10M validation
study, including rejected GPDs and both endpoints, without selecting sizes by
their previous acceptance labels. Verify the frozen source plan, attempts,
reports, raw metadata, stream lengths, SHA256 hashes and finite MI support.
Original streams and published evidence are read-only. Make sorted copies in
a new ignored `runs/` child; never sort or overwrite source data in place.
Use at most twelve extraction workers and one numerical-library thread each.
Retain all failures; do not silently omit a size or regenerate a stream.

## Frozen candidate functions

Compare these same three m-axis smoothers in two families:

- `loglinear`: a global degree-one polynomial in log(m).
- `logquadratic`: a global degree-two polynomial in log(m).
- `pchip`: shape-preserving piecewise cubic interpolation in log(m), with
  extrapolation disabled. This is a flexible interpolation comparator, not
  a low-parameter global model.

Direct quantile family: estimate fitting-only `higher` quantiles at p knots
0.05, 0.01, 0.001, 0.0005, 0.0001, 1e-5, 1e-6, 1e-7. Smooth log(cutoff)
against log(m) separately at these fixed knots. At query p, interpolate
log(cutoff) with PCHIP against log(p), without extrapolation. Check quantile
ordering; crossing/invalid predictions must be reported, not sorted or clipped.
Rare-p knots are noisy diagnostics, not precise tail calibration estimates.

GPD family: reuse the existing q=0.995 primary parameters, without fitting new
GPDs. Smooth log(u), log(scale), shape and logit(p_u) against log(m).
Here p_u is the original (strict tail_count+1)/(N+1) pseudocount probability,
not exactly tail_count/N. p is an inverse-tail-function input, not a separate
set of fitted parameters. Require p <= predicted p_u, positive scale, finite
valid GPD support and 0 <= cutoff <= log(m). No clipping or fallback.
This tests smoothing of the existing GPD procedure, not all possible GPD
thresholds or a jointly pooled alternative fit. The q=0.995 GPD cannot cover
the p=0.05/0.01 body; show those unsupported predictions explicitly.

## Leave-entire-size-out evaluation

For each m, omit that size's entire fitting distribution and parameter set
from candidate-function training. Train on the other eighteen sizes, then
predict cutoffs for the omitted m. Primary interpolation summaries use the
seventeen interior sizes only. The two endpoint folds (m=30,1000) require
extrapolation and are reported separately; PCHIP is unavailable there.
Do not replace endpoint failures with nearest-neighbor values.

Evaluate the eight p knots and eight additional probability probes, not used
as direct-surface training knots: 0.02, 0.005, 0.002, 0.00075, 0.0002, 5e-5,
5e-6, 5e-7. No new draws are needed for these checks. Evaluate both the omitted
fitting stream (exploratory size generalization) and its previously inspected
validation stream (independent RNG stream, not untouched study confirmation).
The extra probes assess p interpolation for the direct family; GPD uses its
analytic inverse tail throughout its available p domain.

Always include exact-m fitting-quantile and exact-m unsmoothed GPD baselines.
These use the omitted size's fitting data and are explicitly NOT leave-size-out
methods. Keep original GPD acceptance labels unchanged.

## Metrics and conclusions

Use the engine's MI >= cutoff comparator. Record >=, strict > and ties, null
rate/nominal p, relative null-rate error, cutoff error relative to the exact-m
empirical fitting quantile, and 99.9% pointwise Clopper-Pearson intervals.
Intervals describe fixed-prediction binomial uncertainty only, not uncertainty
in the whole fitted function, simultaneous coverage or post-selection validity.
Do not compute binomial intervals for exact-m baselines evaluated on their own
fitting stream: their cutoffs depend on those same observations. Retain their
counts as in-sample diagnostics with the interval marked not applicable.

Primary comparisons are p=0.001 and 0.0005 over seventeen interior m (34
checks per candidate). Report all candidates' valid/invalid counts, median,
90th percentile and worst absolute relative null-rate errors, observed
fractions within +/-10%, and pointwise interval classifications. Do not choose
a runtime winner or create accepted model artifacts. Secondary p levels,
additional p probes and endpoints remain visible, including support failures.
At 10M draws, p=1e-5,1e-6,1e-7 have only 100,10,1 expected events: precise
10% calibration is not established by apparently good ratios or wide intervals.

Limit scope to these nineteen sizes and the evaluated probabilities. Results
cannot establish m>1000, every integer m, every interior p, biological FDR or
the TF/SIG operating defaults. Any attractive revised function needs a frozen
procedure and fresh confirmation before promotion. Publish compact code,
tables, plots, timings and provenance only; sorted payloads stay local.

## Execution record

Freeze this plan and candidate implementation hashes before reading new
quantile summaries or evaluating candidates. Unit tests and code inspection
may precede execution. Record source pins, environment, commands, code hashes,
runtime, all sizes and all prediction statuses in the output package.
