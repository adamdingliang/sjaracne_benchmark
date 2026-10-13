# THP-1 author-style reconstruction and matched sampling evidence

The metacell and response-reference preparation, all 100 legacy bootstraps,
both original consensuses, and TP/EPR/AUROC scoring are complete. The durable
coordinator finished at 12:03 EDT on 2026-10-12.
**This reconstruction does not reproduce Fig. 6a's numerical performance.**
The preserved full-emitted author-style baseline AUROC is 0.573906 versus
the paper's rounded 0.75; EPR@5,000 is 1.10101 versus the published 18.
These are historical all-source scores, not the current eligible-source
primary scores. The numerical-agreement gate was not satisfied. On
2026-10-12 the user explicitly authorized proceeding with the unchanged
reconstructed reference rather than claiming publication reproduction.
The sampling-only after arm, both consensuses and subsequent scoring are now
complete. No scientific runs were performed as part of repository migration.

## Latest matched comparison

The [completed consensus comparison](evidence/author_reconstruction_20261011/sampling_comparison_20261013/REPORT.md)
uses eligible-source emitted predictions as the primary population.
Both arms retain full SIG inference/DPI hubs, the same metacells and response
reference, and the original probability-based consensus. The after arm
applies only PR70's native sampling changes to the same paper-era baseline;
PR71 and minimum-recurrence consensus are excluded.

The result is a precision-coverage tradeoff, not an overall improvement:
eligible-source precision increases 1.33 percentage points at p_c=0.01
and 0.71 points at p_c=0.001, but response-positive counts fall from
17,727 to 10,416 and from 11,647 to 8,522 respectively. Conditional
emitted-pool AUROC decreases; EPR also decreases at the reported top-k
operating points despite slightly higher TP@5,000.

The [saved post-DPI bootstrap diagnostic](evidence/author_reconstruction_20261011/bootstrap_tp_fp_20261013/REPORT.md)
scores all 100 runs per arm without new inference. Median per-run precision
increases from 27.78% to 37.35% (+9.57 percentage points), while median TP
falls 50.50% and FP falls 68.34%. Every after bootstrap has fewer TPs than
every before bootstrap, so consensus is not the sole origin of TP loss.
These medians describe separate graphs, not unique consensus-edge counts.

Sample count, sampling/tie-noise RNG consumption and affine MI cutoff
change together: 121 replacement draws / MI 0.136987 versus 97 distinct
metacells / MI 0.155902 at nominal p_b=1e-7. Saved networks are post-DPI only;
this evidence cannot separate sampling, MI filtering and DPI contributions.
MI-cutoff tuning and a new pre-DPI benchmark remain deferred.

The execution history and legacy-versus-publication tables below are
retained to explain the reconstruction. They do not describe the after arm.

The original background coordinator was launched on 2026-10-11 at 20:29 EDT
with eight workers. The full-panel one-bootstrap smoke passed in 1,443.9
seconds (MI 1,267 seconds, DPI 172 seconds). The 100-bootstrap batch started
at 20:40 EDT and was interrupted after 72 completed bootstraps; the original
Windows coordinator/child and Linux workers were absent. A WSL runtime
restart was observed, but the interruption's cause was not established.

Recovery was launched as a detached hidden Windows process on 2026-10-12
at 09:06 EDT. All 72 completed bootstrap adjacency/log hashes, original stage
code, input/component bindings and scoring inputs passed verification.
Only seeds 73--100 were queued; eight active WSL workers for seeds 73--80
were verified, using new second-attempt directories and unchanged parameters.
The old driver status, interrupted manifest and stale runner lock are
preserved in `driver_resume_20261012/`; the original logs remain untouched.
`driver_resume_20261012/status.json` is now the coordination status authority.
The recovery subsequently completed the remaining work with unchanged inputs
and parameters; the status and hashed artifacts record that completion.
The earlier three-seed individual-cell pilot in [RESULTS.md](RESULTS.md) is
not the published-workflow baseline.

## Reconstructed inputs

| Component | Reconstructed value |
|---|---:|
| Original conventional-KD cells | 66,283 |
| QC-retained cells | 60,526 |
| Pure NT cells used for inference | 2,424 |
| NT SuperCell metacells, gamma 20 / 10 PCs | 121 |
| Detection-passing genes | 18,017 |
| Nonzero-NT inference genes | 17,971 |
| Full `isSIG` inference/DPI hubs | 6,951 |
| Eligible strict `funcType == 'SIG'` reference sources | 272 |
| Response-positive pairs, strict absolute effect > 0.25 | 1,177,736 |

