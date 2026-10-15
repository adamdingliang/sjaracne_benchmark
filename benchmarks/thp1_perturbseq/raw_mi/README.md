# THP-1 raw-MI sampling pilot: 20 matched seed IDs

## Objective and frozen design

This exploratory comparison asks whether changing the resampling strategy
improves the ranking of perturbation-responsive source-target pairs **before
MI significance filtering, DPI or consensus**. It is not an exact Fig. 6a
reproduction, a direct-regulatory-edge gold-standard test, or an end-to-end
SJARACNe improvement claim. The earlier unfavorable/mixed post-DPI/consensus
results remain available in the original evidence package.

The protocol and seed selection are declared before scoring:

- Original frozen expression: 17,971 genes and 121 NT metacells.
- Before: unmodified paper-era proxy at
  `2922ec9a57d3da4e88b849b840643f543f49807c`, 121 draws with replacement.
- After: the same code with only sampling additions from
  `3a93d10e862ba43229e60ca6491ee38143422379`, 97 distinct metacells at 80%.
  This is neither the complete PR70 implementation nor PR71 calibration.
- Both: AP depth 40, no measurement-noise correction; the native tie-breaking
  jitter remains unchanged. Raw flags are `-p 1 -t 0 -e 1`.
- The same reconstructed response reference and fixed eligible universe:
  272 sources, 17,971 targets, self-pairs excluded; 4,887,840 pairs,
  1,177,495 positives and 3,710,345 operational negatives.
- Uniformly select 20 IDs without replacement from the historical seed pool
  1 through 100 using `random.Random(20261015).sample(...)`; then sort:
  `2, 4, 6, 8, 25, 26, 28, 30, 51, 55, 57, 62, 64, 68, 74, 79, 81, 84, 88, 89`.
- Primary readout: tie-aware TP at **k=5,000**. Prespecified secondary budgets:
  1,000, 10,000, 50,000 and 100,000; full-universe AUROC is secondary.

Each seed is scored independently. Curves and metrics are summarized across
resamples; no averaging of MI, recurrence cutoff or consensus network is used.
The same integer seed IDs do not mean identical observations or jitter between
the two protocols. These overlapping resamples are not biological replicates,
and a 20-resample pilot is not sufficient for a broad significance claim.

## Verified source-row optimization

The user explicitly approved computing only the 272 scored source rows, while
retaining the **entire expression matrix and original 6,951-SIG annotation**.
Without DPI, each MI calculation uses only its two gene vectors and the sampled
observations; source-list selection occurs after sampling/global jitter and
does not alter either. There is no per-pair RNG or cross-pair estimator state.
Computing all 6,951 source rows would therefore add unscored work, not change
the requested pair scores. This argument does not apply when DPI is enabled.

Before the pilot, engineering smoke tests compare subset, expanded and
reordered source lists in both pinned binaries. The actual-data check retains
all 17,971 genes and 121 metacells: MIB2/PABPC1/ITGB2 scores are identical when
four unrelated SIG sources are added or source order is reversed. Tiny inputs
check genuine omitted-zero patterns across three seeds. These are code/scope
equivalence checks, not a new full-6,951-source empirical run or response-label
benchmark. The successful proof is required and hash-bound by the run plan.

Generated native inputs must be literal LF. The unmodified legacy list parser
can misread CRLF hub identifiers; ignored identifiers cause a hard failure.
An initial smoke exposed that issue and is preserved separately from the
successful LF retry. No historical input file or binary is rewritten.

## Scoring definitions

Rank all eligible pairs by the serialized native MI, retaining equal-MI ties.
The original writer uses six significant digits, so rounding ties are real
features of these outputs; neither arm receives extra precision.

The native writer suppresses computed MI=0. Such omissions join the MI=0 tie
only after a successful process exit, complete traversal log, all requested
source rows, valid raw headers and strict pair parsing. Unknown or incomplete
output fails closed. No omitted-bottom group or post-DPI imputation is used.

At each k, report expected TP/FP under uniform ordering within a boundary MI
tie, together with attainable minimum/maximum TP, precision, sensitivity,
specificity and EPR. The fixed random precision is
`1,177,495 / 4,887,840 = 0.24090293462961143` in both arms; random expected
TP@5,000 is about 1,204.51. EPR is precision divided by that same prevalence,
not a separate random network conditioned on each arm's emitted edges.
AUROC gives equal-MI positive-negative pairs half credit and is independently
checked against integration across every complete MI group.

Higher TP at the same k mechanically improves precision, recall, specificity
and EPR: they are related views, not independent lines of evidence.
Reference-negative pairs are not proven absence of biological regulation, and
observational NT-cell MI need not match causal perturbation responses.

## Execution and provenance

Scripts here are new, separate from the frozen migrated helpers. Tests use
only synthetic data:

```powershell
python scripts/check_benchmarks.py --group thp1_raw_mi
```

`smoke.py` creates a fresh engineering proof; `run_pilot.py plan` binds it,
the native binaries/configuration, old preparation/run manifests, reference,
seed set and scorer/runner hashes. Planning does not launch inference.
`run_pilot.py run --plan PLAN --workers 12 --limit 2` can validate the first
matched pair; a later invocation without `--limit` verifies those completed
artifacts and executes the remaining jobs. An incomplete job directory is
never silently overwritten. `report.py` requires every declared seed in both
arms before producing the final paired report and three-panel plot.

Large outputs remain under ignored `runs/thp1_raw_mi_20261015/`: one immutable
plan, per-job raw adjacencies, dense score arrays, logs, timing/RSS, compact
metrics and a completion record. Historical runs and the external raw data
are unchanged. Only code, the declared protocol and compact final evidence
belong in Git. Results will be linked here when the pilot is complete.
