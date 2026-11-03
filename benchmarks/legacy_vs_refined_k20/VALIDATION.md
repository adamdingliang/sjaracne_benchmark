# Package validation

Validated November 3, 2026, on Windows Python and the existing pinned WSL Python
environment. These checks read saved results and synthetic fixtures; they do
not run inference, consensus, R, downloads or a new scientific experiment.

```bash
python benchmarks/legacy_vs_refined_k20/package_evidence.py validate
python scripts/check_benchmarks.py --group legacy_refined_k20
```

Results:

- 38 frozen evidence artifacts verified: 3,440,669 bytes, including 24 original
  NetBID2 PNGs and three DREAM sweep figures.
- All 400 unique dataset/configuration/K cases present; confusion denominators,
  precision, recall and F1 recomputed from recorded counts.
- 20 tests passed on both Windows and WSL: immutable-copy and publication-hash
  guards, package paths/hashes, all detailed/concise metric tables, K6/K20
  contrasts, document links, the 24-image catalog and overview-plot/code hashes.
- Independent read-only scientific review matched dataset dimensions,
  probabilities, cutoffs, tolerances, source pins, Npar, QC environment and
  primary/control tables to the original run artifacts.
- Both overview figures were visually inspected; original QC plots remain
  byte-identical to their source payloads.
- `git diff --check` passed before commit.

Only this benchmark's new checks were run for the summary PR. This is not a
claim that all historical repository test groups or the SJARACNe engine
regression suite were rerun. Packaging validation does not establish calibration,
statistical equivalence, biological accuracy or universal suitability of K20.