Inference uses only NT metacells. Perturbed cells supply the separate
`scran::findMarkers` response reference. Metacells average supplied
log2(CPM+1) values, not raw counts followed by a new normalization. The full
inferred SIG prediction pool is retained for the author-style metrics;
it is not restricted to the eligible perturbation sources.

The full inference list contains 6,525 strict SIG genes and 426 combined
TF/SIG genes. The reference's 272 qualifying strict-SIG sources are a subset
of that list. Its 1,177,736 positive pairs span all reference targets; that
count is not directly comparable with the number of TPs recovered among
ranked network predictions. Predictions outside the reference are treated
as nonmembers for the author's metrics, not as experimentally verified
biological negatives.

The independent audit passed raw-count metacell averaging, pure-NT
membership, pinned annotation/hub selection, three sampled source-effect
vectors and all positive-target membership for those sampled sources. Raw
library sizes and detected-feature counts agreed exactly with metadata
throughout the preparation scan. This is technical validation, not proof
that response-positive pairs are direct regulatory edges.

## Legacy baseline and comparison

The native baseline is the unmodified SJARACNe 0.2.1 release at
`2922ec9a57d3da4e88b849b840643f543f49807c`, inferred as a paper-era proxy from
the public example. It is **not** a verified original THP-1 binary snapshot.
Parameters are legacy `-r 1`, `Npar=40`, DPI epsilon 0 and wrapper-default
bootstrap p=1e-7. At 121 metacells the native affine MI cutoff is approximately
0.136987. The exact author THP-1 bootstrap invocation is unavailable.

The full workflow uses 100 seeds (1--100) and the original probability-based
consensus script. Consensus p=0.01 is primary, following the paper Methods;
p=0.001 is a separately labeled secondary interpretation of an author
analysis-folder label; the label alone does not establish which parameter
it represents. Both use the **same** 100 post-DPI adjacencies. Neither
cutoff is selected by matching the published metrics. PR70, PR71 and the
minimum-recurrence rule are not applied here.

The comparison uses the authors' active R definitions: MI-descending order,
unique ordinal ranks for ROC even at tied MI, a seed-1 R shuffle of the same
prediction list, TP/EPR every 1,000 edges, and strict response-positive
membership. The published source workbook provides complete TP/EPR series
but only a partial ROC segment (FPR 0.80012--1.0). Its published TP@10,000 is
80 and EPR@10,000 is 8. The paper's rounded AUROC of about 0.75 cannot be
recalculated from that incomplete workbook segment.

## Completed scoring and numerical agreement

| Metric | Published Fig. 6a | Primary p_c=0.01 | Secondary p_c=0.001 |
| --- | ---: | ---: | ---: |
| AUROC | approximately 0.75 | 0.573906 | 0.554708 |
| R-shuffled AUROC | Full curve unavailable | 0.497796 | 0.499643 |
| Emitted network edges | Exact pool not recovered | 916,917 | 561,830 |
| Reference-positive emitted edges | Exact total not recovered | 17,727 | 11,647 |

| Top k | Published TP | Published EPR | Primary TP | Primary EPR | Secondary TP | Secondary EPR |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000 | 1 | 1 | 27 | 1.50000 | 28 | 1.75000 |
| 5,000 | 54 | 18 | 109 | 1.10101 | 108 | 1.18681 |
| 10,000 | 80 | 8 | 194 | 1.07778 | 205 | 1.00985 |
| 50,000 | 190 | 3.22034 | 960 | 1.03004 | 1,027 | 0.986551 |
| 100,000 | 303 | 2.68142 | 2,090 | 1.11170 | 2,198 | 1.05521 |

Higher reconstructed TP counts are **not evidence of outperforming the
published network**: the reference and emitted edge pool have not been
recovered exactly. For example, the primary reconstructed shuffle has 99
positives in its first 5,000 edges, whereas the workbook's random comparator
has 3. EPR therefore exposes a major difference in background membership and
early enrichment despite the larger reconstructed TP count.

The primary AUROC is approximately 0.176 below the paper's rounded value,
and its early EPR is mostly near 1, unlike the published enrichment. Neither
declared consensus alternative resolves this mismatch. This is not a finding
about PR70: both networks still use legacy sampling with replacement.
Unknown author inputs and settings remain possible contributors; their
individual contribution has not been established. Do not tune cutoffs or
response labels to force agreement.

