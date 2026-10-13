# Supplementary fixed-universe THP-1 ROC

This is the completed reconstructed legacy baseline, not a sampling-change comparison or exact Fig. 6a reproduction.

Universe: 272 eligible assayed strict-SIG inference sources x 17,971 frozen NT inference targets, excluding self-pairs.
Fixed totals: 4,887,840 candidate pairs; 1,177,495 reference-positive; 3,710,345 operational reference-negative.

Emitted pairs rank by consensus MI; equal MI stays tied. Every omitted pair has one shared bottom score, below every emitted pair, including emitted MI=0. This is an evaluation policy, not estimated missing MI.
Sensitivity=TP/fixed positives; specificity=TN/fixed negatives. ROC uses whole tied groups and includes the omitted group. AUROC is checked independently by positive-negative pair counting.

| Consensus p | Eligible emitted pairs | TP | FP | Sensitivity | Specificity | Fixed-universe AUROC | Preserved emitted-edge ordinal AUROC |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.01 | 42,067 | 17,727 | 24,340 | 0.015055 | 0.993440 | 0.504259 | 0.573906 |
| 0.001 | 26,667 | 11,647 | 15,020 | 0.009891 | 0.995952 | 0.502926 | 0.554708 |

The two AUROC columns differ in population AND tie handling. They are different estimands, not a corrected version of the same metric.
The fixed-universe AUROC measures thresholded-network selection plus ranking. A large unscored/omitted tied group limits resolution; it is not unthresholded all-pair MI AUROC.
Reference positives represent perturbation responses, not proven direct edges; nonmembers are operational negatives, not verified biological negatives.
Top-k is ranked within the eligible-source universe, not the full author-style SIG network. Tied boundaries report expected TP plus its min/max range. Top-k above eligible emitted counts is unavailable, not padded with arbitrary missing pairs.
Do not select labels, source filters or thresholds to match the publication. Preserve this exact universe/reference across any future matched sampling comparison.
