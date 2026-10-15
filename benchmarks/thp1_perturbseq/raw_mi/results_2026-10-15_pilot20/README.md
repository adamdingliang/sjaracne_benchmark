# THP-1 raw-MI pilot results — 20 matched resamples

Fixed-size sampling without replacement improved raw-MI ranking on this
frozen THP-1 response reference. This is an encouraging exploratory result,
not proof of biological or end-to-end SJARACNe improvement.

The protocol and randomly selected seed IDs were committed before pilot
scoring in `8ddd07a`. The primary endpoint was TP@5,000. Both arms use the
same 121 NT-cell metacells, 17,971 genes and reconstructed response reference:
the before protocol draws 121 observations with replacement, whereas the
after protocol selects 97 distinct observations (80%). Thus the contrast
includes sample count and RNG consumption, not replacement alone at equal m.

## Main readout

Values are medians across the 20 resamples. Fractional counts arise from
expected ordering within exact serialized-MI ties, not fractional edges.

| Metric | Before | After |
| --- | ---: | ---: |
| TP@5,000 | 2,535.00 | 2,624.50 |
| FP@5,000 | 2,465.00 | 2,375.50 |
| Precision@5,000 | 50.70% | 52.49% |
| EPR@5,000 | 2.1046 | 2.1789 |
| Full-ranking AUROC | 0.625604 | 0.665975 |

TP@5,000 increased in **18/20 pairs**. Two decreased: seed 6, by 40 TP;
seed 79, by 64 TP. The median paired TP change was **+112.33**, with an
interquartile range of +79.75 to +133.25. This is not the same statistic as
subtracting the two marginal medians. At fixed k, FP changes by the opposite
amount; precision and EPR are related views of the same counts.

AUROC increased in **20/20 pairs**; the median paired change was +0.037765.
This AUROC covers all 4,887,840 fixed eligible non-self pairs, unlike the
previous emitted-edge AUROC and the paper's reported-network evaluation.
Those absolute AUROC values should not be compared as the same metric.

See the [full report](REPORT.md), [plot](raw_mi_comparison.png),
[paired per-seed metrics](paired_seed_metrics.tsv) and
[machine-readable summary](summary.json).

## Scope and limits

- No MI significance filtering, DPI or consensus was applied. Scores were
  ranked independently within each resample, not averaged into one network.
- Only the 272 eligible source rows were computed, retaining all genes and
  the full original SIG annotation. Pairwise independence was checked in code
  and with subset/expanded/reordered-list engineering tests before the pilot.
  This is not a full-6,951-source empirical run or a shortcut usable with DPI.
- The fixed universe contains 1,177,495 response-positive pairs and 3,710,345
  operational negatives. Perturbation responses can be indirect; a negative
  label is not proof of biological non-regulation.
- Twenty overlapping computational resamples are not 20 biological
  replicates. IQRs describe resampling variation, not biological confidence
  intervals. No significance or cross-dataset claim follows from this pilot.
- Earlier mixed/unfavorable post-DPI/consensus results remain unchanged.
  This raw-MI result does not supersede them. No extension to 100 resamples
  or threshold tuning was selected after observing these scores.

## Provenance and validation

The compact package preserves these files byte-for-byte from the local run:

- [Frozen plan](provenance/plan.json), including seed selection, input/binary
  hashes, commands and runner/scorer hashes.
- [Fixed universe](provenance/universe.json).
- [Engineering smoke proof](provenance/engineering_smoke_proof.json).
- [Final completion manifest](provenance/run_manifest.json): 40/40 complete,
  no failed jobs.
- [Report provenance](provenance/report_provenance.json).
- [Independent audit](provenance/independent_audit.json).

All 37 new synthetic tests passed. The independent audit reconstructed the
reference labels, verified 240 artifact hashes/sizes and checked primary-k
TP/FP and derived metrics for all 40 jobs with exact agreement. Independent
scikit-learn AUROC checks for seeds 2 and 89 in both arms agreed within
1.11e-16. The engineering smoke passed 24 native commands and 16 exact
comparisons before the pilot.

All scientific jobs completed successfully. A Windows access error interrupted
the coordinator's status-file replacement after it had recorded 38 results;
the other two jobs had also finished. A verification-only resume checked all
40 completed outputs and rebuilt the final status without rerunning native
inference. The audit records this incident; it is not a scientific job failure.

Large raw adjacencies, dense arrays, full per-job metric grids and logs stay
local under `D:/GitHub/sjaracne_benchmark/runs/thp1_raw_mi_20261015/`.
Copied provenance intentionally retains the original absolute paths and
hashes; it is an execution record, not a portable self-contained rerun bundle.
The code and frozen protocol live in the [parent folder](../README.md).
