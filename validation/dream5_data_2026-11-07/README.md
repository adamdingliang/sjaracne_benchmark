# DREAM5 data addition validation: 2026-11-07

Adds yeast Network 4 source metadata and input preparation, plus Systems Genetics A gold-reference metadata and validation. The benchmark index now separates DREAM, bulk and single-cell data; estimator-calibration studies remain engineering evidence. Raw sources and generated matrices stay external. No inference or parameter tuning was launched.

Passed checks:

- 9 offline Network 4 parser/preparation tests.
- 6 offline Systems Genetics A gold-verifier tests.
- Actual Network 4 verification from both the external originals and original source ZIP; independent exact-token transpose and full 333-TF list checks.
- Actual Systems Genetics A verification from both the extracted originals and pinned archived source ZIP; independent verification of all 15 model graphs and their fixed 999,000-pair universes.
- 66 local documentation links, the three requested data categories, and preservation of historical THP-1 exploratory evidence.
- `git diff --check`.

Commands:

```powershell
python scripts/check_benchmarks.py --group dream5_network4 --group dream5_systems_genetics_a
python benchmarks/dream5_network4/prepare.py verify --data-root D:/GitHub/_datasets/DREAM5_Network4/data/Network4
python benchmarks/dream5_systems_genetics_a/verify_gold.py --data-root D:/GitHub/_datasets/DREAM5_SysGenA/data
```

The repository-wide `python scripts/verify_migration.py` check fails on the existing `benchmarks/brca100_hub_size_dpi_analysis/README.md` frozen-import hash mismatch. Its bytes are identical to the untouched base commit `bd329ebf1ebdfb27307a81c583fe8301b62961be`; this data addition does not change that file or the historical import manifest. [checks.json](checks.json) records the base/current/expected hashes rather than rewriting old provenance to make the check pass.

Systems Genetics A expression/genotype inputs remain pending authorized Synapse access. Complete gold-reference verification is not a claim that the expression benchmark is ready or that inference succeeded.

Follow-up: the user subsequently supplied all three SysGenA input ZIPs. See [input validation and preparation](../sysgena_inputs_2026-11-07/README.md) for the current complete-bundle status; the checks above remain the earlier gold-only snapshot.
