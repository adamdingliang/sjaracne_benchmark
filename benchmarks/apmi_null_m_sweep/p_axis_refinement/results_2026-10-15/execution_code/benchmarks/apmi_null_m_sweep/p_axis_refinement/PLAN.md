# Denser-p refinement of the existing smooth-cutoff exploration

Prospective refinement specification, October 15, 2026. Requested after
reviewing the original smoothing results. Previously inspected draws and
validation results are development evidence, not fresh confirmation. Original
plans, source streams, sorted caches and published results remain unchanged.
No new null generation, GPD optimization, high-m sweep, runtime model, engine
change or default change is authorized by this analysis.

## Fixed inputs and probability grid

Reuse all nineteen original sizes m=30,50,80,90,100,150,200,250,300,400,500,
516,600,644,700,725,800,900,1000, each with 10M fitting and 10M validation
draws, Npar=40. Use the verified sorted copies produced by the first smoothing
analysis. Before fitting, verify its frozen request/completion/extraction/code
hashes, all 38 cached stream hashes and ascending finite MI support, original
raw hashes and stream identity. No re-sorting or new large stream copies.
Use at most twelve verification/extraction workers and one numerical thread
per process. Fail closed if any size/cache/provenance fails; retain failures.

Coarse p knots remain 0.05,0.01,0.001,0.0005,0.0001,1e-5,1e-6,1e-7.
Dense knots are mantissas {1,1.5,2,3,4,5,6,7.5} times 10^e for
e=-4,-3,-2, retaining p<=0.05, plus the three original rare knots
1e-5,1e-6,1e-7. This gives 22 moderate knots and 25 total knots, including
every coarse knot. Construct the grid with decimal arithmetic, not approximate
floating duplicate matching.

New probability-interpolation probes are the geometric midpoints of the 21
adjacent moderate dense-knot intervals. Freeze their decimal values to fourteen
significant figures. None is a coarse/dense knot or an old query point.
Also retain all sixteen old query probabilities as regression diagnostics.
The union contains 49 distinct query p values. Record overlapping role flags,
not a misleading single role: old query, coarse knot, dense knot, new probe,
main operating p, moderate, lower-precision diagnostic and rare diagnostic.

Old moderate probes such as 0.02 and 0.005 now become dense fitting knots.
Improvement at those points is a regression result, not new evidence for
p interpolation. The new midpoint probes are the main refinement comparison.

## Frozen candidates and leakage controls

Keep the original three m-axis rules: global degree-one and degree-two
least-squares polynomials of log(cutoff) on log(m), and PCHIP in log(m).
For each rule compare the old coarse and new dense p grids. Both use the
same PCHIP interpolation of log(cutoff) against log(p), without extrapolation.
No new smoothing hyperparameters, reweighting or model-family search.

In each fold leave out the entire evaluated m: neither its fitting quantiles
nor its old GPD parameters train the smooth surface. Fit on the other eighteen
sizes. Use all sizes regardless of old acceptance labels. The seventeen
interior folds are interpolation; m=30 and 1000 are endpoint extrapolation.
PCHIP is unavailable at endpoints. Do not substitute a nearby size.

Reject any full predicted knot sequence that crosses quantile order. Retain
the offending p/cutoff pairs, and mark that candidate fold's full surface
unavailable. No sorting, isotonic repair, clipping or rare-knot omission. If a
rare-knot issue invalidates moderate predictions, explain it rather than
reporting only the valid subset. Physical MI support must also hold.

Include three decomposition baselines: coarse and dense p-axis interpolation
of that evaluated size's own empirical knot cutoffs, plus its exact fitting
quantile at every query p. These are explicitly NOT leave-m-out methods.
No GPD refit or parameter smoothing is needed in this refinement; its earlier
results remain available unchanged as context.

## Evaluation and summaries

Use fitting-only empirical `higher` quantiles, and the engine's MI >= cutoff
rule. Score both original streams at each query; retain >=, strict > and tie
counts, observed/nominal ratios, relative null-rate and cutoff errors, and
99.9% pointwise Clopper-Pearson intervals where applicable. In-sample baseline
fit-stream intervals are not applicable. Previously inspected validation
intervals remain descriptive, not simultaneous or post-selection guarantees.

Main new-p comparison: seventeen interior sizes times sixteen new midpoint
probes with p>=0.0005 = 272 checks per candidate. Report all candidates and
all unavailable outcomes, median/90th/worst absolute null-rate errors,
observed fractions within +/-10% with the full denominator, and pointwise
interval classifications. Also report all 357 midpoint checks down to
p=1e-4; these have less precision near the lower endpoint.

Retain the 34 operating-probability checks at p=0.001 and 0.0005, old-query
regression checks, all query values, and endpoints separately. Compare coarse
predictions/counts on all old query points to the frozen earlier analysis;
unexpected differences are errors to investigate, not silently accepted.
Provide exact-m baseline error/ties alongside smooth-surface failures.

Probabilities below 1e-4 are tail diagnostics, not the model-selection target.
At 10M draws, p=1e-5,1e-6,1e-7 have only 100,10,1 expected exceedances.
No apparently good rare-p curve establishes 10% accuracy. Do not tune until
all reused validation points pass or alter this grid after seeing results.

## Provenance, deliverables and stopping point

Freeze this plan, grid and tested implementation hashes before extracting new
quantile summaries. Record command/environment, all inputs and code hashes,
per-size records, predictions, evaluation/summary tables, crossing diagnostics,
old-result reproduction checks, runtime and figures. Compact files may be
published; original raw/sorted payloads stay local and read-only.

This refinement can support another exploratory decision, not runtime promotion.
It cannot establish all integer m, all interior p, m>1000, biological FDR or
default TF/SIG operating choices. A promising selected procedure still needs
a frozen supported domain and fresh confirmation. Stop after this refinement;
do not launch the expensive broad-grid sweep automatically.
