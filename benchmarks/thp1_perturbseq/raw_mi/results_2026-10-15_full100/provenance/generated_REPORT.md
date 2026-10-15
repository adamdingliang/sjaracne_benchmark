# THP-1 per-resample raw-MI pilot

This is a sampling-stage ranking benchmark against a frozen Perturb-seq response reference, not an exact reproduction of scMINER Fig. 6a and not a direct-regulatory-edge gold-standard benchmark.

## Matched design

- 100 seed IDs selected before scoring: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76, 77, 78, 79, 80, 81, 82, 83, 84, 85, 86, 87, 88, 89, 90, 91, 92, 93, 94, 95, 96, 97, 98, 99, 100.
- Before: 121 draws with replacement from 121 NT-cell metacells. After: 97 distinct metacells (80% fixed-size sampling without replacement).
- Same metacell matrix, genes, original full SIG annotation and eligible-source response reference.
- Only the 272 scored source rows are computed, retaining all 17,971 genes. Code inspection and engineering subset/expanded/reordered-source checks verify that other source rows cannot affect these pairwise MI values when DPI is disabled. This is not a full-6,951-source empirical run or a DPI-compatible shortcut.
- No MI thresholding, DPI pruning or consensus construction in either arm; raw MI is ranked separately for each resample, never averaged across resamples.
- Fixed scoring universe: 4,887,840 non-self eligible pairs; 1,177,495 response-positive and 3,710,345 operational negatives.
- Fixed random precision is 0.24090293; EPR@k = (TP@k / k) / random precision. No random graph simulation is needed.
- Primary endpoint: tie-expected TP@5,000. Other declared top-k metrics and full-ranking AUROC are secondary.
- Exact equal serialized native MI scores are ties (native output has approximately six significant digits). A boundary tie contributes expected TP proportionally; paired TSV also records feasible TP minimum and maximum. AUROC awards half-credit to tied positive/negative pairs.

## Results

The primary-k direction is mixed across selected resamples. Higher: 96; lower: 4; unchanged: 0.

Numbers below are medians across selected resamples. The delta column is the median of paired after-minus-before differences, not the difference of marginal medians.

| k | TP before | TP after | Paired TP delta | Precision before | Precision after | EPR before | EPR after |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1,000 | 519.00 | 561.25 | +42.00 | 0.5190 | 0.5613 | 2.1544 | 2.3298 |
| 5,000 | 2487.50 | 2624.25 | +134.67 | 0.4975 | 0.5249 | 2.0651 | 2.1787 |
| 10,000 | 4885.50 | 5184.50 | +302.50 | 0.4885 | 0.5184 | 2.0280 | 2.1521 |
| 50,000 | 22976.00 | 25141.60 | +2117.44 | 0.4595 | 0.5028 | 1.9075 | 2.0873 |
| 100,000 | 44270.90 | 49064.75 | +4655.32 | 0.4427 | 0.4906 | 1.8377 | 2.0367 |

Full-ranking AUROC median: 0.620105 before; 0.665936 after; paired median delta +0.047204.

At fixed k, FP = k - TP: a TP increase implies an equal FP decrease. Precision, sensitivity and EPR share the same TP numerator and fixed denominators, so their directions are not independent confirmations.

![TP, EPR and sampled ROC comparison](raw_mi_comparison.png)

TP/EPR lines show medians; bands show the interquartile range. ROC lines are individual resamples (common-FPR interpolation when available, otherwise common rank budgets), not an averaged ROC. AUROC values use all MI tie groups, not sparse plotted coordinates.

The dashed TP reference is the analytic expectation under uniform ranking of the same fixed pairs, k times reference-positive prevalence; it is not a separately generated network.

TP/EPR panels stop at the largest prespecified top-k budget; the ROC panel and AUROC cover the entire eligible universe.

## Limits and defensible interpretation

- These are computational resamples of the same cells, not independent biological replicates. IQR is descriptive, not a biological confidence interval; no significance claim or p-value is inferred from the number of resamples.
- This is an initial pilot. Mixed or small effects remain inconclusive; do not choose additional seeds or thresholds because they improve the result.
- The two protocols also differ in observation count (121 draws versus 97 distinct metacells) and RNG consumption. This does not isolate replacement alone at equal sample counts. Matching integer seed IDs does not mean matching sampled cells.
- Response-positive pairs may be indirect. Operational negatives mean absence of the defined response label, not proven biological non-regulation. MI in NT cells is association, not causal perturbation effect.
- Any result here concerns raw-MI response-associated ranking, not accuracy or improvement of the whole threshold/DPI/consensus workflow. Existing unfavorable end-to-end results are retained as separate evidence.

Compact numerical artifacts: `paired_seed_metrics.tsv` and `summary.json`. No multi-million-edge ranked CSV is generated by this reporting step.
