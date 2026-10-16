# Prospective broad-grid analysis specification - October 16, 2026

This specification resolves the analysis choices left open in PROTOCOL.md.
It is frozen before the newly authorized generation starts. Generation and
statistical analysis are separate phases: generation may start with this
specification and its immutable run plan; tested analysis-code hashes must be
frozen before any new distribution's statistical summaries are opened. Basic
raw integrity checks are not statistical model selection. Implementation may
proceed while generation runs, but generated statistical results must not be
used to amend this specification or the implementation. A genuine bug fix needs
an explicit recorded amendment and sealing-state audit, not silent replacement.

No engine/default change, biological calibration or guarantee of success is
authorized. The old studies and yesterday's exploratory results remain frozen.

## 1. Streams, roles and allowed access

Use the PROTOCOL.md grid, fresh seeds, kernel and 10M fitting plus 10M validation
draws at each of 200 sizes. Final interpolation-test sizes are
350,850,...,9850; development sizes are 450,950,...,9950; the other 160 sizes
are training. These partitions are fixed, not randomized after generation.

At training sizes use the first 8M fitting draws for candidate construction and
the last 2M only for internal-development diagnostics. At development sizes,
the full 10M fitting stream is used only to score out-of-size predictions and
select a candidate. It is not used in the initial candidate fits. All 200 final
validation streams and the 20 final-test fitting streams stay sealed throughout
selection. No per-m threshold is selected using the 2M diagnostics: each q is
one fixed global candidate, avoiding an undeclared per-m selection algorithm.

After selection, refit that one procedure once on the full 10M fitting streams
at all 180 training plus development sizes. Freeze the resulting function,
model parameters, numerical policy, proposed domain and hashes before opening
the 20 final-test fitting distributions or any final validation. The final-test
fitting streams may then provide exact-m diagnostic baselines but may not train
or revise the primary function. Opening failures and unusual counts must be
reported, not used to choose a second winner.

## 2. Probability grids and inferential roles

The primary report grid is the eight requested probabilities in PROTOCOL.md.
Candidate selection uses exactly {0.05,0.01,0.001,0.0005}, equal weights. No
rare-p count is allowed to choose the winner.

For empirical surfaces use the same 25 decimal probability knots declared by
`../p_axis_refinement/grid.py`: mantissas {1,1.5,2,3,4,5,6,7.5} times
10^-4,10^-3,10^-2, clipped above 0.05, plus 1e-5,1e-6,1e-7. Use the same 49
query probabilities in that module (the union of dense knots, 21 rounded
geometric midpoint probes and the old queries). Pin the source file hash and
literal decimal/float arrays in the analysis manifest. Do not generate extra
probes adaptively. The four selection probabilities belong to these knots.

For the new study, split p interpolation prospectively at p=0.0001: use the
22 knots at or above 0.0001 for a moderate-body PCHIP, and the four knots
{0.0001,0.00001,0.000001,0.0000001} for a separate rare-extension PCHIP.
Both return the identical literal predicted 0.0001 cutoff at their common
boundary, giving value continuity but not requiring derivative continuity.
This is a prospective representation change from yesterday's single 25-knot
PCHIP. Old results are not recomputed. The split prevents uncertain rare knots
or their numerical failures from influencing the moderate-p predictions or
their selection eligibility; all rare results remain visible diagnostics.

The 49-query tables are interpolation and tail diagnostics, not a new
49-probability family-wise acceptance claim. Exact-m empirical cutoffs are
diagnostic baselines, not extra selectable model families.

## 3. Finite model families

There are eight family/threshold choices:

1. Pure GPD with one fixed threshold quantile q=0.80.
2. Pure GPD with q=0.90.
3-7. Empirical body joined to a GPD tail, with one fixed q chosen from
   {0.95,0.975,0.99,0.995,0.9975}.
8. Direct empirical quantile surface, without a GPD.

Each family/threshold is crossed with the 13 selectable m-axis smoothers in
section 4, giving exactly 104 selectable candidates. Logquadratic and PCHIP
m-axis smoothers are fixed benchmark-only comparators for each of the eight
families, giving 16 additional benchmarks. They cannot become primary after
seeing results. There is no per-m q adaptation, optimizer-search expansion,
isotonic repair, favorable-result retry or model-averaging search.

