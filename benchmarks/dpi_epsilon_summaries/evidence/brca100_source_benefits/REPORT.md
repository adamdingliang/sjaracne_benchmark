> Publication copy of a frozen local report/process. Scientific text and numbers are unchanged; relative links are adapted to this compact package. See [publication provenance](PUBLICATION.json) for original hashes and [local artifacts](README.md#local-artifacts) for omitted sidecars.

# Who benefits in the paired BRCA100 pilot?

## Scope and definitions

This secondary analysis uses only the completed original four-strategy pilot. No new native inference, truth labels, biological precision or direct-edge claim is introduced. The fixed-grid extension is separate.

The evaluated population is 479 probe IDs (254 gene-symbol values). Degree strata are fixed at 0–9, 10–19, 20–49, 50–99 and >=100 pre-DPI targets, using each observation seed's common-source no-DPI baseline. Strata do not change with strategy or panel context within a seed, but a source can change strata between observation resamples. Summary counts are medians across distinct computational comparison families, not independent biological observations.

Identity improves when a source's target-set Jaccard across the two contexts increases. Count consistency improves when the absolute difference in target counts decreases. Undefined empty/empty Jaccards remain undefined, not perfect agreement. All 479 sources remain in raw denominators. Matched diagnostics use the original common eligibility across four strategies and both contexts; unavailable sources remain explicit. Matched target counts are equal by construction, so their count gap is not a biological coverage outcome.

## Natural full TF versus full SIG: distribution across sources

| Strategy | Comparator | Pre-DPI degree | Sources | Identity improved / worsened / unchanged | Count-gap improved / worsened / unchanged |
| --- | --- | --- | ---: | --- | --- |
| dynamic_0.025 | fixed | 0-9 | 21 | 0 / 0 / 21 | 0 / 0 / 21 |
| dynamic_0.025 | fixed | 10-19 | 176 | 1 / 1 / 174 | 1 / 1 / 174 |
| dynamic_0.025 | fixed | 20-49 | 193 | 13 / 16 / 163 | 15 / 13 / 164 |
| dynamic_0.025 | fixed | 50-99 | 46 | 21 / 10 / 18 | 30 / 2 / 14 |
| dynamic_0.025 | fixed | >=100 | 42 | 33 / 8 / 0 | 39 / 2 / 0 |
| dynamic_0.025 | fixed | all | 479 | 71 / 38 / 380 | 86 / 20 / 377 |
| dynamic_0.025 | strict | 0-9 | 21 | 0 / 0 / 21 | 0 / 0 / 21 |
| dynamic_0.025 | strict | 10-19 | 176 | 16 / 0 / 160 | 15 / 0 / 161 |
| dynamic_0.025 | strict | 20-49 | 193 | 96 / 5 / 98 | 85 / 9 / 105 |
| dynamic_0.025 | strict | 50-99 | 46 | 43 / 3 / 0 | 41 / 4 / 2 |
| dynamic_0.025 | strict | >=100 | 42 | 39 / 3 / 0 | 32 / 7 / 2 |
| dynamic_0.025 | strict | all | 479 | 198 / 11 / 273 | 174 / 21 / 285 |
| dynamic_0.05 | fixed | 0-9 | 21 | 0 / 0 / 21 | 0 / 0 / 21 |
| dynamic_0.05 | fixed | 10-19 | 176 | 5 / 0 / 167 | 5 / 0 / 167 |
| dynamic_0.05 | fixed | 20-49 | 193 | 58 / 5 / 130 | 49 / 11 / 133 |
| dynamic_0.05 | fixed | 50-99 | 46 | 42 / 6 / 2 | 40 / 5 / 4 |
| dynamic_0.05 | fixed | >=100 | 42 | 38 / 3 / 0 | 34 / 6 / 0 |
| dynamic_0.05 | fixed | all | 479 | 147 / 14 / 318 | 135 / 18 / 326 |
| dynamic_0.05 | strict | 0-9 | 21 | 0 / 0 / 21 | 0 / 0 / 21 |
| dynamic_0.05 | strict | 10-19 | 176 | 23 / 0 / 153 | 22 / 0 / 154 |
| dynamic_0.05 | strict | 20-49 | 193 | 114 / 5 / 81 | 104 / 10 / 87 |
| dynamic_0.05 | strict | 50-99 | 46 | 46 / 2 / 0 | 43 / 3 / 1 |
| dynamic_0.05 | strict | >=100 | 42 | 40 / 2 / 0 | 33 / 7 / 0 |
| dynamic_0.05 | strict | all | 479 | 218 / 9 / 252 | 197 / 20 / 259 |

Full family and degree-stratified results, including expansion/membership comparisons and matched10/20/50-target diagnostics, are in [source_summary.tsv](source_summary.tsv). Raw source-level records are retained in [compressed source differences](README.md#local-artifacts).

## Recurrence of edges retained by relaxed DPI

A rescued edge is present under a relaxed strategy and absent under strict DPI in the **same** sample/panel/H. Its rescued status can change: if strict retains it in another resample, that is still a relaxed-post recurrence, not a loss. The table therefore separates post-DPI presence from repeated rescued status. Candidate availability means the edge passed the MI threshold before DPI in that opportunity. Conditional retention divides by those candidate opportunities; unconditional retention divides by all distinct opportunities. A high conditional value does not cancel pre-DPI instability.

The edge denominator is the union of edges rescued in at least one opportunity in that group. Consequently every such edge has at least one hit by construction. Repeated panel labels pointing to the same full/baseline physical graph are not replication. The strict-retained union is provided as a descriptive reference, not a degree/MI-matched control or accuracy standard.

| Axis | Context | H | Strategy | Rescued-edge union | Relaxed-post in >=2 opportunities | Rescued status in >=2 | Mean unconditional retention | Mean candidate-conditional retention |
| --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: |
| hub_membership | sig | 2608 | dynamic_0.025 | 1669 | 0.781 | 0.343 | 0.771 | 0.771 |
| hub_membership | sig | 2608 | dynamic_0.05 | 3211 | 0.800 | 0.433 | 0.792 | 0.792 |
| hub_membership | sig | 2608 | fixed | 2599 | 0.784 | 0.387 | 0.785 | 0.785 |
| observation_resample | sig | 10680 | dynamic_0.025 | 4871 | 0.214 | 0.057 | 0.420 | 0.854 |
| observation_resample | sig | 10680 | dynamic_0.05 | 9541 | 0.261 | 0.134 | 0.445 | 0.871 |
| observation_resample | sig | 10680 | fixed | 4310 | 0.206 | 0.049 | 0.417 | 0.854 |
| observation_resample | sig | 2608 | dynamic_0.025 | 2272 | 0.303 | 0.037 | 0.461 | 0.816 |
| observation_resample | sig | 2608 | dynamic_0.05 | 4611 | 0.333 | 0.087 | 0.476 | 0.834 |
| observation_resample | sig | 2608 | fixed | 3685 | 0.321 | 0.068 | 0.470 | 0.827 |
| observation_resample | tf | 2608 | dynamic_0.025 | 2377 | 0.326 | 0.042 | 0.475 | 0.808 |
| observation_resample | tf | 2608 | dynamic_0.05 | 4678 | 0.363 | 0.095 | 0.492 | 0.831 |
| observation_resample | tf | 2608 | fixed | 3821 | 0.356 | 0.076 | 0.488 | 0.819 |

All recurrence groups and denominators are in [recurrence_by_group.tsv](recurrence_by_group.tsv), with edge-level rescued-union records in [recurrence_edges.tsv.gz](README.md#local-artifacts).

## Conditional interpretation

This describes the distribution and computational repeatability of the observed robustness benefit. A benefit concentrated in high-degree probes is narrower than improvement across all sources. Raw agreement and rescue recurrence can improve simply because tolerance retains more edges; interpret them with matched-budget diagnostics and retained pruning from the primary report. Three overlapping observation resamples do not establish generalization or biological independence. Reproducible indirect edges remain possible. No production default or optimal schedule is selected.

Engine `b41c4ca637ac2bffe73617a86af65c83e75ee075`; original design `dc9d9123922370db29acc1e6d2bbed5d3d75ed64f2faeca0c9924fc8252f130b`. Input, source-code and report hashes are in [provenance.json](original_provenance.json).
