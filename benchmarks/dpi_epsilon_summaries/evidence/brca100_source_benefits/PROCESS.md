> Publication copy of a frozen local report/process. Scientific text and numbers are unchanged; relative links are adapted to this compact package. See [publication provenance](PUBLICATION.json) for original hashes and [local artifacts](README.md#local-artifacts) for omitted sidecars.

# BRCA100 fixed-tolerance controls and source-benefit follow-up

Recorded 2026-10-26 after reviewing the paired common-source pilot, before
running the additional tolerance grid or inspecting degree-stratified outcomes.
This is exploratory development on the same dataset, not held-out confirmation.

## Authorized scope

1. Compare dynamic tolerance with a shared fixed-epsilon grid over the complete
   original hub-size trajectory, including density-matched edge identity.
2. Explain which sources/edges benefit using existing pilot outputs only.

LUAD/independent-dataset transfer, new observation resamples, consensus, new
biological references, engine changes and production-default changes are deferred.
No commit, push or PR update is included. Preserve the completed pilot unchanged.

## Frozen controls and provenance

Reuse the original completed evidence at
`/home/adam/sjaracne-benchmarks/brca100-common-sources-20261026`, engine
`b41c4ca637ac2bffe73617a86af65c83e75ee075`, input hashes, 479 common probe IDs
(254 distinct symbols), all 28,278 expression rows, exact source/annotation
panels, source ordering, three observation seeds and three panel memberships.
The original design fingerprint is
`dc9d9123922370db29acc1e6d2bbed5d3d75ed64f2faeca0c9924fc8252f130b`.
The 479-node anchor and H both count probes, not unique biological genes.

Retain m=80/100 without replacement, PCHIP p_b=0.0005 for both contexts,
Npar=40, noise=0, no gene filtering, and matched actual selected observation
indices. The native cutoff must match the original decimal/hex value and model
hashes. This common cutoff remains a diagnostic, not a proposed TF/SIG default.

New fixed epsilon values: **0.05, 0.15, 0.20, 0.25**. Reuse fixed 0.10, strict
0, both dynamic slopes 0.025/0.05 and no-DPI controls from the original evidence.
The dynamic schedule remains
`min(0.30, slope * max(0, log2(H/479)))`; no new slope/anchor fitting is allowed.
The expanded design has eight strategies and 504 logical DPI views; baseline
and full-list aliases must be deduplicated. Expect 144 new physical jobs,
in addition to the 174 original native jobs (including no-DPI controls).

Write new immutable evidence to a separate WSL directory,
`/home/adam/sjaracne-benchmarks/brca100-common-sources-fixed-grid-20261026`.
Freeze new protocol/scripts/tests and record original harness/design/manifest
hashes before launch. Never rewrite originals or validate reused native records
under a different design identity. Preserve incomplete/failed evidence.

## Validation and execution

Use at most 12 workers. Test the adapter/runner with synthetic evidence first.
Before the full batch, run a small native smoke spanning a small panel and the
full SIG panel. Successful smoke artifacts are reused, not rerun. Record runtime,
PID, logs, progress and final status; detach longer execution from this session.

Retain original gates: actual samples, complete rank cache/source traversal,
source/annotation identities, cutoff/model headers, pre=pruned+post, serialized
common-source pre-DPI identity across contexts, weighted post subset of no-DPI,
strict subset of every relaxed graph, and nested epsilon graphs within a fixed
panel/sample. Serialized MI equality does not establish hidden full-precision
identity. Final validation/analysis must not launch missing native inference.

## Fixed-grid endpoints and interpretation

Report each original comparison family separately: baseline-to-H expansion,
same-H membership, same-H TF/SIG, natural full TF/SIG, and observation resampling.
Show complete within-TF and within-SIG trajectories; do not pick different fixed
tolerances retrospectively for each H and call them one fixed strategy.
Physical aliases and shared full panels are not independent replication.

Keep pooled edge Jaccard and per-source metrics distinct. For every family,
report **both left and right pruning fractions**, strict-pruning retention,
coverage and candidate-weighted combined pruning. A combined rate alone can
hide unequal sacrifices in the TF and SIG contexts.

In baseline-to-H comparisons, dynamic tolerance is zero at H=479 whereas a
positive fixed tolerance also relaxes that baseline. Requiring preservation of
pruning in BOTH contexts can therefore structurally prevent a positive fixed
arm from dominating dynamic. This is an anchor asymmetry, not evidence that
dynamic wins. Never turn the nondominated-cell count into a success rate;
inspect the combined-pruning trade-off and the complete H curves as well.

Retain top-10/20/50-target comparisons, one shared eligible-source population
across all eight strategies and both contexts, explicit available/479 counts,
and the three original deterministic MI-tie namespaces. Verify adding the fixed
grid has not changed eligibility: strict is a subset of every relaxed arm.
No padding, silent source exclusions or truth-based tie breaking.

At each physical comparison family, report whether a shared fixed arm weakly
improves agreement while preserving at least as much pruning in BOTH contexts,
with at least one strict gain. Also show the less restrictive combined-pruning
trade-off, disclosing left/right changes. Use a small numerical tolerance for
roundoff only; no statistical superiority claim from three dependent repeats.
The plots/tables describe a frontier, not an optimized scalar objective or an
automatically selected winner. Show every H cell instead of hiding failures
inside a whole-trajectory average.

Include verified no-DPI raw agreement with pruning zero as the context-agreement
upper bound. Pre-DPI context agreement is one within the same observation seed;
it need not be one across different observation resamples. Maximizing agreement
alone would favor disabling DPI and is not a success criterion. No new numerical
pruning threshold is chosen after looking at this follow-up.

## Existing-output source and edge analysis

Use only original strict, fixed 0.10 and dynamic pilot graphs for this part.
Define degree strata BEFORE inspecting stratified outcomes from each seed's
context-invariant, common-source **pre-DPI** target count:
**0-9, 10-19, 20-49, 50-99, >=100**. All 479 sources remain accounted for;
the same probe can change strata between observation resamples.

For natural full TF/SIG, within-class baseline-to-H expansion, and genuinely
different same-H memberships, compare each dynamic arm with strict and fixed
0.10. Report per-source improved/worsened/unchanged Jaccard and absolute
target-count discrepancy, with explicit undefined empty-union handling. Show
stratum counts, not only medians already at their ceiling. Stratification is
descriptive; no gene/probe collapsing and no independent-gene p-values.

Within the SAME panel/sample, rescued edges are dynamic-post minus strict-post.
Report their recurrence across the existing three observation selections and
across genuinely distinct same-H panels. Distinguish repeated **rescued status**
from relaxed-graph **edge presence**: an edge can be rescued once and retained by
strict DPI in another run. Report no-DPI candidate availability/opportunities;
MI-threshold dropout must not be labeled a DPI removal. Deduplicate full-panel
and baseline aliases before support calculations. Reproducible rescued edges
can still be indirect, and these observations overlap substantially.

## Conditional decision

Evidence for a dynamic-specific engineering benefit requires an advantageous
agreement/pruning trade-off across H, not simply beating fixed epsilon 0.10 at
the natural full-list endpoint. If a shared fixed tolerance explains the gains,
state that the evidence supports tolerance relaxation rather than requiring a
dynamic rule. If improvements concentrate in high-degree probes, narrow the
conclusion accordingly. Without reference edges this follow-up cannot identify
TP/FP, biological precision or direct regulation, or justify a production default.
