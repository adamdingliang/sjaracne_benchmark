# Historical BRCA100 hub-DPI interpretation notes

These notes preserve the later clarifications of the August 25/26, 2026 study.
The [frozen analysis](../brca100_hub_size_dpi_analysis/README.md) retains its
original import bytes. The [annotated presentation at c8f673e](https://github.com/adamdingliang/sjaracne_benchmark/blob/c8f673e9ebbd12fde4900c4387002740afb64a98/benchmarks/brca100_hub_size_dpi_analysis/README.md)
contains the full later discussion; no numerical results were changed.

## Recorded calibration and source

The nested-panel runs used historical estimator-matched **GPD-model** cutoffs,
not empirical PCHIP: at `m=80`, `Npar=40`, TF `pb=0.001` used MI
`0.14732247558240297` and SIG `pb=0.0005` used `0.1644671599536221`.
The null-model SHA-256 was
`e3a8522682a8ea239821aaa10b12db72d00e07bfdcad43599d8e76a06be80944`.

The clean base commit `32fe12c168ef80291e487dbf4045f430b9c5d90a` alone does
not identify the executed code. The runs used dirty diagnostic snapshots:

- Pilot source-tree fingerprint:
  `3be6f0c75cf905f983d789410542adda388d07bc0231b4439371e0dd3f22169d`.
- Witness-screen fingerprint:
  `0af71bd617b5c1d7025a648c6c9b7afcc2b50a281cd8a9028e319d773427ba6b`.

The [2026-10-17 PCHIP refresh](../brca100_pchip_refresh/results_2026-10-17/RESULTS.md)
used different cutoffs: TF `0.14783093032516142` and SIG
`0.16445222440051604`. It did not repeat the nested-panel experiment. A change
to MI calibration does not invalidate the recorded finding, but its pruning
fractions are not measurements of PCHIP hub-size sensitivity.

## What the panel comparison establishes

Hub-list expansion changes both source-row availability and annotation
eligibility. More eligible witnesses can remove a fixed edge when its lookup
values are unchanged, but adding a row can change direct-versus-reverse lookup
availability. The observed increase in pruning is not a universal monotonicity
theorem for every nested panel.

The fixed-source audit evaluated the same 1,335 SIG sources at each panel size.
Its 26,700 matched checks established equal **pre-DPI edge counts**, not equal
target identities or MI values. Equal counts do not prove byte-identical
candidate networks, and the design does not separate source-row effects from
annotation effects. It also cannot label additional removals biologically
correct or incorrect.

Post-DPI K6 counts used a historical benchmark-only support aggregator.
Reproducing its full-panel anchors does not validate a later production
consensus implementation. Likewise, witness sidecars are diagnostics rather
than a production `K_DPI > 1` pruning option.

## Later work is separate evidence

At the October 19 diagnostic-port review, PCHIP, threshold-sweep and recurrence
PRs were already merged into engine `develop` at `04ff6ae097d4c9ac1e7ea3d5060aa59f64a24eea`.
The [port validation](../../validation/pr4_dpi_diagnostics_2026-10-19/VALIDATION.md)
checks software compatibility; it does not turn the August runs into PCHIP
replications. Dynamic DPI tolerance was not tested in those August runs.

Use the [study guide](README.md) for dated comparisons and the
[2026-11-09 native batch](../native_bulk_2026-11-09/README.md) for the later
consensus-first +0.025 workflow. None of these topology summaries alone
establishes edge accuracy or a universally optimal hub panel.
