# Legacy SJARACNe versus SJARACNe2

Final comparison dated **2026-11-09**. The four DREAM index entries expand to
18 scored networks: N1, N3, N4 and all 15 Systems Genetics A simulations.
The three bulk datasets contribute separate TF and SIG networks. The tables
contain 48 method rows with matched expression inputs and requested hub panels.

[Bar plots](bars/README.md) · [Classic DREAM](#classic-dream) · [Systems Genetics A](#systems-genetics-a) ·
[Bulk](#bulk) · [Definitions](#definitions) · [Execution and provenance](#execution-and-provenance)

Download [the complete table](comparison.tsv). Rates in that TSV are fractions;
rates in the tables below are percentages. `TP` is interpreted from the requested
accuracy-column label `TF`.

See [ROC curves and AUROC comparisons](roc/README.md) for the same final DREAM
networks ranked by saved MI.

## Compared workflows

| Setting | Legacy SJARACNe | SJARACNe2 develop |
| --- | --- | --- |
| Resampling | 100 full-size bootstraps with replacement | 100 resamples, each using 80% without replacement |
| MI cutoff | Original affine calibration, p=1e-7 | PCHIP calibration, TF/DREAM p=0.001 and SIG p=0.0005 |
| Consensus and DPI | Strict DPI epsilon=0 in each run, then historical probability consensus pc=1e-5 | K20 candidate edges, supporting-run mean MI, then dynamic DPI |
| Dynamic tolerance | Not used | min(0.30, 0.025 + 0.05 * max(0, log2(H / 479))) |
| Shared settings | Npar=40, seeds 1-100 | Npar=40, seeds 1-100 |

The legacy baseline is the actual pre-sampling-change implementation, not
the legacy-plus-K20 control. The SJARACNe2 scientific settings match
[develop at 7c1e71f](https://github.com/adamdingliang/SJARACNe2/tree/7c1e71f36cd4ae1d4f377668b62015fa722c5b2a).
Execution-version distinctions are recorded below.

## Classic DREAM

| Dataset | Method | Profiles | Edges | Active / requested hubs | TP | FP | Precision (%) | Recall (%) | F1 (%) | Median targets | Adjusted scale-free R2 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DREAM5 N1 | Legacy SJARACNe | 805 | 15,202 | 195 / 195 | 1,627 | 12,089 | 11.86 | 40.55 | 18.36 | 63 | 0.7602 |
| DREAM5 N1 | SJARACNe2 | 805 | 8,027 | 194 / 195 | 1,385 | 5,810 | 19.25 | 34.52 | 24.72 | 35 | 0.8096 |
| DREAM5 N3 | Legacy SJARACNe | 805 | 46,195 | 334 / 334 | 339 | 5,021 | 6.32 | 16.41 | 9.13 | 113.5 | 0.6468 |
| DREAM5 N3 | SJARACNe2 | 805 | 21,166 | 316 / 334 | 219 | 2,148 | 9.25 | 10.60 | 9.88 | 46 | 0.7266 |
| DREAM5 N4 | Legacy SJARACNe | 536 | 54,402 | 333 / 333 | 232 | 6,119 | 3.65 | 5.89 | 4.51 | 126 | 0.6105 |
| DREAM5 N4 | SJARACNe2 | 536 | 27,365 | 333 / 333 | 113 | 2,829 | 3.84 | 2.87 | 3.28 | 63 | 0.6939 |

## Systems Genetics A

Each row pair is a distinct 1,000-gene simulated network. A100, A300 and A999
denote expression profile counts. The five networks within each group are
different generating graphs. All 1,000 genes are requested sources, not
1,000 validated TFs. Zero median targets means at least half of the requested
sources have no retained outgoing targets.

| Dataset | Method | Profiles | Edges | Active / requested hubs | TP | FP | Precision (%) | Recall (%) | F1 (%) | Median targets | Adjusted scale-free R2 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A100 network 1 | Legacy SJARACNe | 100 | 17,091 | 1,000 / 1,000 | 355 | 16,736 | 2.08 | 17.43 | 3.71 | 17 | 0.0435 |
| A100 network 1 | SJARACNe2 | 100 | 686 | 367 / 1,000 | 103 | 583 | 15.01 | 5.06 | 7.57 | 0 | 0.0181 |
| A100 network 2 | Legacy SJARACNe | 100 | 17,556 | 1,000 / 1,000 | 495 | 17,061 | 2.82 | 16.20 | 4.80 | 17 | 0.0567 |
| A100 network 2 | SJARACNe2 | 100 | 894 | 436 / 1,000 | 151 | 743 | 16.89 | 4.94 | 7.65 | 0 | 0.0478 |
| A100 network 3 | Legacy SJARACNe | 100 | 16,944 | 1,000 / 1,000 | 573 | 16,371 | 3.38 | 15.14 | 5.53 | 17 | 0.0683 |
| A100 network 3 | SJARACNe2 | 100 | 1,380 | 543 / 1,000 | 196 | 1,184 | 14.20 | 5.18 | 7.59 | 1 | 0.1229 |
| A100 network 4 | Legacy SJARACNe | 100 | 16,862 | 1,000 / 1,000 | 711 | 16,151 | 4.22 | 14.69 | 6.55 | 17 | 0.0716 |
| A100 network 4 | SJARACNe2 | 100 | 1,574 | 559 / 1,000 | 238 | 1,336 | 15.12 | 4.92 | 7.42 | 1 | 0.1398 |
| A100 network 5 | Legacy SJARACNe | 100 | 17,032 | 1,000 / 1,000 | 814 | 16,218 | 4.78 | 14.36 | 7.17 | 17 | 0.0123 |
| A100 network 5 | SJARACNe2 | 100 | 1,640 | 571 / 1,000 | 292 | 1,348 | 17.80 | 5.15 | 7.99 | 1 | 0.0917 |
| A300 network 1 | Legacy SJARACNe | 300 | 20,220 | 1,000 / 1,000 | 724 | 19,496 | 3.58 | 36.51 | 6.52 | 20 | 0.0549 |
| A300 network 1 | SJARACNe2 | 300 | 1,976 | 755 / 1,000 | 383 | 1,593 | 19.38 | 19.31 | 19.35 | 1 | 0.1237 |
| A300 network 2 | Legacy SJARACNe | 300 | 19,802 | 1,000 / 1,000 | 755 | 19,047 | 3.81 | 24.31 | 6.59 | 19 | 0.0102 |
| A300 network 2 | SJARACNe2 | 300 | 2,334 | 777 / 1,000 | 345 | 1,989 | 14.78 | 11.11 | 12.68 | 2 | 0.2913 |
| A300 network 3 | Legacy SJARACNe | 300 | 17,502 | 1,000 / 1,000 | 981 | 16,521 | 5.61 | 25.65 | 9.20 | 18 | -0.0074 |
| A300 network 3 | SJARACNe2 | 300 | 2,872 | 845 / 1,000 | 565 | 2,307 | 19.67 | 14.77 | 16.87 | 2 | 0.2183 |
| A300 network 4 | Legacy SJARACNe | 300 | 19,634 | 1,000 / 1,000 | 1,141 | 18,493 | 5.81 | 23.71 | 9.33 | 20 | 0.0200 |
| A300 network 4 | SJARACNe2 | 300 | 2,932 | 824 / 1,000 | 573 | 2,359 | 19.54 | 11.91 | 14.80 | 2 | 0.2099 |
| A300 network 5 | Legacy SJARACNe | 300 | 18,394 | 1,000 / 1,000 | 1,063 | 17,331 | 5.78 | 20.16 | 8.98 | 18 | 0.0221 |
| A300 network 5 | SJARACNe2 | 300 | 3,150 | 853 / 1,000 | 519 | 2,631 | 16.48 | 9.84 | 12.32 | 3 | 0.1849 |
| A999 network 1 | Legacy SJARACNe | 999 | 18,322 | 1,000 / 1,000 | 932 | 17,390 | 5.09 | 45.51 | 9.15 | 18 | 0.0050 |
| A999 network 1 | SJARACNe2 | 999 | 3,454 | 914 / 1,000 | 663 | 2,791 | 19.20 | 32.37 | 24.10 | 3 | 0.2347 |
| A999 network 2 | Legacy SJARACNe | 999 | 15,490 | 1,000 / 1,000 | 1,143 | 14,347 | 7.38 | 36.95 | 12.30 | 15 | 0.0181 |
| A999 network 2 | SJARACNe2 | 999 | 3,942 | 927 / 1,000 | 800 | 3,142 | 20.29 | 25.86 | 22.74 | 3 | 0.2709 |
| A999 network 3 | Legacy SJARACNe | 999 | 15,454 | 1,000 / 1,000 | 1,091 | 14,363 | 7.06 | 28.99 | 11.35 | 15 | -0.0116 |
| A999 network 3 | SJARACNe2 | 999 | 4,196 | 924 / 1,000 | 694 | 3,502 | 16.54 | 18.44 | 17.44 | 4 | 0.2100 |
| A999 network 4 | Legacy SJARACNe | 999 | 14,862 | 1,000 / 1,000 | 1,219 | 13,643 | 8.20 | 25.72 | 12.44 | 14 | 0.0021 |
| A999 network 4 | SJARACNe2 | 999 | 4,544 | 957 / 1,000 | 799 | 3,745 | 17.58 | 16.86 | 17.21 | 4 | 0.2525 |
| A999 network 5 | Legacy SJARACNe | 999 | 15,512 | 1,000 / 1,000 | 1,331 | 14,181 | 8.58 | 24.00 | 12.64 | 15 | -0.0060 |
| A999 network 5 | SJARACNe2 | 999 | 4,648 | 944 / 1,000 | 809 | 3,839 | 17.41 | 14.59 | 15.87 | 4 | 0.1502 |

## Bulk

TCGA cohorts contain primary tumors. These are LUAD517 and BLCA406, not the
separate LUAD100 or BLCA MIBC372 subsets. Bulk accuracy columns are N/A
because no independent edge-level gold standard was used.

| Dataset | Panel | Method | Profiles | Edges | Active / requested hubs | TP | FP | Precision (%) | Recall (%) | F1 (%) | Median targets | Adjusted scale-free R2 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| BRCA100 | TF | Legacy SJARACNe | 100 | 800,099 | 2,608 / 2,608 | N/A | N/A | N/A | N/A | N/A | 283 | 0.2624 |
| BRCA100 | TF | SJARACNe2 | 100 | 88,915 | 2,573 / 2,608 | N/A | N/A | N/A | N/A | N/A | 9 | 0.8083 |
| BRCA100 | SIG | Legacy SJARACNe | 100 | 851,887 | 10,680 / 10,680 | N/A | N/A | N/A | N/A | N/A | 71 | 0.4552 |
| BRCA100 | SIG | SJARACNe2 | 100 | 259,121 | 9,456 / 10,680 | N/A | N/A | N/A | N/A | N/A | 4 | 0.9282 |
| TCGA-LUAD517 | TF | Legacy SJARACNe | 517 | 442,965 | 1,929 / 1,929 | N/A | N/A | N/A | N/A | N/A | 182 | 0.7939 |
| TCGA-LUAD517 | TF | SJARACNe2 | 517 | 272,586 | 1,928 / 1,929 | N/A | N/A | N/A | N/A | N/A | 110 | 0.7696 |
| TCGA-LUAD517 | SIG | Legacy SJARACNe | 517 | 633,732 | 9,464 / 9,464 | N/A | N/A | N/A | N/A | N/A | 53 | 0.8279 |
| TCGA-LUAD517 | SIG | SJARACNe2 | 517 | 1,335,639 | 9,460 / 9,464 | N/A | N/A | N/A | N/A | N/A | 117 | 0.8087 |
| TCGA-BLCA406 | TF | Legacy SJARACNe | 406 | 382,365 | 1,920 / 1,920 | N/A | N/A | N/A | N/A | N/A | 162 | 0.8335 |
| TCGA-BLCA406 | TF | SJARACNe2 | 406 | 267,566 | 1,920 / 1,920 | N/A | N/A | N/A | N/A | N/A | 112 | 0.8645 |
| TCGA-BLCA406 | SIG | Legacy SJARACNe | 406 | 595,101 | 9,420 / 9,428 | N/A | N/A | N/A | N/A | N/A | 49 | 0.8967 |
| TCGA-BLCA406 | SIG | SJARACNe2 | 406 | 1,539,525 | 9,422 / 9,428 | N/A | N/A | N/A | N/A | N/A | 133 | 0.8913 |

## What the comparison supports

- SJARACNe2 improves F1 in **17/18** DREAM settings. Precision rises and
  recall falls in all 18. Fewer reference false positives come with fewer true
  positives. Yeast N4 is the F1 exception: 4.51% to 3.28%.
- Target coverage falls substantially. Classic DREAM medians decline from
  63 to 35, 113.5 to 46 and 126 to 63. In A100, two networks have a median
  of zero. Higher F1 does not imply larger regulons.
- Bulk TF medians fall in all three datasets. BRCA100 is particularly sparse:
  TF 283 to 9 and SIG 71 to 4. TCGA SIG coverage increases: LUAD517 median
  53 to 117 and BLCA406 median 49 to 133, with more than twice as many edges.
- Adjusted scale-free R2 improves for three of six bulk networks: BRCA TF/SIG
  and BLCA TF. It falls for LUAD TF/SIG and BLCA SIG. This topology statistic
  does not establish biological accuracy. N4 illustrates the distinction:
  its R2 improves while its F1 falls.

These are descriptive comparisons of complete workflows. Sampling, MI
calibration/cutoffs, consensus and DPI all differ. The table cannot attribute
improvement to any one change. The 15 Systems Genetics simulations share one
simulation framework and are not 15 independent biological cohorts.

## Definitions

- **Profiles:** expression columns, not resample count. **Edges:** all emitted
  directed nonself edges. **Active hubs:** requested sources with at least one
  target. H and the requested count include zero-target sources.
- **TP/FP:** reference-labelled directed pairs. N1/N3/N4 unlabelled predictions
  are excluded from TP/FP and precision, but included in Edges and target counts.
  Thus Edges can exceed TP + FP. N3/N4 references are incomplete, and a labelled
  FP is not proof that the association is biologically false. SysGenA uses the
  complete generating-model nonself universe.
- **Precision:** TP/(TP+FP). **Recall:** TP/(TP+FN). **F1:**
  2TP/(2TP+FP+FN). **Median targets:** median unique outgoing nonself targets
  over the entire requested matched panel, including zero-target hubs.
- **Adjusted scale-free R2:** the existing NetBID2 QC fit on total degree
  (in+out) of nodes present in the emitted graph. For k=1 through the maximum
  degree, fit log10(p(k)+1/V) against log10(k), with an intercept. V is the
  incident-node count. Zero-target requested hubs are not inserted as isolated
  nodes. Finite negative fits are retained; undefined fits are N/A.

## Execution and provenance

**Legacy:** N1/N3/N4/SysGenA/LUAD/BLCA use historical commit
[`e59973a`](https://github.com/adamdingliang/SJARACNe2/commit/e59973a1891672a14f06d7847545c53368f3066c).
BRCA100 reused actual commit `12113fbc`; its `SJARACNe` source tree is
identical to e59973a. Recorded expression and hub SHA-256 fingerprints match
within every legacy/current pair. Input normalization only changes line endings.

**DREAM:** accuracy and target-count values are inherited from the
[frozen scored comparison](../consensus_before_dpi/per_dataset.tsv), selecting
`legacy` and `new_relaxed`. The initial native implementation reproduced all
18 relaxed graphs with exact directed edges and binary64 MI values on saved
inputs. Its broader [receipt](../consensus_before_dpi/native_equivalence.json)
also covers offset zero (36 comparisons total). The later sequential reader
preserves manifest-order sums and passed three byte-identical long-row
comparisons plus 22 native tests, documented in
[the pinned implementation validation](https://github.com/adamdingliang/SJARACNe2/blob/7c1e71f36cd4ae1d4f377668b62015fa722c5b2a/docs/native_consensus_validation.md#sequential-input-revision).
The DREAM rows are therefore saved-input native-equivalent results, not a claim
that the latest binary reran all 18 datasets. N1/N3 raw files retain historical
MI serialization precision. Lost input precision cannot be recovered. Accuracy
scores were not independently rescored for this report.

**Bulk:** the [completed native batch](../native_bulk_2026-11-09/README.md)
provides all six SJARACNe2 rows. Four arms used the initial native implementation.
LUAD SIG and BLCA SIG replayed their saved raw MI through the later sequential
reader on HDD. No MI inference was rerun for recovery or this report.

**Topology:** DREAM R2 was newly calculated from the 36 saved final graphs
using the same R/igraph method as the bulk NetBID2 QC. Edge counts, active and
requested hubs, and zero-inclusive medians were checked against the scored
tables. Bulk counts and medians were also independently checked against all
12 saved target-size tables. Input/raw graph hashes quoted in provenance are
existing recorded receipts, not fresh rereads of every expression/raw MI file.

Reproduce the presentation without inference:

```bash
python build_report.py
```

The builder validates row coverage, matching dimensions, QC counts/medians and
the accuracy equations, then regenerates this README and `comparison.tsv`.
See [DREAM provenance](dream_provenance.json), [bulk provenance](bulk_provenance.json),
[topology provenance](topology_provenance.json) and
[the topology calculation](compute_dream_topology.R) for exact sources and versions.
The external input graphs are not distributed with this report.
