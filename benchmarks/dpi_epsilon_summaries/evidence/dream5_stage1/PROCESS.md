> Publication copy of a frozen local report/process. Scientific text and numbers are unchanged; relative links are adapted to this compact package. See [publication provenance](PUBLICATION.json) for original hashes and [local artifacts](README.md#local-artifacts) for omitted sidecars.

# Prospective DREAM5 DPI tolerance Stage 1 protocol

Date: 2026-10-25 (America/New_York). Written before new reference scoring.

## Question and scope

Does relaxing DPI improve direct TF-target recovery, and what is the extra
reference-negative cost of recovering reference-positive edges? This is not
calibration of a dynamic epsilon(H) function, a hub-size experiment, a consensus
benchmark, or a claim of optimal universal parameters. No 100-resample batch.

## Frozen inference design

- Current engine develop commit b41c4ca637ac2bffe73617a86af65c83e75ee075.
  Build its immutable Git archive with the system C++ compiler; no engine edits.
- DREAM5 Network 1: all 1,643 released genes, 805 profiles and 195 candidate TFs.
  Network 3: all 4,511 genes, 805 profiles and 334 candidate TFs.
- Use each full supplied TF list for both source selection (-s) and regulator
  annotation (-l). No gold-derived source or gene filtering, normalization,
  adjacency replay, replacement sampling, or added decoy regulators.
- Seeds 1, 2, 3. Select exactly 644 of 805 observations without replacement
  (-u 644), with Npar=40, zero measurement-noise correction and no gene filters.
- Current experimental native PCHIP (-M pchip) at p=0.001 for BOTH TF datasets.
  This is the provisional TF operating point, chosen without scoring these
  labels, not a DREAM-optimized cutoff or biological FDR guarantee. Actual
  m=644 is interpolated. Freeze the resulting numerical cutoff and model hashes.
- Five direct inference stages per dataset/seed: thresholded no-DPI (-e 1),
  strict DPI (-e 0), and epsilon 0.05, 0.10, 0.15. No-DPI is NOT an
  unthresholded all-pair MI baseline: it uses the same p-filter as every stage.
- Total 30 jobs. Up to 12 single-process workers. Initial ten-job engineering
  smoke uses seed 1 for both datasets; freeze/validate and reuse these jobs.

## Primary and secondary endpoints

Primary: paired recovered TP and added FP relative to strict epsilon-zero DPI,
plus incremental precision TP_added/(TP_added+FP_added). Unlabeled additions
are reported separately, not included in that denominator. All epsilon values
will be reported; selecting the largest observed score is exploratory, not
independent validation of a winning epsilon.

Secondary: total TP/FP/FN/TN, emitted-edge precision, recall/sensitivity,
specificity, retained-MI Average Precision and AUROC on a fixed explicitly
labeled universe. Missing pairs have a tied bottom score of zero. Average
Precision is grouped-threshold stepwise precision-recall area, not a trapezoidal
area or accuracy fraction. Top-k summaries, if available, use explicit emitted
labels with documented tie handling and mark k exceeding available predictions
unavailable rather than supplementing arbitrary omitted pairs.

Network 1 scoring: 278,392 explicit pairs, 4,012 positive and 274,380 negative.
Network 3 scoring: 152,280 explicit pairs, 2,066 positive and 150,214 operational
negative. All other predictions are unlabelled and excluded, never implicitly
negative. Network 3's biological reference is incomplete: benchmark FPs are
not necessarily biologically false edges. Network 1 is a known simulated
reference, not validation in human cancers. These local scores are not the
official DREAM5 leaderboard scoring procedure.

Summarize three per-seed statistics with medians/ranges; summarize changes
within seed first. No pooled-network score, arbitrary significance threshold,
independent-biological-replication claim or precision/recall claim based on
averaged counts. Three seeds are a small diagnostic pilot.

## Engineering gates before scoring

1. Verify input hashes and dimensions; preserve numeric expression strings in
   the transposition. Freeze source/model/binary/compiler/harness provenance.
2. Native exit zero, complete 195/334-source traversal, all genes ranked,
   zero missing hubs, and exact planned command including the same -s/-l file.
3. Exactly 644 unique sorted actual observation indices in [0,804]. Ordered
   indices match across all five modes for a seed. Equal column indices across
   the two datasets do not imply matched biological samples.
4. Same native binary64/hex cutoff and bundled model identities throughout;
   consistency with the frozen Python callable within 64 ULPs. Record native
   cutoff exactly, do not claim port-bitwise parity.
5. Native pre = pruned + post, emitted count = post, equal pre counts across
   modes; no-DPI pruned=0 and dpi_applied=0, all other modes dpi_applied=1.
6. Exact weighted serialized subset chain E0 <= E.05 <= E.10 <= E.15 <= E1;
   E1 is the common thresholded no-DPI graph. Shared six-digit MI tokens match.
7. Hash all original files, frozen copies, job logs and outputs; reject changed
   or incomplete evidence rather than silently rerunning/overwriting it.

These checks do not directly fingerprint full-precision pre-DPI MI in each
pruned run: the existing CLI only serializes retained six-digit MI. Record that
limitation rather than changing the scientific engine for this experiment.

Raw networks/builds/logs remain outside Git. Only compact methods, tests,
tables, provenance and figures are candidates for a later publication change.
