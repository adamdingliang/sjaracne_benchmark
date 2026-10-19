# BRCA100 PCHIP: fixed K=6 versus legacy consensus

Declared before the consensus comparison. This is a software-compatibility and
descriptive network-QC check for PR #3, not new MI calibration or biological
validation. Neither probabilities nor K will be selected from these results.

## Fixed inputs and intervention

- Reuse exactly the 100 TF and 100 SIG post-DPI adjacency files from the
  [current PCHIP refresh](../brca100_pchip_refresh/results_2026-10-17/RESULTS.md).
  Match every file, seed-metadata record, expression input and driver list to
  the frozen SHA256 ledgers before starting any consensus job.
- Original inference: engine `86f8729087b3a6d22bdce128649b4e49d725fb9e`, BRCA100,
  28,278 expression nodes, seeds 1–100, 80/100 samples without replacement,
  Npar 40, DPI epsilon 0, and each full TF/SIG list as source and DPI annotation.
- TF: 2,608 candidate drivers, explicit p_b=0.001, MI cutoff
  0.14783093032516142. SIG: 10,680 candidates, explicit p_b=0.0005, MI cutoff
  0.16445222440051604. These are fixed exploratory BRCA100 settings.
- Run the production consensus implementation at PR #3 commit
  `f512ef3a29c661e7cdd7b3b2c4027285d8d19fa3`, once per class with `-k 6` and
  once with explicit legacy `-p 1e-5`. This low-level `-p` corresponds to the
  workflow's `-pc`, not its MI probability `-pb`.
- B=100 for each class; K=6 means inclusive support >=6, or K/B=0.06. Preserve
  directed source–target pairs and average MI over the supporting runs only.
  Determine the legacy rule's actual effective recurrence boundary from these
  inputs; do not assume a historical K=9 mapping still holds.

No expression resampling, MI calculation, MI filtering, DPI or null draws will
be repeated. Original input files remain read-only. Use a fresh Linux work
directory for all generated outputs; keep large networks outside Git.

## Software correctness gates

1. Verify all 200 input networks, their exact seed sets, model/input provenance
   and the existing legacy consensus outputs against their frozen ledgers.
2. Require the refreshed production legacy mode to reproduce the frozen
   consensus edge tables and MI values. Investigate any mismatch; do not
   silently change comparison tolerances or accept changed edge membership.
3. Independently reconstruct distinct-file support and supporting-run MI sums
   from raw adjacency rows. Check every selected K=6 edge and every omitted
   eligible edge, deterministic order, four-decimal MI, metadata B/K/K/B, and
   legacy selection. Record complete support histograms and per-run edge totals.
4. Compare the two consensus edge sets, including intersection, additions,
   removals, Jaccard and any nesting implied by the measured support boundary.
   Use valid header-only networks in B; do not inflate recurrence with repeated
   rows or copied input runs.

The independent reference must not call the production consensus selector to
decide membership. The legacy compatibility check is against the existing
frozen outputs; an independent normal-tail calculation is a diagnostic, not
a proposal to recalibrate its probability label.

## Descriptive QC and reporting

For each of the four consensus networks report edges, zero-filled per-source
target-count summaries, fractions of candidate drivers with at least 10, 20
and 50 targets, active drivers, incident-node coverage over all 28,278 expression
nodes, weak components and largest weak-component fraction.

Use the unchanged historical R QC script and pinned NetBID2 environment:
R 4.4.3, NetBID2 2.2.0 at `5defa454d600b94f5dd6d1f9f4428f99759a6821`,
igraph 2.3.3. Cross-check its topology and target counts independently.
The machine-readable scale-free adjusted R-squared uses the existing regression
`lm(log10(P(k) + 1/V) ~ log10(k))`, for total degree k=1..max(k) and V incident
nodes. Preserve portable HTML reports and method/environment hashes.

At most four consensus processes may run concurrently, with one numerical
thread each. Previous TF/SIG consensus peak memory was about 1.4/3.8 GiB;
available memory is checked and recorded before launch. Runtime, output hashes,
commands and source pins are retained. Incomplete outputs are not overwritten.

## Conditional interpretation

Passing the correctness gates establishes that the refreshed software applies
the stated recurrence rule and preserves explicit legacy selection on these
fixed PCHIP networks. Density and target coverage describe the cost of changing
that rule. They do not establish that added edges are biologically correct,
that K=6 is optimal, or that the network or downstream activities are more
reliable. Scale-free fit is descriptive QC, not a merge threshold or optimization
objective. No PR merge is part of this run.
