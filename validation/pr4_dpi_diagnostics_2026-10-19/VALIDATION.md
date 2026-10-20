# PR #4: current-engine diagnostic validation

The diagnostic port passes the software checks below. This is **not a new
BRCA100 hub-size experiment**, a PCHIP null calibration, or biological validation.
The historical August 2026 pruning tables remain unchanged.

## Pinned revisions and scope

- Unmodified fork `develop` baseline:
  [`04ff6ae097d4c9ac1e7ea3d5060aa59f64a24eea`](https://github.com/adamdingliang/SJARACNe/commit/04ff6ae097d4c9ac1e7ea3d5060aa59f64a24eea).
- Built and tested diagnostic candidate:
  [`b469fb93a9cbc2625eb2475f0b3d2dba74bb7353`](https://github.com/adamdingliang/SJARACNe/commit/b469fb93a9cbc2625eb2475f0b3d2dba74bb7353).
- The candidate preserves the old PR #4 head `b3f9a83` as its second merge
  parent and the current baseline as its first parent. History is not rewritten.
  Its net diff from the baseline contains seven paths: README, five native
  diagnostic source/header files, and the adjacency/DPI test module. The other
  102 tracked paths are unchanged, including the PCHIP data, AP-MI estimator,
  consensus, workflow and packaging files. Retired calibration code and duplicate
  benchmark directories are not restored to the engine tree.

The native port adds per-run `DPI_STATS` accounting and optional `-W` per-source
counts of edges with at least 1, 2, 3, 5 or 10 eligible witnesses. These are
diagnostic counts, not a selectable production `K_DPI` pruning threshold.
Malformed/nonfinite/out-of-range `-e` inputs are now rejected explicitly;
valid-input DPI logic and PCHIP conversion are not changed by the port.

## Completed checks

| Check | Measured result | Evidence |
| --- | --- | --- |
| Fresh native builds | Baseline and candidate built with the same GCC 13.3.0 compiler and Makefile flags | [Build logs and source identities](regression_b469fb9/manifest.json) |
| Independent differential checks | 173/173 synthetic cases; 697 native invocations | [Controller](regression_b469fb9/check_diagnostics.py), [report](regression_b469fb9/differential/report.json), [log](regression_b469fb9/diagnostic_differential.log) |
| Additional inferred-pruning checks | 12/12 cases; 48 native invocations; six PCHIP cases actually pruned edges | [Controller](regression_b469fb9/check_inferred_pruning.py), [report](regression_b469fb9/inferred_pruning/report.json) |
| Full Python regression | 170/170 tests, zero failures/errors/skips | [Summary](regression_b469fb9/RESULTS.md), [test identities/results](regression_b469fb9/python_tests.json), [log](regression_b469fb9/python_tests.log) |
| Real CWL integration | Affine/PCHIP crossed with default K6/explicit legacy consensus; all four combinations passed | [Integration matrix](regression_b469fb9/manifest.json) |
| CWL validation and shell utilities | All ten CWL documents and four Bats utility tests passed | [Manifest](regression_b469fb9/manifest.json), [Bats log](regression_b469fb9/bats_tests.log) |
| Packaging and isolation | Fresh wheel installed; declared dependencies satisfied; tracked source files and binaries unchanged during tests | [Package identity](regression_b469fb9/installed_package_identity.log), [manifest](regression_b469fb9/manifest.json) |

The combined differential total is **185 cases and 745 native invocations**.
For successful runs, the entire serialized adjacency file, including headers
and MI strings, matched byte-for-byte between unmodified baseline, candidate
without `-W`, and candidate with `-W`. No header/path normalization was used.
The checks also verified native sample selections, PCHIP cutoff strings,
pre/pruned/post edge conservation, and agreement between witness-count >=1
and native pruning marks.

The replay cases include all eight A/B/C annotation combinations, sparse and
asymmetric rows, direct-row preference and reverse fallback, empty source rows,
strict MI ties/epsilon boundaries, and nonzero high-witness counts. A separate
exhaustive Python triple-loop oracle checked 156 replay cases. The inference
checks use small synthetic expression matrices, not BRCA100 resampling jobs.
The original 12 inference cases had no actual pruning; the additional fixed
correlated-hub fixtures cover that gap without changing probabilities or MI
cutoffs. The supplementary report keeps these checks separate.

## Provenance and reproduction

Both sources were exported from their exact Git commits into fresh isolated
WSL directories and built there. Python 3.9.25, NumPy 1.20.1, SciPy 1.7.3,
pandas 1.2.3 and the pinned CWL environment were checked against the installed
package requirements. The [manifest](regression_b469fb9/manifest.json) records
all commands, compiler details, source/archive hashes and durations.

- Baseline executable SHA256:
  `c8477b6a0209374a1ec98d005e3723d2a887dc4b5317cde1aa02a192e1a8ddc4`.
- Candidate executable SHA256:
  `b2eb2e296e8d144cfd7f43e4e9dedbb0e5f13b2bb9f593817367e18d8e4f904a`.
- Full local build/test root:
  `/home/adam/sjaracne-regression/pr4-b469fb9-20261019`.
- Synthetic fixtures and per-invocation artifacts remain local under
  `D:\GitHub\_validation\pr4_refresh_20261019\{differential,inferred_pruning}`.
  This compact package retains the reports, controllers, command logs and hashes,
  not hundreds of generated fixture/output files or native binaries.

The environment-specific regression controller is preserved in
[run_regression.py](regression_b469fb9/run_regression.py). It requires the
recorded local dependency caches and a fresh work directory; it does not install
global dependencies or modify source checkouts. Its original `SHA256SUMS`
remains unchanged. Verify the entire compact delivery from this directory with
`sha256sum -c PRESENTATION_SHA256SUMS`.

## Conditional conclusion and limitations

For these pinned revisions and tested inputs, the current-engine diagnostics
preserve native network output and correctly describe the existing one-witness
DPI decision. This supports retaining the diagnostic port for review without
repeating the historical scientific experiment. It does not prove compatibility
for every possible input or establish an optimal hub list, dynamic epsilon,
edge accuracy, biological FDR or downstream activity improvement.

The historical study used different MI cutoffs; these tests do not turn its
pruning fractions into current-PCHIP measurements. PCHIP still changes the
pre-DPI candidate graph, not the pruning rule. The `-W` collision checks compare
literal CLI path strings only, not aliases/symlinks/case variants; use a dedicated
diagnostic output path. Optional witness counting has additional cost; these are
correctness checks, not a performance benchmark.

Evidence is Linux/WSL only, not native Windows, live LSF/Slurm, hosted CI or a
new full-network run. PR #4 remains unmerged; validation does not itself record
or authorize a merge.
