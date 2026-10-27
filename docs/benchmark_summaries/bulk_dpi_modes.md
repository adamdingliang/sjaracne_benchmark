# No-DPI, fixed-epsilon and dynamic-epsilon comparisons in bulk RNA data

## Question and matched design

Can a hub-size-dependent DPI tolerance reduce panel-context sensitivity without simply abandoning pruning? This summary compares strategies in the **same common-source experiments** described in the [BRCA100 report](https://github.com/adamdingliang/sjaracne_benchmark/blob/4b7a643135ffb6e754d7c59d677aafb9c555dce2/benchmarks/dpi_epsilon_summaries/evidence/brca100_fixed_grid/RESULTS.md) and [LUAD100 report](https://github.com/adamdingliang/sjaracne_benchmark/blob/4b7a643135ffb6e754d7c59d677aafb9c555dce2/benchmarks/dpi_epsilon_summaries/evidence/luad100_common/RESULTS.md), not two additional studies.

Engine `b41c4ca637ac2bffe73617a86af65c83e75ee075` used three matched 80-of-100 observation resamples without replacement, three nested membership draws, PCHIP `p_b=0.0005` for both TF/SIG, and identical targets and samples within each comparison. Reconstruction (`-s`) and annotation (`-l`) used the same selected panel. Only edges originating from shared evaluated sources are scored: BRCA100 has 479 probe IDs representing 254 symbols; LUAD100 has 477 Ensembl genes/477 symbols. These are not whole-network summaries.

The frozen candidate rule was `epsilon(H)=min(0.30, 0.05*max(0,log2(H/479)))`. It was applied through ordinary native `-e` runs, with **no LUAD retuning** or native automatic-H option. Fixed epsilon is the same at every H; strict DPI is zero; no-DPI uses epsilon one. Increasing epsilon relaxes pruning.

## Full-list endpoint comparison

Values are medians of three matched observation pairs. Pruning is the fraction of pre-DPI common-source candidate edges removed. Raw Jaccard compares retained TF/SIG edge identities; Top20 compares equally sized target sets per eligible source.

| Dataset | Mode | TF pruning | SIG pruning | Combined pruning | Raw Jaccard | Top20 Jaccard |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| BRCA100 | No DPI | 0.0000 | 0.0000 | 0.0000 | 1.0000 | — |
| BRCA100 | Strict | 0.2809 | 0.4131 | 0.3457 | 0.7737 | 0.8042 |
| BRCA100 | Fixed 0.10 | 0.2187 | 0.3425 | 0.2788 | 0.8063 | 0.8862 |
| BRCA100 | Fixed 0.20 | 0.1512 | 0.2637 | 0.2048 | 0.8331 | 0.9514 |
| BRCA100 | Fixed 0.25 | 0.1184 | 0.2231 | 0.1676 | 0.8506 | 0.9711 |
| BRCA100 | Dynamic 0.05 | 0.2031 | 0.2446 | 0.2217 | 0.8626 | 0.9500 |
| LUAD100 | No DPI | 0.0000 | 0.0000 | 0.0000 | 1.0000 | — |
| LUAD100 | Strict | 0.6081 | 0.7974 | 0.7027 | 0.4703 | 0.5940 |
| LUAD100 | Fixed 0.10 | 0.4842 | 0.7000 | 0.5921 | 0.5388 | 0.7732 |
| LUAD100 | Fixed 0.20 | 0.3321 | 0.5556 | 0.4439 | 0.6268 | 0.9089 |
| LUAD100 | Fixed 0.25 | 0.2563 | 0.4690 | 0.3626 | 0.6792 | 0.9551 |
| LUAD100 | Dynamic 0.05 | 0.4837 | 0.5307 | 0.5072 | 0.6740 | 0.8894 |

Combined pruning is candidate-weighted within each pair before taking the median. Top20 uses the same eligible-source intersection across all tested strategies and both contexts: median 276/479 BRCA sources and 457/477 LUAD sources. No-DPI matched-budget scores were intentionally not evaluated.

No-DPI retains the **MI-thresholded** candidate graph: median 21,799 common-source edges and 22 targets/source in BRCA; 111,469 edges and 155 targets/source in LUAD. Its raw context Jaccard of one is guaranteed by the matched construction, not evidence of accuracy. BRCA median targets remained 22 for all strategies. In LUAD, full TF/SIG target medians were 88/46 under strict DPI, 133/97 at fixed 0.20, and 112/103 under dynamic 0.05. Nonempty-source coverage was 100% throughout.

## Across-H balance and conditional conclusion

Panels expanded from 479 to 2,608 TF/10,680 SIG nodes in BRCA, and from 477 to 1,929/9,464 in LUAD. Dynamic 0.05 reduced the paired full-minus-baseline pruning increase from 11.57/24.89 to 3.65/7.68 percentage points in BRCA TF/SIG, and from 14.05/32.97 to 1.61/6.31 in LUAD. Identity did not improve uniformly at every H.

Against fixed 0.20, BRCA dynamic achieved nearly identical Top20 agreement with more combined pruning. LUAD showed a larger cost: paired Top20 agreement was 0.0168 lower, while combined pruning was 6.33 percentage points higher. Fixed 0.25 achieved better Top20 agreement in both datasets by relinquishing still more pruning. Endpoint agreement alone therefore cannot select a strategy.

**Combined conditional conclusion across the three benchmark summaries:** the [DREAM5 Network 1/3 comparisons](https://github.com/adamdingliang/sjaracne_benchmark/blob/f4770ff52416e5d4c95a387c8b85b07f0237a885/docs/benchmark_summaries/dream5_dpi.md) did not demonstrate a dynamic-specific precision/recall advantage over matched fixed tolerance: full-H outputs were identical by construction, and smaller-H matched-budget/matched-recall controls favored fixed tolerance. BRCA/LUAD instead support a plausible experimental engineering compromise: less hub-size-related variation while retaining substantial TF/overall pruning and LUAD target-list sizes. Together, this supports investigating an experimental policy, **not an established accuracy improvement, universal optimum or new default**.

The bulk experiments have no reference edges or TP/FP labels; three overlapping resamples show low cross-resample edge stability. BRCA probes and LUAD genes are not equivalent biological units, LUAD preparation used all 517 patients for feature selection, and the independent-rank PCHIP calibration does not establish calibration for tied/zero-rich RNA-seq. The DREAM study used different anchors, so it does not validate the bulk rule's `H_ref=479`. No consensus or downstream activity was tested. Full trajectories, fixed-grid controls, provenance and adverse results remain in the linked reports.
