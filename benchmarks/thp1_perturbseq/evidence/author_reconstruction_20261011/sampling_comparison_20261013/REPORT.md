# THP-1 before/after sampling comparison

Eligible-source emitted predictions are primary; full emitted SIG predictions and the fixed eligible universe are secondary. All arms use the same frozen reconstructed perturbation-response reference. This is not exact Figure 6a reproduction or direct-edge validation.

## Operational comparison

| Arm | Inference profile | Sampling | Draws | Nominal p_b | Affine MI cutoff |
|---|---|---|---:|---:|---:|
| Legacy with replacement | legacy_reconstruction | legacy -r 1 | 121 | 1e-07 | 0.136987064 |
| 80% without replacement | sampling_only_backport | fixed-size without replacement -u 80% | 97 | 1e-07 | 0.155902064 |

The expression/metacells, full SIG hub list, response labels, eligible universe, DPI setting, nominal bootstrap p-value, seed numbers, and original consensus settings are fixed. Sample count, sample-size-dependent affine MI cutoff and sampling/tie-noise RNG consumption change together. This does not isolate replacement alone at a common numerical MI cutoff. PR71 and K-based consensus are excluded.

## Primary eligible-source emitted predictions

| p_c | Arm | Eligible edges | Response-positive matches | Positive fraction | MI-tied AUROC | Fixed-reference sensitivity |
|---:|---|---:|---:|---:|---:|---:|
| 0.01 | Legacy with replacement | 42,067 | 17,727 | 42.14% | 0.622142 | 1.5055% |
| 0.01 | 80% without replacement | 23,964 | 10,416 | 43.47% | 0.610740 | 0.8846% |
| 0.001 | Legacy with replacement | 26,667 | 11,647 | 43.68% | 0.609177 | 0.9891% |
| 0.001 | 80% without replacement | 19,201 | 8,522 | 44.38% | 0.606931 | 0.7237% |

Conditional emitted-pool AUROC compares different emitted pools, not the same all-pair ranking. Its changes must be read alongside pool size and fixed-reference coverage. No statistical uncertainty or independent repeated-batch significance is inferred from a single matched batch.

## Primary top-k comparison

TP below is the MI-tie expectation and attainable range. EPR uses saved integer prefix TP divided by the actual eligible-pool R seed-1 shuffled TP; it is not the analytic random-expectation lift. Each shuffle operates on its own arm's emitted pool.

| p_c | k | Before TP (range) | After TP (range) | Before EPR | After EPR |
|---:|---:|---:|---:|---:|---:|
| 0.01 | 1,000 | 556.14 (555-557) | 517.00 (517-517) | 1.3113 | 1.2193 |
| 0.01 | 5,000 | 2,658.12 (2,657-2,660) | 2,687.71 (2,687-2,688) | 1.2554 | 1.2347 |
| 0.01 | 10,000 | 5,195.25 (5,194-5,196) | 5,199.36 (5,198-5,201) | 1.2308 | 1.1900 |
| 0.01 | 50,000 | unavailable | unavailable | unavailable | unavailable |
| 0.01 | 100,000 | unavailable | unavailable | unavailable | unavailable |
| 0.001 | 1,000 | 561.00 (561-561) | 519.40 (519-520) | 1.3486 | 1.1876 |
| 0.001 | 5,000 | 2,636.33 (2,635-2,638) | 2,693.40 (2,691-2,695) | 1.2070 | 1.1983 |
| 0.001 | 10,000 | 5,186.00 (5,184-5,187) | 5,177.00 (5,176-5,179) | 1.1821 | 1.1615 |
| 0.001 | 50,000 | unavailable | unavailable | unavailable | unavailable |
| 0.001 | 100,000 | unavailable | unavailable | unavailable | unavailable |

Top-k above an arm's emitted pool is unavailable, never padded or extrapolated. TP curves retain the tie-expected counts/ranges and show the realized shuffle as dashed lines; EPR uses integer TP. ROC recounts entire equal-MI groups and excludes omitted pairs. The ROC diagonal is random expectation, not one realized shuffle.

## Secondary MI-tied AUROCs

| p_c | Population | Before AUROC | After AUROC | After - before |
|---:|---|---:|---:|---:|
| 0.01 | full_emitted | 0.573904 | 0.557080 | -0.016823 |
| 0.01 | fixed_eligible_universe | 0.504259 | 0.502601 | -0.001659 |
| 0.001 | full_emitted | 0.554705 | 0.553911 | -0.000794 |
| 0.001 | fixed_eligible_universe | 0.502926 | 0.502182 | -0.000744 |

The fixed-universe AUROC includes every omitted eligible pair in one shared bottom-score tie and therefore measures thresholded selection plus ranking, not unthresholded MI discrimination. Full-emitted scoring includes unassessed sources as operational reference nonmembers. These are not established biological negatives.

PNG and deterministic PDF figures, complete ranked and ROC coordinates, all-population summary/top-k tables and comparison.json are saved here. manifest.json binds the unchanged score inputs, scripts and new outputs by SHA256. Historical scoring templates retain baseline-only wording; this additive report identifies each actual inference arm from its bound run manifest.
