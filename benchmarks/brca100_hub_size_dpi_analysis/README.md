# BRCA100 hub-list size and DPI pruning: historical August 2026 study

The numerical results below are the unchanged **August 25/26 historical
benchmark**, not a run of the current PCHIP workflow. This documentation refresh
does not rerun inference or rewrite the frozen evidence.

## Question

Did the number of supplied hub genes change DPI pruning under the recorded
historical SJARACNe workflow, even when the expression matrix, target universe,
per-subsample AP-MI cutoff, samples, and other inference parameters are fixed?

The answer in this nested-panel BRCA100 analysis is **yes**. Hub-list size was a
material technical covariate of DPI pruning. This does not establish that the
additional edges removed with a larger list are biologically wrong, nor does it
identify an optimal hub count.

## Historical cutoffs and current scope

Both analyses used base engine commit
`32fe12c168ef80291e487dbf4045f430b9c5d90a` plus frozen **dirty diagnostic
snapshots**, not that clean commit alone:

- pilot source-tree fingerprint:
  `3be6f0c75cf905f983d789410542adda388d07bc0231b4439371e0dd3f22169d`;
- witness-screen source-tree fingerprint:
  `0af71bd617b5c1d7025a648c6c9b7afcc2b50a281cd8a9028e319d773427ba6b`.

The [pilot design](../brca100_hub_size_dpi_pilot/results_2026-08-25/pilot_design.json)
and [screen design](../brca100_kdpi_witness_screen/results_2026-08-26/screen_design.json)
record the historical estimator-matched **GPD-model** cutoffs at `m=80` and
`Npar=40`: TF `p_b=0.001`, MI cutoff `0.14732247558240297`; SIG
`p_b=0.0005`, MI cutoff `0.1644671599536221`. The exact-size null-model SHA256
was `e3a8522682a8ea239821aaa10b12db72d00e07bfdcad43599d8e76a06be80944`.
These are neither the earlier affine cutoff function nor the current empirical
PCHIP cutoffs.

The [current-PCHIP full-panel refresh](../brca100_pchip_refresh/results_2026-10-17/RESULTS.md)
used TF `0.14783093032516142` and SIG `0.16445222440051604` at the same
probabilities. It did not replicate this nested-panel study. PCHIP changes the
MI cutoff, not the DPI decision rule; that calibration change does not invalidate
the historical finding or require rerunning it merely to retain that label.
It can change candidate networks, so none of the pruning fractions below is a
measurement of current-PCHIP hub-size sensitivity.

