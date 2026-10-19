# PR #3: examples and merge evidence

The requested software-validation and documentation gates pass for the named
snapshots below. This is evidence for a maintainer's merge decision, **not a
record of a merge** or proof that K=6 improves biological accuracy.

## Revision boundary

- Fully built/regression-tested runtime:
  [`f512ef3a29c661e7cdd7b3b2c4027285d8d19fa3`](https://github.com/adamdingliang/SJARACNe/commit/f512ef3a29c661e7cdd7b3b2c4027285d8d19fa3).
- Examples/documentation head:
  [`11326f324f66c201d58a76a6b25e8802218ccb22`](https://github.com/adamdingliang/SJARACNe/commit/11326f324f66c201d58a76a6b25e8802218ccb22).
- The only changed tracked paths between them are `README.md`, the two manual
  LSF scripts and `.gitattributes`. The attributes change preserves its prior
  bytes and adds LF rules only for those two scripts.
- All other **105 tracked blobs are unchanged**, including runtime code, CWL,
  native C++, model data and automated tests. The complete `SJARACNe/` Git tree
  is `8cd43f28a3dc7006dfba324afd8cf97598eb947b` at both revisions.
  [Identity and example-job proof](examples_11326f3/check_examples.json).

The full 152-test build/regression is attributed to `f512ef3`, not relabeled as
a fresh full regression at the documentation head. Focused tests and example
checks below ran at `11326f3`. Any later runtime/CWL/model change requires new
validation; these results do not automatically certify a future head.

## Completed checks

| Gate | Measured result | Evidence |
| --- | --- | --- |
| Fresh build, installed wheel and full regression | PASS: 152/152 Python tests; no failures/errors/skips | [Summary](regression_f512ef3/RESULTS.md), [manifest](regression_f512ef3/manifest.json), [test log](regression_f512ef3/python_tests.log) |
| Real CWL integration | PASS: affine/PCHIP crossed with default K6/explicit legacy consensus, four combinations | [Manifest integration matrix](regression_f512ef3/manifest.json) |
| CWL documents and utility scripts | PASS: 10 CWL documents validated; four Bats utility tests | [CWL logs](regression_f512ef3/), [Bats log](regression_f512ef3/bats_tests.log) |
| Focused checks at examples head | PASS: 26 synthetic consensus + 20 mocked-wrapper tests, CLI help and Bash syntax | [Commands and results](focused_checks_11326f3/checks.json), [consensus log](focused_checks_11326f3/consensus.stderr.log), [wrapper log](focused_checks_11326f3/wrapper.stderr.log) |
| Actual documented arguments | PASS: five README workflows and two manual LSF scripts; real wrapper parses arguments/writes jobs with final execution mocked | [Example proof](examples_11326f3/check_examples.json), [short log](examples_11326f3/check_examples.log) |
| Example-checker contracts | PASS: 11 synthetic tests, including dirty/runtime-change rejection and narrow LF-attribute policy | [Checker test log](examples_11326f3/checker_tests.stderr.log), [context](examples_11326f3/verification_context.json) |
| Current-PCHIP BRCA100 | PASS: four consensus jobs, two independent support audits and four pinned NetBID2 reports | [Frozen report and QC links](https://github.com/adamdingliang/sjaracne_benchmark/blob/d39103d44b03e6c7244417bea37aa9034db7ecc2/benchmarks/brca100_pchip_recurrence/results_2026-10-18/RESULTS.md) |

The current-PCHIP check reused all 200 frozen post-DPI networks without inference
or cutoff tuning. Explicit legacy consensus reproduced the frozen tables
byte-for-byte; the independent support/MI audits verified all observed directed
pairs in the raw union, selected and omitted. It used runtime `f512ef3`.

## Example and migration behavior

- Full TF/SIG PCHIP examples explicitly supply `-pb 0.001` / `-pb 0.0005`,
  100 networks, 80 sampled observations and `-k 6`. These probabilities remain
  provisional BRCA100 choices, not automatic TF/SIG defaults.
- The two-network local smoke example uses `-k 1`. The five-network manual LSF
  smoke example also uses `-k 1` and now supplies required `-tmp`.
- The real-data LSF example requires expression/hub environment variables,
  supplies output/tmp paths and uses `-k 6`. It retains the old affine MI cutoff
  policy; no PCHIP probability is silently selected for an arbitrary dataset.
- Both shell examples have enforced LF line endings. Actual WSL execution
  against an argv-only stub caught and then verified the CRLF portability fix.
- Explicit `-pc` still selects deprecated legacy consensus and cannot be combined
  with `-k`. Existing explicit-legacy CWL fixtures/answer keys are unchanged;
  they exercise compatibility, not the new default.
- The default K=6 does not shrink for fewer than six networks: choose a feasible
  explicit K for a smoke test or explicitly request legacy mode. Record K and B.
- The enhanced network's regression p-value is not a consensus-edge probability.
  K6 recurrence and B are recorded in the metadata.

The README links to the current PCHIP K6 process/results; detailed evidence stays
in this benchmark repository. SJARACNe has no runtime dependency on it.

## Scientific tradeoff and limits

K6 raised median targets from 50 to 107 for TF and 21 to 47 for SIG, while
scale-free adjusted R-squared fell from 0.8957 to 0.8722 and 0.9247 to 0.8641.
It retained every legacy edge and added only support-6-to-8 edges here; those
additions are 45.97% of TF and 48.77% of SIG K6 edges. The legacy effective
boundary >=9 is **measured for these inputs**, not a general mapping from
`p_c=1e-5` to K=9.

This supports a transparent, density-favoring engineering policy if that
tradeoff is desired. It does not establish optimal K, biological edge accuracy,
FDR control or downstream activity reproducibility. BRCA100 is reused development
data; its scale-free fit is descriptive QC. PCHIP remains experimental and m=80
is off the broad calibration grid. Full limitations are in the frozen report.

All execution evidence is Linux/WSL. The new LSF checks use stubs/mocks, **not a
live scheduler**. No native Windows/macOS or hosted-CI validation is claimed.
The latest full native/CWL integration remains the four-way regression above.

## Recheck and integrity

With a compatible Python environment and an unchanged checkout at the named head:

```bash
python validation/pr3_minimum_recurrence_2026-10-18/check_examples.py \
  --engine /path/to/SJARACNe --output-dir /new/example-evidence
python -m unittest discover \
  -s validation/pr3_minimum_recurrence_2026-10-18 -p test_check_examples.py
```

These commands start no inference, CWL, LSF job or network QC. Windows-created
linked worktrees inspected from WSL use read-only path translation and
command-local checkout normalization; no Git configuration is rewritten.

All 30 original regression artifacts and their original `SHA256SUMS` remain
byte-preserved. Verify this complete merge-evidence delivery from this directory
with `sha256sum -c MERGE_EVIDENCE_SHA256SUMS`. Large binaries, environments and
native data remain local; existing frozen benchmark packages are unchanged.
