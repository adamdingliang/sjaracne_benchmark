# DREAM5 Network 3: sampling and DPI benchmark results

The [prospectively specified three-seed pilot](PLAN_2026-10-15.md) is complete:
four sampling configurations, five direct native stages per configuration/seed, **60 jobs**, no
PR71 calibration or consensus. The same pinned PR70 executable retains the
legacy with-replacement baseline. All 334 supplied TFs and 4,511 genes were
used for inference/DPI; only the supplied explicit labels are scored.

See the [full report and plots](results_2026-10-15_pilot3/REPORT.md),
[per-seed metrics](results_2026-10-15_pilot3/per_seed_stage_metrics.tsv), and
[compact provenance manifest](results_2026-10-15_pilot3/package_manifest.json).
These are local, explicitly defined Average Precision and AUROC metrics, not
official DREAM5 leaderboard scores.

## What Average Precision measures

**Average Precision** summarizes how well the MI-ranked edge list places
reference-positive pairs near the top. Sort the explicitly labeled pairs by
decreasing MI, then calculate precision and recall as the score threshold is
lowered. Average Precision weights each threshold's precision by the increase
in recall at that threshold:

$$
\mathrm{Average\ Precision}=\sum_j (R_j-R_{j-1})\,P_j
$$

Here `P_j` is precision at threshold `j`, `R_j` is recall at that threshold,
and the starting recall is zero. Equal-MI pairs enter together as one group;
larger increases in recovered reference positives receive more weight. Higher
is better, with 1 representing a perfect ranking. This is a stepwise summary,
not trapezoidal integration of the precision-recall curve.

The **Precision** column evaluates only emitted labeled edges at the selected
filtering/DPI stage. **Average Precision** instead evaluates ranking over all
152,280 explicitly labeled pairs, including all 2,066 reference positives;
omitted post-DPI pairs share a bottom score of zero. It is calculated separately
for each sampling configuration and seed, then summarized by the median. It is
not accuracy: a value of 0.0458 does not mean 4.58% of predictions are correct.

## Main result: nominal p=1e-7, after DPI

Each entry is the median of three per-seed statistics. Counts and rates are
summarized independently; they need not add up to, or equal ratios of, other
table medians. FP means an **explicit reference-negative**, not a proven
biologically false edge. Unlabeled predictions are excluded.

| Sampling | TP | FP | Precision | Sensitivity | Specificity | AUROC | Average Precision |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Legacy, 805 replacement draws | 206 | 3,242 | 5.97% | 9.97% | 97.84% | 0.539562 | 0.042117 |
| 64%, 516 distinct profiles | 217 | 2,233 | 8.75% | 10.50% | 98.51% | 0.545407 | 0.047296 |
| 80%, 644 distinct profiles | 200 | 2,134 | 8.79% | 9.68% | 98.58% | 0.541570 | 0.045776 |
| 90%, 725 distinct profiles | 203 | 2,064 | 8.87% | 9.83% | 98.63% | 0.542443 | 0.045498 |

The declared primary comparison, **80% versus legacy post-DPI Average Precision**,
increased in all three seeds: paired differences +0.003659, +0.004731 and +0.002568
(median +0.003659). Median labeled FP count decreased by about 34%, while
median TP count decreased from 206 to 200. Paired TP changes were **-7, +8,
-5**, not uniformly positive. This is a precision/coverage tradeoff, not the
unqualified precision-and-recall improvement seen in the Network 1 pilot.

## Raw MI and stage controls

| Sampling | Raw-MI AUROC | Raw-MI Average Precision | Raw TP@5,000 |
| --- | ---: | ---: | ---: |
| Legacy | 0.640041 | 0.066079 | 311 |
| 64% | 0.638397 | 0.075918 | 329 |
| 80% | 0.640926 | 0.073642 | 327 |
| 90% | 0.645688 | 0.075440 | 330 |

Raw-MI Average Precision improved in the configuration medians, but overall
AUROC did not uniformly improve: the 80% change is very small and 64% is slightly
lower. Top-ranked recovery improved more visibly than the global ranking statistic. All eight
fixed budgets, with boundary-tie handling, are saved in
[metrics.json](results_2026-10-15_pilot3/metrics.json).

