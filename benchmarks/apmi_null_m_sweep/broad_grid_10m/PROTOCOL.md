# Proposed broad-grid AP-MI calibration protocol

Status on October 15, 2026: **timing and protocol only**. The user explicitly
selected "Stop after timing and the detailed protocol"; the full sweep,
model fitting and smoothing must not start without a new request. The user
selected a target of **at most 10% relative null-rate error** at directly
testable probabilities. No engine code or defaults are changed by this plan.

## 1. Objective and scope

Develop and independently test a convenient MI-cutoff function T(m,p), rather
than requiring an exact-m file for every dataset. Investigate whether smooth
m-dependent GPD parameters can provide it; do not assume a GPD can represent
every requested probability. Competing empirical-body/tail and quantile-surface
models are research candidates, not automatic runtime fallbacks.

Primary scope is the pinned production-shared AP-MI kernel, Npar=40,
unique ordinal ranks, independent uniform relative rank permutations and no
expression-dependent noise correction. No expression values, DREAM5 labels,
network edge counts or biological reference data enter calibration or selection.
Results do not establish biological FDR or optimal TF/SIG operating settings.

This proposed experiment is separate from the completed 5M and 10M studies.
Their frozen evidence and acceptance labels must remain unchanged. Their
already inspected draws/results may inform exploration, not fresh confirmation.

## 2. Requested grid and computational budget

- Sample counts: m=50,100,...,10000, exactly 200 integer sizes.
- Primary probability grid: 0.05, 0.01, 0.001, 0.0005, 0.0001, 0.00001,
  0.000001, 0.0000001. The intermediate 1e-5 and 1e-6 levels make explicit
  the requested extension through 1e-7; no extra draws are needed per p.
- For each m: 10,000,000 fresh fitting draws and 10,000,000 separate fresh
  validation draws. Total: 4,000,000,000 null pairs, 400 raw streams and
  32,000,000,000 binary bytes (29.80 GiB), excluding small metadata/logs.
- Reuse each fitting distribution across all probabilities, thresholds and
  candidate models. Never regenerate the nulls just to try a different fit.
- Proposed new base seeds: fit=20261019, validation=20261020; actual fit
  seed=base+m, validation=base+1000000000+m. These are RNG identifiers,
  not dates. The future launcher must verify all 400 seeds are unique and
  disjoint from prior scientific streams before generation.
- Pinned generator SHA256:
  `08224b6b20e29628be6d89d22eb7e355f8c6a05623e06f801fae5347a70a7f18`.
  Pin the engine/source hashes, generator, analysis code, protocol, dependencies,
  tie policy, seed derivation and commands in a new immutable run plan.

Timing draws are excluded from every scientific stream. Their seeds may
repeat across capacity-test workers: those workers measure contention, not
independent scientific replication. See [measured timing](TIMING.md).

## 3. Accuracy target, uncertainty and evidence limits

For a fixed candidate cutoff T, define

    r(m,p) = P_null(MI >= T(m,p)) / p

The user-approved target is 0.9 <= r <= 1.1, not exact equality to one.
This is a new prospective criterion, not a retrospective change to the earlier
nominal-in-Clopper-Pearson-interval gate.

At 10M validation draws, the expected counts under nominal calibration are:

| p | Expected count | Approximate relative sampling standard error |
| ---: | ---: | ---: |
| 0.05 | 500000 | 0.14% |
| 0.01 | 100000 | 0.31% |
| 0.001 | 10000 | 1.00% |
| 0.0005 | 5000 | 1.41% |
| 0.0001 | 1000 | 3.16% |
| 0.00001 | 100 | 10.00% |
| 0.000001 | 10 | 31.62% |
| 0.0000001 | 1 | 100.00% |

These are sampling standard errors, not confidence half-widths or total model
uncertainty. At p=1e-7, even a perfectly calibrated cutoff has approximately
37% probability of zero validation exceedances. A wide interval containing
nominal p is not evidence that a 10% accuracy target has been established.

For each fixed-function prediction, report actual counts, observed/nominal
ratio, relative error, a 99.9% pointwise exact Clopper-Pearson interval, and
a simultaneous-study interval. For one preselected primary function across
200 x 8 = 1600 checks, use Bonferroni family confidence 99%, giving individual
confidence 1-0.01/1600 = 0.99999375. This adjustment does not need independence
between the nested p checks. Multiple model families are development candidates;
choose one primary function before opening final validation, not several
post-hoc winners with an unchanged 1600-comparison claim.

Classify precision-supported accuracy using the simultaneous-study interval:

