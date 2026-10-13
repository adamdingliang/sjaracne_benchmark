# THP-1 baseline: three scoring populations

Eligible-source emitted predictions are the primary evaluation. Full emitted SIG edges and the fixed eligible universe are secondary.

These are three evaluations of the same reconstructed legacy baseline, not three inference runs or a before/after sampling comparison. No reference, hub list, MI threshold, DPI setting or consensus cutoff was changed.

## AUROC and population sizes

All new AUROCs use consensus MI and retain equal-MI ties. Reference positives describe perturbation responses, not established direct regulation.

| Consensus p_c | Population | Candidate pairs | Reference-positive pairs | Positive fraction | AUROC |
|---:|---|---:|---:|---:|---:|
| 0.01 | Eligible-source predictions (primary) | 42,067 | 17,727 | 42.14% | 0.622142 |
| 0.01 | All emitted SIG edges | 916,917 | 17,727 | 1.93% | 0.573904 |
| 0.01 | Fixed eligible universe | 4,887,840 | 1,177,495 | 24.09% | 0.504259 |
| 0.001 | Eligible-source predictions (primary) | 26,667 | 11,647 | 43.68% | 0.609177 |
| 0.001 | All emitted SIG edges | 561,830 | 11,647 | 2.07% | 0.554705 |
| 0.001 | Fixed eligible universe | 4,887,840 | 1,177,495 | 24.09% | 0.502926 |

## TP, precision and enrichment at fixed k

Ranks are recalculated within each population. TP is the expected count under uniform ordering within a boundary MI tie; the range gives attainable integer counts. Values above the emitted edge count are unavailable, including in the fixed-universe view: no arbitrary ordering of omitted pairs is introduced.

Random TP expectation is k * P/N for that population. Precision lift = TP / random TP expectation. This is EPR against an expectation, not the original author-style EPR against one realized random shuffle. The original scoring artifacts are unchanged.

