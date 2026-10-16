# Staged AP-MI null calibration across sample counts

This study fits SJARACNe's independence-null GPD tail at exact selected
observation counts, using the production-shared AP-MI kernel. It focuses on
the provisional TF probability 0.001 and SIG probability 0.0005. These are
exploratory operating points, not validated biological optima or FDR controls.

The [prospective protocol](PLAN_2026-10-15.md) fixes the design and safeguards.
The existing engine/calibrator is an external, hash-pinned dependency; this
benchmark does not modify the shared engine checkout or install new defaults.

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
accounted for. Timing provenance remains under the ignored
`runs/apmi_null_m_sweep_timing_20261015/` until compact packaging.

The staged runner provides frozen plans and per-size records; commands and
completed results will be documented after its technical smoke checks. Large
raw streams stay local under ignored `runs/`.