For per-m GPD fits, choose u by the literal binary64 NumPy `higher` quantile at
q, fit strict excesses MI>u with SciPy `genpareto.fit(excesses, floc=0.0)` using
the pinned library's MLE/default optimizer, and record every fit exception and
warning. Require at least 10,000 strict excesses in an 8M fit and at least
20,000 in a final 10M fit. Zero location, positive finite scale and finite shape
are mandatory. Retain exact u, strict-tail count k, count of ties at u, n,
pi_actual=k/n and pi_regularized=(k+1)/(n+1). Use pi_actual, not the regularized
quantity, as the mass in this new study's GPD model and smoothing. This
prospective convention differs from the old calibrator's add-one tail mass;
old artifacts and labels must not be rewritten. The objective pseudocount in
section 6 does not change the fitted mass.

For a negative GPD shape, require its finite endpoint to include all fitting
observations, with tolerance 64*float64_epsilon*max(1,log(m)) for that support
diagnostic. Record the endpoint and its relationship to the physical upper
bound log(m), but do not reject a model solely because its extrapolated
endpoint is above that bound: positive-shape GPDs likewise have unbounded
modeled support. Every requested cutoff must nevertheless remain literally
finite and within [0,log(m)]; do not clip it to either bound or the endpoint.
Do not call the existing cutoff helper that clips a result to its endpoint.
Support failure or too few excesses at any construction m makes that global
candidate unavailable; do not silently omit that size or replace q there.

Smooth log(u), log(scale), shape and logit(pi_actual) separately versus log(m),
using the same declared smoother for all four quantities in a candidate. Any
u<=0 or pi outside (0,1) makes that GPD construction invalid. Record smoothed
mass separately from each observed per-m mass; never silently substitute the
observed mass at one prediction size. For p<=pi_smoothed use

    L = log(pi_smoothed/p)
    T = u + scale*expm1(shape*L)/shape  (shape != 0)
    T = u + scale*L                   (shape == 0)

This stable expression, not a rounded near-zero-shape branch or endpoint clip,
defines the GPD query. Validate scale, support and p<=pi at every query. Pure
GPD candidates must cover the largest selection p=0.05 at every scored size.
The continuous tail does not model an atom at u; record MI>=u versus MI>u so
this limitation remains visible.

For the direct empirical family extract the 25 `higher` cutoffs independently
from each construction m. Smooth log(cutoff) across m separately for each p.
Nonpositive empirical cutoffs are invalid for this representation, not repaired
by a small positive constant. For a queried m, use the two separately scoped
PCHIPs specified in section 2 on log(p) versus log(cutoff), with extrapolation
disabled. Exact p=0.0001 returns their shared literal predicted knot. The
moderate-body PCHIP requires all its 22 knots to be valid and noncrossing;
failure of a rare-only knot, rare-column fit or rare-extension PCHIP makes
that extension unavailable without invalidating an otherwise valid moderate
candidate. Reject crossed or nonpositive knot sequences within their declared
scope instead of sorting, repairing or dropping knots after inspecting data.

For a hybrid candidate, construct the same empirical 25-knot surface and the
GPD parameter curves. At each queried m use the GPD for p<=pi_smoothed. For
p>pi_smoothed use PCHIP on log(p), log(cutoff) through the empirical knots
strictly above pi_smoothed, inserting the boundary pair (pi_smoothed,u). Within
each body segment apply the same prospective 0.0001 scope split as the direct
empirical family if the body extends below that boundary. This
gives cutoff continuity at the boundary. If pi_smoothed>=0.05 all requested
probabilities use the tail. Otherwise a valid body must have the upper
endpoint knot and a monotone boundary-to-body sequence. No body extrapolation,
boundary shifting, rescaling or discontinuity repair is allowed. An exact
query p=pi_smoothed returns literal u. The body/tail source is reported for
every prediction.
An invalid rare GPD query is reported as such and does not invalidate a
hybrid's moderate-domain eligibility unless its shared parameter construction
or moderate predictions are themselves invalid.

