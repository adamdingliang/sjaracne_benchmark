# Supplementary fixed-universe THP-1 ROC

This is the completed reconstructed legacy baseline, not a sampling-change comparison or exact Fig. 6a reproduction.

Universe: 272 eligible assayed strict-SIG inference sources x 17,971 frozen NT inference targets, excluding self-pairs.
Fixed totals: 4,887,840 candidate pairs; 1,177,495 reference-positive; 3,710,345 operational reference-negative.

Emitted pairs rank by consensus MI; equal MI stays tied. Every omitted pair has one shared bottom score, below every emitted pair, including emitted MI=0. This is an evaluation policy, not estimated missing MI.
Sensitivity=TP/fixed positives; specificity=TN/fixed negatives. ROC uses whole tied groups and includes the omitted group. AUROC is checked independently by positive-negative pair counting.

| Consensus p | Eligible emitted pairs | TP | FP | Sensitivity | Specificity | Fixed-universe AUROC | Preserved emitted-edge ordinal AUROC |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 0.01 | 23,964 | 10,416 | 13,548 | 0.008846 | 0.996349 | 0.502601 | 0.557081 |
| 0.001 | 19,201 | 8,522 | 10,679 | 0.007237 | 0.997122 | 0.502182 | 0.553911 |

The two AUROC columns differ in population AND tie handling. They are different estimands, not a corrected version of the same metric.
The fixed-universe AUROC measures thresholded-network selection plus ranking. A large unscored/omitted tied group limits resolution; it is not unthresholded all-pair MI AUROC.
Reference positives represent perturbation responses, not proven direct edges; nonmembers are operational negatives, not verified biological negatives.
Top-k is ranked within the eligible-source universe, not the full author-style SIG network. Tied boundaries report expected TP plus its min/max range. Top-k above eligible emitted counts is unavailable, not padded with arbitrary missing pairs.
Do not select labels, source filters or thresholds to match the publication. Preserve this exact universe/reference across any future matched sampling comparison.
