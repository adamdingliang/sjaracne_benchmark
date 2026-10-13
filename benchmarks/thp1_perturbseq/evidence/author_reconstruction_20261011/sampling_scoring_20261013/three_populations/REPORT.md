# THP-1 baseline: three scoring populations

Eligible-source emitted predictions are the primary evaluation. Full emitted SIG edges and the fixed eligible universe are secondary.

These are three evaluations of the same reconstructed legacy baseline, not three inference runs or a before/after sampling comparison. No reference, hub list, MI threshold, DPI setting or consensus cutoff was changed.

## AUROC and population sizes

All new AUROCs use consensus MI and retain equal-MI ties. Reference positives describe perturbation responses, not established direct regulation.

| Consensus p_c | Population | Candidate pairs | Reference-positive pairs | Positive fraction | AUROC |
|---:|---|---:|---:|---:|---:|
| 0.01 | Eligible-source predictions (primary) | 23,964 | 10,416 | 43.47% | 0.610740 |
| 0.01 | All emitted SIG edges | 513,367 | 10,416 | 2.03% | 0.557080 |
| 0.01 | Fixed eligible universe | 4,887,840 | 1,177,495 | 24.09% | 0.502601 |
| 0.001 | Eligible-source predictions (primary) | 19,201 | 8,522 | 44.38% | 0.606931 |
| 0.001 | All emitted SIG edges | 409,780 | 8,522 | 2.08% | 0.553911 |
| 0.001 | Fixed eligible universe | 4,887,840 | 1,177,495 | 24.09% | 0.502182 |

## TP, precision and enrichment at fixed k

Ranks are recalculated within each population. TP is the expected count under uniform ordering within a boundary MI tie; the range gives attainable integer counts. Values above the emitted edge count are unavailable, including in the fixed-universe view: no arbitrary ordering of omitted pairs is introduced.

Random TP expectation is k * P/N for that population. Precision lift = TP / random TP expectation. This is EPR against an expectation, not the original author-style EPR against one realized random shuffle. The original scoring artifacts are unchanged.

