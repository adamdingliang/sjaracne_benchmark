> Publication copy of a frozen local report/process. Scientific text and numbers are unchanged; relative links are adapted to this compact package. See [publication provenance](PUBLICATION.json) for original hashes and [local artifacts](README.md#local-artifacts) for omitted sidecars.

# DREAM5: matched-budget and fixed-tolerance DPI controls

## Question and interpretation

This post-pilot follow-up asks whether apparent changes in precision reflect different output sizes, and whether a hub-size-dependent tolerance offers an advantage over a fixed positive tolerance. All results use explicitly labelled directed reference pairs. Unlabelled pairs are not called false positives. Network 3 has an incomplete biological reference; benchmark-defined FPs are not all proven biologically false edges.

Fixed positive epsilon is chosen to equal each dynamic schedule at the full hub panel. **Fixed and dynamic full-panel outputs are therefore identical by design.** Any specific advantage of making epsilon depend on H must be demonstrated at smaller H or across the trajectory, not inferred from the shared full-panel scores.

No automatic winner or new default is selected. Flatter pruning alone is not an accuracy benefit. These small-H controls do not validate extrapolation to thousands of BRCA100 regulators.

## Primary full-network matched controls

These are paired dynamic-minus-strict differences across the three unique sample seeds, using all reference-covered TFs. The budget is the strict network's emitted labelled-edge count, not its total network size. Positive TP changes at matched budget, or negative FP changes at matched recall, indicate a favorable trade-off on this reference. No winning slope is selected.

### Same labelled-edge budget

| Network | Slope | Both available / total | Expected TP change | Precision change (pp) |
| --- | --- | --- | --- | --- |
| network1 | 0.025 | 3 / 3 | 59.00 | 0.8190 |
| network1 | 0.05 | 3 / 3 | 90.00 | 1.2493 |
| network1 | 0.1 | 3 / 3 | 135.00 | 1.8072 |
| network3 | 0.025 | 3 / 3 | 4.00 | 0.1766 |
| network3 | 0.05 | 3 / 3 | 9.00 | 0.3810 |
| network3 | 0.1 | 3 / 3 | 12.00 | 0.5298 |

### Same recall

| Network | Slope | Both available / total | Expected FP change | Interpolated precision change (pp) |
| --- | --- | --- | --- | --- |
| network1 | 0.025 | 3 / 3 | -1474.00 | 4.5183 |
| network1 | 0.05 | 3 / 3 | -2114.00 | 6.9552 |
| network1 | 0.1 | 3 / 3 | -2531.00 | 8.7636 |
| network3 | 0.025 | 3 / 3 | -19.00 | 0.0704 |
| network3 | 0.05 | 3 / 3 | -130.00 | 0.5059 |
| network3 | 0.1 | 3 / 3 | -376.00 | 1.7505 |

Counts can be fractional because MI-boundary randomization is used for evaluation. Recall precision is calculated from expected counts, not E[precision] for a variable-size random network. All differences are paired within seed before their medians are taken.

## Matched comparison definitions

- **Matched edge count:** rank only emitted, explicitly labelled pairs by retained MI. Compare methods at the same requested count; never fill a budget with omitted zero-score pairs.
- **Matched recall:** compare within the shared attainable emitted-edge recall range. Interpolation inside an MI-tie group is an expected randomized tie split, not a new deterministic edge ranking. An unattainable target is reported unavailable, not extrapolated. The reported interpolated precision is TP_expected / (TP_expected + FP_expected): precision from expected counts, not the expectation of precision over variable-size randomized networks.
- Tables summarize matched per-seed/per-trajectory values descriptively. The source set and reference labels remain fixed within each trajectory, but differ between trajectories. Shared native jobs and repeated full panels are not independent biological replicates.
- Main matched tables use paired differences only when both arms attain the requested target. Availability is reported explicitly, so different available subsets of individual arms are not compared. Individual-arm summaries are supplemental; a partially available group does not have full expected coverage.

## Reference coverage

| Network | Scope | Panel | Evaluated sources | Reference-covered sources | Explicit pairs | Positives |
| --- | --- | --- | --- | --- | --- | --- |
| network1 | Full TF list |  | 195 | 178 | 278392 | 4012 |
| network3 | Full TF list |  | 334 | 141 | 152280 | 2066 |
| network1 | Smallest-panel sources | 1 | 49 | 44 | 68816 | 1176 |
| network1 | Smallest-panel sources | 2 | 49 | 44 | 68816 | 1257 |
| network1 | Smallest-panel sources | 3 | 49 | 45 | 70380 | 998 |
| network3 | Smallest-panel sources | 1 | 84 | 38 | 41040 | 293 |
| network3 | Smallest-panel sources | 2 | 84 | 40 | 43200 | 320 |
| network3 | Smallest-panel sources | 3 | 84 | 39 | 42120 | 450 |

## Full-reference absolute scores

| Network | Strategy | Slope | Precision | Recall | Average Precision | AUROC |
| --- | --- | --- | --- | --- | --- | --- |
| network1 | dynamic | 0.025 | 0.1519 | 0.3357 | 0.2091 | 0.6574 |
| network1 | dynamic | 0.05 | 0.1360 | 0.3562 | 0.2060 | 0.6660 |
| network1 | dynamic | 0.1 | 0.1079 | 0.3978 | 0.1942 | 0.6813 |
| network1 | fixed | 0.025 | 0.1519 | 0.3357 | 0.2091 | 0.6574 |
| network1 | fixed | 0.05 | 0.1360 | 0.3562 | 0.2060 | 0.6660 |
| network1 | fixed | 0.1 | 0.1079 | 0.3978 | 0.1942 | 0.6813 |
| network1 | no_dpi |  | 0.0419 | 0.6102 | 0.1827 | 0.7395 |
| network1 | strict | 0.0 | 0.1691 | 0.3148 | 0.2074 | 0.6486 |
| network3 | dynamic | 0.025 | 0.0737 | 0.1142 | 0.0479 | 0.5477 |
| network3 | dynamic | 0.05 | 0.0633 | 0.1336 | 0.0516 | 0.5539 |
| network3 | dynamic | 0.1 | 0.0483 | 0.1902 | 0.0597 | 0.5713 |
| network3 | fixed | 0.025 | 0.0737 | 0.1142 | 0.0479 | 0.5477 |
| network3 | fixed | 0.05 | 0.0633 | 0.1336 | 0.0516 | 0.5539 |
| network3 | fixed | 0.1 | 0.0483 | 0.1902 | 0.0597 | 0.5713 |
| network3 | no_dpi |  | 0.0161 | 0.8069 | 0.0734 | 0.6405 |
| network3 | strict | 0.0 | 0.0879 | 0.0968 | 0.0458 | 0.5416 |

The complete fixed reference universe includes emitted and omitted labelled pairs for these absolute Average Precision/AUROC scores; omitted pairs are tied at zero. The matched-budget and matched-recall tables below deliberately do not pad omitted pairs.

## Matched labelled-edge budgets: strict-network count

The budget equals the strict-DPI emitted **reference-labelled** edge count in each matched case, not the total number of network edges. Differences are first arm minus second arm; for example, `dynamic_vs_strict` is dynamic minus strict.

| Scope | Network | H | Annotation | Comparison | Slope | Both available / total | TP change | FP change | Expected precision change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full | network1 | 195 | full | dynamic_vs_fixed | 0.025 | 3 / 3 | 0.00 | 0.00 | 0.0000 |
| full | network1 | 195 | full | dynamic_vs_fixed | 0.05 | 3 / 3 | 0.00 | 0.00 | 0.0000 |
| full | network1 | 195 | full | dynamic_vs_fixed | 0.1 | 3 / 3 | 0.00 | 0.00 | 0.0000 |
| full | network1 | 195 | full | dynamic_vs_strict | 0.025 | 3 / 3 | 59.00 | -59.00 | 0.0082 |
| full | network1 | 195 | full | dynamic_vs_strict | 0.05 | 3 / 3 | 90.00 | -90.00 | 0.0125 |
| full | network1 | 195 | full | dynamic_vs_strict | 0.1 | 3 / 3 | 135.00 | -135.00 | 0.0181 |
| full | network1 | 195 | full | fixed_vs_strict | 0.025 | 3 / 3 | 59.00 | -59.00 | 0.0082 |
| full | network1 | 195 | full | fixed_vs_strict | 0.05 | 3 / 3 | 90.00 | -90.00 | 0.0125 |
| full | network1 | 195 | full | fixed_vs_strict | 0.1 | 3 / 3 | 135.00 | -135.00 | 0.0181 |
| full | network3 | 334 | full | dynamic_vs_fixed | 0.025 | 3 / 3 | 0.00 | 0.00 | 0.0000 |
| full | network3 | 334 | full | dynamic_vs_fixed | 0.05 | 3 / 3 | 0.00 | 0.00 | 0.0000 |
| full | network3 | 334 | full | dynamic_vs_fixed | 0.1 | 3 / 3 | 0.00 | 0.00 | 0.0000 |
| full | network3 | 334 | full | dynamic_vs_strict | 0.025 | 3 / 3 | 4.00 | -4.00 | 0.0018 |
| full | network3 | 334 | full | dynamic_vs_strict | 0.05 | 3 / 3 | 9.00 | -9.00 | 0.0038 |
| full | network3 | 334 | full | dynamic_vs_strict | 0.1 | 3 / 3 | 12.00 | -12.00 | 0.0053 |
| full | network3 | 334 | full | fixed_vs_strict | 0.025 | 3 / 3 | 4.00 | -4.00 | 0.0018 |
| full | network3 | 334 | full | fixed_vs_strict | 0.05 | 3 / 3 | 9.00 | -9.00 | 0.0038 |
| full | network3 | 334 | full | fixed_vs_strict | 0.1 | 3 / 3 | 12.00 | -12.00 | 0.0053 |
| trajectory | network1 | 195 | full | dynamic_vs_fixed | 0.025 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 195 | full | dynamic_vs_fixed | 0.05 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 195 | full | dynamic_vs_fixed | 0.1 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 195 | full | dynamic_vs_strict | 0.025 | 9 / 9 | 21.00 | -21.00 | 0.0101 |
| trajectory | network1 | 195 | full | dynamic_vs_strict | 0.05 | 9 / 9 | 33.00 | -33.00 | 0.0152 |
| trajectory | network1 | 195 | full | dynamic_vs_strict | 0.1 | 9 / 9 | 50.00 | -50.00 | 0.0241 |
| trajectory | network1 | 195 | full | fixed_vs_strict | 0.025 | 9 / 9 | 21.00 | -21.00 | 0.0101 |
| trajectory | network1 | 195 | full | fixed_vs_strict | 0.05 | 9 / 9 | 33.00 | -33.00 | 0.0152 |
| trajectory | network1 | 195 | full | fixed_vs_strict | 0.1 | 9 / 9 | 50.00 | -50.00 | 0.0241 |
| trajectory | network1 | 195 | panel | dynamic_vs_fixed | 0.025 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 195 | panel | dynamic_vs_fixed | 0.05 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 195 | panel | dynamic_vs_fixed | 0.1 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 195 | panel | dynamic_vs_strict | 0.025 | 9 / 9 | 21.00 | -21.00 | 0.0101 |
| trajectory | network1 | 195 | panel | dynamic_vs_strict | 0.05 | 9 / 9 | 33.00 | -33.00 | 0.0152 |
| trajectory | network1 | 195 | panel | dynamic_vs_strict | 0.1 | 9 / 9 | 50.00 | -50.00 | 0.0241 |
| trajectory | network1 | 195 | panel | fixed_vs_strict | 0.025 | 9 / 9 | 21.00 | -21.00 | 0.0101 |
| trajectory | network1 | 195 | panel | fixed_vs_strict | 0.05 | 9 / 9 | 33.00 | -33.00 | 0.0152 |
| trajectory | network1 | 195 | panel | fixed_vs_strict | 0.1 | 9 / 9 | 50.00 | -50.00 | 0.0241 |
| trajectory | network1 | 49 | full | dynamic_vs_fixed | 0.025 | 9 / 9 | -3.00 | 3.00 | -0.0005 |
| trajectory | network1 | 49 | full | dynamic_vs_fixed | 0.05 | 9 / 9 | -4.00 | 4.00 | -0.0007 |
| trajectory | network1 | 49 | full | dynamic_vs_fixed | 0.1 | 9 / 9 | -7.00 | 7.00 | -0.0013 |
| trajectory | network1 | 49 | full | dynamic_vs_strict | 0.025 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 49 | full | dynamic_vs_strict | 0.05 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 49 | full | dynamic_vs_strict | 0.1 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 49 | full | fixed_vs_strict | 0.025 | 9 / 9 | 3.00 | -3.00 | 0.0005 |
| trajectory | network1 | 49 | full | fixed_vs_strict | 0.05 | 9 / 9 | 4.00 | -4.00 | 0.0007 |
| trajectory | network1 | 49 | full | fixed_vs_strict | 0.1 | 9 / 9 | 7.00 | -7.00 | 0.0013 |
| trajectory | network1 | 49 | panel | dynamic_vs_fixed | 0.025 | 9 / 9 | -4.00 | 4.00 | -0.0007 |
| trajectory | network1 | 49 | panel | dynamic_vs_fixed | 0.05 | 9 / 9 | -3.00 | 3.00 | -0.0006 |
| trajectory | network1 | 49 | panel | dynamic_vs_fixed | 0.1 | 9 / 9 | -6.00 | 6.00 | -0.0011 |
| trajectory | network1 | 49 | panel | dynamic_vs_strict | 0.025 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 49 | panel | dynamic_vs_strict | 0.05 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 49 | panel | dynamic_vs_strict | 0.1 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 49 | panel | fixed_vs_strict | 0.025 | 9 / 9 | 4.00 | -4.00 | 0.0007 |
| trajectory | network1 | 49 | panel | fixed_vs_strict | 0.05 | 9 / 9 | 3.00 | -3.00 | 0.0006 |
| trajectory | network1 | 49 | panel | fixed_vs_strict | 0.1 | 9 / 9 | 6.00 | -6.00 | 0.0011 |
| trajectory | network1 | 98 | full | dynamic_vs_fixed | 0.025 | 9 / 9 | -6.00 | 6.00 | -0.0018 |
| trajectory | network1 | 98 | full | dynamic_vs_fixed | 0.05 | 9 / 9 | -7.00 | 7.00 | -0.0022 |
| trajectory | network1 | 98 | full | dynamic_vs_fixed | 0.1 | 9 / 9 | -9.00 | 9.00 | -0.0027 |
| trajectory | network1 | 98 | full | dynamic_vs_strict | 0.025 | 9 / 9 | 7.00 | -7.00 | 0.0018 |
| trajectory | network1 | 98 | full | dynamic_vs_strict | 0.05 | 9 / 9 | 12.00 | -12.00 | 0.0036 |
| trajectory | network1 | 98 | full | dynamic_vs_strict | 0.1 | 9 / 9 | 20.00 | -20.00 | 0.0059 |
| trajectory | network1 | 98 | full | fixed_vs_strict | 0.025 | 9 / 9 | 12.00 | -12.00 | 0.0036 |
| trajectory | network1 | 98 | full | fixed_vs_strict | 0.05 | 9 / 9 | 20.00 | -20.00 | 0.0059 |
| trajectory | network1 | 98 | full | fixed_vs_strict | 0.1 | 9 / 9 | 28.00 | -28.00 | 0.0074 |
| trajectory | network1 | 98 | panel | dynamic_vs_fixed | 0.025 | 9 / 9 | -5.00 | 5.00 | -0.0015 |
| trajectory | network1 | 98 | panel | dynamic_vs_fixed | 0.05 | 9 / 9 | -7.00 | 7.00 | -0.0021 |
| trajectory | network1 | 98 | panel | dynamic_vs_fixed | 0.1 | 9 / 9 | -9.00 | 9.00 | -0.0026 |
| trajectory | network1 | 98 | panel | dynamic_vs_strict | 0.025 | 9 / 9 | 7.00 | -7.00 | 0.0018 |
| trajectory | network1 | 98 | panel | dynamic_vs_strict | 0.05 | 9 / 9 | 11.00 | -11.00 | 0.0032 |
| trajectory | network1 | 98 | panel | dynamic_vs_strict | 0.1 | 9 / 9 | 19.00 | -19.00 | 0.0056 |
| trajectory | network1 | 98 | panel | fixed_vs_strict | 0.025 | 9 / 9 | 11.00 | -11.00 | 0.0032 |
| trajectory | network1 | 98 | panel | fixed_vs_strict | 0.05 | 9 / 9 | 19.00 | -19.00 | 0.0056 |
| trajectory | network1 | 98 | panel | fixed_vs_strict | 0.1 | 9 / 9 | 29.00 | -29.00 | 0.0075 |
| trajectory | network3 | 167 | full | dynamic_vs_fixed | 0.025 | 9 / 9 | -3.00 | 3.00 | -0.0034 |
| trajectory | network3 | 167 | full | dynamic_vs_fixed | 0.05 | 9 / 9 | -3.00 | 3.00 | -0.0031 |
| trajectory | network3 | 167 | full | dynamic_vs_fixed | 0.1 | 9 / 9 | -8.00 | 8.00 | -0.0077 |
| trajectory | network3 | 167 | full | dynamic_vs_strict | 0.025 | 9 / 9 | 2.00 | -2.00 | 0.0019 |
| trajectory | network3 | 167 | full | dynamic_vs_strict | 0.05 | 9 / 9 | 7.00 | -7.00 | 0.0075 |
| trajectory | network3 | 167 | full | dynamic_vs_strict | 0.1 | 9 / 9 | 9.00 | -9.00 | 0.0091 |
| trajectory | network3 | 167 | full | fixed_vs_strict | 0.025 | 9 / 9 | 7.00 | -7.00 | 0.0075 |
| trajectory | network3 | 167 | full | fixed_vs_strict | 0.05 | 9 / 9 | 9.00 | -9.00 | 0.0091 |
| trajectory | network3 | 167 | full | fixed_vs_strict | 0.1 | 9 / 9 | 19.00 | -19.00 | 0.0202 |
| trajectory | network3 | 167 | panel | dynamic_vs_fixed | 0.025 | 9 / 9 | -4.00 | 4.00 | -0.0036 |
| trajectory | network3 | 167 | panel | dynamic_vs_fixed | 0.05 | 9 / 9 | -3.00 | 3.00 | -0.0030 |
| trajectory | network3 | 167 | panel | dynamic_vs_fixed | 0.1 | 9 / 9 | -8.00 | 8.00 | -0.0084 |
| trajectory | network3 | 167 | panel | dynamic_vs_strict | 0.025 | 9 / 9 | 2.00 | -2.00 | 0.0019 |
| trajectory | network3 | 167 | panel | dynamic_vs_strict | 0.05 | 9 / 9 | 7.00 | -7.00 | 0.0068 |
| trajectory | network3 | 167 | panel | dynamic_vs_strict | 0.1 | 9 / 9 | 9.00 | -9.00 | 0.0098 |
| trajectory | network3 | 167 | panel | fixed_vs_strict | 0.025 | 9 / 9 | 7.00 | -7.00 | 0.0068 |
| trajectory | network3 | 167 | panel | fixed_vs_strict | 0.05 | 9 / 9 | 9.00 | -9.00 | 0.0087 |
| trajectory | network3 | 167 | panel | fixed_vs_strict | 0.1 | 9 / 9 | 21.00 | -21.00 | 0.0215 |
| trajectory | network3 | 334 | full | dynamic_vs_fixed | 0.025 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 334 | full | dynamic_vs_fixed | 0.05 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 334 | full | dynamic_vs_fixed | 0.1 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 334 | full | dynamic_vs_strict | 0.025 | 9 / 9 | 5.00 | -5.00 | 0.0088 |
| trajectory | network3 | 334 | full | dynamic_vs_strict | 0.05 | 9 / 9 | 7.00 | -7.00 | 0.0124 |
| trajectory | network3 | 334 | full | dynamic_vs_strict | 0.1 | 9 / 9 | 13.00 | -13.00 | 0.0260 |
| trajectory | network3 | 334 | full | fixed_vs_strict | 0.025 | 9 / 9 | 5.00 | -5.00 | 0.0088 |
| trajectory | network3 | 334 | full | fixed_vs_strict | 0.05 | 9 / 9 | 7.00 | -7.00 | 0.0124 |
| trajectory | network3 | 334 | full | fixed_vs_strict | 0.1 | 9 / 9 | 13.00 | -13.00 | 0.0260 |
| trajectory | network3 | 334 | panel | dynamic_vs_fixed | 0.025 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 334 | panel | dynamic_vs_fixed | 0.05 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 334 | panel | dynamic_vs_fixed | 0.1 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 334 | panel | dynamic_vs_strict | 0.025 | 9 / 9 | 5.00 | -5.00 | 0.0088 |
| trajectory | network3 | 334 | panel | dynamic_vs_strict | 0.05 | 9 / 9 | 7.00 | -7.00 | 0.0124 |
| trajectory | network3 | 334 | panel | dynamic_vs_strict | 0.1 | 9 / 9 | 13.00 | -13.00 | 0.0260 |
| trajectory | network3 | 334 | panel | fixed_vs_strict | 0.025 | 9 / 9 | 5.00 | -5.00 | 0.0088 |
| trajectory | network3 | 334 | panel | fixed_vs_strict | 0.05 | 9 / 9 | 7.00 | -7.00 | 0.0124 |
| trajectory | network3 | 334 | panel | fixed_vs_strict | 0.1 | 9 / 9 | 13.00 | -13.00 | 0.0260 |
| trajectory | network3 | 84 | full | dynamic_vs_fixed | 0.025 | 9 / 9 | -4.00 | 4.00 | -0.0019 |
| trajectory | network3 | 84 | full | dynamic_vs_fixed | 0.05 | 9 / 9 | -8.00 | 8.00 | -0.0042 |
| trajectory | network3 | 84 | full | dynamic_vs_fixed | 0.1 | 9 / 9 | -18.00 | 18.00 | -0.0095 |
| trajectory | network3 | 84 | full | dynamic_vs_strict | 0.025 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 84 | full | dynamic_vs_strict | 0.05 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 84 | full | dynamic_vs_strict | 0.1 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 84 | full | fixed_vs_strict | 0.025 | 9 / 9 | 4.00 | -4.00 | 0.0019 |
| trajectory | network3 | 84 | full | fixed_vs_strict | 0.05 | 9 / 9 | 8.00 | -8.00 | 0.0042 |
| trajectory | network3 | 84 | full | fixed_vs_strict | 0.1 | 9 / 9 | 18.00 | -18.00 | 0.0095 |
| trajectory | network3 | 84 | panel | dynamic_vs_fixed | 0.025 | 9 / 9 | -4.00 | 4.00 | -0.0019 |
| trajectory | network3 | 84 | panel | dynamic_vs_fixed | 0.05 | 9 / 9 | -8.00 | 8.00 | -0.0041 |
| trajectory | network3 | 84 | panel | dynamic_vs_fixed | 0.1 | 9 / 9 | -17.00 | 17.00 | -0.0092 |
| trajectory | network3 | 84 | panel | dynamic_vs_strict | 0.025 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 84 | panel | dynamic_vs_strict | 0.05 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 84 | panel | dynamic_vs_strict | 0.1 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 84 | panel | fixed_vs_strict | 0.025 | 9 / 9 | 4.00 | -4.00 | 0.0019 |
| trajectory | network3 | 84 | panel | fixed_vs_strict | 0.05 | 9 / 9 | 8.00 | -8.00 | 0.0041 |
| trajectory | network3 | 84 | panel | fixed_vs_strict | 0.1 | 9 / 9 | 17.00 | -17.00 | 0.0092 |

MI ties crossing a budget use a uniform expected selection, with attainable TP bounds retained in the per-case tables. A rounded expected TP is not a count from one uniquely determined graph.

## Matched recall: strict-network recall

The target equals strict-DPI emitted recall in each matched case. Both arms are evaluated by the same tie-boundary randomization convention; trailing FPs after the last required TP are not automatically retained in the strict arm. Requested nominal-recall grids are retained in the complete tables.

| Scope | Network | H | Annotation | Comparison | Slope | Both available / total | TP change | FP change | Interpolated precision change |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full | network1 | 195 | full | dynamic_vs_fixed | 0.025 | 3 / 3 | 0.00 | 0.00 | 0.0000 |
| full | network1 | 195 | full | dynamic_vs_fixed | 0.05 | 3 / 3 | 0.00 | 0.00 | 0.0000 |
| full | network1 | 195 | full | dynamic_vs_fixed | 0.1 | 3 / 3 | 0.00 | 0.00 | 0.0000 |
| full | network1 | 195 | full | dynamic_vs_strict | 0.025 | 3 / 3 | 0.00 | -1474.00 | 0.0452 |
| full | network1 | 195 | full | dynamic_vs_strict | 0.05 | 3 / 3 | 0.00 | -2114.00 | 0.0696 |
| full | network1 | 195 | full | dynamic_vs_strict | 0.1 | 3 / 3 | 0.00 | -2531.00 | 0.0876 |
| full | network1 | 195 | full | fixed_vs_strict | 0.025 | 3 / 3 | 0.00 | -1474.00 | 0.0452 |
| full | network1 | 195 | full | fixed_vs_strict | 0.05 | 3 / 3 | 0.00 | -2114.00 | 0.0696 |
| full | network1 | 195 | full | fixed_vs_strict | 0.1 | 3 / 3 | 0.00 | -2531.00 | 0.0876 |
| full | network3 | 334 | full | dynamic_vs_fixed | 0.025 | 3 / 3 | 0.00 | 0.00 | 0.0000 |
| full | network3 | 334 | full | dynamic_vs_fixed | 0.05 | 3 / 3 | 0.00 | 0.00 | 0.0000 |
| full | network3 | 334 | full | dynamic_vs_fixed | 0.1 | 3 / 3 | 0.00 | 0.00 | 0.0000 |
| full | network3 | 334 | full | dynamic_vs_strict | 0.025 | 3 / 3 | 0.00 | -19.00 | 0.0007 |
| full | network3 | 334 | full | dynamic_vs_strict | 0.05 | 3 / 3 | 0.00 | -130.00 | 0.0051 |
| full | network3 | 334 | full | dynamic_vs_strict | 0.1 | 3 / 3 | 0.00 | -376.00 | 0.0175 |
| full | network3 | 334 | full | fixed_vs_strict | 0.025 | 3 / 3 | 0.00 | -19.00 | 0.0007 |
| full | network3 | 334 | full | fixed_vs_strict | 0.05 | 3 / 3 | 0.00 | -130.00 | 0.0051 |
| full | network3 | 334 | full | fixed_vs_strict | 0.1 | 3 / 3 | 0.00 | -376.00 | 0.0175 |
| trajectory | network1 | 195 | full | dynamic_vs_fixed | 0.025 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 195 | full | dynamic_vs_fixed | 0.05 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 195 | full | dynamic_vs_fixed | 0.1 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 195 | full | dynamic_vs_strict | 0.025 | 9 / 9 | 0.00 | -611.00 | 0.0712 |
| trajectory | network1 | 195 | full | dynamic_vs_strict | 0.05 | 9 / 9 | 0.00 | -868.00 | 0.1212 |
| trajectory | network1 | 195 | full | dynamic_vs_strict | 0.1 | 9 / 9 | 0.00 | -949.00 | 0.1413 |
| trajectory | network1 | 195 | full | fixed_vs_strict | 0.025 | 9 / 9 | 0.00 | -611.00 | 0.0712 |
| trajectory | network1 | 195 | full | fixed_vs_strict | 0.05 | 9 / 9 | 0.00 | -868.00 | 0.1212 |
| trajectory | network1 | 195 | full | fixed_vs_strict | 0.1 | 9 / 9 | 0.00 | -949.00 | 0.1413 |
| trajectory | network1 | 195 | panel | dynamic_vs_fixed | 0.025 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 195 | panel | dynamic_vs_fixed | 0.05 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 195 | panel | dynamic_vs_fixed | 0.1 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 195 | panel | dynamic_vs_strict | 0.025 | 9 / 9 | 0.00 | -611.00 | 0.0712 |
| trajectory | network1 | 195 | panel | dynamic_vs_strict | 0.05 | 9 / 9 | 0.00 | -868.00 | 0.1212 |
| trajectory | network1 | 195 | panel | dynamic_vs_strict | 0.1 | 9 / 9 | 0.00 | -949.00 | 0.1413 |
| trajectory | network1 | 195 | panel | fixed_vs_strict | 0.025 | 9 / 9 | 0.00 | -611.00 | 0.0712 |
| trajectory | network1 | 195 | panel | fixed_vs_strict | 0.05 | 9 / 9 | 0.00 | -868.00 | 0.1212 |
| trajectory | network1 | 195 | panel | fixed_vs_strict | 0.1 | 9 / 9 | 0.00 | -949.00 | 0.1413 |
| trajectory | network1 | 49 | full | dynamic_vs_fixed | 0.025 | 9 / 9 | 0.00 | 64.00 | -0.0011 |
| trajectory | network1 | 49 | full | dynamic_vs_fixed | 0.05 | 9 / 9 | 0.00 | 191.00 | -0.0030 |
| trajectory | network1 | 49 | full | dynamic_vs_fixed | 0.1 | 9 / 9 | 0.00 | 265.00 | -0.0054 |
| trajectory | network1 | 49 | full | dynamic_vs_strict | 0.025 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 49 | full | dynamic_vs_strict | 0.05 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 49 | full | dynamic_vs_strict | 0.1 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 49 | full | fixed_vs_strict | 0.025 | 9 / 9 | 0.00 | -64.00 | 0.0011 |
| trajectory | network1 | 49 | full | fixed_vs_strict | 0.05 | 9 / 9 | 0.00 | -191.00 | 0.0030 |
| trajectory | network1 | 49 | full | fixed_vs_strict | 0.1 | 9 / 9 | 0.00 | -265.00 | 0.0054 |
| trajectory | network1 | 49 | panel | dynamic_vs_fixed | 0.025 | 9 / 9 | 0.00 | 74.00 | -0.0013 |
| trajectory | network1 | 49 | panel | dynamic_vs_fixed | 0.05 | 9 / 9 | 0.00 | 207.00 | -0.0038 |
| trajectory | network1 | 49 | panel | dynamic_vs_fixed | 0.1 | 9 / 9 | 0.00 | 269.00 | -0.0057 |
| trajectory | network1 | 49 | panel | dynamic_vs_strict | 0.025 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 49 | panel | dynamic_vs_strict | 0.05 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 49 | panel | dynamic_vs_strict | 0.1 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network1 | 49 | panel | fixed_vs_strict | 0.025 | 9 / 9 | 0.00 | -74.00 | 0.0013 |
| trajectory | network1 | 49 | panel | fixed_vs_strict | 0.05 | 9 / 9 | 0.00 | -207.00 | 0.0038 |
| trajectory | network1 | 49 | panel | fixed_vs_strict | 0.1 | 9 / 9 | 0.00 | -269.00 | 0.0057 |
| trajectory | network1 | 98 | full | dynamic_vs_fixed | 0.025 | 9 / 9 | 0.00 | 129.00 | -0.0069 |
| trajectory | network1 | 98 | full | dynamic_vs_fixed | 0.05 | 9 / 9 | 0.00 | 105.00 | -0.0043 |
| trajectory | network1 | 98 | full | dynamic_vs_fixed | 0.1 | 9 / 9 | 0.00 | 391.00 | -0.0190 |
| trajectory | network1 | 98 | full | dynamic_vs_strict | 0.025 | 9 / 9 | 0.00 | -249.00 | 0.0104 |
| trajectory | network1 | 98 | full | dynamic_vs_strict | 0.05 | 9 / 9 | 0.00 | -405.00 | 0.0159 |
| trajectory | network1 | 98 | full | dynamic_vs_strict | 0.1 | 9 / 9 | 0.00 | -607.00 | 0.0235 |
| trajectory | network1 | 98 | full | fixed_vs_strict | 0.025 | 9 / 9 | 0.00 | -405.00 | 0.0159 |
| trajectory | network1 | 98 | full | fixed_vs_strict | 0.05 | 9 / 9 | 0.00 | -611.00 | 0.0235 |
| trajectory | network1 | 98 | full | fixed_vs_strict | 0.1 | 9 / 9 | 0.00 | -956.00 | 0.0464 |
| trajectory | network1 | 98 | panel | dynamic_vs_fixed | 0.025 | 9 / 9 | 0.00 | 134.00 | -0.0055 |
| trajectory | network1 | 98 | panel | dynamic_vs_fixed | 0.05 | 9 / 9 | 0.00 | 88.00 | -0.0048 |
| trajectory | network1 | 98 | panel | dynamic_vs_fixed | 0.1 | 9 / 9 | 0.00 | 455.00 | -0.0223 |
| trajectory | network1 | 98 | panel | dynamic_vs_strict | 0.025 | 9 / 9 | 0.00 | -269.00 | 0.0105 |
| trajectory | network1 | 98 | panel | dynamic_vs_strict | 0.05 | 9 / 9 | 0.00 | -425.00 | 0.0160 |
| trajectory | network1 | 98 | panel | dynamic_vs_strict | 0.1 | 9 / 9 | 0.00 | -620.00 | 0.0212 |
| trajectory | network1 | 98 | panel | fixed_vs_strict | 0.025 | 9 / 9 | 0.00 | -425.00 | 0.0160 |
| trajectory | network1 | 98 | panel | fixed_vs_strict | 0.05 | 9 / 9 | 0.00 | -621.00 | 0.0214 |
| trajectory | network1 | 98 | panel | fixed_vs_strict | 0.1 | 9 / 9 | 0.00 | -996.00 | 0.0466 |
| trajectory | network3 | 167 | full | dynamic_vs_fixed | 0.025 | 9 / 9 | 0.00 | 13.00 | -0.0010 |
| trajectory | network3 | 167 | full | dynamic_vs_fixed | 0.05 | 9 / 9 | 0.00 | 69.00 | -0.0053 |
| trajectory | network3 | 167 | full | dynamic_vs_fixed | 0.1 | 9 / 9 | 0.00 | 414.00 | -0.1921 |
| trajectory | network3 | 167 | full | dynamic_vs_strict | 0.025 | 9 / 9 | 0.00 | -77.00 | 0.0043 |
| trajectory | network3 | 167 | full | dynamic_vs_strict | 0.05 | 9 / 9 | 0.00 | -144.00 | 0.0083 |
| trajectory | network3 | 167 | full | dynamic_vs_strict | 0.1 | 9 / 9 | 0.00 | -265.00 | 0.0283 |
| trajectory | network3 | 167 | full | fixed_vs_strict | 0.025 | 9 / 9 | 0.00 | -143.00 | 0.0083 |
| trajectory | network3 | 167 | full | fixed_vs_strict | 0.05 | 9 / 9 | 0.00 | -264.00 | 0.0281 |
| trajectory | network3 | 167 | full | fixed_vs_strict | 0.1 | 9 / 9 | 0.00 | -607.00 | 0.2373 |
| trajectory | network3 | 167 | panel | dynamic_vs_fixed | 0.025 | 9 / 9 | 0.00 | 14.00 | -0.0010 |
| trajectory | network3 | 167 | panel | dynamic_vs_fixed | 0.05 | 9 / 9 | 0.00 | 86.00 | -0.0063 |
| trajectory | network3 | 167 | panel | dynamic_vs_fixed | 0.1 | 9 / 9 | 0.00 | 454.00 | -0.1774 |
| trajectory | network3 | 167 | panel | dynamic_vs_strict | 0.025 | 9 / 9 | 0.00 | -87.00 | 0.0046 |
| trajectory | network3 | 167 | panel | dynamic_vs_strict | 0.05 | 9 / 9 | 0.00 | -157.00 | 0.0101 |
| trajectory | network3 | 167 | panel | dynamic_vs_strict | 0.1 | 9 / 9 | 0.00 | -278.00 | 0.0279 |
| trajectory | network3 | 167 | panel | fixed_vs_strict | 0.025 | 9 / 9 | 0.00 | -156.00 | 0.0101 |
| trajectory | network3 | 167 | panel | fixed_vs_strict | 0.05 | 9 / 9 | 0.00 | -277.00 | 0.0278 |
| trajectory | network3 | 167 | panel | fixed_vs_strict | 0.1 | 9 / 9 | 0.00 | -637.00 | 0.2269 |
| trajectory | network3 | 334 | full | dynamic_vs_fixed | 0.025 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 334 | full | dynamic_vs_fixed | 0.05 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 334 | full | dynamic_vs_fixed | 0.1 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 334 | full | dynamic_vs_strict | 0.025 | 9 / 9 | 0.00 | -81.00 | 0.0108 |
| trajectory | network3 | 334 | full | dynamic_vs_strict | 0.05 | 9 / 9 | 0.00 | -157.00 | 0.0438 |
| trajectory | network3 | 334 | full | dynamic_vs_strict | 0.1 | 9 / 9 | 0.00 | -323.00 | 0.3940 |
| trajectory | network3 | 334 | full | fixed_vs_strict | 0.025 | 9 / 9 | 0.00 | -81.00 | 0.0108 |
| trajectory | network3 | 334 | full | fixed_vs_strict | 0.05 | 9 / 9 | 0.00 | -157.00 | 0.0438 |
| trajectory | network3 | 334 | full | fixed_vs_strict | 0.1 | 9 / 9 | 0.00 | -323.00 | 0.3940 |
| trajectory | network3 | 334 | panel | dynamic_vs_fixed | 0.025 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 334 | panel | dynamic_vs_fixed | 0.05 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 334 | panel | dynamic_vs_fixed | 0.1 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 334 | panel | dynamic_vs_strict | 0.025 | 9 / 9 | 0.00 | -81.00 | 0.0108 |
| trajectory | network3 | 334 | panel | dynamic_vs_strict | 0.05 | 9 / 9 | 0.00 | -157.00 | 0.0438 |
| trajectory | network3 | 334 | panel | dynamic_vs_strict | 0.1 | 9 / 9 | 0.00 | -323.00 | 0.3940 |
| trajectory | network3 | 334 | panel | fixed_vs_strict | 0.025 | 9 / 9 | 0.00 | -81.00 | 0.0108 |
| trajectory | network3 | 334 | panel | fixed_vs_strict | 0.05 | 9 / 9 | 0.00 | -157.00 | 0.0438 |
| trajectory | network3 | 334 | panel | fixed_vs_strict | 0.1 | 9 / 9 | 0.00 | -323.00 | 0.3940 |
| trajectory | network3 | 84 | full | dynamic_vs_fixed | 0.025 | 9 / 9 | 0.00 | 284.00 | -0.0095 |
| trajectory | network3 | 84 | full | dynamic_vs_fixed | 0.05 | 9 / 9 | 0.00 | 347.00 | -0.0124 |
| trajectory | network3 | 84 | full | dynamic_vs_fixed | 0.1 | 9 / 9 | 0.00 | 974.00 | -0.0649 |
| trajectory | network3 | 84 | full | dynamic_vs_strict | 0.025 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 84 | full | dynamic_vs_strict | 0.05 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 84 | full | dynamic_vs_strict | 0.1 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 84 | full | fixed_vs_strict | 0.025 | 9 / 9 | 0.00 | -284.00 | 0.0095 |
| trajectory | network3 | 84 | full | fixed_vs_strict | 0.05 | 9 / 9 | 0.00 | -347.00 | 0.0124 |
| trajectory | network3 | 84 | full | fixed_vs_strict | 0.1 | 9 / 9 | 0.00 | -974.00 | 0.0649 |
| trajectory | network3 | 84 | panel | dynamic_vs_fixed | 0.025 | 9 / 9 | 0.00 | 301.00 | -0.0094 |
| trajectory | network3 | 84 | panel | dynamic_vs_fixed | 0.05 | 9 / 9 | 0.00 | 357.00 | -0.0123 |
| trajectory | network3 | 84 | panel | dynamic_vs_fixed | 0.1 | 9 / 9 | 0.00 | 1004.00 | -0.0650 |
| trajectory | network3 | 84 | panel | dynamic_vs_strict | 0.025 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 84 | panel | dynamic_vs_strict | 0.05 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 84 | panel | dynamic_vs_strict | 0.1 | 9 / 9 | 0.00 | 0.00 | 0.0000 |
| trajectory | network3 | 84 | panel | fixed_vs_strict | 0.025 | 9 / 9 | 0.00 | -301.00 | 0.0094 |
| trajectory | network3 | 84 | panel | fixed_vs_strict | 0.05 | 9 / 9 | 0.00 | -357.00 | 0.0123 |
| trajectory | network3 | 84 | panel | fixed_vs_strict | 0.1 | 9 / 9 | 0.00 | -1004.00 | 0.0650 |

## Fixed versus dynamic controls within trajectories

Use the per-trajectory comparisons to assess fixed versus dynamic tolerance at identical H, source population, reference labels and sample selection. A difference at a changing density is not itself a matched-budget benefit. Paired control differences are **dynamic minus fixed**. The full-panel paired differences should be zero because the controls share exactly the same tolerance there.

| Scope | Network | H | Annotation | Slope | AUROC_fixed_explicit_universe_MI_ties_delta | FP_delta | TP_delta | average_precision_fixed_explicit_universe_delta | median_source_pruning_fraction_delta | precision_delta | recall_delta |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| full | network1 | 195 | full | 0.025 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| full | network1 | 195 | full | 0.05 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| full | network1 | 195 | full | 0.1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| full | network3 | 334 | full | 0.025 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| full | network3 | 334 | full | 0.05 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| full | network3 | 334 | full | 0.1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| trajectory | network1 | 195 | full | 0.025 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| trajectory | network1 | 195 | full | 0.05 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| trajectory | network1 | 195 | full | 0.1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| trajectory | network1 | 195 | panel | 0.025 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| trajectory | network1 | 195 | panel | 0.05 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| trajectory | network1 | 195 | panel | 0.1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| trajectory | network1 | 49 | full | 0.025 | -0.0046 | -558.0000 | -15.0000 | 0.0011 | 0.0349 | 0.0060 | -0.0145 |
| trajectory | network1 | 49 | full | 0.05 | -0.0084 | -1174.0000 | -31.0000 | -0.0004 | 0.0789 | 0.0114 | -0.0286 |
| trajectory | network1 | 49 | full | 0.1 | -0.0168 | -2568.0000 | -58.0000 | 0.0018 | 0.1605 | 0.0211 | -0.0570 |
| trajectory | network1 | 49 | panel | 0.025 | -0.0042 | -563.0000 | -14.0000 | 0.0010 | 0.0361 | 0.0059 | -0.0140 |
| trajectory | network1 | 49 | panel | 0.05 | -0.0088 | -1180.0000 | -30.0000 | -0.0001 | 0.0807 | 0.0111 | -0.0294 |
| trajectory | network1 | 49 | panel | 0.1 | -0.0162 | -2579.0000 | -57.0000 | 0.0018 | 0.1698 | 0.0205 | -0.0570 |
| trajectory | network1 | 98 | full | 0.025 | -0.0040 | -245.0000 | -12.0000 | -0.0010 | 0.0176 | 0.0046 | -0.0102 |
| trajectory | network1 | 98 | full | 0.05 | -0.0060 | -531.0000 | -18.0000 | -0.0009 | 0.0402 | 0.0097 | -0.0170 |
| trajectory | network1 | 98 | full | 0.1 | -0.0121 | -1332.0000 | -44.0000 | 0.0009 | 0.0914 | 0.0160 | -0.0374 |
| trajectory | network1 | 98 | panel | 0.025 | -0.0038 | -252.0000 | -12.0000 | -0.0009 | 0.0152 | 0.0046 | -0.0103 |
| trajectory | network1 | 98 | panel | 0.05 | -0.0059 | -535.0000 | -18.0000 | -0.0007 | 0.0395 | 0.0093 | -0.0170 |
| trajectory | network1 | 98 | panel | 0.1 | -0.0121 | -1352.0000 | -44.0000 | 0.0006 | 0.0867 | 0.0158 | -0.0366 |
| trajectory | network3 | 167 | full | 0.025 | -0.0036 | -187.0000 | -5.0000 | -0.0058 | 0.0067 | 0.0024 | -0.0111 |
| trajectory | network3 | 167 | full | 0.05 | -0.0098 | -435.0000 | -10.0000 | -0.0097 | 0.0155 | 0.0044 | -0.0281 |
| trajectory | network3 | 167 | full | 0.1 | -0.0217 | -1273.0000 | -27.0000 | -0.0245 | 0.0466 | 0.0059 | -0.0688 |
| trajectory | network3 | 167 | panel | 0.025 | -0.0037 | -188.0000 | -5.0000 | -0.0056 | 0.0068 | 0.0023 | -0.0111 |
| trajectory | network3 | 167 | panel | 0.05 | -0.0097 | -448.0000 | -10.0000 | -0.0098 | 0.0163 | 0.0041 | -0.0281 |
| trajectory | network3 | 167 | panel | 0.1 | -0.0215 | -1293.0000 | -27.0000 | -0.0244 | 0.0463 | 0.0052 | -0.0688 |
| trajectory | network3 | 334 | full | 0.025 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| trajectory | network3 | 334 | full | 0.05 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| trajectory | network3 | 334 | full | 0.1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| trajectory | network3 | 334 | panel | 0.025 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| trajectory | network3 | 334 | panel | 0.05 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| trajectory | network3 | 334 | panel | 0.1 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 |
| trajectory | network3 | 84 | full | 0.025 | -0.0036 | -466.0000 | -6.0000 | -0.0043 | 0.0173 | 0.0054 | -0.0171 |
| trajectory | network3 | 84 | full | 0.05 | -0.0082 | -1066.0000 | -13.0000 | -0.0080 | 0.0417 | 0.0099 | -0.0356 |
| trajectory | network3 | 84 | full | 0.1 | -0.0299 | -2737.0000 | -37.0000 | -0.0295 | 0.1002 | 0.0144 | -0.1094 |
| trajectory | network3 | 84 | panel | 0.025 | -0.0036 | -481.0000 | -6.0000 | -0.0044 | 0.0173 | 0.0051 | -0.0171 |
| trajectory | network3 | 84 | panel | 0.05 | -0.0081 | -1085.0000 | -13.0000 | -0.0082 | 0.0422 | 0.0097 | -0.0356 |
| trajectory | network3 | 84 | panel | 0.1 | -0.0314 | -2789.0000 | -38.0000 | -0.0296 | 0.1013 | 0.0140 | -0.1094 |

## Evidence and limitations

Engine `b41c4ca637ac2bffe73617a86af65c83e75ee075`; design `3247a52d286d6b74df6551bcadaec520a41a5b85d23b143b992182bcda293c1e`.

The original expression genes, observation resamples, PCHIP MI cutoff and panel memberships are held fixed. Any new native jobs add only fixed-positive-epsilon controls; historical graphs and reports are preserved. Validation uses the existing native completion, sample/model/cutoff and serialized-MI gates. Serialized MI is not full-precision pre-DPI identity.

These local scores are not official DREAM5 leaderboard scores. Computational panel and sample repetitions are not independent biological datasets. This is an explicitly requested post-pilot control analysis, not an independently preregistered confirmation or proof of biological precision.

[All run metrics](runs.tsv) | [Matched budgets](matched_budget.tsv) | [Matched recall](matched_recall.tsv) | [Paired budget comparisons](matched_budget_comparisons.tsv) | [Paired recall comparisons](matched_recall_comparisons.tsv) | [Paired controls](paired_controls.tsv) | [Complete analysis](README.md#local-artifacts)
