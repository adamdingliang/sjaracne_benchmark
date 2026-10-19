# PR #3 commit-pinned regression evidence

See the [consolidated merge evidence](MERGE_EVIDENCE.md) for the examples update
at `11326f3`, its focused checks and the current-PCHIP BRCA100 results.

This compact archive records the successful Linux/WSL regression run for engine
commit [`f512ef3a29c661e7cdd7b3b2c4027285d8d19fa3`](https://github.com/adamdingliang/SJARACNe/commit/f512ef3a29c661e7cdd7b3b2c4027285d8d19fa3).
It does not certify a later documentation commit, native Windows execution,
live IBM LSF execution or hosted CI.

The [result summary](regression_f512ef3/RESULTS.md) reports 152/152 Python tests,
four real CWL integration combinations, 10 CWL document validations and four
Bats utility tests, with no failures, errors or skips. The
[manifest](regression_f512ef3/manifest.json) retains exact commands, environment,
installed-package identity and source/binary hashes; the
[test inventory](regression_f512ef3/python_tests.json),
[Python log](regression_f512ef3/python_tests.log),
[Bats log](regression_f512ef3/bats_tests.log) and
[individual build/CWL logs](regression_f512ef3/) provide the underlying evidence.
These software checks do not establish biological edge accuracy or that K=6
is an optimal consensus policy.

All 30 frozen evidence files were copied byte-for-byte from
`D:\GitHub\_validation\sjaracne_pr3_refresh_20261018_r2` after verifying the
commit, complete/passed status and every checksum. The original
[`SHA256SUMS`](regression_f512ef3/SHA256SUMS) was also preserved, giving 31 files
and 175,538 bytes in the archive. Its SHA256 is
`d3ce71115f9135070cfedfe011b3a681bbcc9747678d8c868b841f824a29dc1e`.
The copied checksums were verified again. To verify locally:

```bash
cd validation/pr3_minimum_recurrence_2026-10-18/regression_f512ef3
sha256sum -c SHA256SUMS
```

The source export, compiled binaries, wheel and full execution workspace remain
local at `/home/adam/sjaracne-regression/pr3-f512ef3-20261018-r2`; they are not
duplicated here. The earlier failed R1 evidence remains local and was neither
deleted nor relabeled as a passing run. The successful R2 archive is immutable
evidence for the named engine commit, not an assertion that every platform or
future revision has passed.
