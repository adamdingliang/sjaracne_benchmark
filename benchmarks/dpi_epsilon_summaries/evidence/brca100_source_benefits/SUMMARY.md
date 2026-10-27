> Publication copy of a frozen local report/process. Scientific text and numbers are unchanged; relative links are adapted to this compact package. See [publication provenance](PUBLICATION.json) for original hashes and [local artifacts](README.md#local-artifacts) for omitted sidecars.

# BRCA100 source-benefit summary: exact counts

This guide is derived from the hash-verified tables of the completed original four-strategy pilot. It introduces no native inference or new numerical analysis. The [generated report](REPORT.md) is preserved unchanged. Its category cells are separate medians across three observation resamples: **separate medians need not add to the median source count**. Use the exact tables below when accounting for improved/worsened/unchanged sources.

## Full TF versus full SIG: each matched observation resample

Each row evaluates exactly479 common source probes. Categories are **improved / worsened / unchanged / undefined** relative to the comparator. Identity refers to target-set Jaccard across TF/SIG contexts; count consistency refers to the absolute target-count difference. These are raw retained sets, so gains can reflect density and must be read with the primary matched-budget results.

| Dynamic slope | Comparator | Observation seed | Sources | Target identity | Target-count consistency |
| --- | --- | ---: | ---: | --- | --- |
| dynamic_0.025 | fixed | 1 | 479 | 74 / 39 / 366 / 0 | 96 / 22 / 361 / 0 |
| dynamic_0.025 | fixed | 2 | 479 | 71 / 28 / 380 / 0 | 86 / 16 / 377 / 0 |
| dynamic_0.025 | fixed | 3 | 479 | 60 / 38 / 381 / 0 | 78 / 20 / 381 / 0 |
| dynamic_0.025 | strict | 1 | 479 | 198 / 8 / 273 / 0 | 174 / 20 / 285 / 0 |
| dynamic_0.025 | strict | 2 | 479 | 186 / 11 / 282 / 0 | 164 / 22 / 293 / 0 |
| dynamic_0.025 | strict | 3 | 479 | 200 / 14 / 265 / 0 | 180 / 21 / 278 / 0 |
| dynamic_0.05 | fixed | 1 | 479 | 152 / 12 / 315 / 0 | 143 / 18 / 318 / 0 |
| dynamic_0.05 | fixed | 2 | 479 | 147 / 14 / 318 / 0 | 135 / 18 / 326 / 0 |
| dynamic_0.05 | fixed | 3 | 479 | 127 / 14 / 338 / 0 | 109 / 26 / 344 / 0 |
| dynamic_0.05 | strict | 1 | 479 | 225 / 3 / 251 / 0 | 202 / 18 / 259 / 0 |
| dynamic_0.05 | strict | 2 | 479 | 211 / 11 / 257 / 0 | 197 / 20 / 262 / 0 |
| dynamic_0.05 | strict | 3 | 479 | 218 / 9 / 252 / 0 | 196 / 25 / 258 / 0 |

## Distribution by pre-DPI degree

Here the denominator is **source-resample evaluations pooled across the three seeds**, not unique probes or independent biological observations. Each probe appears once per seed; its bin is assigned from that seed's pre-DPI degree and can change across seeds. Each strategy/comparator combination totals1437 evaluations (=479 x3). Category counts are additive.

| Dynamic slope | Comparator | Pre-DPI degree | Source-resample evaluations | Target identity | Target-count consistency |
| --- | --- | --- | ---: | --- | --- |
| dynamic_0.025 | fixed | 0-9 | 63 | 0 / 0 / 63 / 0 | 0 / 0 / 63 / 0 |
| dynamic_0.025 | fixed | 10-19 | 527 | 3 / 4 / 520 / 0 | 3 / 4 / 520 / 0 |
| dynamic_0.025 | fixed | 20-49 | 583 | 45 / 46 / 492 / 0 | 53 / 37 / 493 / 0 |
| dynamic_0.025 | fixed | 50-99 | 140 | 57 / 31 / 52 / 0 | 86 / 11 / 43 / 0 |
| dynamic_0.025 | fixed | >=100 | 124 | 100 / 24 / 0 / 0 | 118 / 6 / 0 / 0 |
| dynamic_0.025 | strict | 0-9 | 63 | 0 / 0 / 63 / 0 | 0 / 0 / 63 / 0 |
| dynamic_0.025 | strict | 10-19 | 527 | 52 / 0 / 475 / 0 | 50 / 0 / 477 / 0 |
| dynamic_0.025 | strict | 20-49 | 583 | 287 / 15 / 281 / 0 | 252 / 27 / 304 / 0 |
| dynamic_0.025 | strict | 50-99 | 140 | 129 / 10 / 1 / 0 | 119 / 15 / 6 / 0 |
| dynamic_0.025 | strict | >=100 | 124 | 116 / 8 / 0 / 0 | 97 / 21 / 6 / 0 |
| dynamic_0.05 | fixed | 0-9 | 63 | 0 / 0 / 63 / 0 | 0 / 0 / 63 / 0 |
| dynamic_0.05 | fixed | 10-19 | 527 | 18 / 0 / 509 / 0 | 18 / 0 / 509 / 0 |
| dynamic_0.05 | fixed | 20-49 | 583 | 175 / 16 / 392 / 0 | 150 / 28 / 405 / 0 |
| dynamic_0.05 | fixed | 50-99 | 140 | 119 / 14 / 7 / 0 | 116 / 13 / 11 / 0 |
| dynamic_0.05 | fixed | >=100 | 124 | 114 / 10 / 0 / 0 | 103 / 21 / 0 / 0 |
| dynamic_0.05 | strict | 0-9 | 63 | 0 / 0 / 63 / 0 | 0 / 0 / 63 / 0 |
| dynamic_0.05 | strict | 10-19 | 527 | 67 / 0 / 460 / 0 | 66 / 0 / 461 / 0 |
| dynamic_0.05 | strict | 20-49 | 583 | 332 / 14 / 237 / 0 | 305 / 25 / 253 / 0 |
| dynamic_0.05 | strict | 50-99 | 140 | 136 / 4 / 0 / 0 | 125 / 13 / 2 / 0 |
| dynamic_0.05 | strict | >=100 | 124 | 119 / 5 / 0 / 0 | 99 / 25 / 0 / 0 |

## Rescued-edge support: what the denominators mean

A rescued edge is relaxed-post minus strict-post **within the same sample/panel/H**. Across opportunities it may instead survive strict DPI. Consequently, relaxed-post recurrence and repeated rescued status are different quantities. The rescued-edge union and strict-retained union **can overlap** across opportunities; they are not disjoint or matched control groups.

The union of edges rescued at least once has >=1hit by construction. Unconditional retention divides by all three distinct observation selections; candidate-conditional retention divides by the number of selections where the edge passed the MI threshold before DPI. Conditional retention cannot establish observation-resample stability or direct regulation.

See the unchanged [recurrence report](REPORT.md#recurrence-of-edges-retained-by-relaxed-dpi), [all support groups](recurrence_by_group.tsv), and [edge-level opportunities](README.md#local-artifacts).

## Conditional conclusion

The observed benefit is uneven across sources and should be described with degree strata and matched-target-budget agreement, not the already-saturated median. This analysis alone cannot establish that dynamic tolerance is preferable to a well-chosen fixed tolerance. The fixed-grid follow-up addresses that question. No truth labels, independent-dataset validation, consensus or production-default change is introduced.

## Provenance note

The protocol copy frozen for this reading guide includes the fixed-grid anchor/asymmetric-pruning caveat added after the initial source analysis began. The degree bins and support definitions are unchanged; this later copy is **not** represented as the protocol version used for that initial analysis. Both hashes are retained in [SUMMARY_PROVENANCE.json](original_SUMMARY_PROVENANCE.json).
