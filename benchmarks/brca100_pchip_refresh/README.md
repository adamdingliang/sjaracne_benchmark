# BRCA100 TF/SIG: current PCHIP workflow and NetBID2 QC

This refresh runs the current empirical PCHIP MI cutoff function through the
complete BRCA100 workflow: fixed-size subsampling without replacement, MI
thresholding, seed-level DPI, consensus, then NetBID2 network QC.

- [Fixed design and interpretation constraints](PROTOCOL.md)
- [Current results, QC HTMLs and provenance](results_2026-10-17/RESULTS.md)
- Historical threshold sweep: [process](../brca100_pr67_threshold_sweep/README.md)
  and [combined 13-point results](../brca100_pr67_threshold_sweep/COMBINED_RESULTS.md)

The historical sweep motivates **initial**, density-oriented probabilities
`p_b=0.001` for TF and `p_b=0.0005` for SIG. Its old cutoff function and network
results are not current PCHIP calibration or new PCHIP outcomes. These are
explicit run settings, not software defaults or biologically optimal cutoffs.

## Matched design

Use all 28,278 BRCA100 expression nodes, 2,608 candidate TFs and 10,680 SIGs.
Each class receives seeds 1–100 and 80/100 observations without replacement,
`Npar=40`, DPI epsilon 0, and its full class-specific hub list as both evaluated
sources and DPI annotation. Every network is inferred afresh; no historical
post-DPI adjacency is replayed or filtered to construct a new network.

The engine is frozen at
[`86f8729`](https://github.com/adamdingliang/SJARACNe/commit/86f8729087b3a6d22bdce128649b4e49d725fb9e),
the current PCHIP PR #1. The AP-MI kernel and stock consensus source are
unchanged relative to the historical sweep. Consensus uses `p_c=1e-5`, not the
separate minimum-recurrence `K=6` proposal. The
[protocol](PROTOCOL.md) records exact input/model hashes and required outputs.

The run uses twelve total native workers and serialized consensus. The runner
exports exact Git blobs, builds a fresh source snapshot, validates every seed
and final network, and records commands, headers, timings and SHA256 manifests.
Completed work is reused only after validating its provenance and contents;
unverified partial work is not silently overwritten.

## Run under WSL/Linux

The controller needs Python 3.9+, Git, make, a C++ compiler and GNU time. Stock
consensus needs the normal SJARACNe scientific-Python dependencies. The QC
adapter can use system Python 3.10+ and an existing pinned NetBID2 environment.
Use a fresh, durable Linux work directory; large native networks stay local.

```bash
BENCH_ROOT=/mnt/d/GitHub/sjaracne_benchmark
ENGINE_REPO=/mnt/d/GitHub/SJARACNe
WORK_DIR="$HOME/sjaracne-benchmarks/brca100-pchip-refresh-20261017-full100"
PYTHON_RUN=/mnt/d/GitHub/SJARACNe-pr67-develop/SJARACNe/build/pchip-test-env/bin/python

# ENGINE_REPO supplies Git objects read-only; the runner exports the pinned
# commit, regardless of that checkout's HEAD. Its checkout is not modified.
"$PYTHON_RUN" "$BENCH_ROOT/benchmarks/brca100_pchip_refresh/run.py" \
  --engine-repo "$ENGINE_REPO" --work-root "$WORK_DIR" --phase prepare

# Optional first-seed TF/SIG smoke test, reused by the complete run.
"$PYTHON_RUN" "$BENCH_ROOT/benchmarks/brca100_pchip_refresh/run.py" \
  --engine-repo "$ENGINE_REPO" --work-root "$WORK_DIR" \
  --phase infer --seed-end 1 --workers 2

"$PYTHON_RUN" "$BENCH_ROOT/benchmarks/brca100_pchip_refresh/run.py" \
  --engine-repo "$ENGINE_REPO" --work-root "$WORK_DIR" --phase all --workers 12
```

A Windows-created linked worktree may contain a Git pointer WSL cannot resolve.
Using the main repository's object store avoids that problem without switching
branches or touching the main checkout. The native calls reproduce workflow
arguments directly; CWL scheduling itself is not being benchmarked here.

An additional [implementation anchor](validate_anchor.py) runs only TF seed 1
at the exact historical explicit MI cutoff and compares adjacency data hashes.
It checks one compiler/runtime example, not PCHIP calibration, and is not
included among the 200 PCHIP networks:

```bash
"$PYTHON_RUN" "$BENCH_ROOT/benchmarks/brca100_pchip_refresh/validate_anchor.py" \
  --work-root "$WORK_DIR"
```

## NetBID2 QC and compact results

The adapter reuses the historical R QC script unchanged, with R 4.4.3, NetBID2
2.2.0 at commit `5defa454d600b94f5dd6d1f9f4428f99759a6821`, and igraph 2.3.3.
It independently cross-checks topology and zero-filled target counts, records
the actual package versions, and optionally packages portable HTML reports and
compact provenance. It does not install packages or modify the existing R
environment.

```bash
python3 "$BENCH_ROOT/benchmarks/brca100_pchip_refresh/analyze_qc.py" \
  --work-root "$WORK_DIR" \
  --netbid-wrapper /mnt/d/GitHub/SJARACNe-brca100-netbid-qc/benchmarks/brca100_netbid_qc/netbid2-r \
  --reference-root "$HOME/sjaracne-benchmarks/brca100-pr67-threshold-sweep-20260818" \
  --package-root "$BENCH_ROOT/benchmarks/brca100_pchip_refresh/results_2026-10-17"
```

The old wrapper is used because its pinned environment still lives in that
worktree. The migrated copy alone has no installed R environment. Published
HTMLs embed figures; download and open locally because GitHub does not render
them as ordinary pages. The standard template may request MathJax online;
offline viewing can omit mathematical typesetting, not the embedded figures.

After the QC package is complete, the presentation step validates all 200 seed
records and the consensus/QC inventories, then adds the comparison report,
target-size plot and compact native provenance. It leaves the original QC
manifest/checksums unchanged and adds `PRESENTATION_SHA256SUMS` covering the
complete augmented package. Use Python 3.10+; `--plot` also needs Matplotlib
(both are already available in the pinned NetBID2 environment):

```bash
/mnt/d/GitHub/SJARACNe-brca100-netbid-qc/benchmarks/brca100_netbid_qc/netbid2-r python \
  "$BENCH_ROOT/benchmarks/brca100_pchip_refresh/report_results.py" \
  --work-root "$WORK_DIR" \
  --package-root "$BENCH_ROOT/benchmarks/brca100_pchip_refresh/results_2026-10-17" \
  --plot
```

The current report presents final edge counts, zero-filled median targets,
active-source and incident-node fractions, largest weak-component fraction,
NetBID2 scale-free adjusted R-squared and historical edge overlap. These are
post-DPI, post-consensus descriptive QC—not biological edge accuracy, edge FDR
or validated driver-activity robustness. Off-grid `m=80` remains an interpolated
calibration query, not a newly confirmed null-rate guarantee.

## Lightweight checks

```bash
python -m unittest discover -s benchmarks/brca100_pchip_refresh -p 'test_*.py'
```

Synthetic tests check orchestration, scope, provenance, resume behavior,
topology auditing and HTML packaging. They do not substitute for the full run.
