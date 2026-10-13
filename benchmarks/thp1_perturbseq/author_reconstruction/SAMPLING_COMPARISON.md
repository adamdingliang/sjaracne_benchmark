# Matched THP-1 sampling-only comparison

The legacy reconstruction is complete and has been compared with Figure 6a.
It does not reproduce the published result: the full emitted-network overlap
is 17,727 rather than the published 711, and our reference labels 96 of the
same 188 published IFNGR2 predictions positive rather than 25. The active
public label threshold matches, but the authors' processed DE assay and exact
cell/source selection are unavailable. No reference labels were tuned to
match the publication.

After reviewing these limitations, the user authorized proceeding on
2026-10-12 with a matched comparison using the frozen reconstructed response
reference. This is not an exact Figure 6a reproduction or a direct-edge gold
standard benchmark.

The user selected a **sampling-only backport to the paper-era baseline** on
2026-10-12. Using the complete PR70 head would mix sampling changes with
intervening implementation changes relative to this baseline.

## Matched design

| Setting | Legacy reconstruction | Sampling-only after arm |
| --- | --- | --- |
| Native source base | `2922ec9a57d3da4e88b849b840643f543f49807c` | Same base, with only native sampling additions from `3a93d10e862ba43229e60ca6491ee38143422379` |
| Inference input | Same frozen 121 NT metacells and 17,971 genes | Identical input bytes |
| Hubs / DPI annotation | Same frozen 6,951 SIG hubs | Identical input bytes |
| Sampling | 121 draws with replacement, `-r 1` | 97 distinct observations, `-u 80%`; `ceil(121 * 0.8)` |
| Seeds | 1 through 100 | 1 through 100 |
| AP depth / DPI tolerance | 40 / 0 | 40 / 0 |
| Nominal bootstrap p-value | `1e-7` | `1e-7` |
| Legacy affine MI cutoff | 0.13698706405152791 | 0.15590206402074738 |
| Consensus | Original 0.2.1 probability-based script; primary `p_c=0.01`, secondary `p_c=0.001` | Identical script and declared cutoffs |
| Response reference / scoring | Frozen reconstructed reference; eligible-source emitted predictions are primary | Identical reference and scoring definitions |

PR71 calibration and minimum-recurrence consensus are excluded from both arms.
The backport has its own source/build directory; it does not replace the
running legacy binary or modify frozen baseline helpers.

This tests the operational sampling strategy, not replacement alone. The
sample count, sample-size-dependent affine MI threshold, and sampling/tie-noise
RNG behavior change together. Paired seed numbers do not imply identical
observations or noise realizations. It differs from the earlier reduced-panel
pilot, which imposed a common explicit MI threshold.

## Launch gate and verification

`run_sampling_backport.py` provides a read-only plan and a guarded native run.
The full run requires a complete, hash-verified 100-bootstrap baseline, both
original consensuses, completed scoring, and an explicit decision to proceed
with the reconstructed benchmark despite the publication mismatch. The
acceptance artifact binds the baseline manifest and summary hashes and
records the review limitations and scope. Completion alone does not authorize
launch, and acceptance does not assert agreement with Figure 6a.

The baseline review should inspect primary-consensus TP/EPR curves and the
published anchors at 1,000, 5,000, 10,000, 50,000 and 100,000 edges, together
with the available ROC segment and the paper's rounded AUROC of 0.75. Report
the secondary consensus separately, rather than selecting the alternative
that looks most favorable. Do not tune preparation, response labels, or
thresholds to obtain agreement.

Before full inference, the separate build must establish unchanged
configuration/consensus hashes, a narrowly scoped source patch, and legacy
`-r 1` adjacency-body agreement with the pristine build on a small fixture.
Sampler checks must establish 97 unique selected indices at 80% of 121.
These small checks are engineering validation, not THP-1 performance results.

## Interpretation

Use eligible-source emitted predictions as the primary scoring population,
with full emitted SIG predictions and the fixed eligible source-target
universe as secondary views. Preserve the existing three-population metric
definitions and whole-MI-tie handling. Retain the author-style ordinal-rank
calculation separately as a compatibility result, not a substitute for the
primary analysis. Report TP, EPR, AUROC, emitted edge counts and
reference-positive membership. Conditional emitted-pool AUROC is not an
all-pair ranking comparison; each arm's seeded shuffled comparator uses its
own scoring population. Keep the response reference and fixed-universe
source/target definitions identical across arms.

