# Native consensus-first bulk networks (2026-11-09)

All six TF/SIG networks completed, including enhancement and NetBID2 QC. This
records the batch finalized on November 9; it is separate from the
[earlier consensus-order comparison](../consensus_before_dpi/README.md).

## Method

100 seeded 80% resamples without replacement, PCHIP cutoffs (Npar=40),
K20 candidate edges, supporting-run mean MI, then native DPI. TF uses
`pb=0.001`; SIG uses `pb=0.0005`. Dynamic DPI uses Href=479, slope=0.05,
offset=0.025 and cap=0.30. Enhancement uses the full expression matrix.

The [cohort guide](../../docs/BULK_DATASETS.md) distinguishes BRCA100, LUAD517
and BLCA406 from the LUAD100 and BLCA MIBC372 subsets.

## Completed networks

| Dataset | Network | Profiles | Edges | Active / requested hubs | Median targets | Adjusted scale-free R2 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| BRCA100 | TF | 100 | 88,915 | 2,573 / 2,608 | 9 | 0.808341 |
| BRCA100 | SIG | 100 | 259,121 | 9,456 / 10,680 | 4 | 0.928183 |
| LUAD517 | TF | 517 | 272,586 | 1,928 / 1,929 | 110 | 0.769609 |
| LUAD517 | SIG | 517 | 1,335,639 | 9,460 / 9,464 | 117 | 0.808739 |
| BLCA406 | TF | 406 | 267,566 | 1,920 / 1,920 | 112 | 0.864511 |
| BLCA406 | SIG | 406 | 1,539,525 | 9,422 / 9,428 | 133 | 0.891282 |

Median targets includes requested hubs with zero targets. These are descriptive
coverage/topology measurements. Bulk cohorts have no independent edge-level
reference here, so TP, FP, precision, recall and F1 are not calculated.

## Execution and provenance

- Four completed networks were retained: BRCA100 TF/SIG, LUAD517 TF and BLCA406 TF.
- LUAD517 SIG and BLCA406 SIG reused their existing 100 raw-MI graphs. Native
  consensus/DPI, enhancement and QC completed with sequential HDD reading;
  no MI resampling was repeated and no raw graphs were copied.
- The original batch used native SHA-256 `e9fc297e3025b8aeb6d236a57290cb05edfbdd3f23e2f429b4f3ecf2d4cd9475`
  from source `99a36f47542baceda1db2062d8e266743e90e5c5`.
- The two sequential replays used native SHA-256 `7fb2648e5934110fbec5bea7ffd489929f465139fbf5475342c7472f20847036`
  from source `b2e1d2b093a9b5bcad76c9811c664aff64f63cc2`. Raw content rehashing was off;
  producer hashes and seed/runtime/input/settings checks were retained.
- This is a finalized six-arm set; only the two SIG replays used the revised reader.

Recorded three-column network SHA-256 values:

| Arm | SHA-256 |
| --- | --- |
| BRCA100_TF | `f255043f649bebbcd6d145f489cc1c3f2851384e0598a35797bdf7dbaf2ae2aa` |
| BRCA100_SIG | `4784f42ce60faa7a20104cb2efb835039a04e34c87cfabd4d7368939586e05a2` |
| LUAD517_TF | `2d2c14cc68db2a4c87c24298df73215b8e38020213861ccc506fa716a74f7eb8` |
| LUAD517_SIG | `79e96936a8580b2b39e77421b0c312acff3ee26804841e9358a05b8e1b25d5c6` |
| BLCA406_TF | `dec620050a5b50339c9650d4ea6af3be66ff63f07a041200c3e949328a0dd88b` |
| BLCA406_SIG | `ae7c0ffb7a29902a6de97191b837e4100405e3af4b73e5a2af8815c4fae022b1` |

Local evidence roots:

- `D:\GitHub\local_runs\bulk_native_consensus_20261108_99a36f4`
- `D:\GitHub\local_runs\SIG_sequential_HDD_optional_hashes_20261109`

The table is transcribed from successful per-arm metrics and NetBID2 receipts.
The roots retain plans, settings, logs, networks and QC HTMLs. These local paths
are provenance locations, not public downloads. This documentation update did
not rerun inference, rehash large graphs or alter the original receipts.
