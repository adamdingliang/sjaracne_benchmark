# Historical versus refined workflows: consensus K20

[Results](RESULTS.md) · [Concise summary](../../docs/benchmark_summaries/legacy_refined_k20.md) · [Original NetBID2 figures](NETBID2_FIGURES.md) · [Validation](VALIDATION.md)

## Objective

Compare the genuine pre-sampling-change SJARACNe workflow with the refined
workflow, then assess minimum recurrence **K=20 out of B=100 resampled
networks** as a practical default. Evaluate reference-edge recovery on two
DREAM5 networks and target coverage/topology on three bulk-expression datasets.

K20 was chosen after reviewing the complete DREAM5 recurrence trajectories,
with target coverage considered alongside precision and recall. It was not
selected as the highest-F1 setting or established on an independent test set.
This package records the decision and its limitations; it does not change an
SJARACNe implementation, CLI default or workflow engine.

## Data and matched design

| Dataset | Observations N | New observations per resample m | Expression rows | TF hubs | SIG hubs | Evaluation reference |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| DREAM5 Network 1 | 805 | 644 | 1,643 | 195 | Not run | Supplied simulated directed-edge labels |
| DREAM5 Network 3 | 805 | 644 | 4,511 | 334 | Not run | Supplied E. coli labels; incomplete biological reference |
| BRCA100 | 100 | 80 | 28,278 | 2,608 | 10,680 | No independent edge reference; NetBID2 QC only |
| TCGA-LUAD | 517 | 414 | 29,841 | 1,929 | 9,464 | No independent edge reference; NetBID2 QC only |
| TCGA-BLCA | 406 | 325 | 29,778 | 1,920 | 9,428 | No independent edge reference; NetBID2 QC only |

Use the same prepared expression and full source/annotation lists within each
legacy/new comparison. TF and SIG are reconstructed separately. BRCA expression
rows are probe IDs, whereas the prepared TCGA rows are gene IDs; these are not
identical biological units. TCGA inputs use log2(TPM+1) followed by the documented
IQR filter. There is no additional filtering during this comparison.

| Setting | Historical legacy | Refined/new |
| --- | --- | --- |
| Canonical inference source | `e59973a1891672a14f06d7847545c53368f3066c` | `4ef87a01698394dd020aa6e2c0b66c6cab230ec2` |
| Observation sampling | N draws with replacement | 80% without replacement, with actual m recorded above |
| Resamples | Seeds 1-100, B=100 | Seeds 1-100, B=100 |
| AP-MI parameter Npar | 40 | 40 |
| Per-resample cutoff | Affine conversion, p_b=1e-7 | PCHIP; TF p_b=0.001, SIG p_b=0.0005 |
| DPI | Strict, epsilon=0 | Dynamic rule below |
| Primary final consensus | Original approximate probability, p_c=1e-5 | Minimum recurrence K=20 |
| Secondary consensus control | K=20 on saved legacy resamples | The same K=20 on saved refined resamples |

The legacy comparison uses the historical executable, **not** the modern
`--profile legacy` settings profile. Reused BRCA legacy jobs actually ran
`12113fbc80d753d945598ffc2c7d9e45787bc8e0`; its complete scientific source tree
matches canonical `e59973a`. Actual source commits and binary hashes are retained,
not relabeled as new executions.

The frozen refined engine was reused for consistency. Its native estimator/DPI
and consensus sources are unchanged in the later preparation pin `20b7dd0`;
[source-equivalence evidence](evidence/scientific_source_equivalence.json) records
the exact Git identities. These results do not validate a later WDL/Sprocket
runner or every subsequent source revision.

## MI and DPI settings

Legacy MI cutoff uses `(1.062 - log(p_b)) / (48.7 + 0.634*N)`, with natural log.
The new cutoff is
the bundled empirical PCHIP function evaluated at the **actual selected m**
and the requested p_b. It does not use a GPD fit or a nearby sample-size model.

For the new workflow:

```text
epsilon(H) = min(0.30, 0.05 * max(0, log2(H / 479)))
```

H is the matched full source/annotation-list size. Larger epsilon relaxes DPI.
The DREAM5 lists have fewer than 479 hubs, so both workflows use epsilon=0:
**these DREAM5 comparisons do not test positive dynamic DPI tolerance**.