- **Confirmed within target:** the whole interval is inside [0.9p,1.1p].
- **Inconsistent with target:** the interval is disjoint from [0.9p,1.1p].
- **Unresolved:** it overlaps the band but is not wholly inside it, including
  insufficient precision even when the observed ratio looks ideal.

Pointwise classifications may also be tabulated, explicitly labeled as such.
No blanket claim that all eight p values satisfy 10% accuracy is possible from
10M validation draws. Even at p=1e-4, a 99.9% interval near the expected count
is roughly +/-10.4%, so that level is generally precision-limited for this
target; the study-wide interval is wider. The p<=1e-5 levels are tail diagnostics
or extrapolations, not strongly validated probabilities at the proposed budget.
Do not increase draws silently to obtain a passing label.

## 4. Separate training, development and final interpolation tests

Assign m groups before opening any new statistical summaries:

- Final interpolation-test m: 350,850,...,9850 (20 sizes).
- Development m for choosing model/smoother complexity: 450,950,...,9950
  (20 sizes).
- Training m: the remaining 160 sizes, including endpoints 50 and 10000.

The previously explored grid sizes belong to training, not the final test set.
All newly generated validation streams remain sealed until the complete
candidate function, hyperparameters and supported domain are frozen. Basic
raw integrity checks (size, metadata, finite support, hashes) are allowed;
they are not used to choose statistical parameters.

For training m, split each 10M fitting stream deterministically into the first
8M fitting observations and last 2M internal-development observations. These
are both parts of the fitting stream, never called the final held-out stream.
Development-m fitting streams may evaluate interpolation and choose smoothing
complexity, but their final validation streams remain untouched.

After selecting the procedure, refit using the full 10M fitting streams at
the 180 training+development m values. Freeze that single function and its
supported domain before opening the 20 final-test-m fitting distributions or
any of the 200 final validation streams. Evaluate interpolation predictions
at the final-test m without fitting those m or modifying the function.

If test results lead to changes, those data become development evidence;
confirmation of the revised function requires fresh validation. The protocol
does not permit tuning until all m pass against the same held-out streams.

## 5. Fit and compare explicitly specified function families

For a GPD tail, parameters depend on m, not separately on each requested p:

    T(m,p) = u(m) + sigma(m)/xi(m) * ((pi_u(m)/p)^xi(m) - 1)

Use the continuous exponential limit at xi=0. Require p<=pi_u(m), sigma>0,
finite cutoffs within [0,log(m)], and valid finite endpoints where applicable.
Never clip an invalid prediction to hide a support failure. The actual tail
mass and any smoothed model tail mass must both be recorded and distinguished.

Predeclared full-data threshold candidates are q=0.80,0.90,0.95,0.975,0.99,
0.995,0.9975. Require at least 10,000 strict exceedances in an 8M internal fit
and at least 20,000 in the final 10M per-m refit; record failures/skips. The
internal threshold minimum is explicitly different because the fitting subset
is smaller. Do not introduce extra thresholds after inspecting final validation.

Candidate families for implementation review:

1. **One GPD across the requested probability range.** Only thresholds whose
   actual tail mass covers p=0.05 are eligible; q=0.80 or 0.90 are candidates.
   q=0.995 cannot produce a valid p=0.05 or 0.01 prediction. Even q=0.95 may
   not cover p=0.05 because the tail uses strict exceedances and may have ties.
   Whether a sufficiently low-threshold GPD fits accurately is a research
   question, not assumed from extreme-value theory.
2. **Empirical body plus GPD tail.** Fit moderate-p quantiles directly and join
   a GPD at an explicitly chosen tail boundary. Require continuity and
   monotonicity across the join; keep the source/method visible in provenance.
3. **Empirical quantile surface.** Fit T(m,p) directly over well-resolved p
   levels without imposing a GPD. It can provide the same convenient function
   interface, but must not manufacture claims of precision at p=1e-7.

For a GPD-based smooth function, investigate regularized curves for u(m),
log(sigma(m)), xi(m), and pi_u(m), using log(m) as a candidate predictor. Do
not fit unrelated parameter sets for each p and call them one GPD. For direct
quantile surfaces, enforce smaller p giving equal or larger cutoffs. Monotonicity
in m is not assumed: finite AP partitions can produce changes that a forced
monotone-m curve would hide.

