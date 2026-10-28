# Bulk RNA DPI strategies and combined conditional conclusion

## Question and matched design

Can a hub-size-dependent DPI tolerance reduce context sensitivity without simply abandoning pruning? These are the **same common-source experiments** summarized in the [companion source-consistency summary](https://github.com/adamdingliang/sjaracne_benchmark/blob/81ca0bb1ce7fcb97479e24e82a155e31e45fa383/docs/benchmark_summaries/common_tf_sig_sources.md), not additional independent studies.

| Dataset | Fixed evaluated sources | Common-only baseline H | Full TF H | Full SIG H |
| --- | --- | ---: | ---: | ---: |
| BRCA100 | 479 probe IDs representing 254 gene symbols | 479 | 2,608 | 10,680 |
| LUAD100 | 477 Ensembl gene IDs representing 477 symbols | 477 | 1,929 | 9,464 |

Engine `b41c4ca637ac2bffe73617a86af65c83e75ee075` used three matched 80-of-100 observation resamples without replacement, three nested panel-membership draws and PCHIP `p_b=0.0005` for both TF and SIG. Samples, targets and MI cutoffs were held fixed within comparisons. Reconstruction (`-s`) and annotation (`-l`) used the same selected panel. **All scores below concern edges from the fixed common-source population, not all inferred sources.** Repeated baseline and full-list native jobs are not independent replication.

## What dynamic epsilon means

`H` counts source nodes in the reconstruction and annotation panel. Larger epsilon relaxes DPI pruning.

```text
dynamic: epsilon(H) = min(0.30, s * max(0, log2(H / 479)))
fixed:   the same epsilon at every H
strict:  epsilon = 0
no DPI:  epsilon = 1
```

For slope `s=0.05`, each doubling above the numerical anchor 479 adds 0.05 until the cap of 0.30. At or below 479, dynamic epsilon is zero. LUAD's baseline H=477 is therefore zero-clamped; the rule was transferred **without retuning**. The anchor counts computational nodes, not equivalent biological coverage across probes and genes. The table highlights slope 0.05, not an established optimum. The schedule used ordinary native `-e` runs, not an automatic dynamic-H engine option.

## Full-list endpoint comparison

Values are medians over three unique matched observation resamples. Pruning is the fraction of pre-DPI common-source candidate edges removed. Raw Jaccard compares all retained common-source edges between the full TF and full SIG contexts, as edge-set intersection divided by union.

**Top-20 Jaccard.** For each eligible common source gene or probe, take its
20 highest-MI targets that remain after DPI in the full TF reconstruction,
and separately take its 20 highest-MI retained targets in the full SIG
reconstruction. "Equally sized" means 20 targets on each side, not necessarily
the same target genes. Eligibility requires at least 20 retained targets in
both contexts and every compared pruned strategy; short lists are not padded.

Pool the selected directed source-target pairs across those eligible sources.
Jaccard is the number of pairs shared by both contexts divided by the number
present in either context. It is not an average of per-source Jaccards.
For example, if one source has 20 selected targets in each context and 15
are shared, its Jaccard is `15 / (20 + 20 - 15) = 0.60`.

**Combined pruning fraction.** A candidate is an edge that passed the MI
cutoff before DPI. For all fixed common sources, add the candidate edges
removed in the TF and SIG reconstructions, then divide by their total
pre-DPI candidate counts:

```text
combined pruning = (TF edges removed + SIG edges removed)
                   / (TF candidates before DPI + SIG candidates before DPI)
```

Count each reconstruction separately, not a deduplicated edge union. This
uses all common-source candidates, not only the selected Top-20 edges.
"Candidate-weighted" refers to the number of candidate edges, not the number
of TF or SIG hubs. Here the matched pre-DPI candidate counts are equal, so TF
and SIG have equal weight within each resample. If each starts with 1,000
candidates and removes 200 or 400, combined pruning is `600 / 2,000 = 30%`.
Calculate this fraction for each of the three matched resamples, then take
its median; do not average the separately displayed TF and SIG medians.

Jaccard measures target-set consistency, and pruning measures edge removal.
Neither establishes whether the retained or removed edges are biologically correct.

| Dataset | Mode | TF pruning fraction | SIG pruning fraction | Combined pruning fraction | Raw Jaccard | Top-20 Jaccard |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| BRCA100 | No DPI | 0.0000 | 0.0000 | 0.0000 | 1.0000 | Not evaluated |
| BRCA100 | Strict DPI | 0.2809 | 0.4131 | 0.3457 | 0.7737 | 0.8042 |
| BRCA100 | Fixed epsilon 0.10 | 0.2187 | 0.3425 | 0.2788 | 0.8063 | 0.8862 |
| BRCA100 | Fixed epsilon 0.20 | 0.1512 | 0.2637 | 0.2048 | 0.8331 | 0.9514 |
| BRCA100 | Fixed epsilon 0.25 | 0.1184 | 0.2231 | 0.1676 | 0.8506 | 0.9711 |
| BRCA100 | Dynamic slope 0.05 | 0.2031 | 0.2446 | 0.2217 | 0.8626 | 0.9500 |
| LUAD100 | No DPI | 0.0000 | 0.0000 | 0.0000 | 1.0000 | Not evaluated |
| LUAD100 | Strict DPI | 0.6081 | 0.7974 | 0.7027 | 0.4703 | 0.5940 |
| LUAD100 | Fixed epsilon 0.10 | 0.4842 | 0.7000 | 0.5921 | 0.5388 | 0.7732 |
| LUAD100 | Fixed epsilon 0.20 | 0.3321 | 0.5556 | 0.4439 | 0.6268 | 0.9089 |
| LUAD100 | Fixed epsilon 0.25 | 0.2563 | 0.4690 | 0.3626 | 0.6792 | 0.9551 |
| LUAD100 | Dynamic slope 0.05 | 0.4837 | 0.5307 | 0.5072 | 0.6740 | 0.8894 |

Pruning fractions and Jaccard range from zero to one. Median Top-20 eligibility was 276 of 479 BRCA sources and 457 of 477 LUAD sources. No-DPI matched-budget scores were intentionally not evaluated.

| Dataset | No-DPI candidate edges | No-DPI median targets per source |
| --- | ---: | ---: |
| BRCA100 | 21,799 | 22 |
| LUAD100 | 111,469 | 155 |

No-DPI is still MI-thresholded. Its raw Jaccard of one is guaranteed because there is no context-dependent pruning, not evidence of accuracy. Nonempty-source coverage was 100% throughout; BRCA median targets remained 22 under every strategy. LUAD full TF target medians were 88 under strict DPI and 112 under dynamic slope 0.05; corresponding full SIG medians were 46 and 103.

## Figures and trade-offs

### Figure 1. Pruning increase as the source panel expands

![Paired full-minus-common-baseline pruning increases in BRCA100 and LUAD100](https://github.com/adamdingliang/sjaracne_benchmark/blob/81ca0bb1ce7fcb97479e24e82a155e31e45fa383/docs/benchmark_summaries/figures/bulk_pruning_increase.png?raw=true)

The increase is full-panel pruning minus common-only baseline pruning, paired before taking medians. Dynamic slope 0.05 reduces the measured increase in both contexts:

| Dataset | Context | Strict-DPI increase (percentage points) | Dynamic-slope-0.05 increase (percentage points) |
| --- | --- | ---: | ---: |
| BRCA100 | TF | 11.57 | 3.65 |
| BRCA100 | SIG | 24.89 | 7.68 |
| LUAD100 | TF | 14.05 | 1.61 |
| LUAD100 | SIG | 32.97 | 6.31 |

A flatter trajectory alone does not select a strategy. Positive fixed epsilon also relaxes the baseline, while dynamic starts at zero. This anchor asymmetry affects baseline-to-full comparisons and is not evidence of superiority.

### Figure 2. Agreement versus pruning at the full contexts

![Full-context Top-20 target agreement versus combined pruning in both bulk datasets](https://github.com/adamdingliang/sjaracne_benchmark/blob/81ca0bb1ce7fcb97479e24e82a155e31e45fa383/docs/benchmark_summaries/figures/bulk_full_context_tradeoff.png?raw=true)

Points summarize full TF versus full SIG contexts. Higher agreement and more pruning describe competing engineering objectives, not a validated accuracy score. No-DPI is omitted because its matched Top-20 score was not evaluated. Fixed epsilon 0.25 gives better Top-20 agreement than dynamic in both datasets but retains less pruning. Compared with fixed 0.20, dynamic has nearly identical BRCA agreement; in LUAD the paired Top-20 difference is -0.0168 and combined pruning is 6.33 percentage points higher. Paired differences need not equal subtraction of separately displayed medians. Identity does not improve at every H.

## Combined conditional conclusion

Across all three summaries, [DREAM5 Networks 1 and 3](https://github.com/adamdingliang/sjaracne_benchmark/blob/2a121d17d0e34c7d1964e05bffb36c1b1d080ccf/docs/benchmark_summaries/dream5_dpi.md) did **not** demonstrate a dynamic-specific precision or recall advantage over matched fixed tolerance. Their full-H outputs were identical by construction; smaller-H matched-budget and matched-recall controls favored fixed tolerance in the summarized groups.

BRCA100 and LUAD100 instead support a **plausible experimental engineering compromise**: less hub-size-related pruning variation, substantial TF and overall pruning, and better preservation of LUAD target-list sizes versus strict DPI. Strong fixed tolerance remains competitive. Together these results support an experimental option, **not an established accuracy improvement, optimal anchor or slope, universal policy, or new default**.

The bulk datasets have no reference edges or TP or FP labels. Three overlapping observation resamples show low cross-resample edge stability. BRCA probes and LUAD genes are not equivalent biological units; LUAD feature selection used all 517 prepared patients. The independent-rank PCHIP study does not establish calibration for tied or zero-rich RNA-seq. DREAM used different anchors and cannot validate the bulk anchor 479. No consensus or downstream activity was tested.

Detailed process, complete trajectories, adverse results and provenance: [BRCA100](https://github.com/adamdingliang/sjaracne_benchmark/blob/4b7a643135ffb6e754d7c59d677aafb9c555dce2/benchmarks/dpi_epsilon_summaries/evidence/brca100_fixed_grid/RESULTS.md) and [LUAD100](https://github.com/adamdingliang/sjaracne_benchmark/blob/4b7a643135ffb6e754d7c59d677aafb9c555dce2/benchmarks/dpi_epsilon_summaries/evidence/luad100_common/RESULTS.md). Figures use saved results only; no inference was rerun. [Selected plot data and hashes](https://github.com/adamdingliang/sjaracne_benchmark/blob/81ca0bb1ce7fcb97479e24e82a155e31e45fa383/docs/benchmark_summaries/figures/bulk_dpi_summary_figures.json) document the calculations.