| p_c | Population | k | TP (tie range) | Precision | Fixed-reference sensitivity | Random TP expectation | Precision lift |
|---:|---|---:|---:|---:|---:|---:|---:|
| 0.01 | Eligible-source predictions (primary) | 1,000 | 556.14 (555-557) | 55.61% | 0.0472% | 421.40 | 1.320 |
| 0.01 | Eligible-source predictions (primary) | 5,000 | 2,658.12 (2,657-2,660) | 53.16% | 0.2257% | 2,107.00 | 1.262 |
| 0.01 | Eligible-source predictions (primary) | 10,000 | 5,195.25 (5,194-5,196) | 51.95% | 0.4412% | 4,213.99 | 1.233 |
| 0.01 | Eligible-source predictions (primary) | 50,000 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 0.01 | Eligible-source predictions (primary) | 100,000 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 0.01 | All emitted SIG edges | 1,000 | 27.00 (27-27) | 2.70% | 0.0023% | 19.33 | 1.397 |
| 0.01 | All emitted SIG edges | 5,000 | 109.00 (109-109) | 2.18% | 0.0093% | 96.67 | 1.128 |
| 0.01 | All emitted SIG edges | 10,000 | 194.00 (194-194) | 1.94% | 0.0165% | 193.33 | 1.003 |
| 0.01 | All emitted SIG edges | 50,000 | 960.89 (959-963) | 1.92% | 0.0816% | 966.66 | 0.994 |
| 0.01 | All emitted SIG edges | 100,000 | 2,090.00 (2,090-2,090) | 2.09% | 0.1775% | 1,933.33 | 1.081 |
| 0.01 | Fixed eligible universe | 1,000 | 556.14 (555-557) | 55.61% | 0.0472% | 240.90 | 2.309 |
| 0.01 | Fixed eligible universe | 5,000 | 2,658.12 (2,657-2,660) | 53.16% | 0.2257% | 1,204.51 | 2.207 |
| 0.01 | Fixed eligible universe | 10,000 | 5,195.25 (5,194-5,196) | 51.95% | 0.4412% | 2,409.03 | 2.157 |
| 0.01 | Fixed eligible universe | 50,000 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 0.01 | Fixed eligible universe | 100,000 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 0.001 | Eligible-source predictions (primary) | 1,000 | 561.00 (561-561) | 56.10% | 0.0476% | 436.76 | 1.284 |
| 0.001 | Eligible-source predictions (primary) | 5,000 | 2,636.33 (2,635-2,638) | 52.73% | 0.2239% | 2,183.79 | 1.207 |
| 0.001 | Eligible-source predictions (primary) | 10,000 | 5,186.00 (5,184-5,187) | 51.86% | 0.4404% | 4,367.57 | 1.187 |
| 0.001 | Eligible-source predictions (primary) | 50,000 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 0.001 | Eligible-source predictions (primary) | 100,000 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 0.001 | All emitted SIG edges | 1,000 | 28.00 (28-28) | 2.80% | 0.0024% | 20.73 | 1.351 |
| 0.001 | All emitted SIG edges | 5,000 | 108.00 (108-108) | 2.16% | 0.0092% | 103.65 | 1.042 |
| 0.001 | All emitted SIG edges | 10,000 | 205.00 (205-205) | 2.05% | 0.0174% | 207.30 | 0.989 |
| 0.001 | All emitted SIG edges | 50,000 | 1,026.11 (1,024-1,027) | 2.05% | 0.0871% | 1,036.52 | 0.990 |
| 0.001 | All emitted SIG edges | 100,000 | 2,198.11 (2,198-2,201) | 2.20% | 0.1867% | 2,073.05 | 1.060 |
| 0.001 | Fixed eligible universe | 1,000 | 561.00 (561-561) | 56.10% | 0.0476% | 240.90 | 2.329 |
| 0.001 | Fixed eligible universe | 5,000 | 2,636.33 (2,635-2,638) | 52.73% | 0.2239% | 1,204.51 | 2.189 |
| 0.001 | Fixed eligible universe | 10,000 | 5,186.00 (5,184-5,187) | 51.86% | 0.4404% | 2,409.03 | 2.153 |
| 0.001 | Fixed eligible universe | 50,000 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 0.001 | Fixed eligible universe | 100,000 | unavailable | unavailable | unavailable | unavailable | unavailable |

## Coverage and denominator interpretation

Conditional sensitivity/specificity at k in an emitted pool use the positives/operational negatives within that pool. They are saved under explicit names in metrics.json. At the whole emitted output those rates are mechanically 1 and 0, so they are not presented as evidence of recovery.

Fixed-reference sensitivity always uses the same frozen eligible positive denominator. Fixed-universe specificity is assessed only within eligible sources. Unassessed-source predictions in the full pool cannot match the response reference and are compatibility-score nonmembers, not confirmed biological false positives.

| p_c | Eligible emitted pairs | TP | Operational FP | Missed response-positive pairs | Fixed-reference sensitivity | Fixed-universe specificity | Unassessed-source predictions in full pool |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.01 | 42,067 | 17,727 | 24,340 | 1,159,768 | 1.5055% | 99.3440% | 874,850 |
| 0.001 | 26,667 | 11,647 | 15,020 | 1,165,848 | 0.9891% | 99.5952% | 535,163 |

The fixed universe has a large omitted bottom-score group; its AUROC measures thresholded selection plus ranking, not unthresholded MI discrimination. The primary emitted pool changes if a method emits different edges. Report its size and fixed-reference coverage alongside its conditional AUROC, rather than treating a higher conditional AUROC alone as overall improvement.

The older full-emitted ordinal AUROC is preserved separately in metrics.json. It is not interchangeable with the new MI-tied AUROC. These reconstructed labels and inputs are not an exact reproduction of Figure 6a.

Inputs and outputs are SHA256-bound in metrics.json. Reference labels and the fixed-universe definition must remain identical across a future before/after sampling comparison.
