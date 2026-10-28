> Publication copy of a frozen local report/process. Scientific text and numbers are unchanged; relative links are adapted to this compact package. See [publication provenance](PUBLICATION.json) for original hashes and [local artifacts](README.md#local-artifacts) for omitted sidecars.

# DREAM5 Stage 1: direct-edge recovery versus DPI tolerance

**Complete:** 30/30 direct inference runs; three matched seeds per setting.
All matched-run integrity checks passed. All 34 lightweight tests passed, and
an independent parser/scikit-learn audit reproduced all 30 scores, 24 paired
comparisons and six weighted graph-nesting families.

[Process](README.md#local-artifacts) | [Prospective protocol](PROCESS.md) |
[Full machine-generated report and plots](REPORT.md) | [Validation](VALIDATION.md)

## Conditional conclusion

Relaxing DPI recovers more reference-positive edges, but also admits many more
reference-negative edges and lowers emitted-edge precision in both datasets.
This pilot does **not** support a uniform accuracy improvement or a new default.

- **Network 1:** epsilon 0.05 has a slightly higher median Average Precision
  than strict DPI, but its paired change is negative in two of three seeds;
  its median paired change is -0.001269. At epsilon 0.10 the paired change is
  also negative in two seeds, and at 0.15 it is negative in all three. Thus the
  slightly higher separate group median at 0.05 is not consistent paired
  evidence of improvement. Strict DPI outperforms the no-DPI baseline in
  Average Precision for all three seeds at this MI cutoff.
- **Network 3:** each tested positive epsilon improves Average Precision
  relative to strict DPI in all three seeds, while precision falls and recall
  rises. The thresholded no-DPI baseline has still higher Average Precision,
  but far lower emitted precision and many more benchmark-defined FPs. The
  incomplete biological reference limits interpretation of those FPs.

The added labeled edges have median incremental precision of only 4.87-6.04%
in Network 1 and 3.25-3.80% in Network 3. This is an explicit precision/coverage
trade-off, not a result that recovers TPs without a substantial FP cost.
The appropriate operating point depends on the intended precision/recall
trade-off; no acceptable FP budget was prespecified here.

These results test fixed epsilon at full TF lists, **not** the BRCA100 dynamic
epsilon(H) schedule, slope 0.05, large-H behavior or biological activity accuracy.

## Matched current-engine design

- Engine develop commit: `b41c4ca637ac2bffe73617a86af65c83e75ee075`.
- Full released genes and TF lists for both source selection and annotation:
  Network 1 has 1,643 genes / 195 TFs; Network 3 has 4,511 genes / 334 TFs.
- Seeds 1, 2, 3, each selecting exactly 644 of 805 profiles without replacement.
  Actual ordered sample-index lists match across modes, not just seed labels.
- Native experimental PCHIP, Npar=40, **p_b=0.001 for both TF networks**.
  Identical native cutoff in all 30 jobs:
  `0.021543205318573955` (`0x1.60f6c092d59f0p-6`). It also equals the frozen
  Python callable here. This is a provisional label-independent operating point,
  not a DREAM-optimized cutoff or biological FDR guarantee; m=644 is interpolated.
- Five settings: thresholded no-DPI (`-e 1`), epsilon 0, 0.05, 0.10 and 0.15.
  Every setting runs directly from expression. No rounded-adjacency replay,
  consensus, 100-resample extension, hub-size changes or engine changes.

This is a new current-engine/PCHIP comparison, **not** a rerun of the old PR70
affine benchmark. Historical and new numerical results must not be mixed to
attribute effects solely to DPI.

## Absolute metrics

Each cell is the median of three per-seed values, not a pooled network.
Counts and rates are summarized separately, so ratios of displayed counts need
not equal displayed median rates. All FPs below mean explicitly negative labels;
unlabelled pairs are excluded, not counted as FPs.

| Network | DPI setting | TP | FP | Precision | Recall | Average Precision | AUROC |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | No DPI | 2,448 | 56,018 | 4.19% | 61.02% | 0.18268 | 0.73951 |
| 1 | epsilon 0 | 1,263 | 6,207 | 16.91% | 31.48% | 0.20741 | 0.64863 |
| 1 | epsilon 0.05 | 1,347 | 7,519 | 15.19% | 33.57% | 0.20914 | 0.65744 |
| 1 | epsilon 0.10 | 1,430 | 9,081 | 13.59% | 35.64% | 0.20609 | 0.66612 |
| 1 | epsilon 0.15 | 1,512 | 10,933 | 12.16% | 37.69% | 0.19999 | 0.67356 |
| 3 | No DPI | 1,667 | 101,608 | 1.61% | 80.69% | 0.07342 | 0.64054 |
| 3 | epsilon 0 | 200 | 2,134 | 8.79% | 9.68% | 0.04578 | 0.54157 |
| 3 | epsilon 0.05 | 236 | 2,967 | 7.37% | 11.42% | 0.04784 | 0.54768 |
| 3 | epsilon 0.10 | 276 | 4,098 | 6.31% | 13.36% | 0.05160 | 0.55388 |
| 3 | epsilon 0.15 | 331 | 5,673 | 5.50% | 16.02% | 0.05505 | 0.56247 |

**Average Precision** summarizes precision along the MI ranking, weighted by
increments in recall, using complete tied-score groups. Here retained labeled
pairs keep their MI and omitted labeled pairs share a bottom score of zero.
It is not emitted-edge precision, accuracy or a trapezoidal PR area. AUROC is
also computed on that same fixed labeled universe, giving half credit to ties.
These local definitions are not the official DREAM5 leaderboard score.

No-DPI is still MI-thresholded. None of these columns is an unthresholded raw-MI
ranking; underlying MI estimation is held fixed across epsilon modes.

![Metric trajectories](metric_trajectories.svg)

## Recovery cost relative to strict DPI

Differences are calculated **within seed first**, then their medians are taken.
They need not equal subtraction of the separate group medians above. Incremental
precision is TP_added/(TP_added+FP_added) on the newly retained labeled edges;
unlabelled additions are reported separately in the per-seed tables.

| Network | Epsilon | Additional TP | Additional FP | Incremental precision | Paired Average Precision change | Seeds with positive Average Precision change |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0.05 | +85 | +1,312 | 6.04% | -0.001269 | 1/3 |
| 1 | 0.10 | +170 | +2,900 | 5.48% | -0.002056 | 1/3 |
| 1 | 0.15 | +245 | +4,756 | 4.87% | -0.005928 | 0/3 |
| 3 | 0.05 | +32 | +833 | 3.80% | +0.002814 | 3/3 |
| 3 | 0.10 | +75 | +1,964 | 3.66% | +0.006574 | 3/3 |
| 3 | 0.15 | +118 | +3,511 | 3.25% | +0.009137 | 3/3 |

![Paired recovery cost](paired_tp_fp_tradeoff.svg)

## Reference and interpretation limits

- Network 1 scoring uses the supplied 278,392 explicitly labeled directed pairs
  (4,012 positives); it is known simulated-network recovery, not human biology.
- Network 3 scoring uses 152,280 explicitly labeled directed pairs (2,066
  positives). Its real-expression, strong-evidence biological reference is
  incomplete. An operational zero label is not proof that an interaction is
  biologically absent; therefore extra benchmark FPs cannot all be called
  biologically incorrect. All other inference pairs remain unlabelled.
- Three computational seeds are not independent biological datasets. No
  significance claim, precise uncertainty interval or independent validation of
  a retrospectively selected epsilon is made.
- One provisional MI cutoff is tested. Results can depend on that cutoff,
  network topology, sample selection and reference coverage. There is no
  universal epsilon recommendation or hub-size scaling calibration here.
- Native outputs expose six-significant-digit retained MI. Exact serialized
  token identity, complete traversal and sample/cutoff matching are verified;
  this is not a direct full-precision pre-DPI MI fingerprint in every job.

The next decision is which precision/recall trade-off is useful, not automatic
promotion of a new DPI default. No Stage 2 jobs have been run.

## Files

- [Full report](REPORT.md), [per-seed metrics](runs_per_seed.tsv),
  [metric medians/ranges](runs_summary.tsv), [paired per-seed changes](comparisons_per_seed.tsv),
  [paired summaries](comparisons_summary.tsv), [full analysis](README.md#local-artifacts).
- [Frozen design](README.md#local-artifacts), [build manifest](README.md#local-artifacts),
  [30-job completion](README.md#local-artifacts), [smoke gate](README.md#local-artifacts),
  [independent audit](README.md#local-artifacts).
- Raw source archive/build, prepared inputs, native graphs and logs remain in
  `/home/adam/sjaracne-benchmarks/dream5-dpi-epsilon-stage1-20261025-r2`.
  They were not added to Git or uploaded.
