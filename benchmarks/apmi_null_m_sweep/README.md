# Staged AP-MI null calibration across sample counts

The later [19-size 10M + 10M extension](expanded_10m/README.md) and its
[results](expanded_10m/RESULTS.md) are separate from the original experiment
below; original code, plans and result packages remain unchanged.

This study fits SJARACNe's independence-null GPD tail at exact selected
observation counts, using the production-shared AP-MI kernel. It focuses on
the provisional TF probability 0.001 and SIG probability 0.0005. These are
exploratory operating points, not validated biological optima or FDR controls.

The [prospective protocol](PLAN_2026-10-15.md) fixes the design and safeguards.
The existing engine/calibrator is an external, hash-pinned dependency; this
benchmark does not modify the shared engine checkout or install new defaults.

The [completed 2026-10-15 results](RESULTS.md) include all eleven sizes,
accepted and rejected fits, runtime, held-out checks and empirical diagnostics.
Only m=90, 100, 150 passed both gates; all three DREAM5-size GPDs were rejected.

## Stages

1. Measure native generation time at m=30, 300 and 1000 using 200,000 draws
   each. Timing draws do not enter production calibration.
2. Fit and validate anchors m=30, 50, 80, 90, 100, 150, 300, 1000.
3. Fit exact DREAM5 sample counts m=644, 516, 725. No nearest-size substitution.

Every production size uses fresh **5,000,000 fitting draws plus 5,000,000
independent validation draws**, with Npar=40. Fit data determine the tail;
validation data do not refit or choose it. No expression or reference-edge
data enter calibration.

The primary GPD fit uses strict exceedances above q=0.995. Three valid fits at
q=0.9925, 0.995, 0.9975 must agree within 10% at p=0.0005. Both proposed
operating probabilities must pass independent held-out checks using the
existing conservative 99.9% pointwise Clopper-Pearson intervals. This differs
from the original protocol's extreme-p=1e-7 stability requirement; old results
are preserved, not retrospectively relabeled as passing.

Small-m model failures and scientific rejections remain visible. A rejected
candidate is not a usable runtime model. Fitting a valid independence null
does not establish biological edge accuracy, a useful network density, or a
multiple-testing error guarantee. Ties/zero inflation and nonexchangeable
observations require additional validation beyond this synthetic rank study.

## Runtime-first pilot

```powershell
python benchmarks/apmi_null_m_sweep/time_generator.py --generator PATH_TO_PINNED_GENERATOR --out runs/FRESH_TIMING_DIRECTORY
```

On 2026-10-15 the sequential 200,000-draw native pilot took 0.11 seconds at
m=30, 0.71 seconds at m=300 and 2.22 seconds at m=1000. These are generator
measurements, not full-calibration timings. Full generation, GPD fitting,
sorting, hashing, process overhead and parallel contention must also be
accounted for. [Compact timing provenance](timing_2026-10-15/timing_results.json)
includes exact commands, native times, metadata and raw-stream hashes. Timing
binary payloads remain only under ignored `runs/`.

## Reproduce the staged run

The driver uses Windows Python 3.13 with NumPy 2.4.4 and SciPy 1.17.1 for
fitting, and WSL Ubuntu for the pinned native generator. Each child is limited
to one numerical-library thread. The engine checkout is read-only to this
workflow. Replace the machine-specific paths below with verified equivalents;
the generator must match the SHA256 in the protocol.

```powershell
python benchmarks/apmi_null_m_sweep/run_staged.py plan --engine-root D:/GitHub/SJARACNe --generator D:/GitHub/SJARACNe/SJARACNe/bin/apmi_null_generator.exe --engine-commit 7633ebb4a0d966dbda15a4e32d0efa492fb71aeb --python C:/Users/adamd/miniconda3/python.exe --distro Ubuntu --protocol benchmarks/apmi_null_m_sweep/PLAN_2026-10-15.md --out runs/FRESH_CALIBRATION_DIRECTORY
python benchmarks/apmi_null_m_sweep/run_staged.py run --plan runs/FRESH_CALIBRATION_DIRECTORY/plan.json --m 80 --workers 1
python benchmarks/apmi_null_m_sweep/run_staged.py run --plan runs/FRESH_CALIBRATION_DIRECTORY/plan.json --stage anchors --workers 8
python benchmarks/apmi_null_m_sweep/run_staged.py run --plan runs/FRESH_CALIBRATION_DIRECTORY/plan.json --stage dream --workers 3
python benchmarks/apmi_null_m_sweep/summarize.py --run runs/FRESH_CALIBRATION_DIRECTORY --out benchmarks/apmi_null_m_sweep/FRESH_RESULT_DIRECTORY
python scripts/check_benchmarks.py --group apmi_null_m_sweep
```

The m=80 technical smoke uses the full production draw counts. The anchor
stage verifies and reuses that completed attempt regardless of its scientific
acceptance; it does not simulate it again. A failure is preserved and never
silently retried. Fresh generation occurs in WSL; only those newly generated,
strictly verified files enter the calibrator's `--reuse-raw` fitting path.
There is no reuse of earlier historical calibration streams.

The legacy calibrator's original CSV column `cutoff_p1e-7` actually contains
the configured default-p cutoff (0.0005 here). Original reports remain
unchanged; the new summary labels both probabilities correctly. Empirical
fit-stream quantiles are diagnostic only, not replacement runtime models.
Large raw streams stay local under ignored `runs/`.