## 4. Exact m-axis smoothers

Let x=(log(m)-log(50))/(log(10000)-log(50)). This fixed coordinate has domain
[0,1] in both construction and final refitting. No m extrapolation is allowed.

The 13 selectable smoothers are:

- Piecewise-linear interpolation in x of each transformed response, with
  literal transformed-knot return at a supplied x and no extrapolation.
- Cubic B-splines with K in {4,6,8} interior knots at j/(K+1), j=1..K,
  repeated four endpoint knots at 0 and 1, crossed with lambda in
  {0,0.01,1,100}. Use the standard complete degree-3 B-spline basis, so the
  number of columns is d=K+4. Use the same fixed knots after final refit.

Normalize each spline basis column to unit root-mean-square on the construction
m values; record and reuse its scale for predictions. If Z is this normalized
basis, form R0=integral_0^1 Z''(x)^T Z''(x) dx. Compute it by eight-point
Gauss-Legendre quadrature separately in each knot interval. Set
R=R0/(trace(R0)/d). The coefficient vector minimizes

    mean_i (Z_i beta - y_i)^2 + lambda * beta^T R beta.

Do not penalize coefficients with an unrelated identity ridge; R has the
intended linear null space. Solve via deterministic symmetric least squares
or the corresponding augmented least-squares system and record rank/condition
diagnostics; do not introduce an adaptive ridge after a numerical failure.
Responses y are the transformations specified in section 3. No per-response
lambda selection or weighting by estimated variance is allowed. With lambda=0,
use unpenalized least squares in this same fixed basis. Column normalization
is recomputed and recorded at the final 180-size refit because its construction
m set changes, while K, lambda and coordinate do not change.

Benchmark-only logquadratic is unweighted least squares in {1,x,x^2} for each
transformed response. Benchmark-only PCHIP interpolates each transformed
response versus x with extrapolation disabled. GPD and empirical response
transformations are identical to the corresponding selectable family.

## 5. Numerical policy and shape checks

Use IEEE754 binary64 end to end, little-endian native raw input and pinned
NumPy/SciPy versions. Empirical `higher` quantiles retain full binary64 values;
store their hexadecimal representations as well as round-trippable JSON floats.
At an exact construction m and exact empirical p knot, a genuine interpolating
smoother (piecewise-linear or benchmark PCHIP) must return the original literal
empirical cutoff, not exp(log(cutoff)). At an exact p knot after a noninterpolating
m smoother return that predicted knot literally, not a second log/exp round
trip. Hybrid boundary queries return literal u. Do not override a spline or
quadratic's predicted value with an observed value at its construction m.

This is a prospective exact-knot convention. Yesterday's frozen log/exp
round-trip results are not recomputed or relabeled under it. At every query
record the literal cutoff and counts at nextafter(T,-infinity), T and
nextafter(T,+infinity) to expose numerical atom sensitivity; adjacent-float
counts do not choose the cutoff.

Require smaller p to give an equal or larger cutoff. Check all 25 predicted
empirical knots, hybrid joins and all 49 query probabilities at every grid m
using the function alone, before opening any validation counts. Crossings or
support violations in the proposed moderate-p domain make a selectable
candidate ineligible. Outside that domain invalid rare-p predictions remain
explicit diagnostic failures rather than removing a good moderate-p candidate.
Record moderate-body and rare-extension shape/support checks separately. The
22-knot moderate construction must remain valid in full; failures restricted
to the three rare-only knots or their separate extension must not leak into
moderate predictions or eligibility. At the common 0.0001 boundary both
interpolants return the identical predicted knot; a failure of that shared
knot invalidates both. For hybrids the same scope policy applies to empirical
body portions, and rare-only GPD query failures remain diagnostic. This
prospective split is fixed before examining new draws, not favorable
post-hoc deletion of noisy knots.
Do not force monotonicity in m, sort crossed cutoffs, clip invalid predictions,
round cutoffs for scoring or add random tie breaking.

All scored tail probabilities use the actual engine comparator MI>=T. Report
strict MI>T, exact tie counts, zeros and unique counts separately. For a zero
cutoff, additionally report the engine's omission of zero-MI edges; a zero
cutoff is not valid in these log-cutoff candidates.

