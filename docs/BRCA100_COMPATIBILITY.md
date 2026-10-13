# BRCA100 migration compatibility

The compact BRCA100 evidence packages and their scientific definitions are
preserved. Imported engine-version pins, paths, binary hashes, model hashes,
and result checksums describe historical runs; they have not been changed to
pretend those runs originated in this repository.

## What works without an engine build

The saved threshold, recurrence, hub-size and witness-screen reports can be
browsed directly. Synthetic Python tests exercise scoring, packaging,
provenance rejection, recurrence probability calculations and panel analysis.
They do not run inference, regenerate NetBID2 reports, or validate a fresh
end-to-end scientific run.

Checks performed on 2026-10-13 with the local Windows Miniconda Python:

| Imported suite | Collected | Passed | Skipped / compatibility issue |
| --- | ---: | ---: | --- |
| Threshold sweep | 15 | 15 | None |
| Consensus recurrence | 18 | 12 | Five C++ aggregator tests need `g++`; one symlink test needs Windows symlink privileges |
| Hub-size pilot | 6 | 6 with external fixtures | One test assumes an in-repository engine `tests/inputs`; see below |
| DPI witness screen | 9 | 9 | None |

The untouched hub-size pilot suite initially passed five tests and failed its
real-input panel test because it searched for this repository's nonexistent
`tests/inputs/BRCA100_TF.txt`. The same six imported tests passed when their
in-memory `REPO_ROOT` was explicitly pointed to the separate engine checkout
`D:\GitHub\SJARACNe-hub-dpi-analysis`. No fixture was copied, no test source
was edited, and no inference ran. A local example from this repository root:

```powershell
python -c "import sys, unittest; from pathlib import Path; sys.path.insert(0, str(Path('benchmarks/brca100_hub_size_dpi_pilot').resolve())); import test_pilot; test_pilot.REPO_ROOT=Path(r'D:\GitHub\SJARACNe-hub-dpi-analysis'); result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_pilot)); sys.exit(not result.wasSuccessful())"
```

Replace that path with the intended engine checkout. This test-only binding
does not make the inference runners portable. The C++ aggregator and symlink
checks were not enabled by changing the machine configuration.

The new root test launcher provides the same explicit test-only binding:

```powershell
python scripts/check_benchmarks.py --group hub_dpi --engine-repo 'D:\GitHub\SJARACNe'
```

Without `--engine-repo`, only that real-input fixture test is explicitly
skipped; the other synthetic panel/pruning tests still run unchanged.

## Fresh-run adapters still needed

Before claiming a fresh BRCA100 run from this repository, introduce a
separately tested operational layer with explicit external paths:

- **Threshold sweep and matched NetBID2 QC:** expose the external engine Git
  checkout/build/configuration, BRCA100 input root, and pinned NetBID2 runner
  environment. Historical defaults and documented commands refer to
  `/mnt/d/GitHub/SJARACNe` and `SJARACNe-brca100-netbid-qc`; those paths are not
  defaults for a generally portable new installation.
- **Consensus recurrence:** expose both the frozen source-sweep work root and
  an engine checkout for `SJARACNe/bin/create_consensus_network.py`. The
  imported runner can import `SJARACNe.bin.create_consensus_network`, so a
  benchmark-repository root must not be substituted for an engine root. Keep
  the original consensus implementation/version pin and its probability
  definitions when auditing historical anchors.
- **Hub-size pilot:** retain the instrumented engine and BRCA100 fixture
  source. The runner exports `tests/inputs` from a Git engine checkout and
  records a source/build snapshot. The supplied hub list, annotation list,
  model, sampling indices and expression target universe remain separate
  scientifically controlled inputs.
- **Witness screen:** retain its frozen baseline work root, sidecars and
  instrumented engine source-tree fingerprint. Historical build acceptance
  must not silently accept a different engine snapshot because the new
  repository's directory layout differs.
- **Panel tests:** add an explicit external-engine fixture option in a future
  adapter rather than adding the full engine fixture tree to this repository.

New adapters should write new provenance into fresh output directories and
fail closed on missing/mismatched inputs. They must not mutate dated result
packages or replace original historical hashes. Native DPI instrumentation,
minimum-recurrence implementation, calibration runtime models and core
regression tests remain engine-owned.

No new inference, downloads, calibration, biological-reference validation or
native build was performed for these compatibility checks. A successful
synthetic suite is not an end-to-end reproduction claim.
