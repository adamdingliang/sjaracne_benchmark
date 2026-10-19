# BRCA100 current PCHIP: K=6 versus legacy consensus

## Scope and outcome

All **four production consensus jobs, both independent support audits and four
pinned NetBID2 QC reports passed**. K6 retains all legacy edges and substantially
increases target counts, but scale-free adjusted R-squared decreases in both
classes. This is a density/coverage tradeoff, not uniform QC improvement.

This is a **consensus-only** comparison on the frozen current-PCHIP BRCA100
post-DPI networks. No subsampling, MI inference/filtering, DPI or null calibration
was rerun. No probability or K was tuned from these results. PR #3 is not merged
as part of this check.

## Fixed matched design

- Original inference: engine `86f8729087b3a6d22bdce128649b4e49d725fb9e`;
  BRCA100, 100 observations and 28,278 expression genes; 100 seeds per class.
- Each run samples 80 observations without replacement (`m=80`), with `Npar=40`
  and DPI epsilon 0. TF and SIG remain separate networks, using their complete
  class-specific source lists as DPI annotations.
- TF: 2,608 candidate sources, explicit `p_b=0.001`, PCHIP MI cutoff
  `0.14783093032516142`. SIG: 10,680 candidates, explicit `p_b=0.0005`, cutoff
  `0.16445222440051604`. These are provisional BRCA100 choices, not universal
  or automatically selected TF/SIG defaults.
- Production consensus: tested PR #3 engine
  `f512ef3a29c661e7cdd7b3b2c4027285d8d19fa3`; compare inclusive `K=6` against
  explicit legacy `p_c=1e-5`, always using the same 100 post-DPI files per class.
- [Prospective protocol](../PROTOCOL.md), [process/reproduction](../README.md),
  and [original PCHIP inference package](../../brca100_pchip_refresh/results_2026-10-17/RESULTS.md).

## Exact support and edge-set comparison

The legacy rule's measured effective boundary is **support >=9 in both classes**.
K6 is therefore a strict superset here: it adds precisely support-6, -7 and -8
edges without removing any legacy edge. This is a measured mapping for these
inputs, not a general equivalence between `p_c=1e-5` and K=9.

| Network | Legacy edges | K6 edges | Shared | K6-only | Legacy-only | Increase over legacy | Added / K6 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| TF | 221,487 | 409,958 | 221,487 | 188,471 | 0 | 85.09% | 45.97% |
| SIG | 379,059 | 739,975 | 379,059 | 360,916 | 0 | 95.21% | 48.77% |

Directed-edge Jaccard is 0.540268 for TF and 0.512259 for SIG; legacy-edge
retention is 100% for both. [Full overlap values](overlap_summary.tsv).

| Added-edge support out of 100 | TF edges | SIG edges |
| --- | ---: | ---: |
| 6 | 84,807 | 164,313 |
| 7 | 59,836 | 113,551 |
| 8 | 43,828 | 83,052 |

There is no biological true/false label for these additions. Six occurrences
among overlapping subsamples are not six independent confirmations, and 6/100
is neither an edge p-value nor a false-discovery rate.

## Density, coverage and topology

| Network | Consensus rule | Edges | Median targets [Q25, Q75] | Active sources | Incident-node coverage | Largest component | Scale-free adjusted R-squared |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| TF | Legacy p_c=1e-5 (effective K>=9) | 221,487 | 50 [32, 99] | 2,608 / 2,608 | 97.687% | 100% | 0.895698 |
| TF | K>=6 | 409,958 | 107 [73, 188] | 2,608 / 2,608 | 99.905% | 100% | 0.872164 |
| SIG | Legacy p_c=1e-5 (effective K>=9) | 379,059 | 21 [12, 46] | 10,679 / 10,680 | 99.558% | 100% | 0.924687 |
| SIG | K>=6 | 739,975 | 47 [29, 90] | 10,680 / 10,680 | 99.993% | 100% | 0.864105 |

K6 increases median target counts by 114% for TF and 123.81% for SIG. However,
the scale-free adjusted R-squared **decreases for both**; the density-oriented
rule is not a uniform QC improvement. Every network has one weak component
among its incident nodes, so this comparison does not demonstrate an LCC gain.

| Network | Consensus rule | Sources with >=10 targets | >=20 targets | >=50 targets |
| --- | --- | ---: | ---: | ---: |
| TF | Legacy p_c=1e-5 | 99.923% | 96.051% | 51.150% |
| TF | K>=6 | 100.000% | 100.000% | 97.201% |
| SIG | Legacy p_c=1e-5 | 84.560% | 53.408% | 22.875% |
| SIG | K>=6 | 99.897% | 93.839% | 48.240% |

[Full metrics and counts](coverage_summary.tsv); paired zero-filled target
counts for [TF](tf_paired_target_sizes.tsv) and [SIG](sig_paired_target_sizes.tsv).