## 6. Selection objective, tie breaking and failed refits

For a fixed candidate and scoring stream with n observations, let c be the
MI>=T count. Define the selection rate as (c+0.5)/(n+1), solely to keep log loss
finite at c=0 or c=n. The exact loss is

    mean over 20 development m and four selection p of
        [log(((c+0.5)/(n+1))/p)]^2.

Thus all 80 cells have equal weight. Do not weight by tail counts, number of
edges, apparent precision or per-cell uncertainty. Display the unregularized
observed rate c/n and its worst/median errors alongside this loss. Use the
same formula for last-2M internal diagnostics, which are reported but do not
change the primary candidate ordering. Any invalid or unavailable primary
cell gives infinite candidate loss; no available-case average is permitted.

Choose the smallest finite loss. Losses within absolute 1e-12 of the minimum
are ties. Resolve ties by this prospective order: piecewise-linear first;
then spline K ascending with lambda descending; within that smoother order,
direct empirical first, pure GPD q ascending second, hybrid q ascending last.
Persist the complete ordered candidate list and all failures before selecting.
Quadratic/PCHIP benchmarks and exact-m empirical baselines are never eligible.

If no candidate has finite loss, record no selected function. After selection,
a failed 180-size refit, unavailable primary prediction, support failure or
crossing means no primary function is promoted. Do not switch to the runner-up
or drop failing sizes. Diagnostic alternatives may be reported with their
selection and opening history, but cannot inherit the original primary-test
claim. No full-data override is made merely because a simpler candidate was
more accurate at selected individual cells.

## 7. Frozen proposed domain, final scoring and claims

The prospectively proposed moderate-p function domain is m in [50,10000] and
p in [0.0005,0.05]. It must not be narrowed after inspecting final counts to
hide failure. Continuous-domain promotion is not established by this study:
the directly tested core is 200 grid sizes crossed with the four selection
probabilities, while additional fixed probabilities are diagnostics. Every
core check must meet the interval criterion before calling even that grid
confirmed. Off-grid integer m and arbitrary interior p need separately frozen
confirmation before a general runtime-domain claim.

For the single frozen primary function, report all 200x8=1600 primary-grid
counts, actual/nominal ratios, absolute relative errors, 99.9% pointwise exact
Clopper-Pearson intervals and Bonferroni 99% study-family intervals (individual
confidence 1-0.01/1600). The 49-query diagnostic family receives descriptive
99.9% pointwise intervals only, explicitly not simultaneous 99% coverage over
all 9800 queries. No multiple-winner or post-hoc favorable-subdomain claim is
allowed under the 1600-comparison correction.

Classify confirmed when the whole simultaneous interval lies inside
[0.9p,1.1p], inconsistent when disjoint, otherwise unresolved. Missing,
invalid, zero-count or unresolved predictions are not passes. The rare levels
retain their planned labels as weakly measured diagnostics/extrapolations;
10M draws cannot establish 10% accuracy at 1e-7. Report all failures even if
they make a universal function unusable.

Score the untouched legacy-affine function on the same final draws as a fixed
comparator. Do not tune its coefficients or interpret a nominal p label as an
independent guarantee. None of the scientific conclusions requires network
inference, biological reference edges or downstream activity calculations.

## 8. Implementation gate and execution boundary

Before statistical access, freeze tested code plus a manifest enumerating all
104 candidates, 16 benchmarks, basis/penalty rules, grids, stream permissions,
objective and refit/validation phases. Synthetic tests must cover exact-knot
preservation, atom/tie comparisons, GPD support/zero-shape/negative endpoints,
hybrid continuity, crossing rejection, spline penalty normalization and ranks,
candidate tie order, no-fallback failed refit, and refusal to read sealed data.

Generation may proceed under its separately pinned immutable plan, with 12
native single-threaded workers and no statistical controller. Until the
analysis implementation gate is satisfied, neither fitting summaries nor
development/test/validation CDFs are opened. Final validation is never opened
automatically merely because all 400 generation jobs finish. No new draws,
extra retries, off-grid sizes or second confirmatory study are implicit in
this specification.
