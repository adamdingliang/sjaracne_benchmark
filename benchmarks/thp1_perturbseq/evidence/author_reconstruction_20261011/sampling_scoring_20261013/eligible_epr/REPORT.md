# Eligible-source EPR: reconstructed legacy baseline

Only eligible-source emitted predictions are ranked and shuffled. The same frozen response labels, inference outputs and consensus alternatives are retained.

The random comparator is a uniform permutation without replacement of the same eligible edge pool, using R seed 1 reset separately for each network (Mersenne-Twister, Inversion, Rejection). No new source-target pairs are generated.

EPR = integer prefix TP / actual shuffled prefix TP, following the author-style calculation. Saved author MI tie order is preserved. Boundary ties are flagged; the tie-expectation numerator and random-expectation lift are separately reported, not substituted for this EPR.

| Consensus p_c | k | TP | Shuffled TP | EPR | Precision | Splits MI tie |
|---:|---:|---:|---:|---:|---:|---|
| 0.01 | 1,000 | 517 | 424 | 1.2193 | 51.70% | yes |
| 0.01 | 5,000 | 2,688 | 2,177 | 1.2347 | 53.76% | yes |
| 0.01 | 10,000 | 5,199 | 4,369 | 1.1900 | 51.99% | yes |
| 0.01 | 50,000 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 0.01 | 100,000 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 0.001 | 1,000 | 519 | 437 | 1.1876 | 51.90% | yes |
| 0.001 | 5,000 | 2,695 | 2,249 | 1.1983 | 53.90% | yes |
| 0.001 | 10,000 | 5,177 | 4,457 | 1.1615 | 51.77% | yes |
| 0.001 | 50,000 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 0.001 | 100,000 | unavailable | unavailable | unavailable | unavailable | unavailable |

These EPRs are conditional enrichment within emitted eligible predictions. Their random baseline is not the earlier full-SIG shuffle. At the complete edge pool EPR is 1 by construction. The result is baseline-only, not evidence of improvement after the sampling change.

The entire 1,000-edge trajectory plus full-pool endpoints is saved in ranked_curves.tsv. metrics.json records tied-boundary alternatives, analytic random expectations, R/RNG provenance and SHA256-bound inputs/outputs. Original global scores and the three-population report are unchanged.