Target-count summaries and >=10/20/50 fractions include all 2,608 TF or 10,680
SIG candidates, including zero-target sources. Incident-node coverage uses all
28,278 expression genes. Largest weak-component fraction uses incident nodes;
it does not count expression genes with no emitted edge as a connected component.
Machine-readable graph density uses directed edges divided by
`V_incident * (V_incident - 1)`.

Scale-free adjusted R-squared uses the unchanged pinned R regression
`lm(log10(P(k) + 1/V) ~ log10(k))`, for total degree `k=1..max(k)` and `V`
incident nodes. This is the historical summary-script definition; it need not
be identical to a fit label displayed in a NetBID2 HTML figure. It is descriptive
QC, not edge accuracy, a merge threshold or a tuning objective.

## Validation and provenance

- All 200 raw adjacency full/data hashes, paired seed metadata, exact seed sets,
  expression input, hub lists and frozen legacy outputs matched their ledgers.
  The runner verified inputs again after aggregation.
- Both production legacy reruns reproduced the frozen three-column and enhanced
  edge tables and bootstrap metadata byte-for-byte. Parameter provenance differs
  only in its output-directory line.
- The independent, engine-free source-streamed audit checked every observed
  ordered pair in the raw union, whether selected or omitted, against
  distinct-file support, supporting-run mean MI rounded to four decimals,
  sorting and enhanced-table projections. Reverse
  directions remain distinct. Metadata records `B=100`, `K=6` and `K/B=0.06`.
- Complete support histograms conserve 13,299,047 TF occurrences over 5,585,549
  unique pairs and 27,306,507 SIG occurrences over 13,244,122 unique pairs.
  Every per-run hash/count in both audits matches the frozen 200-seed ledger.
- The independent canonical normal-tail calculation matched explicit legacy
  membership in all support bins. This checks implementation consistency; it
  does not validate the legacy probability interpretation.
- All **55 synthetic comparison/reporting tests passed in WSL**, with no skips,
  failures or errors. These augment, not replace, the earlier commit-pinned
  engine regression suite; they are not hosted CI or native Windows validation.
- The consensus driver used four parallel processes, one numerical thread each.
  Per-job elapsed seconds were TF legacy 220.10, TF K6 355.81, SIG legacy 388.65
  and SIG K6 598.82. Available memory and peak RSS are retained in manifests.
- One coordinator-started TF audit ran before its enhanced table was complete
  and correctly failed the projection check. That diagnostic is preserved in
  [operational evidence](operational_notes/tf_premature_incomplete_ncol.json)
  and the local work root; the canonical audit was rerun unchanged after
  completion and passed. It is not treated as successful validation or an
  engine defect.

[Passed support audits](support_audits/), [provenance and commands](provenance/),
[contract-test log](provenance/validation/tests.stderr.log) and
[report inventory](report_manifest.json) retain the proof chain. R 4.4.3,
NetBID2 2.2.0 (`5defa454d600b94f5dd6d1f9f4428f99759a6821`) and igraph 2.3.3
match the original QC environment. All network topology/target-size summaries
were cross-checked independently; no biological edge labels were introduced.

Large adjacencies, expression and full consensus tables remain at the durable
WSL paths in the process page. Compact ledgers, support audits, summaries,
source snapshots, logs and QC reports are retained here.

## NetBID2 HTML reports

Use the [four-network QC index](qc/QC_INDEX.md) for TF/SIG under both rules.
Download the HTML and open it locally; GitHub does not render it as a normal
web page. Figures are embedded; MathJax typesetting can require internet access.
The original QC package and its `SHA256SUMS` remain unchanged. For the complete
presentation, run `sha256sum -c PRESENTATION_SHA256SUMS` in this directory.

## Conditional conclusion

K6 is implemented correctly on these current-PCHIP, 100-run BRCA100 inputs and
retains every edge selected by explicit legacy consensus. It substantially
increases density and target coverage by admitting support-6-to-8 edges.

This supports the proposed **transparent, density-favoring engineering policy**
if that coverage tradeoff meets the intended application requirement. It does
not establish that K6 is optimal, that the additions are biologically correct,
or that downstream activity estimates improve. Almost half the K6 network
consists of these lower-recurrence additions. Report both K and B and reconsider
the rule when B changes. TF/SIG hub-list and DPI contexts still differ; this
check does not resolve that technical sensitivity.

The higher median target counts come with lower scale-free fit in both classes;
neither outcome substitutes for an application-specific activity/edge benchmark.
BRCA100 is reused development data, not an independent biological validation set.

PCHIP remains experimental, and `m=80` is off the 50-step broad calibration
grid. No new null-rate guarantee, biological FDR or downstream reproducibility
claim is supplied by network density, connectivity or scale-free fit.
