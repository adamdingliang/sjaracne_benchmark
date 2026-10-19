# BRCA100 PCHIP consensus recurrence

Consensus-only comparison of inclusive `K=6` against explicit legacy
`p_c=1e-5`, using the same frozen 100 TF and 100 SIG post-DPI adjacency files.
Inference is not rerun, and the original adjacencies are neither copied nor
modified. `K=6` means support in at least six distinct files: `6/100 = 0.06`.
It is a stability rule, not a significance or biological-accuracy guarantee.

The inputs retain BRCA100, 80 observations sampled without replacement,
`Npar=40`, DPI epsilon zero, TF `p_b=0.001` and SIG `p_b=0.0005`.
Inference provenance remains engine `86f8729`; production consensus code is
exported as raw Git blobs from tested engine `f512ef3`. The runner verifies all
200 full/data hashes, paired seed metadata and input hashes against the
[frozen PCHIP package](../brca100_pchip_refresh/results_2026-10-17/).
The legacy rule's actual integer support boundary must be derived from these
networks; it is not assumed to be nine.

Durable WSL locations:

- Original inputs: `/home/adam/sjaracne-benchmarks/brca100-pchip-refresh-20261017-full100/arms/{tf,sig}/adj`.
- New outputs: `/home/adam/sjaracne-benchmarks/brca100-pchip-recurrence-20261018/arms/{tf,sig}/{k6,legacy_pc}`.
- Compact delivery: [results and interpretation](results_2026-10-18/RESULTS.md),
  [four-network QC index](results_2026-10-18/qc/QC_INDEX.md).

## Reproduce

Run in Linux/WSL with the existing tested Python and pinned NetBID2 environment.
Preparation requires a fresh work directory. Existing/failed consensus outputs
are not implicitly resumed or overwritten. Up to four independent consensus
processes run concurrently, with one numerical thread each and a memory
preflight. No native inference executable is invoked.

```bash
BENCH_REPO=/mnt/d/GitHub/sjaracne_benchmark
RECURRENCE_DIR="$BENCH_REPO/benchmarks/brca100_pchip_recurrence"
RECURRENCE_PYTHON=/home/adam/sjaracne-regression/pr3-f512ef3-20261018-r2/venv/bin/python
RECURRENCE_WORK=/home/adam/sjaracne-benchmarks/brca100-pchip-recurrence-20261018
RECURRENCE_RAW=/home/adam/sjaracne-benchmarks/brca100-pchip-refresh-20261017-full100

"$RECURRENCE_PYTHON" -B "$RECURRENCE_DIR/run.py" \
  --engine-repo /mnt/d/GitHub/SJARACNe --work-root "$RECURRENCE_WORK" \
  --raw-root "$RECURRENCE_RAW" --phase prepare --workers 4
"$RECURRENCE_PYTHON" -B "$RECURRENCE_DIR/run.py" \
  --engine-repo /mnt/d/GitHub/SJARACNe --work-root "$RECURRENCE_WORK" \
  --raw-root "$RECURRENCE_RAW" --phase consensus --workers 4
```

The runner records `design.json`, `verification.json`, `run_manifest.json`,
per-network `consensus_manifest.json` files, commands, hashes and timings.
Legacy three-column/enhanced data and bootstrap metadata must reproduce the
frozen bytes; parameter provenance may differ only in the output-path line.

Independently audit directed membership, per-file support, mean MI, ordering,
metadata and the legacy gate. Audit JSON stays outside the QC-owned `analysis/`
directory. Each output JSON must be new.

```bash
for recurrence_arm in tf sig; do
  case "$recurrence_arm" in
    tf) recurrence_baseline_sha=e37efad096edbe9b5347c98f8a874c46c862a5fbdf53921aa16bc65cf21f9324 ;;
    sig) recurrence_baseline_sha=eb8be36db4c3db94ef4a0848ae22825d7f99d5f3e350bd8f579d03040132f608 ;;
  esac
  "$RECURRENCE_PYTHON" -B "$RECURRENCE_DIR/validate_support.py" \
    --adjacency-dir "$RECURRENCE_RAW/arms/$recurrence_arm/adj" \
    --drivers "$RECURRENCE_WORK/inputs/BRCA100_${recurrence_arm^^}.txt" \
    --k6-network "$RECURRENCE_WORK/arms/$recurrence_arm/k6/consensus_network_3col_.txt" \
    --legacy-network "$RECURRENCE_WORK/arms/$recurrence_arm/legacy_pc/consensus_network_3col_.txt" \
    --expected-runs 100 --minimum-recurrence 6 --legacy-p 1e-5 \
    --historical-legacy-network "$RECURRENCE_RAW/arms/$recurrence_arm/consensus/consensus_network_3col_.txt" \
    --historical-legacy-sha256 "$recurrence_baseline_sha" \
    --output "$RECURRENCE_WORK/support_audits/$recurrence_arm.json" || exit 1
done
```

After the runner and both audits pass, verify QC dependencies without running R,
then generate all four reports and a fresh compact QC package. The external
wrapper must use its existing environment; the R script below is the frozen
PCHIP-refresh copy. Both script hashes and the R/NetBID2/igraph versions are
checked. These reports describe topology and target coverage, not edge accuracy.

```bash
NETBID_WRAPPER=/mnt/d/GitHub/SJARACNe-brca100-netbid-qc/benchmarks/brca100_netbid_qc/netbid2-r
FROZEN_QC_R="$BENCH_REPO/benchmarks/brca100_pchip_refresh/results_2026-10-17/provenance/run_netbid_qc.R"

"$RECURRENCE_PYTHON" -B "$RECURRENCE_DIR/analyze_qc.py" \
  --work-root "$RECURRENCE_WORK" --netbid-wrapper "$NETBID_WRAPPER" \
  --r-script "$FROZEN_QC_R" --verify-only
"$RECURRENCE_PYTHON" -B "$RECURRENCE_DIR/analyze_qc.py" \
  --work-root "$RECURRENCE_WORK" --netbid-wrapper "$NETBID_WRAPPER" \
  --r-script "$FROZEN_QC_R" --package-root "$RECURRENCE_DIR/results_2026-10-18/qc"
"$RECURRENCE_PYTHON" -B "$RECURRENCE_DIR/report_results.py" \
  --work-root "$RECURRENCE_WORK" --results-root "$RECURRENCE_DIR/results_2026-10-18"
```

The compact package omits large raw adjacencies and consensus networks; retain
the WSL work roots for full reruns. Download QC HTML and open it locally; figures
are embedded, while MathJax typesetting may require network access.

`report_results.py` binds both independent support proofs to all 200 verified
raw inputs, the production output hashes and QC summaries before exporting
overlap, coverage, paired target counts and compact provenance. It does not
overwrite a prior report. Synthetic checks launch no inference or R:

```bash
python3 "$BENCH_REPO/scripts/check_benchmarks.py" --group brca_pchip_recurrence
```
