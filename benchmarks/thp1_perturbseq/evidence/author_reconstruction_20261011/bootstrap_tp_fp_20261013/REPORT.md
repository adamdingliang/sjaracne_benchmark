# Saved THP-1 post-DPI bootstrap TP/FP audit

Primary population: predictions from the same 272 eligible perturbed sources; full SIG inference used 6,951 hubs. No inference was rerun.

## Per-bootstrap distribution (100 runs per arm)

Each cell is median [Q1, Q3]. Precision is summarized per run, not calculated from median counts.

| Metric | Before | After (80%) | Change in medians |
| --- | ---: | ---: | ---: |
| eligible_edges | 20,586.0 [19,480.0, 21,714.5] | 7,545.0 [7,309.8, 7,699.5] | -63.35% |
| TP | 5,678.5 [5,444.8, 5,991.2] | 2,811.0 [2,722.5, 2,878.8] | -50.50% |
| FP | 14,875.0 [13,989.8, 15,844.2] | 4,709.5 [4,589.0, 4,828.0] | -68.34% |
| precision | 27.78% [27.29%, 28.22%] | 37.35% [36.88%, 37.64%] | +9.57 percentage points |

These are separate post-DPI graphs. Median changes above are not the median of matched seed differences; the latter are saved separately. Matching seed numbers do not imply matching cells or RNG streams.

## Union and existing consensus

The union contains distinct eligible pairs appearing in at least one bootstrap. It is not a final network. Consensus rows contain distinct pairs surviving the original probability-based consensus, not a new K-edge rule.

| Stage | Before TP | After TP | Before FP | After FP |
| --- | ---: | ---: | ---: | ---: |
| bootstrap_union | 310,549 | 97,791 | 991,998 | 225,360 |
| consensus_pc1e-02 | 17,727 | 10,416 | 24,340 | 13,548 |
| consensus_pc1e-03 | 11,647 | 8,522 | 15,020 | 10,679 |

All 100 after runs have fewer TPs than every before run: the TP deficit is already present in the saved post-DPI bootstraps. Consensus is therefore not the sole origin of the deficit.

## Boundaries

- This compares operational sampling protocols: 121 replacement draws versus 97 distinct metacells; the affine MI cutoff rises from 0.1369870641 to 0.1559020640 at the same nominal bootstrap p=1e-7. RNG consumption also changes.
- Existing files are post-DPI only. This audit cannot separate sampling, MI filtering and DPI contributions, or determine whether lowering the cutoff would rescue the lost TPs.
- TP means a match to the unchanged reconstructed perturbation-response reference; FP means no positive label within the eligible tested population. These are not established direct-edge biological truth labels.
- The 100 runs share data and are not independent biological replicates. Changes are descriptive; no significance claim is made.
- Fixed reference: 4,887,840 non-self pairs, 1,177,495 response-positive labels, 3,710,345 operational negative labels. Per-run FN/TN and sensitivity/specificity use those frozen denominators.

Per-run counts, matched seed differences and eligible-pair recurrence histograms are in the accompanying TSV files. Hashes of all native checkpoints, prepared inputs, helpers and outputs are recorded in manifest.json.