Fork PRs #1 (PCHIP), #2 (BRCA100 threshold-sweep evidence; formerly upstream #72), and #3
(minimum recurrence; formerly upstream #73) are now merged into fork `develop`
(`04ff6ae097d4c9ac1e7ea3d5060aa59f64a24eea`). They are not pending
dependencies. Porting and testing PR #4's diagnostics on that current engine is
engineering validation, with a separate
test work root; it does not regenerate or replace these historical scientific
runs.

See the [current diagnostic-port software validation](../../validation/pr4_dpi_diagnostics_2026-10-19/VALIDATION.md)
for the pinned candidate, baseline and compatibility checks. That is a separate
engineering check, not a PCHIP replication of the pruning-rate tables below.

## Why hub-list size can create technical bias

For a candidate source-target edge $A-B$, SJARACNe removes the edge when at
least one eligible intermediary $C$ completes a stronger DPI triangle. With
DPI tolerance $\epsilon_{\mathrm{DPI}}$, define

$$
T_{AB}=\frac{I(A;B)}{1-\epsilon_{\mathrm{DPI}}}.
$$

An intermediary qualifies when both

$$
I(A;C)\gt T_{AB}
\qquad\text{and}\qquad
I(B;C)\gt T_{AB},
$$

and the annotation-protection rule permits $C$. The recorded native rule is
therefore a one-witness gate:

$$
\text{prune }A-B
\quad\Longleftrightarrow\quad
\left|\mathcal{W}_{AB}\right|\ge 1,
$$

where $\mathcal{W}_{AB}$ is the set of eligible qualifying intermediaries
available to the run.

The hub list affects $\mathcal{W}_{AB}$ through two coupled implementation
channels:

1. **Source-row availability.** The $A-C$ value comes from source row $A$.
   The $B-C$ lookup prefers row $B$, if it exists, and otherwise can fall
   back to the reverse $C-B$ value from row $C$. Only reconstructed source
   rows can supply those stored relationships. Adding hubs therefore makes
   more triangles testable and can also change direct-versus-reverse lookup
   availability.
2. **Annotation eligibility.** If either endpoint of $A-B$ is annotated, an
   unannotated intermediary cannot remove the edge. The standard workflow uses
   the same list for reconstruction (**-s**) and annotation (**-l**). Increasing
   that list therefore also converts more potential intermediaries into
   eligible annotated witnesses.

When the compared edge and lookup values are otherwise unchanged, an additional
eligible qualifying intermediary supplies another way to remove that edge.
This is not a universal monotonicity theorem for nested hub lists: adding a
source row can change a direct-versus-reverse lookup, and the audit did not
establish identical candidate-edge identities and MI values across panels.
The increases below are observed effects of the recorded nested-panel design.

~~~text
Candidate edge:        A -------- B       weaker
                       \        /
                        \      /
                         C                both A-C and B-C stronger

Smaller panel: C lacks the required source-row/annotation status
               -> the triangle is unavailable or protected -> retain A-B

Larger panel:  C becomes available and eligible
               -> the same A-B edge has a qualifying witness -> prune A-B
~~~

This is a technical context effect because the decision for $A-B$ can change
when other hubs are added, even if the samples and the pre-DPI $A-B$ edge are
unchanged. The additional witness can still be biologically meaningful.
The analysis establishes sensitivity to the supplied opportunity set, not
edge-level biological error.

## Matched 100-seed pilot

The workflow-faithful pilot held the 28,278-gene BRCA100 expression and target
universe fixed. It used deterministic nested TF and SIG panels, the same
80-of-100 sample indices at each matched seed, $N_{\mathrm{par}}=40$,
$\epsilon_{\mathrm{DPI}}=0$, and the historical estimator-matched GPD-model
AP-MI filters specified above. The same panel was supplied to **-s** and **-l**.

| Network | Small hubs | Middle hubs | Full hubs | Median pruning fraction over 100 seeds, small / middle / full | Difference of arm medians, full minus small |
|---|---:|---:|---:|---:|---:|
| TF | 326 | 1,304 | 2,608 | 0.1079 / 0.1917 / 0.2420 | +0.1341 |
| SIG | 1,335 | 5,340 | 10,680 | 0.2249 / 0.3432 / 0.4166 | +0.1917 |

Every adjacent-size paired difference was positive in all 100 matched seeds.
The median increases were:

- TF, 326 to 1,304: +8.243 percentage points;
- TF, 1,304 to 2,608: +5.115 points;
- SIG, 1,335 to 5,340: +11.749 points;
- SIG, 5,340 to 10,680: +7.555 points.

These are not small fluctuations around zero. Under this one nested panel
trajectory, the list size materially changes how much of each pre-DPI network
is removed.

## Fixed-source mechanism audit

The pilot changes both the evaluated source population and the surrounding
hub/annotation panel. A separate ten-seed SIG audit therefore held the
evaluated source population fixed at the same 1,335 genes while expanding the
available reconstructed/annotated panel to 1,335, 5,340, and 10,680 hubs.

A **source row** contains the candidate edges from one source gene to its
targets. At every panel size, the audit counts only edges from the original
1,335 source genes; their targets still span the same expression-gene universe.
This is not a subnetwork restricted to 1,335 genes at both endpoints. Added
source rows remain available to the DPI algorithm, but their own edge counts
are excluded from both the numerator and denominator of the reported fraction.

For each matched seed $s$ and available panel size $H$, calculate

$$
r_{s,H}=\frac{\text{edges pruned from the fixed 1,335 source rows}}
{\text{pre-DPI edges in those same 1,335 source rows}}.
$$

This is a ratio of summed edge counts, not a median of per-gene pruning
fractions. The table then takes the median of these per-seed ratios over seeds
1 through 10, using the native $K_{\mathrm{DPI}}=1$ rule:

| Available SIG panel | Fixed evaluated sources | Median pruning fraction over 10 seeds |
|---:|---:|---:|
| 1,335 | 1,335 | 0.2264 |
| 5,340 | 1,335 | 0.3372 |
| 10,680 | 1,335 | 0.3959 |

The two sections use different seed windows. The primary pilot value 0.2249
for 1,335 SIG hubs is the median over seeds 1 through 100
(0.2249030821). The fixed-source value 0.2264 is the median over seeds 1
through 10 (0.2264073464). Recomputing the primary pilot from only those first
ten seeds gives exactly 0.2264073464. At this smallest panel, the fixed 1,335
sources are also the complete source set, and the audit exactly reproduced the
pilot's per-seed pre-DPI counts, pruned counts, and fractions. The numerical
difference is therefore caused only by summarizing 10 rather than 100 seeds,
not by a different denominator or DPI calculation.

### What the 26,700 comparisons check

For each source gene and seed, the audit compares that row's pre-DPI edge count
in each larger panel with its count in the smallest panel:

$$
1{,}335\ \text{sources}\times 10\ \text{seeds}\times
2\ \text{larger-versus-small comparisons}=26{,}700.
$$

All comparisons had identical counts, with zero mismatches. Therefore the
total evaluated pre-DPI edge count also stayed fixed across panel sizes within
each seed. Counts can differ between seeds; these are matched count checks,
not 26,700 independent experiments.

For example, the recorded **seed 1** results are:

| Available SIG panel | Evaluated source rows | Pre-DPI edges in those rows | Pruned edges in those rows | Pruning fraction |
|---:|---:|---:|---:|---:|
| 1,335 | 1,335 | 55,894 | 12,302 | 22.01% |
| 5,340 | 1,335 | 55,894 | 18,222 | 32.60% |
| 10,680 | 1,335 | 55,894 | 21,583 | 38.61% |

The denominator is unchanged, but more edges from the original source rows
are pruned as the surrounding panel expands.

### What the 0.1692 increase means

First calculate the paired full-minus-small difference within each seed:

$$
\Delta_s=r_{s,10680}-r_{s,1335}.
$$

Then take the median of those ten differences: 0.169159, rounded to 0.1692,
or **16.92 percentage points**. This is not a 16.92% relative increase and is
not calculated by subtracting the two separately reported arm medians. The
full-panel pruning fraction exceeded the small-panel fraction in all ten seeds.

With an all-source summary, a larger panel could change the aggregate pruning
fraction simply by adding source genes with different pruning rates, even if
pruning in the original rows were unchanged. This fixed-source audit excludes
that change in the measured source population as the sole explanation:
the original rows themselves have higher aggregate pruning, with the same
pre-DPI edge count within each matched seed. This supports **panel-context
sensitivity in the fixed source population** under this nested-panel design.

The audit checked pre-DPI edge **counts**, not target identities or MI values
across panels. Equal counts do not establish identical candidate-edge sets.
Source-row availability and annotation eligibility also change together, so
the audit does not apportion their effects or establish whether the additional
removed edges are biologically correct or incorrect.

The example and paired summary are recorded in
[seed-level metrics](../brca100_kdpi_witness_screen/results_2026-08-26/seed_level_metrics.tsv)
and
[paired hub-size effects](../brca100_kdpi_witness_screen/results_2026-08-26/paired_hub_size_effects.tsv).

## Relationship to consensus recurrence

Consensus recurrence $K_{\mathrm{edge}}$ is applied after DPI and is not the
cause of this effect. The pilot independently aggregated support
$K_{\mathrm{edge}}\ge 6$ across the 100 post-DPI networks as a supplementary
topology check:

| Network | Hubs, small / middle / full | $K_{\mathrm{edge}}\ge 6$ edges | Zero-filled median targets |
|---|---:|---:|---:|
| TF | 326 / 1,304 / 2,608 | 61,621 / 227,784 / 416,408 | 115 / 113 / 110.5 |
| SIG | 1,335 / 5,340 / 10,680 | 127,581 / 424,006 / 739,958 | 48 / 49 / 47 |

The full-size counts exactly reproduced the historical independent anchors used
for upstream PR #73 (now merged fork PR #3): 416,408 TF edges and 739,958 SIG
edges. This package used a **historical benchmark-only direct support
aggregator**, not the production minimum-recurrence implementation from fork
PR #3. It is not validation of that production implementation.
Consensus filtering cannot recover edges that DPI already removed, so
$K_{\mathrm{edge}}$ does not correct the upstream panel-size dependence.

## What the witness-threshold screen showed

The diagnostic also counted how many eligible DPI witnesses supported each
removal. Requiring a fixed $K_{\mathrm{DPI}}\gt 1$ did not mitigate the
hub-size effect:

- $K_{\mathrm{DPI}}=2,3,5$ increased the fixed-source full-minus-small gap;
- $K_{\mathrm{DPI}}=10$ reduced the absolute gap only by retaining 1.66% of
  small-panel pruning while retaining 40.9% in the full panel.

A fixed witness-count threshold is therefore rejected as a hub-size-bias
correction in this screen. It can make DPI more conservative for a fixed panel,
but that is a different objective.

## Why call this a technical-bias risk

The observed size trajectory is systematic rather than seed noise. In the
fixed-source audit, expanding the surrounding panel changed pruning while the
samples, evaluated source population, and every matched source-row pre-DPI edge
count remained fixed. Therefore hub-list size was a technical exposure in this
historical design. Because edge identities and MI values were not independently
hashed across panels, this audit should not be read as proving that the input
candidate-edge sets were byte-identical.

Calling every extra removal a biological error would overstate the evidence.
Some added intermediaries may reveal genuine indirect relationships. The bias
risk is that changing the surrounding panel changes the opportunities and stored
lookups used to find a qualifying witness. The observed larger panels had more
pruning, but that is not guaranteed for every panel expansion. Pruning fractions
and retained networks should not be compared as if hub size were biologically
neutral.

In particular, raw TF-versus-SIG pruning differences cannot be attributed only
to biology: the two networks use different hub universes and per-subsample
filters as well as different list sizes.

## Defensible conclusion

This analysis supports the following limited conclusions:

- record hub-list size and composition as part of network provenance;
- treat DPI pruning fraction as panel-dependent, not an intrinsic property of
  the dataset;
- use matched hub-size sensitivity checks before comparing networks built from
  substantially different regulator universes;
- do not infer that extra pruning from a larger panel is biologically correct
  or incorrect without external evidence;
- do not claim an optimal hub count or extrapolate these whole-transcriptome
  BRCA100 results to Xenium 5k.

Under the recorded nested-panel design and historical cutoffs, hub context
materially changed DPI pruning. This is a reason to record and match panel
context, not a validated correction or a numerical prediction for current
PCHIP. Dynamic $\epsilon_{\mathrm{DPI}}$ was not tested; dynamic-epsilon work,
additional fixed-epsilon studies, and edge-level biological adjudication are
outside this PR's scope.

## Audit instrumentation

The historical native instrumentation exposed measurements without changing the
default DPI decision rule:

- every run emits one machine-readable **DPI_STATS** record containing exact
  pre-DPI, pruned, and retained edge counts;
- optional **-W** writes per-source counts of edges with at least 1, 2, 3, 5,
  or 10 qualifying witnesses;
- the witness path fails closed on invalid DPI state, exact CLI-path collisions
  with known input/output files, malformed accounting, or any disagreement
  between the reconstructed one-witness counts and native pruning marks.

The path-collision guard compares the path strings supplied to the CLI; it does
not resolve lexical aliases or symbolic links. The diagnostic should therefore
be written to a dedicated output path.

All 30 historical witness-audit runs exactly reproduced the frozen native
$K_{\mathrm{DPI}}=1$ sample selection, DPI totals, and adjacency data. The
sidecar is diagnostic output, not a production $K_{\mathrm{DPI}}\gt 1$ pruning
option. Current-engine diagnostic-port tests must be reported separately; their
success would not turn these runs into current-PCHIP scientific results.

## Evidence and provenance

- [100-seed pilot design and runner](../brca100_hub_size_dpi_pilot/)
- [Compact pilot evidence](../brca100_hub_size_dpi_pilot/results_2026-08-25/)
- [Witness diagnostic and ten-seed fixed-source screen](../brca100_kdpi_witness_screen/)
- [Compact witness-screen evidence](../brca100_kdpi_witness_screen/results_2026-08-26/)

All required historical validation gates passed in both analyses. The pilot
contains 600 matched inference runs; the witness screen contains 30 matched candidate runs
and 300 source-group/threshold analysis rows. The frozen manifests record the
exact source snapshots, binaries, panels, samples, inputs, commands, and
artifact hashes. Large adjacency files and logs remain in the recorded external
WSL work roots and are deliberately excluded from Git.