The fixed numerical MI control, **0.03759353615996272**, was declared before
E. coli scoring. Its post-DPI **labeled edge sets and MI weights are identical**
to the nominal-cutoff results in all 12 configuration/seed groups, not just equal in
median counts. Small differences in the full networks involve only unlabeled
pairs. It does not isolate sample-count or RNG differences.

**DPI removes substantial reference-positive coverage.** Median fractions of
pre-DPI TPs pruned were 88.97%, 83.05%, 86.12% and 87.07% for legacy/64/80/90%.
Only about 10% of all reference-positive pairs remain in the final networks.
The [full report](results_2026-10-15_pilot3/REPORT.md#dpi-pruning-diagnostics)
shows global/labeled/TP/FP pruning and TP retention, rather than reporting
precision gains alone. This is a diagnostic of this fixed workflow, not a
reference-based tuning or a verdict on individual removed edges.

## Defensible conclusion and scope

This E. coli pilot supports fewer labeled FPs and higher post-DPI Average
Precision and emitted-edge precision with fixed-size sampling, but **does not
demonstrate uniformly improved recall, raw AUROC or full-workflow performance**.
Three computational seeds
cannot establish a best fraction, statistical significance or a new default.
The reference is incomplete; expression profiles span heterogeneous and
potentially correlated experiments; sampling changes draw count, selected
profiles and RNG consumption as well as replacement. No cutoff/DPI tuning,
consensus test or automatic extension to more seeds was performed.

The [validation record](VALIDATION_2026-10-15.md) documents the smoke gate,
54 Network 3 tests and independent all-stage numerical recalculation.

## Dataset-readiness evidence

The cached source archive matches the published MD5, and the bundled source
files are byte-identical to the selected ZIP members. Independent source
inspection established these dimensions and counts:

| Quantity | Count |
| --- | ---: |
| Expression profiles | 805 |
| Released genes | 4,511 |
| Supplied candidate TFs | 334 |
| Explicitly labeled directed non-self pairs | 152,280 |
| Reference-positive pairs | 2,066 |
| Operational reference-negative pairs | 150,214 |
| Sources in the labeled reference | 141 |
| Target nodes in the labeled reference | 1,081 |
| Other candidate-TF-to-gene pairs, **unlabeled** | 1,354,060 |

All 3,631,355 expression entries are finite. Gene and TF IDs are unique;
all TFs and all reference endpoints occur in expression. Reference pairs are
unique, binary-labeled and non-self. The supplied reference agrees with the
official archive's positive-edge-only file and its scoring-universe rules.

The preparation workflow preserves all genes, profiles and TFs and transposes
original numeric strings without normalization or precision changes. Generated
inputs stay under ignored `runs/`; they are not native-network predictions.

## Checks performed on 2026-10-15

- All nine Network 3 checks passed (eight synthetic tests and one bundled
  source-manifest integrity test). The existing six Network 1 checks also passed.
- Bundled-input verification and a real-data preparation run completed
  successfully. The compact execution record is preserved as
  [preparation_check_2026-10-15.json](preparation_check_2026-10-15.json).
- The prepared `.exp` has SHA256
  `a8ea101efa68ae9f047ad5ae4d625e5ddb3b8d03eb6757407c332c46397409f9`;
  the generated 334-TF hub file is byte-identical to the original TF list.
- An independent read-only comparison checked all 3,631,355 generated numeric
  tokens, every gene/profile position and the input header against the original
  transpose, with exact agreement. All seven bundled source/README files also
  matched their exact archive members and manifest hashes/sizes.
- The historical scientific migration and engine-archive integrity checks
  passed. No Network 1, THP-1 or SJARACNe engine files were changed.

The execution record retains its original local paths. Large generated inputs
remain in `runs/dream5_network3_prepared_20261015/`, not in this Git package.

For process, commands and caveats see [README.md](README.md). Source identities
and checksums are in [data/provenance.json](data/provenance.json).
Dataset readiness alone is not evidence of a sampling improvement; the
completed comparison and its limitations are reported separately above.
