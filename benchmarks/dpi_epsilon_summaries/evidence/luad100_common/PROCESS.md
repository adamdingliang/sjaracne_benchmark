> Publication copy of a frozen local report/process. Scientific text and numbers are unchanged; relative links are adapted to this compact package. See [publication provenance](PUBLICATION.json) for original hashes and [local artifacts](README.md#local-artifacts) for omitted sidecars.

# Prespecified LUAD100 common-source DPI transfer pilot

Recorded 2026-10-26 before new LUAD network inference or agreement/pruning
outcomes. User authorized matching BRCA100's tests to evaluate whether its
conditional engineering conclusion transfers to LUAD. No epsilon tuning on
LUAD, production-default change, direct-edge accuracy claim or GitHub write.

## Question

Does the frozen dynamic schedule reduce measured sensitivity to TF/SIG hub
context while maintaining a useful agreement/pruning trade-off against shared
fixed tolerances, especially epsilon 0.20/0.25? This is not a contest to maximize
agreement, equalize density or force identical targets. Extra intermediaries
can justify differences; no-DPI context agreement is the trivial upper bound.
No reference edges are available here.

## Frozen input and representation

- Use only the completed, independently validated `E:\TCGA\LUAD\` preparation:
  517 patient-distinct primary tumors; 29,841 retained gene-level Ensembl rows;
  1,929 TF and 9,464 SIG sources, with exactly 477 common gene IDs.
- Verify preparation status/manifest, independent-validation record and hashes
  of exported input files before staging. Preserve original E-drive data,
  preparation code/protocol, patient selection and gene filtering unchanged.
- Preserve the gene-level `log2(TPM+1)` matrix and the full-cohort IQR feature
  selection. No symbol collapse, protein-coding-only filter, per-panel IQR,
  imputation, normalization, new noise, adjacency replay or extra gene filter.
- This full-517-patient feature selection is not held-out-patient validation.
  BRCA used probe-level nodes whereas LUAD uses gene IDs; a comparison cannot
  isolate a tissue effect from platform, mapping and feature-selection changes.
- Before inference, record all-zero/constant row counts in the chosen 100-patient
  cohort (and native 80-patient samples where practical), including common-source
  counts. Do not silently remove them. RNA-seq zeros/ties remain a limitation:
  the independent-rank PCHIP calibration is not a demonstrated p/FDR guarantee
  for tied expression. That does not invalidate a matched engineering comparison.

## Matching the BRCA design

- Choose exactly 100 of the 517 patient columns using Python's deterministic
  `random.Random(2026102701).sample(...,100)`; serialize in original header order.
  Record all chosen/excluded patient IDs, indices and source hashes. No outcome-
  based sample selection. All other prepared rows and values are preserved.
- From that fixed population, native fixed-size subsampling selects exactly
  80 observations without replacement, with seeds 1, 2 and 3. Validate the actual
  ordered selected indices, map them back to full-cohort patient IDs, and require
  identical choices across every context/tolerance within a seed.
- Reuse the exact BRCA engine build at commit
  `b41c4ca637ac2bffe73617a86af65c83e75ee075`, with its frozen binary/config/model
  and source hashes. No rebuild or native-code edits. Native parameters remain
  PCHIP p_b=0.0005 for BOTH contexts, Npar=40, noise=0, native gene filters 0/0.
  Require the same model identities and native m80 cutoff as BRCA (including hex).
- Keep reconstruction and annotation memberships the same (`-s` equals `-l`).
  TF and SIG reconstruction remain separate. All 29,841 rows are targets.
- Evaluate E = the same 477 shared Ensembl gene IDs in EVERY reconstruction,
  including zero-target sources in denominators. Symbols are annotations only.
- Baseline panel contains only E (H=477). TF panels: H=477,964,1929. SIG panels:
  H=477,964,1929,9464. Thus 964 is floor(full TF/2), paralleling BRCA's half-TF
  point; the full-TF size is also an intermediate SIG point.
- Three random nested auxiliary memberships per class: reuse panel seeds
  2026102601/2026102602/2026102603 with SIG offset +1000, selecting non-E hubs
  without truth labels and ordering all files by expression-row order.
  Common baseline and full-list aliases are one physical experiment, not
  independent repetitions. Same-H genuinely distinct memberships remain separate.

## Tolerances: frozen before outcomes

Strict epsilon 0; shared fixed epsilon 0.05,0.10,0.15,0.20,0.25; dynamic slopes
0.025 and 0.05, with

```text
epsilon(H) = min(0.30, slope * max(0, log2(H/479)))
```

**H_ref=479 is retained as a frozen numerical count of computational source rows.**
Do not change it to 477 based on LUAD's retained intersection. The H=477 common
baseline has epsilon 0 under the max(0,...) rule. This near-equality is not a
claim that 479 BRCA probes and 479 LUAD genes cover the same biology.
At a single H, dynamic epsilon is simply a fixed number; its distinct claim
concerns the H trajectory, not one favorable endpoint.

Add thresholded no-DPI epsilon 1 controls for every distinct source panel/sample.
Expect 504 logical DPI views and 318 unique native jobs INCLUDING no-DPI,
after physical aliases are deduplicated. All LUAD native jobs are new; BRCA
graphs are not recycled as LUAD data. The historical graph/scoring definitions
are reused through frozen, explicitly parameterized helpers only.

## Outcomes and comparisons

Repeat the complete BRCA common-source analysis:

1. Paired natural full TF(H1929) versus full SIG(H9464), same evaluated E.
2. Within-TF and within-SIG E baseline to each larger H.
3. Same-H TF/SIG comparisons and genuinely different same-H memberships.
4. Observation-resample agreement, explicitly descriptive with three overlapping
   samples, not independent biological replicates.

Report pooled edge Jaccard, source target-count distributions, source coverage,
per-source target-count discrepancy, pooled versus median-source pruning and
strict pruning retained. Report pruning at BOTH endpoints plus the candidate-
weighted combined rate; a combined number can conceal sacrificing one context.

Top-10/20/50-target comparisons require a SINGLE eligibility intersection across
all eight strategies and both paired contexts. Report available/477 and missing
budgets; do not pad short sources. Adding relaxed controls should not reduce
strict-arm eligibility. Retain all three original label-independent SHA-256
tie namespaces. Six-significant-digit adjacency scores and deterministic tie
ordering do not establish hidden full-precision rank identity.

Describe agreement versus retained pruning across EVERY H cell, not a weighted
score selected afterward. Shared fixed epsilon must remain the SAME at all H.
Show both-context and combined-pruning comparisons without interpreting
nondominated-cell counts as a success rate: dynamic is zero at the H477 anchor,
while a positive fixed arm also relaxes that baseline, structurally protecting
dynamic from some both-endpoint dominance comparisons.

Secondary source-level outcomes use strategy-independent PRE-DPI degree strata
0-9,10-19,20-49,50-99,>=100 within seed. Show exact per-family improved/worsened/
unchanged/undefined source counts versus strict and fixed controls. Medians at
their ceiling must not hide heterogeneous effects. Give explicit denominators
if pooling source-resample evaluations; they are not unique biological genes.

For within-context relaxed-minus-strict rescued edges, distinguish repeated
rescued STATUS from relaxed-graph PRESENCE across three samples/memberships.
An edge may survive strict DPI elsewhere. Report pre-DPI candidate availability
and unconditional versus candidate-conditional retention; aliases are not
replication. Reproducible indirect edges are possible.

## Software/integrity gates and execution

Freeze protocol, code/tests, historical helper copies, input identities, source
lists, selected observations, native commands and binary/model/source hashes
before inference. Synthetic tests must cover the LUAD477/29841/504 axis, alias
deduplication, max-zero dynamic baseline, shared budgets, complete-status gates,
no overwrite and frozen helper relocation.

Use at most 12 native workers. Time a small smoke spanning baseline/full TF/full
SIG and positive epsilon. Require native source matching, rank cache29841x80,
complete source traversal, correct sampling/model/cutoff headers and arithmetic
pre=pruned+post/emitted=post before the full batch. Reuse successful smoke jobs.
Require common-source no-DPI candidate identities and literal scores to match
across contexts within each seed, strict weighted-subset of relaxed, post subset
of no-DPI and epsilon nesting within fixed context. Missing/changed/failed
evidence stops validation; scorers must never launch or silently repair inference.

Use fresh WSL evidence root
`/home/adam/sjaracne-benchmarks/luad100-common-sources-20261026` and copy compact
reports/tables/plots to this benchmark module's `results_2026-10-26/` only after
completion. Preserve E-drive preparation and all BRCA evidence. If runtime
exceeds20minutes, launch a detached pipeline with PID/logs/progress/final status,
automatic validation/analysis/hash-checked Windows copy. Do not hold chat open
just to wait. No consensus, NetBID2 network-QC, activity or full517 inference.

## Conditional interpretation

The BRCA-derived hypothesis is an engineering balance, not uniquely maximal
top-target identity or accuracy. Primary descriptive contrasts are dynamic0.05
versus fixed0.20/0.25: full-context agreement, per-context/combined pruning and
the H trajectory. Report exact paired differences and ranges, including adverse
directions; no binary scientific acceptance threshold is invented afterward.
If the same useful balance recurs without retuning, describe replication of that
trade-off in LUAD under this prespecified representation/cohort policy. If fixed
tolerance explains the benefit equally well, or the pruning sacrifice/identity
loss differs materially, narrow or reject the transfer claim. Neither a favorable
result nor software-test success establishes direct-edge accuracy, optimal H_ref,
an optimal slope, biological FDR, full-cohort performance or a new default.
