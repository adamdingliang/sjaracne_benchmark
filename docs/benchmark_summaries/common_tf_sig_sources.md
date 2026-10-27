# Common TF/SIG sources: BRCA100 and LUAD

## Question and matched design

When the **same evaluated source IDs** are reconstructed in separate TF and
SIG contexts, how much do their retained targets change? Evaluation uses their
intersection; reconstruction still uses the surrounding TF or SIG panel.

| Dataset | Fixed evaluated sources | Full TF / SIG source lists | Fixed target-expression rows |
| --- | --- | ---: | ---: |
| BRCA100 | 479 probe IDs, representing 254 distinct gene symbols | 2,608 / 10,680 | 28,278 |
| LUAD100 | 477 Ensembl gene IDs, representing 477 symbols | 1,929 / 9,464 | 29,841 |

Within each dataset, observations, expression values, targets and PCHIP MI
cutoff were matched across contexts: 80 observations without replacement from
100, three observation seeds, `p_b=0.0005` for both TF and SIG, and the same
frozen engine (`b41c4ca`). Reconstruction and DPI annotation lists had identical
membership (`-s` equals `-l`). Three nested panel memberships varied surrounding
hubs. Repeated baseline/full-list jobs were deduplicated, not replication;
the common-only TF/SIG baseline is identical by construction.

Thresholded no-DPI controls verified common-source candidate identities and
serialized MI across contexts within a seed. The experiment therefore examines
post-DPI context sensitivity at recorded precision, not different source
denominators or MI cutoffs. Serialization is not a full-precision fingerprint.

The controls include strict DPI, fixed epsilon 0.05 to 0.25, and dynamic slopes
0.025/0.05. The unchanged dynamic rule is
`epsilon(H)=min(0.30,s*max(0,log2(H/479)))`. Its reference is a numerical count of
source nodes, not equivalent biological coverage across probes and genes.
LUAD's 477-gene baseline is zero-clamped, not retuned.

## Shared-source target consistency

The table compares the natural full TF versus full SIG contexts. All metrics
below concern edges **from the fixed common-source population**, not whole
networks. Values are medians over three unique matched observation pairs;
Jaccard measures edge-identity agreement, not biological accuracy.

| Dataset | Raw Jaccard: strict to dynamic slope 0.05 | Top-20/source Jaccard: strict to dynamic | Top-20/source: fixed 0.20 | Median top-20 eligible sources |
| --- | ---: | ---: | ---: | ---: |
| BRCA100 | 0.7737 to 0.8626 | 0.8042 to 0.9500 | 0.9514 | 276 / 479 |
| LUAD100 | 0.4703 to 0.6740 | 0.5940 to 0.8894 | 0.9089 | 457 / 477 |

Top-10/20/50 comparisons use the same eligible sources and retained-target
budget across all strategies and both contexts, with three common deterministic
MI-tie orders. Short lists are not padded. Stronger fixed tolerance can
match or exceed dynamic agreement; dynamic does not uniformly improve identity
at every intermediate hub size.

Nonempty-source coverage remained **100% under every strategy** in both
datasets. BRCA's median target count stayed 22: its source-level effects were
uneven and stronger among higher-degree sources. In LUAD, dynamic better
preserved median target counts as panels expanded: the common-only post-DPI
baseline (`H=477`, `epsilon=0`) had 111, becoming 112 in
full TF and 103 in full SIG, versus 88 and 46 under strict DPI. These are
displayed medians, not a claim of improved activity robustness.

## Conditional conclusion

For shared TF/SIG sources, the two datasets support a **candidate engineering
balance**: dynamic tolerance can reduce hub-context-related pruning variation
and improve full-context target consistency versus strict DPI while retaining
substantial pruning. It does not establish that common hubs should have
identical targets, that their edges are more accurate, or that dynamic is
preferable to every fixed tolerance. Some extra intermediaries may justify
target differences, and observation-resample instability remains unresolved.

These are three overlapping computational resamples per dataset, not independent
biological replications. LUAD reused gene filtering from all 517 prepared
patients before selecting its fixed 100-patient cohort; this is not held-out
feature-selection validation. Probe/gene representation and preprocessing also
differ, so cross-dataset agreement is not a tissue-only comparison. No reference
edges, consensus, downstream activity validation or production-default change
is claimed. This summary and the separate DPI-strategy summary use the **same
underlying experiments**, not additional independent evidence.

## Detailed evidence

- BRCA100: [process](../../benchmarks/dpi_epsilon_summaries/evidence/brca100_fixed_grid/PROCESS.md),
  [full results and plots](../../benchmarks/dpi_epsilon_summaries/evidence/brca100_fixed_grid/RESULTS.md),
  [exact source-level counts](../../benchmarks/dpi_epsilon_summaries/evidence/brca100_source_benefits/SUMMARY.md).
- LUAD100: [process](../../benchmarks/dpi_epsilon_summaries/evidence/luad100_common/PROCESS.md),
  [full results and plots](../../benchmarks/dpi_epsilon_summaries/evidence/luad100_common/RESULTS.md),
  [input preparation](../../benchmarks/dpi_epsilon_summaries/evidence/luad_preparation/PREPARATION.md).

Raw expression, native networks and large run archives remain outside Git.