Before implementing a full sweep, freeze a finite smoother complexity grid,
loss and tie-breaking rule in the run plan. A proposed grid is cubic-spline
models with 4,6,8 internal knots and a fixed regularization grid, compared
against piecewise-linear interpolation as the simpler baseline. Knot placement,
regularization scaling and domain-edge behavior require explicit implementation
review; they must not be left to adaptive choices made after final validation.
This document is a prospective plan, not an assertion that these models have
already been implemented or tested.

Model selection is driven by fit/internal-development data and development-m
interpolation error at the well-resolved primary p set {0.05,0.01,0.001,0.0005}.
Use equal weighting over these p values and m values in a prespecified
log-null-rate error objective, reporting the worst errors separately. Treat
p=1e-4 as a secondary diagnostic and do not let counts of 10 or 1 choose the
winning smoother. Final confirmation nevertheless reports all eight p levels,
including unresolved or invalid predictions.

The implementation-freeze checklist must fix whether the log-rate loss is
squared or absolute, its exact weighting/normalization, zero-count and
pseudocount treatment, smoother knots/penalties, tie breaking and final-refit
failure handling. A failed 10M refit may not silently drop an m or trigger an
unplanned method fallback. These are required review items before execution,
not details already implemented by the timing-only code.

## 6. Tie handling and matching the actual runtime rule

The inspected engine retains positive MI values at MI>=threshold: native
calculateMI rejects mi<threshold, and adjacency import also uses >=. Fix the
calibration comparator to >=. Record zeros, unique counts, threshold ties,
strict > counts and non-strict >= counts in both streams. The current study's
requested probabilities have positive cutoffs; account explicitly for the
engine's omission of zero-MI edges if a future cutoff becomes zero.

For empirical quantiles, retain the `higher` rule and full-precision values,
not rounded Markdown numbers. Discrete null atoms can make a deterministic
cutoff unable to attain the requested relative-error band; report the observed
tail steps and potential discreteness limitations. Do not claim true-CDF
unattainability from a finite sample alone, or add randomized tie breaking
without a separate policy decision.

## 7. Checkpointed execution, if subsequently authorized

- Use a new run directory and a generation phase separate from statistical
  analysis. Up to eight active CPU workers initially; no nested BLAS threads.
  Schedule large m values early to avoid a long final tail of expensive jobs.
- Complete and verify each (m,stream) separately with raw/meta/provenance hashes,
  native exit status, commands, timing/RSS and a last-written completion record.
  Resume only verified completed streams from this same frozen run plan.
- Preserve incomplete attempts and all failures. No destructive overwrite,
  cross-plan reuse or automatic favorable-result retries. Stream-level
  checkpoints avoid regenerating a good fit stream after an interrupted
  validation stream.
- If a future long run is approved, use a hidden, logged Windows-owned controller
  with recorded PID/start time/plan hash, exclusive lock, heartbeat and
  cooperative stop-after-current-stream behavior. Verify the actual process
  before reporting it running. The workstation must remain powered and awake;
  do not assume product/session lifetime guarantees.
- Do not launch the full generation phase now. No study controller, full-grid
  raw streams, new models or smooth-function fits are authorized in this turn.

## 8. Deliverables and promotion gates

Future deliverables should include all 200 m values and all requested p values,
including failures: raw provenance, per-m summaries, per-(m,p,method) cutoffs,
counts, ties, confidence intervals, error bands, extrapolation labels, GPD
parameters/support, selection history, runtime and interpolation-test results.
Publish compact reports and code only; retain large raw streams locally.

A prospective primary function must outperform or meet the stated accuracy
target on untouched tests; a convenient smooth curve is not evidence of
calibration. Benchmark legacy-affine on the same final draws as a comparator
without tuning it or claiming nominal p is automatically accurate. Keep these
null-calibration comparisons distinct from biological network benchmarks.

Before opening final validation, freeze which primary (m,p) domain is proposed
for supported use. Every check in that claimed domain must be confirmed within
the target using the predeclared study-wide interval; unresolved, invalid or
unavailable predictions are not passes. Do not redefine the claimed domain
after seeing the tests to hide failures. Exploratory subranges may be described
but require new confirmation before promotion. Rare-p diagnostic outputs are
not thereby authorized as supported runtime probabilities.

The 200-point grid does not test every integer m or every interior p. Optional
off-grid m and additional probability checks should be separately budgeted
and frozen before promotion to a general runtime function; they are not
silently added to the 32GB generation budget. Model changes after those tests
again require fresh confirmation.

Any supported calibration artifact should eventually ship inside SJARACNe
with its own method/domain/provenance checks, not depend on this private
benchmark repository. No engine replacement, default p change, hybrid fallback,
interpolation policy or extreme-tail validation claim follows from this protocol.
