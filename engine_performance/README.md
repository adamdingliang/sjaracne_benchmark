# Engineering performance and sampling-method archive

This section preserves the evidence and reusable tools behind earlier SJARACNe
engineering changes. It is separate from the dataset-level network evaluations
in [`benchmarks/`](../benchmarks/). These are historical measurements, not new
performance results or universal speedup claims.

The 60 files below are copied byte for byte from the Git objects at SJARACNe
commit `edf7a2fdf3c5ff866f4fea30fe1ca010c00e6a3a`, preserving the original
`benchmarks/<folder>/` layout below this directory. They total 2,004,300 bytes
(about 1.91 MiB). The original mixed generator/native-test module is preserved
separately as [source text](provenance/test_rank_benchmark_generator.py.txt).
Per-file Git object IDs, SHA-256 values and paths are in the
[archive manifest](../provenance/engine_archive_manifest.json).

## Process and results

| Category | Component | Process | Results |
| --- | --- | --- | --- |
| Performance | Accession lookup | [Process](adjacency_lookup/README.md#workload) | [Results](adjacency_lookup/README.md#results-2026-08-08) |
| Performance | AP stable quadrant scatter | [Process](ap_quadrant_scatter/RESULTS_2026-08-08.md#change-under-test) | [Results](ap_quadrant_scatter/RESULTS_2026-08-08.md#median-results) |
| Performance | AP workspace reuse | [Process](ap_workspace/RESULTS_2026-08-08.md#change-under-test) | [Results](ap_workspace/RESULTS_2026-08-08.md#median-results) |
| Performance | Compact adjacency | [Process](compact_adjacency/README.md#protocol) | [Results](compact_adjacency/RESULTS_2026-08-08.md) |
| Performance | DPI neighbor intersection | [Process](dpi_intersection/README.md#optimization) | [Results](dpi_intersection/README.md#results-2026-08-08) |
| Performance | Single-source DPI skip | [Process](dpi_skip/README.md) | [Results](dpi_skip/README.md#results-2026-08-08) |
| Performance | Rank cache | [Process](rank_cache/README.md) | [Results](rank_cache/RESULTS_2026-08-07.md) |
| Performance | Unused bandwidth pass | [Process](unused_bandwidth/README.md#reproduce) | [Results](unused_bandwidth/README.md#matched-results) |
| Sampling method, not a speed benchmark | Fixed-size sampling without replacement | [Process](without_replacement_sampling/README.md#why-bootstrap-duplicates-can-distort-ap-mi) | [Results](without_replacement_sampling/README.md#included-results) |

## What remains in the engine

The engine keeps its implementation, build/CI configuration and numerical
regression tests. Six tiny synthetic input/reference files were relocated to
`tests/fixtures/rank_cache/`; the five native regression tests remain in
`tests/test_sjaracne_rank_cache.py` and
`tests/test_sjaracne_adaptive_partition_workspace.py`. The fixture Git blobs
are unchanged. SJARACNe does not import this repository or require it for
installation, inference or tests.

The generator-only test moved with its tool to
[`tests/test_rank_benchmark_generator.py`](tests/test_rank_benchmark_generator.py).
Its class body and assertions are unchanged; only its surrounding imports and
generator location were adapted. It creates small synthetic inputs in a
temporary directory and requires no native engine or downloaded dataset.

## Verification and use

From this repository's root:

```powershell
python scripts/verify_engine_archive.py
python scripts/check_benchmarks.py --group migration --group engine_performance
```

To additionally compare against the original engine Git objects, use
`python scripts/verify_engine_archive.py --engine-repo PATH_TO_SJARACNE`.
The optional `--git-index` check verifies the staged archive bytes and modes.

Native timing, fuzzing and output-comparison runners are preserved as source
snapshots, not silently ported to a new engine. Their original commands may
assume an SJARACNe checkout, old relative `benchmarks/` paths, native fixtures,
specific baseline/candidate binaries, Linux/GNU time and particular runtime
versions. Read the original protocol and supply explicit external paths or a
separate adapter before using them. Do not run historical scripts with defaults
that would write into this immutable archive. New outputs belong under ignored
`runs/` or an explicit external directory.

The standalone rank-input generator can be used with every data/output input
supplied explicitly. The frozen specification requires the original
19,936-gene, 1,000-profile matrix and matching TF-list digest, as documented in
the [source protocol](rank_cache/README.md#source-data). BRCA100 does not match
that specification. The placeholders below must identify those original inputs:

```powershell
python engine_performance/rank_cache/prepare_rank_benchmarks.py `
  --expression PATH_TO_ORIGINAL_EXPRESSION_MATCHING_SPEC `
  --tf-list PATH_TO_ORIGINAL_TF_LIST_MATCHING_SPEC `
  --spec engine_performance/rank_cache/spec.json `
  --output-dir runs/engine_performance/rank_cache
```

For different inputs, use a separately reviewed custom specification outside
this immutable archive; do not change the frozen specification or bypass its
source checks. That example is not a claim that a new timing experiment
was run. Historical native performance comparisons were not rerun during this
migration. The original license/rights review still applies; see
[licensing status](../docs/LICENSING.md).