| p_c | Population | k | TP (tie range) | Precision | Fixed-reference sensitivity | Random TP expectation | Precision lift |
|---:|---|---:|---:|---:|---:|---:|---:|
| 0.01 | Eligible-source predictions (primary) | 1,000 | 517.00 (517-517) | 51.70% | 0.0439% | 434.65 | 1.189 |
| 0.01 | Eligible-source predictions (primary) | 5,000 | 2,687.71 (2,687-2,688) | 53.75% | 0.2283% | 2,173.26 | 1.237 |
| 0.01 | Eligible-source predictions (primary) | 10,000 | 5,199.36 (5,198-5,201) | 51.99% | 0.4416% | 4,346.52 | 1.196 |
| 0.01 | Eligible-source predictions (primary) | 50,000 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 0.01 | Eligible-source predictions (primary) | 100,000 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 0.01 | All emitted SIG edges | 1,000 | 33.00 (33-33) | 3.30% | 0.0028% | 20.29 | 1.626 |
| 0.01 | All emitted SIG edges | 5,000 | 119.00 (119-119) | 2.38% | 0.0101% | 101.45 | 1.173 |
| 0.01 | All emitted SIG edges | 10,000 | 218.50 (218-219) | 2.19% | 0.0186% | 202.90 | 1.077 |
| 0.01 | All emitted SIG edges | 50,000 | 1,050.00 (1,049-1,051) | 2.10% | 0.0892% | 1,014.48 | 1.035 |
| 0.01 | All emitted SIG edges | 100,000 | 2,276.21 (2,275-2,279) | 2.28% | 0.1933% | 2,028.96 | 1.122 |
| 0.01 | Fixed eligible universe | 1,000 | 517.00 (517-517) | 51.70% | 0.0439% | 240.90 | 2.146 |
| 0.01 | Fixed eligible universe | 5,000 | 2,687.71 (2,687-2,688) | 53.75% | 0.2283% | 1,204.51 | 2.231 |
| 0.01 | Fixed eligible universe | 10,000 | 5,199.36 (5,198-5,201) | 51.99% | 0.4416% | 2,409.03 | 2.158 |
| 0.01 | Fixed eligible universe | 50,000 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 0.01 | Fixed eligible universe | 100,000 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 0.001 | Eligible-source predictions (primary) | 1,000 | 519.40 (519-520) | 51.94% | 0.0441% | 443.83 | 1.170 |
| 0.001 | Eligible-source predictions (primary) | 5,000 | 2,693.40 (2,691-2,695) | 53.87% | 0.2287% | 2,219.16 | 1.214 |
| 0.001 | Eligible-source predictions (primary) | 10,000 | 5,177.00 (5,176-5,179) | 51.77% | 0.4397% | 4,438.31 | 1.166 |
| 0.001 | Eligible-source predictions (primary) | 50,000 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 0.001 | Eligible-source predictions (primary) | 100,000 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 0.001 | All emitted SIG edges | 1,000 | 33.50 (33-34) | 3.35% | 0.0028% | 20.80 | 1.611 |
| 0.001 | All emitted SIG edges | 5,000 | 113.00 (113-113) | 2.26% | 0.0096% | 103.98 | 1.087 |
| 0.001 | All emitted SIG edges | 10,000 | 217.81 (217-218) | 2.18% | 0.0185% | 207.97 | 1.047 |
| 0.001 | All emitted SIG edges | 50,000 | 1,082.59 (1,082-1,084) | 2.17% | 0.0919% | 1,039.83 | 1.041 |
| 0.001 | All emitted SIG edges | 100,000 | 2,327.59 (2,327-2,329) | 2.33% | 0.1977% | 2,079.65 | 1.119 |
| 0.001 | Fixed eligible universe | 1,000 | 519.40 (519-520) | 51.94% | 0.0441% | 240.90 | 2.156 |
| 0.001 | Fixed eligible universe | 5,000 | 2,693.40 (2,691-2,695) | 53.87% | 0.2287% | 1,204.51 | 2.236 |
| 0.001 | Fixed eligible universe | 10,000 | 5,177.00 (5,176-5,179) | 51.77% | 0.4397% | 2,409.03 | 2.149 |
| 0.001 | Fixed eligible universe | 50,000 | unavailable | unavailable | unavailable | unavailable | unavailable |
| 0.001 | Fixed eligible universe | 100,000 | unavailable | unavailable | unavailable | unavailable | unavailable |

## Coverage and denominator interpretation

Conditional sensitivity/specificity at k in an emitted pool use the positives/operational negatives within that pool. They are saved under explicit names in metrics.json. At the whole emitted output those rates are mechanically 1 and 0, so they are not presented as evidence of recovery.

Fixed-reference sensitivity always uses the same frozen eligible positive denominator. Fixed-universe specificity is assessed only within eligible sources. Unassessed-source predictions in the full pool cannot match the response reference and are compatibility-score nonmembers, not confirmed biological false positives.

| p_c | Eligible emitted pairs | TP | Operational FP | Missed response-positive pairs | Fixed-reference sensitivity | Fixed-universe specificity | Unassessed-source predictions in full pool |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.01 | 23,964 | 10,416 | 13,548 | 1,167,079 | 0.8846% | 99.6349% | 489,403 |
| 0.001 | 19,201 | 8,522 | 10,679 | 1,168,973 | 0.7237% | 99.7122% | 390,579 |

The fixed universe has a large omitted bottom-score group; its AUROC measures thresholded selection plus ranking, not unthresholded MI discrimination. The primary emitted pool changes if a method emits different edges. Report its size and fixed-reference coverage alongside its conditional AUROC, rather than treating a higher conditional AUROC alone as overall improvement.

The older full-emitted ordinal AUROC is preserved separately in metrics.json. It is not interchangeable with the new MI-tied AUROC. These reconstructed labels and inputs are not an exact reproduction of Figure 6a.

Inputs and outputs are SHA256-bound in metrics.json. Reference labels and the fixed-universe definition must remain identical across a future before/after sampling comparison.
