# Focused empirical-surface analysis amendment — October 17, 2026

This amendment is recorded after generation, **before statistical access to any
new broad-grid stream**. It is not the original preregistration. The October 16
specification and all generation artifacts remain unchanged. The user's request
to run quadratic and PCHIP fitting, selection and final evaluation is interpreted
as a focused comparison of these two empirical-cutoff surfaces. The broader
104-candidate GPD/hybrid/spline analysis is deferred, not silently reported as
completed. An asynchronous clarification was offered before access; absent a
contrary instruction, this is the scoped interpretation of the current request.

## What changes

Only direct empirical surfaces are selectable: quadratic first, PCHIP second.
Both were benchmark-only in the October 16 plan. No GPD, hybrid, linear or spline
candidate participates in this pass. Quadratic is ordinary unweighted least
squares of log(cutoff) on {1,x,x²}; PCHIP interpolates log(cutoff) versus x,
where x=(log(m)-log(50))/(log(10000)-log(50)). Both use the same 25 empirical
`higher` quantile knots and separately scoped moderate/rare log-p PCHIPs.

After selecting one method, refit **both fixed procedures once** on the same
180 non-test sizes × full 10M fitting draws. The nonwinner is a prespecified
descriptive comparator, not a fallback. Freeze both artifacts and the primary
identity before opening final data. A failed primary refit stops the primary
workflow; the runner-up cannot replace it or acquire its confirmatory claim.

## What does not change

- Sizes: m=50,100,...,10000. Training160; development20 (m mod500=450);
  final interpolation-test20 (m mod500=350).
- Initial construction: first8M training fitting draws. Last2M are internal
  diagnostics only. Development10M is scoring-only until selection.
- All validation streams and final-test fitting streams remain sealed until
  the selected180-size refit and its hashes are frozen.
- Selection: all80 development cells, four p={.05,.01,.001,.0005}, equal-weight
  mean squared log(((c+.5)/(n+1))/p). Invalid primary cells or moderate shape
  failures at any of200 sizes mean infinite loss. Absolute ties≤1e-12 prefer
  quadratic. No available-case selection or post-refit reranking.
- Literal binary64 empirical knots, engine MI>=T comparator, exact/strict/tie
  and adjacent-ULP diagnostics; no rounding, clipping, repair or extrapolation.
- Full22-knot moderate construction must be valid; three rare-only failures
  cannot invalidate an otherwise valid moderate function. Check all49 queries
  at all200 sizes using functions only before validation access.
- Proposed domain remains m∈[50,10000], p∈[.0005,.05], not narrowed after counts.
  This grid does not establish every off-grid m or arbitrary p.
- One selected primary: 200×8=1600 counts get99% Bonferroni family intervals;
  99.9% pointwise intervals also reported. Whole simultaneous interval inside
  [.9p,1.1p] means confirmed, disjoint means inconsistent, otherwise unresolved.
  All800 core checks must confirm before even the tested core grid is accepted.
  All49 probabilities and other models are descriptive pointwise diagnostics.
- Rare-tail results remain weakly measured:10M draws expect100,10,1 exceedances
  at1e-5,1e-6,1e-7. An interpolated number is not a10%-accuracy guarantee.
- Untouched legacy-affine coefficients are a fixed comparator; exact-m fitting
  empirical cutoffs are diagnostic only, never a runtime fallback.

For the exact-m comparator, calculate all49 direct empirical quantiles from
the180 refitting streams after selection and20 test fitting streams after the
primary freeze. Only the declared25 knots enter either fitted surface; the
remaining quantiles cannot select or change a function. This keeps the
exact-m diagnostic definition identical at construction and test sizes.

## Implementation/access gate

Before access, freeze this amendment, tested numerical/data/controller/report
code, literal grids, partitions, library versions and original plan hash in an
immutable request with a SHA256 sidecar. Each phase rechecks source pins.
Selection and primary freeze are separate hash-locked records. Role-scoped
extraction rejects sealed streams before reading raw bytes. All accessed raw
bytes are checked against completed generation hashes. Use at most12 processes,
one numerical thread each. Only fresh ignored `runs/` caches are written.

No new simulations, SJARACNe engine/default edits, biological claims, adaptive
probability grids or automatic second confirmatory attempt are authorized.
