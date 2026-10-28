> Publication copy of a frozen local report/process. Scientific text and numbers are unchanged; relative links are adapted to this compact package. See [publication provenance](PUBLICATION.json) for original hashes and [local artifacts](README.md#local-artifacts) for omitted sidecars.

# DREAM5 matched-operating-point and fixed-tolerance controls

Requested 2026-10-25, after the full-reference coverage extension. This is a
post-hoc exploratory control study, not independent confirmation of an epsilon
schedule. Preserve all earlier native evidence, analyses and interpretations.

## Questions

1. Does relaxed DPI improve precision when comparing the same number of
   **reference-labelled predictions**, or reduce benchmark-defined FP counts
   at the same recall? This is not equal total network density: unlabelled
   predictions cannot be called FP and do not enter the matched labelled budget.
2. Does epsilon depending on H offer a useful trade-off over simply keeping a
   positive epsilon fixed? Full-H comparisons alone cannot answer this.

## Fixed-tolerance comparison

Reuse the frozen original DREAM5 pilot engine, binary, full gene expression,
source/annotation panels, sample indices, PCHIP p=.001, m=644, Npar=40 and seeds
1-3. Do not change any SJARACNe code, default, MI threshold, sampling, consensus,
or reference label. Keep both main `-s=-l=panel` and full-annotation controls.

For each dynamic slope s=.025,.05,.10, set the fixed positive epsilon to the
**exact binary64 value** of that schedule at its full released TF-list size:

```text
dynamic: epsilon(H) = min(.30, s * log2(H / H_min))
fixed:   epsilon(H) = min(.30, s * log2(H_full / H_min)) for every H
```

The fixed values are approximately .05,.10,.20, but are not rounded to those
decimal labels. This avoids introducing a tolerance-value mismatch at full H.
The dynamic and fixed full-H jobs must alias the same verified native records;
their equality there is by construction, not independent supporting evidence.
The evidence distinguishing the schedules comes from smaller H values.

Source panels remain Network1 H=49,98,195 and Network3 H=84,167,334, three
label-blind nested compositions per dataset. The fixed controls require 216 new
deduplicated native jobs at small/middle H; the original 246 jobs are reused.
The logical trajectory design has 756 views (strict plus three dynamic and
three fixed choices). All original complete files stay read-only. Identical
commands are shared rather than counted as independent computational evidence.

Up to 12 native workers. Run and verify a 12-job smoke first (both datasets,
panel1/sample-seed1/main annotation, both smaller sizes, all three fixed values).
Revalidate actual smoke records before submitting remaining jobs. Record PID,
logs and progress for a detached coordinator. Measure elapsed time; if projected
completion exceeds 20 minutes leave it in the background, not an active chat wait.

## Scoring populations

- Full H: all supplied explicit directed labels, covering 178 / 141 TFs,
  278,392 / 152,280 pairs and 4,012 / 2,066 positives. Three unique sample seeds.
- Each nested trajectory: evaluate all 49 / 84 sources from its smallest panel
  at every H, preserving that trajectory's one explicit labelled universe.
  Coverage differs across the three panel compositions (44-45 / 38-40 labelled
  TFs). Compare within the same trajectory and sample before summarizing.
- Keep the thresholded no-DPI baseline for full-H context. It is not raw,
  unthresholded all-pair MI. No gold-based input selection or epsilon tuning.

Ordinary Average Precision and AUROC retain the same fixed explicit universe;
omitted pairs share the bottom zero score. Matched operating points instead
use only emitted, explicitly labelled positive-MI predictions. Never pad an
unavailable prediction budget or recall with omitted zero-score pairs.

## Matched labelled budgets

Evaluate k=100,250,500,1000,2000,5000 and the strict-DPI emitted labelled count
of that matched case. The latter is the main common operating point; every
relaxed graph contains strict edges, so it should be attainable after gates.
At a boundary MI tie, use the expected TP/FP under uniform label-independent
selection within that tie; give minimum/maximum compatible TP/precision too.
Do not rank ties by reference labels or arbitrary gene identifiers.

## Matched recall

Evaluate recall=.02,.05,.10,.20,.30 and the strict graph's emitted recall for
that case. Interpolate the last MI-score block using the same inclusion
probability for every edge in the block. This is an expected operating point
on a linear TP/FP segment, not a newly realized inferred network or a gold-
guided ordering. Report the complete-threshold floor/ceiling as well.

Interpolate **both** arms. At its maximum emitted recall, strict DPI's negative-
only tail below its last TP can be excluded by a score threshold; do not compare
that interpolated relaxed point against the untrimmed strict FP count.
Precision here means expected TP/(expected TP+expected FP), not the mathematical
expectation of a random variable-size network's precision.

## Pairing, gates and interpretation

For each positive slope, compare dynamic versus strict, fixed versus strict and
dynamic versus fixed, within exactly the same dataset, source population,
annotation, sample seed, H and target. Compare only jointly attainable pairs;
retain unavailable cases and their counts. Never compare summaries formed from
different available subsets. Pair before medians/ranges; no graph pooling.

Verify immutable design/build/model/input/harness hashes, exact actual sample
indices and cutoff, full requested source traversal and native edge accounting.
Verify expanded-source pre-DPI candidate identities and literal serialized MI;
post-DPI graphs must be weighted subsets of no-DPI and supersets of strict DPI.
Check epsilon nesting only at fixed source/annotation context, not across H.
Native six-significant-digit output does not establish full-precision MI identity.

Report absolute coverage/pruning/AP/AUROC and paired operating-point differences
together. Improvement in a selected subset or at one budget is not a universal
accuracy gain. Prespecifying these controls after earlier results does not make
them independent validation. No acceptable FP budget or automatic winner is set.
Network3's reference is incomplete: its operational FP labels are not proof of
biological absence. Network1 is simulated known-network recovery, not human
biology. Neither dataset establishes an appropriate BRCA100 schedule.

Save compact code, tables and a Windows-accessible report in a fresh result
directory. Raw expression, native graphs and builds remain outside Git. No
commits, pushes, PR changes or production default changes are included.
