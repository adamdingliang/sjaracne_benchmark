# DREAM5: DPI tolerance and dynamic-schedule controls

## Design

These exploratory comparisons ask whether relaxing DPI improves recovery of reference edges, and whether making the tolerance depend on hub-list size adds an advantage over a fixed positive tolerance.

DREAM5 Network 1 is simulated; Network 3 is measured *E. coli* expression. Both have 805 profiles. Three paired sample seeds each selected exactly 644 profiles without replacement. The frozen experimental engine (`b41c4ca`) used PCHIP `p_b=0.001`, MI cutoff `0.021543205318573955`, `Npar=40`, zero noise and no consensus. All configurations retained the same expression and sampling within each comparison. **No DPI still applies this MI cutoff; it is not unthresholded raw MI.**

Stage 1 compared no DPI, strict DPI (`epsilon=0`) and fixed tolerances 0.05, 0.10 and 0.15 using all 195 candidate TFs for Network 1 and all 334 for Network 3. The follow-up used three label-blind nested hub panels, evaluated the smallest-panel sources throughout each trajectory, and compared:

| Dataset | Tested hub counts H | Dynamic anchor H_min |
| --- | --- | ---: |
| Network 1 - simulated | 49, 98, 195 | 49 |
| Network 3 - E. coli | 84, 167, 334 | 84 |

```text
dynamic: epsilon(H) = min(0.30, slope * log2(H / H_min))
fixed:   epsilon(H) = dynamic epsilon at the full hub-list size, at every H
```

Slopes were 0.025, 0.05 and 0.10. Main runs used the panel for both reconstruction (`-s`) and annotation (`-l`); full-TF annotation was a control. These DREAM anchors do **not** test the later bulk-data anchor `H_ref=479`.

## Results

Only explicitly labelled directed reference pairs were scored; unlabelled pairs were excluded.

| Dataset | Reference-covered TFs | Labelled directed pairs | Reference positives |
| --- | ---: | ---: | ---: |
| Network 1 - simulated | 178 | 278,392 | 4,012 |
| Network 3 - E. coli | 141 | 152,280 | 2,066 |

Precision is TP/(TP+FP); recall is TP divided by all reference positives. Average Precision summarizes precision across the ranked list, weighting each recall increment by its precision; omitted labelled pairs share the bottom zero score. This is local scoring, not an official DREAM5 leaderboard submission.

The table gives separate medians across three sample seeds. Fixed and dynamic rows at full H are **identical by construction**, because they reuse the same tolerance and native outputs.

| Network | Configuration at full H | TP | FP | Precision | Recall | Average Precision |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | No DPI | 2,448 | 56,018 | 4.19% | 61.02% | 0.1827 |
| 1 | Strict DPI | 1,263 | 6,207 | 16.91% | 31.48% | 0.2074 |
| 1 | Fixed epsilon about 0.09963 | 1,429 | 9,069 | 13.60% | 35.62% | 0.2060 |
| 1 | Dynamic, slope 0.05 | 1,429 | 9,069 | 13.60% | 35.62% | 0.2060 |
| 3 | No DPI | 1,667 | 101,608 | 1.61% | 80.69% | 0.0734 |
| 3 | Strict DPI | 200 | 2,134 | 8.79% | 9.68% | 0.0458 |
| 3 | Fixed epsilon about 0.09957 | 276 | 4,087 | 6.33% | 13.36% | 0.0516 |
| 3 | Dynamic, slope 0.05 | 276 | 4,087 | 6.33% | 13.36% | 0.0516 |

Relaxed DPI recovers positives but also retains many more reference-negative pairs. Fewer raw FPs alone therefore cannot establish a better strategy. The table below compares the full-H slope-0.05 endpoint with strict DPI using paired median differences. A negative FP change means fewer reference-negative predictions.

| Dataset | TP change at the same strict-DPI labelled-edge budget | FP change at that budget | Fewer FPs at the same strict-DPI recall |
| --- | ---: | ---: | ---: |
| Network 1 | +90 | -90 | 2,114 |
| Network 3 | +9 | -9 | 130 |

These favorable selected operating points apply equally to the fixed control, not specifically to dynamic epsilon. MI ties use label-independent expected randomized splits.

At smaller H, the dynamic-specific controls were less favorable. Below are paired dynamic-minus-fixed medians, slope 0.05, panel annotation; each group contains nine paired panel/seed cases.

| Network | H | Same-budget TP change | Same-budget FP change | Same-recall FP change |
| --- | ---: | ---: | ---: | ---: |
| 1 | 49 | -3 | +3 | +207 |
| 1 | 98 | -7 | +7 | +88 |
| 3 | 84 | -8 | +8 | +357 |
| 3 | 167 | -3 | +3 | +86 |

## Conditional conclusion

Positive epsilon offers a precision-recall trade-off and can improve selected matched operating points over strict DPI. **These tests do not demonstrate an accuracy advantage from making epsilon dynamic rather than fixed.** Flatter hub-size pruning is an engineering property, not proof of more correct edges or a new default. Network 3's reference is incomplete: its benchmark-defined FPs are not all proven biological errors. These post-hoc controls and shared panel/seed cases are not independent biological validation or evidence for a universal schedule.

Details: Stage 1 [Process](../../benchmarks/dpi_epsilon_summaries/evidence/dream5_stage1/PROCESS.md) | [Results](../../benchmarks/dpi_epsilon_summaries/evidence/dream5_stage1/RESULTS.md); matched and fixed-tolerance controls [Process](../../benchmarks/dpi_epsilon_summaries/evidence/dream5_controls/PROCESS.md) | [Results](../../benchmarks/dpi_epsilon_summaries/evidence/dream5_controls/RESULTS.md).