Perturbation responses are not direct-edge ground truth. A metric increase
would support this particular reconstructed benchmark, not establish universal
algorithmic superiority. A decrease or mixed result must be reported as such.
The known Figure 6a mismatch remains a limitation. It must not be recast as
successful reproduction, nor may higher absolute TP counts against this
different reference be used to claim improvement over the published network.

## Completed comparison: 2026-10-13

Both arms completed 100 bootstraps and both declared probability-based
consensuses. The after arm was scored with the unchanged frozen reference and
metric helpers; baseline artifacts were not overwritten. Independent
recalculation from the emitted edges verified the MI-tied AUROCs and the
eligible-pool R seed-1 shuffled TP counts.

The primary eligible-source emitted-prediction results are:

| Consensus p_c | Arm | Eligible edges | Response-positive matches | TP at 5,000 | EPR at 5,000 | MI-tied AUROC |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 0.01 | Before: with replacement | 42,067 | 17,727 | 2,659 | 1.2554 | 0.622142 |
| 0.01 | After: 80% without replacement | 23,964 | 10,416 | 2,688 | 1.2347 | 0.610740 |
| 0.001 | Before: with replacement | 26,667 | 11,647 | 2,636 | 1.2070 | 0.609177 |
| 0.001 | After: 80% without replacement | 19,201 | 8,522 | 2,695 | 1.1983 | 0.606931 |

TP in this table is the integer prefix count used by EPR. The plotted TP
curves instead show MI-tie expected counts and attainable ranges. At 5,000,
these expectations are 2,658.125 to 2,687.714 for p_c=0.01 and 2,636.333 to
2,693.400 for p_c=0.001. AUROC advances through whole MI ties; the separately
preserved author-style ordinal AUROC is not substituted for it.

Each EPR comparator shuffles its own emitted population, not a common set of
pairs. The after pools have higher positive fractions (42.14% to 43.47%, and
43.68% to 44.38%), so the actual shuffled TP at 5,000 also increases: 2,118 to
2,177 and 2,184 to 2,249. This explains how slightly higher TP can coexist
with lower EPR.

Across the same fixed universe of 4,887,840 eligible pairs, the following
whole-emitted-network operating points use identical reference denominators:

| Consensus p_c | Before sensitivity | After sensitivity | Before specificity | After specificity |
| ---: | ---: | ---: | ---: | ---: |
| 0.01 | 1.5055% | 0.8846% | 99.3440% | 99.6349% |
| 0.001 | 0.9891% | 0.7237% | 99.5952% | 99.7122% |

These are response-reference sensitivity/specificity, not accuracy against
proven direct-regulatory positives and negatives. The higher specificity
comes with substantially fewer predictions and lower response-positive
coverage. Both secondary AUROCs (full emitted SIG and fixed eligible
universe) also decrease at each cutoff; see the complete tables in the report.

### Defensible conclusion

**This is a mixed result, not an overall improvement on this reconstructed
THP-1 benchmark.** The top-5,000 TP gain is small, top-1,000 TP is lower, and
eligible-edge AUROC, EPR and total reference-positive coverage decrease at
both cutoffs. It does not support a general claim that the changed sampling
strategy improves this benchmark. Nor does it show that sampling without
replacement is universally worse: sample count, affine cutoff and RNG
consumption changed together, and there is only one matched 100-run batch,
without independent repeated-batch uncertainty estimates.

The [complete comparison report](../results/author_reconstruction_20261011/sampling_comparison_20261013/REPORT.md)
and [TP/EPR/ROC overlays](../results/author_reconstruction_20261011/sampling_comparison_20261013/eligible_sampling_comparison.png)
contain the primary results, secondary populations, top-k tie ranges and
provenance. `sampling_scoring_20261013/` contains the new after scores;
`sampling_comparison_20261013/manifest.json` binds the comparison inputs and
outputs by SHA256. Historical component reports may retain baseline-only
template wording; the new driver manifest and comparison report identify the
actual sampling-only after arm explicitly.