| Dataset | New TF MI cutoff | New SIG MI cutoff | New TF epsilon | New SIG epsilon |
| --- | ---: | ---: | ---: | ---: |
| DREAM5 Network 1 | 0.0215432053 | Not run | 0 | Not run |
| DREAM5 Network 3 | 0.0215432053 | Not run | 0 | Not run |
| BRCA100 | 0.1478309303 | 0.1644522244 | 0.1222423154 | 0.2239371090 |
| LUAD517 | 0.0325759151 | 0.0371368538 | 0.1004877791 | 0.2152176256 |
| BLCA406 | 0.0411588482 | 0.0467800900 | 0.1001504375 | 0.2149427099 |

Values above are rounded for display; the frozen manifests retain full values.
The independent-rank null calibration is experimental, particularly for tied or
zero-rich RNA-seq. Interpolation at off-grid m is not direct validation at that m.

## Consensus and scoring

Count each ordered source-target pair at most once per post-DPI resample. Retain
it when support is **at least K**; reverse directions remain separate. K20 means
20 of 100 networks here, not a p-value or a biological FDR guarantee. Resamples
overlap and are dependent. A different B needs an explicit operating-point choice;
the evidence does not validate fixed K20 at arbitrary resample counts.

The full DREAM sweep evaluates every integer K=1-100 on four saved support
ledgers. No MI estimation or DPI is repeated. The historical primary consensus
corresponds to K16 for Network 1 and K15 for Network 3; equal historical p_c does
not imply equal recurrence across datasets. The original BRCA/LUAD legacy
boundaries are K9 for TF and K8 for SIG.

DREAM scoring uses only explicitly labeled directed pairs: Network 1 has
278,392 eligible pairs and 4,012 positives; Network 3 has 152,280 pairs and
2,066 positives. Unlabeled predictions are reported separately, never counted
as FP. Omitted reference positives remain FN.

```text
precision = TP / (TP + FP)
recall    = TP / all fixed reference positives
F1        = 2*TP / (2*TP + FP + FN)
```

These are local labeled-edge metrics, not official DREAM challenge scores.
Reference-negative predictions in Network 3 are not proven biologically false.

For bulk datasets, report edge count, active-hub fraction, median targets across
**all candidate hubs including zeros**, and NetBID2 adjusted scale-free R2.
Active-only medians are separate in the evidence. Target-size QC figures use
active hubs only. Scale-free QC fits a smoothed **total-degree distribution of
incident nodes**, not TF out-degree specifically; it is not an accuracy metric.

## Reuse, new work and validation

The earlier 100-resample DREAM5, BRCA100 and LUAD517 outputs are reused, not rerun
for this PR. K20 bulk follow-up reselects edges from the saved post-DPI networks and
checks every selected pair and rounded mean MI before projecting existing
annotations. NetBID2 QC is rerun. The later BLCA extension adds all four new
100-resample workflows, fresh final-network annotations and fresh QC.

The matched-K20 control covers DREAM5, BRCA100 and LUAD517. There is no BLCA
legacy-K20 control and no BLCA new-K6 baseline; neither is inferred or fabricated.
The original run manifest still records its initial K6 outputs. Later selection
and published metrics are separate evidence, not edits to that historical plan.

The completed-run records validate native signatures/hashes, consensus metadata,
QC summaries, and extracted PNG hashes. NetBID2 v2.2.0 (source `5defa45`), R 4.4.3
and igraph 2.3.3 were used. Original QC PNG payloads are copied without pixel
changes; source artifacts remain untouched. Packaging checks are not a new
independent validation of biological accuracy.

## Compact package and reproduction

The [package manifest](evidence/package_manifest.json) records file identities,
sizes and SHA256 hashes. [Overall metrics](evidence/overall_metrics.tsv),
[assembled provenance](evidence/report_data.json), [all 400 K-sweep rows](evidence/dream5_k_sweep.tsv)
and original QC PNGs are committed. Raw expression, patient-level metadata,
edge files, binaries, environments and large QC HTMLs remain local.

Validate this package without data downloads, R or SJARACNe:

```bash
python benchmarks/legacy_vs_refined_k20/package_evidence.py validate
python -m unittest discover -s benchmarks/legacy_vs_refined_k20 -p 'test_*.py'
```

The packager's `import` command reads the completed local overall/sweep/BLCA
archives; see `python benchmarks/legacy_vs_refined_k20/package_evidence.py --help`.
It verifies frozen publication hashes and refuses differing overwrites. Overview
plots require matplotlib; the committed tables and validation use the standard
library. Full inference reproduction additionally requires the pinned external
engine and original datasets. The package does not make historical absolute
paths portable or claim to bundle a complete inference environment.
