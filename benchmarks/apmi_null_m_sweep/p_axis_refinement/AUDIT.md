# Independent verification and numerical sensitivity

Independent numerical reconstruction found no discrepancy in the frozen run.
The reviewer did not modify the candidates, fit a new model, generate nulls,
or change the original evidence.

Verified:

- All 38 original raw-stream hashes and 38 sorted-cache hashes/support/order.
- All 931 fitting quantiles, all 8,379 predictions and all 16,758 scoring rows.
- All 63 summaries independently aggregated.
- All 1,824 old coarse regression rows matched statuses, cutoffs and counts.
- Fifteen direct unsorted-raw count spot checks.
- Zero quantile crossings. All 392 unavailable score rows are the planned
  endpoint PCHIP cases, not silently omitted errors.
- Leave-entire-m-out masking, new p-probe separation, full denominators and
  in-sample baseline interval suppression.

## Synthetic checks

The plan/candidate execution snapshot includes 39 passing synthetic checks
before the run: grid construction, cache verification and analysis logic.
Packaging added ten checks after execution: nine passed; one real-symlink
test was skipped because this Windows session cannot create symlinks. The
cache suite separately tests symlink rejection with mocking and passes.
The earlier smoothing workflow's 45 checks also passed. No test launches
scientific generation or network inference.

## Post-hoc floating-point sensitivity (not a candidate revision)

The frozen log/exp probability interpolation can reconstruct an exact knot at
a neighboring float. Because the observed MI distributions have repeated
values, a tiny cutoff change can change many threshold decisions. The source
results were retained, not recomputed with a favorable rounding/tie convention.

For each of the 272 main new-probe checks, recount validation MI >= cutoff at
the recorded threshold and its two neighbors `np.nextafter(T, -np.inf)` and
`np.nextafter(T, np.inf)`. Central counts matched the evaluation table.

| Method | Checks whose counts changed under +/-1 floating-point unit | Within 10% below / original / above |
| --- | ---: | ---: |
| Dense quadratic | 0/272 | 261 / 261 / 261 |
| Dense PCHIP | 0/272 | 265 / 265 / 265 |
| Exact-m dense p-only | 0/272 | 272 / 272 / 272 |

Thus the main off-knot result totals were not one-unit fragile on these
validation samples. This does not establish all rounding policies or platforms.

A separate recount replaced only the exact-m dense p-only baseline's exact
p-knot queries with the literal fitting quantile, instead of reconstructing
through log/exp. Among 289 moderate knot queries, 202 thresholds differed in
floating representation and 55 changed validation counts. The full 561-query
observed within-10% count remained **561/561**; no pass/fail status changed.
No candidate or frozen summary was altered by this diagnostic.

The largest example was m=50,p=0.05. The literal threshold
0.06627772298751955 includes 89,319 more tied draws than reconstructed threshold
0.06627772298751956. Errors are +9.9100% and -7.9538%, respectively. This is
an absolute probability jump of 0.0089319 (0.89319 percentage points), despite
the tiny numerical cutoff difference. Future engine work must preserve or
explicitly specify exact-knot and comparison semantics.

The numerical diagnostic can be reproduced from each score row and its
recorded cache path:

```python
values = np.load(cache_path, mmap_mode='r')
thresholds = [np.nextafter(T, -np.inf), T, np.nextafter(T, np.inf)]
counts = [len(values) - np.searchsorted(values, t, side='left')
          for t in thresholds]
```

Literal knot cutoffs are the matching `nominal_p` entries in the frozen
[extraction record](results_2026-10-15/extraction.json). This post-hoc check
adds numerical diagnostics, not new statistical confirmation.
