# Eligible-source EPR: reconstructed legacy baseline

Only eligible-source emitted predictions are ranked and shuffled. The same frozen response labels, inference outputs and consensus alternatives are retained.

The random comparator is a uniform permutation without replacement of the same eligible edge pool, using R seed 1 reset separately for each network (Mersenne-Twister, Inversion, Rejection). No new source-target pairs are generated.

EPR = integer prefix TP / actual shuffled prefix TP, following the author-style calculation. Saved author MI tie order is preserved. Boundary ties are flagged; the tie-expectation numerator and random-expectation lift are separately reported, not substituted for this EPR.

| Consensus p_c | k | TP | Shuffled TP | EPR | Precision | Splits MI tie |
|---:|---:|---:|---:|---:|---:|---|
| 0.01 | 1,000 | 556 | 424 | 1.3113 | 55.60% | yes |
| 0.01 | 5,000 | 2,659 | 2,118 | 1.2554 | 53.18% | yes |
| 0.01 | 10,000 | 5,194 | 4,220 | 1.2308 | 51.94% | yes |
| 0.01 | 50,000 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 0.01 | 100,000 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 0.001 | 1,000 | 561 | 416 | 1.3486 | 56.10% | no |
| 0.001 | 5,000 | 2,636 | 2,184 | 1.2070 | 52.72% | yes |
| 0.001 | 10,000 | 5,187 | 4,388 | 1.1821 | 51.87% | yes |
| 0.001 | 50,000 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 0.001 | 100,000 | unavailable | unavailable | unavailable | unavailable | unavailable |

These EPRs are conditional enrichment within emitted eligible predictions. Their random baseline is not the earlier full-SIG shuffle. At the complete edge pool EPR is 1 by construction. The result is baseline-only, not evidence of improvement after the sampling change.

The entire 1,000-edge trajectory plus full-pool endpoints is saved in ranked_curves.tsv. metrics.json records tied-boundary alternatives, analytic random expectations, R/RNG provenance and SHA256-bound inputs/outputs. Original global scores and the three-population report are unchanged.

