# BRCA100 PCHIP refresh: fixed run protocol

Declared October 17, 2026, before new BRCA100 inference or result inspection.
This is an end-to-end descriptive network-QC refresh, not a biological accuracy
benchmark or a new threshold sweep.

## Question and fixed configurations

Run the current frozen empirical PCHIP cutoff function through native MI
inference, seed-level DPI, the current consensus implementation, and NetBID2
network QC. Use the previously discussed BRCA100 operating probabilities as
initial examples, without selecting new probabilities from this run.

| Network | Candidate sources | Explicit per-resample p | Sampling | Repeats |
| --- | ---: | ---: | --- | ---: |
| TF | 2608 | 0.001 | 80 of 100 samples, without replacement | seeds 1–100 |
| SIG | 10680 | 0.0005 | 80 of 100 samples, without replacement | seeds 1–100 |

- Engine source: `adamdingliang/SJARACNe` commit
  `86f8729087b3a6d22bdce128649b4e49d725fb9e` (current PR #1).
- Bundled PCHIP JSON SHA256:
  `5ae44f3ec251282b242e1e25e5695fe8c6d80a0e7a3f156170dbb72c29e09f59`.
- Frozen calibration primary SHA256:
  `8b4104be3f3ffe0a476a4dd7c8f7f6d95f00f1a51fa467c7194edf3806d427f5`.
- `Npar=40`, DPI epsilon 0, class-specific full hub list supplied as both the
  evaluated source list and DPI annotation, matching the historical sweep.
- Consensus remains the current normal-approximation implementation with
  `pc=1e-5`. **Minimum recurrence K=6 is not applied.** Keeping consensus fixed
  avoids confounding a cutoff-function comparison with a consensus-rule change.
- Twelve total native workers; one numerical thread per worker. Consensus is
  serialized. Timing is an execution diagnostic, not a controlled speed test.
- Every seed is inferred afresh from expression, thresholded before DPI, then
  consolidated. Do not replay or filter historical post-DPI networks.

## Inputs and matching

Use LF-normalized inputs from the pinned engine Git tree, not independently
modified local data. Their expected SHA256 values are:

| Input | SHA256 |
| --- | --- |
| `BRCA100.exp` | `ad8a334f5f8cdf46a1000d3ee259b35258a18b3da2e314bb3a0cf7a421d98bc8` |
| `BRCA100_TF.txt` | `9b1219a489b99432175e4c4ad46add7b06f25aae388ee8dd3261fa91e4c43ffd` |
| `BRCA100_SIG.txt` | `16ca27df655f16684f880a4ad719c4e2ae3f8dc0d7e6b9eccdd24cd97c40797c` |

The expression matrix has 28,278 nodes and 100 observations. Compare each new
configuration to its historical 100-seed counterpart at the same nominal p,
using the archived run manifests and exact input hashes. The old MI cutoffs
were approximately 0.147322 (TF) and 0.164467 (SIG); they are historical context,
not inputs to PCHIP. Report old and new numerical cutoffs explicitly rather
than implying that the same nominal p gives identical networks.

## Required outputs and checks

1. Validate 200 completed seed networks, their headers, seed identities,
   selected-sample counts, cutoff values/model hashes and file SHA256 values.
   Resume only when outputs and their provenance still match; incomplete work
   is not a completed network.
2. Run stock consensus on exactly 100 post-DPI networks per class, retaining
   its parameter and bootstrap records. Validate consensus structure and hashes.
3. Run the same pinned NetBID2 importer/QC functions used for the historical
   sweep, separately for TF and SIG; retain R/package session information,
   machine-readable summaries and self-contained HTML reports.
4. Report consensus edges, zero-filled median targets over all candidate
   sources, active-source fraction, incident-node fraction, largest weak
   component fraction among incident nodes, and NetBID2 scale-free adjusted
   R-squared. Report directed-edge overlap with the matching historical network
   where raw artifacts are available.
5. Store large native artifacts only in a fresh durable local run directory.
   Commit compact reports, scripts, logs/manifests, hashes and representative
   HTML/QC images to this benchmark repository, not the engine repository.

An additional implementation anchor may compare TF seed 1 at the exact
historical explicit MI cutoff to its archived adjacency data hash. This is
separate from the 200 PCHIP networks and does not tune a threshold or calibrate
PCHIP. A match checks only that example, not every build/seed/environment.

## Interpretation constraints

The historical sweep motivates initial density-oriented p choices but does not
validate them under PCHIP. The broad-grid calibration did not directly validate
arbitrary off-grid sample counts such as m=80; a callable value is not a new
null-rate guarantee at that query. No null refitting or new calibration draws
are part of this refresh.

NetBID2 scale-free fit, target counts, connectivity and edge overlap are QC,
not biological truth, edge FDR or evidence of robust driver-activity estimation.
TF and SIG results also reflect their different full hub-list/DPI contexts.
No universal probability default or consensus-rule recommendation is selected
from this one dataset.
