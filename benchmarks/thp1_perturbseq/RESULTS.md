# THP-1 PR70 sampling pilot: 2026-10-11

This pilot **did not demonstrate an overall improvement** from fixed-size
subsampling without replacement. Unthresholded MI ranking improved slightly,
but the post-DPI TP/EPR and reported-edge AUROC declined. Neither arm showed
strong discrimination against this reconstructed perturbation-response
reference. This is not an exact reproduction of scMINER Figure 6a.

## Matched design

Both arms used the same frozen expression matrix, reference, 323 eligible SIG
sources, 2,237 genes, numeric MI cutoff `0.013489523810650165`, `Npar=40`, and
final DPI epsilon=0. Inference used only the 2,415 non-targeting cells.

- Before: pre-PR70 binary, 2,415 draws with replacement (`-r 1`).
- After: PR70-only binary, 1,932 distinct cells (`-u 80%`).
- Seeds: 1, 2, 3; each arm/seed ran unthresholded pre-DPI, thresholded pre-DPI,
  and post-DPI inference directly. All 18 native jobs completed successfully.
- No PR71 calibration, SuperCell aggregation, or consensus step was used.

The cutoff was fixed using the legacy affine formula at m=1,932 and nominal
p=1e-7, then supplied explicitly to both arms. The nominal p is an engineering
anchor, not an estimator-matched calibrated probability. Seeds index paired
operational runs, not identical selected cells or tie-noise streams: the
comparison includes changes in draw count and native tie-noise behavior.

The reconstructed reference uses public GSM6858449 raw counts, documented
pilot QC, exactly single-guide knockdown groups, and mean log2(CPM+1)
differences from non-targeting controls. Reference positives satisfy
`abs(effect) > 0.25`; no FDR filter is applied. Gene selection uses only
non-targeting expression variance, not response labels. There are 387,733
reference positives among 722,228 evaluated nonself pairs (53.69%).

## Results

Entries are independent medians across the three seeds, not pooled networks
or confidence intervals. TP means reference-positive, not proven direct
regulation. Higher TP/EPR/AUROC is better.

| Metric | Before: bootstrap | After: 80% distinct |
|---|---:|---:|
| Post-DPI TP@1,000 | 595 | 565 |
| Post-DPI EPR@1,000, within-emitted expected baseline | 1.0732 | 1.0151 |
| Post-DPI AUROC, reported-edge MI | 0.5326 | 0.5137 |
| Post-DPI AUROC, common-universe MI | 0.5009 | 0.5008 |
| Unthresholded pre-DPI AUROC, common-universe MI | 0.5235 | 0.5259 |
| Unthresholded pre-DPI average precision, common universe | 0.5536 | 0.5547 |
| Threshold-passing pre-DPI edges | 426,704 | 247,133 |
| Post-DPI edges | 17,079 | 15,520 |
| DPI pruning fraction | 0.9596 | 0.9372 |
| Post-DPI precision | 0.5536 | 0.5566 |
| Post-DPI sensitivity, common universe | 0.0244 | 0.0220 |
| Post-DPI specificity, common universe | 0.9771 | 0.9793 |

EPR above is top-k precision divided by the positive fraction in that arm's
entire emitted-edge pool. This analytic expected-random baseline avoids a
noisy single shuffle. The author-style single-shuffle EPR is also retained in
`ranked_curves.json`. Reported-only EPR and AUROC condition on different edge
pools in the two arms; the common-universe metrics use identical candidate
pairs and labels, with absent edges assigned MI=0.

| Post-DPI k | Before TP | After TP | Before EPR, expected within pool | After EPR, expected within pool |
|---:|---:|---:|---:|---:|
| 100 | 50 | 51 | 0.9018 | 0.9263 |
| 1,000 | 595 | 565 | 1.0732 | 1.0151 |
| 5,000 | 2,914 | 2,845 | 1.0527 | 1.0214 |
| 10,000 | 5,739 | 5,616 | 1.0351 | 1.0121 |

## Defensible conclusion and limitations

This operating point does not support claiming improved THP-1 perturbation
response recovery after PR70. The small increase in unthresholded MI AUROC
does not translate into improved post-DPI ranking. Conversely, this pilot
does not establish that PR70 is generally worse: three seeds on one reduced
panel are exploratory, and the reference is reconstructed rather than the
authors' missing prepared inputs.

The high reference-positive prevalence reflects the effect-only definition
and the selected gene panel. It limits direct comparisons with published
EPR values; it is not evidence that half of all pairs are direct regulatory
edges. Knockdown responses can be indirect. Small knockdown groups,
unadjusted group/replicate effects, no SuperCell aggregation, a restricted DPI
hub panel, and no production consensus further limit interpretation. No
cutoffs or labels were tuned to improve these scores.

## Provenance and local artifacts

The runtime snapshots were verified against the user's fork:

- Before: `e59973a1891672a14f06d7847545c53368f3066c`.
- After: PR70-only `8c5f26c4fb5e05c7b280bcaa7d5a6461125a6aa3`; runtime/configuration
  identical to fork develop `1638e8f4eb3d7ffe5057922fa9f9bd1043d466ac`.
- Author-analysis context: `jyyulab/scMINER_analysis` commit
  `c39f0aaffc22be81ae425adf9e7617504ae9ee33`.
- H5AD SHA256:
  `2c124f240f1d660808e81e59aa5742c5310f294f7ff7b45d6f69275fd7d137ea`.

Generated data and networks remain in the ignored local directory
`results/pilot_20261011_frozen/`; they are not included in Git. These links
work in this checkout after the completed run, not in a fresh remote clone:

- [Full generated report](results/pilot_20261011_frozen/REPORT.md)
- [Reported-edge TP/EPR/ROC plots](results/pilot_20261011_frozen/tp_epr_roc_reported.png)
- [Common-universe TP/EPR/ROC plots](results/pilot_20261011_frozen/tp_epr_roc_common.png)
- [Metrics and run provenance](results/pilot_20261011_frozen/metrics.json)
- [Preparation provenance](results/pilot_20261011_frozen/prepare_manifest.json)

See [README.md](README.md) for the complete protocol, metric denominators,
commands, and source links. The scripts record input/binary/config/output
hashes and reject incomplete or altered runs. All 36 synthetic tests passed;
independent raw-count spot checks confirmed normalization, response effects,
labels, and exclusion of knockdown cells from inference.