A read-only independent scoring audit checked 41 recorded input/output
hashes, recomputed TP at every saved 1,000-edge cutoff from the ranked pairs
and frozen response reference, and recomputed both ordinal-rank AUROCs.
All checks agreed; full saved method/random ROC integration also agreed to
within 2.2e-13. No scoring arithmetic or artifact-integrity defect was found.
This audit did not rehash all 100 large native adjacencies again or recover
the missing author inputs. Approximately 95.4% of primary emitted edges have
sources outside the 272 eligible perturbations and are reference nonmembers
under the preserved full-pool scoring rule, not experimentally established
negative interactions. Numerous serialized MI ties also make the preserved
ordinal ordering relevant to top-k scores and AUROC.

The full historical publication comparison and its plots remain in the
unchanged external archive at
`D:\GitHub\SJARACNe\benchmarks\thp1_perturbseq\results\author_reconstruction_20261011\comparison`.
The current imported [sampling comparison report and plots](evidence/author_reconstruction_20261011/sampling_comparison_20261013/REPORT.md)
are browsable in this repository; importing evidence does not rerun it.

## Current artifacts and completion gate

The reconstruction code and commands are in
[author_reconstruction/README.md](author_reconstruction/README.md).
Full generated artifacts remain external to this benchmark repository under
`D:\GitHub\SJARACNe\benchmarks\thp1_perturbseq\results\author_reconstruction_20261011\`:

- Completed preparation provenance: `prepared/prepare_manifest.json`
- Independent audit: `independent_audit.json`
- One-bootstrap native smoke: `legacy_smoke/run_manifest.json`
- Recovered background coordination: `driver_resume_20261012/status.json`
- Original interrupted coordinator evidence: `driver/status.json`
- Full 100-run baseline: `legacy/run_manifest.json`
- Completed comparison: `comparison/REPORT.md` and `comparison/summary.json`
- Full 100-run sampling-only after arm: `sampling_after_80pct_20261012/run_manifest.json`
- After-arm scoring: `sampling_scoring_20261013/scoring_manifest.json`
- Matched before/after comparison: `sampling_comparison_20261013/REPORT.md`
- Individual-bootstrap TP/FP diagnostic: `bootstrap_tp_fp_20261013/REPORT.md`

Selected compact summaries and figures were copied into
`evidence/author_reconstruction_20261011/`. The raw H5AD/workbook, full prepared
expression/reference matrices, native networks/builds and R environment
remain outside this repository. Engine/source dependencies and historical
provenance paths are external, not silently retargeted to the new checkout.
See [migration compatibility](../../docs/MIGRATION.md) and
[data policy](../../docs/DATA.md). Copied runners retain their frozen guards;
old evidence JSON and original local outputs have not been rewritten.

All listed stages are now complete. The original coordinator waited for a
verified native smoke test, then started all 100 jobs. Recovery reused the
verified 72 completed jobs and finished the remaining 28, both original
consensuses and the two R comparisons.
Failed/incomplete jobs cannot produce a completed comparison report. All inputs, components and
outputs are hash-bound; existing results are not overwritten.

All 86 Python tests, R preparation helper/synthetic tests and 12 R scoring
integration cases passed before launching the full-workflow coordinator.
The 28 additional recovery-helper tests passed, covering 72-job reuse,
unchanged native commands, lock preservation, hash checks and failure gates.
The actual unmodified legacy consensus CLI also passed a six-edge runtime
smoke test; that is not a substitute for the full 100-run consensus.
Preparation used archived scran 1.32.0/scater 1.32.1 and scoring pROC 1.18.5 in
an isolated R 4.4 environment. Remaining dependencies are recorded rather
than claimed as a fully historical package lock.

## Limits

The authors' saved QC, eligibility, metacell, DE and network intermediates
were not supplied. Exact QC flags, guide collapsing, normalization
denominator, SuperCell seed/overrides and network invocation therefore
remain reconstruction choices or unknowns. The raw H5AD and workbook are
unchanged. Matching some final metrics would not establish byte-exact
reproduction; disagreement would need investigation, not cutoff tuning or
an immediate conclusion about PR70.

The numerical-agreement gate remains unsatisfied. The user-selected
[sampling-only follow-up](author_reconstruction/SAMPLING_COMPARISON.md)
was completed after an explicit scope decision to use the frozen
reconstructed response benchmark. That decision does not recover missing
author inputs or validate exact Fig. 6a reproduction. Perturbation responses
may be indirect; a nonpositive response label is not proof that a predicted
interaction is biologically false.

Sources: [scMINER paper](https://www.nature.com/articles/s41467-025-59620-6),
[pinned analysis](https://github.com/jyyulab/scMINER_analysis/tree/c39f0aaffc22be81ae425adf9e7617504ae9ee33/network_inference/CROP_Seq_GRN_evaluation/Yao_Regev_Cleary).
