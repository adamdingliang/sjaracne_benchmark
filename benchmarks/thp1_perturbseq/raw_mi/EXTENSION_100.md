# THP-1 raw-MI comparison: extension to all 100 seed IDs

**Completed:** all 100 matched pairs, 200 jobs, zero failures. The
[canonical full report](results_2026-10-15_full100/REPORT.md) is now the primary
THP-1 benchmark result; the original pilot and older filtered-workflow evidence
remain visible. The protocol and the post-pilot decision history below are
retained, not restated as if the full extension had been planned beforehand.

## Decision and unchanged objective

After reviewing the completed [20-pair pilot](results_2026-10-15_pilot20/README.md),
the user requested all 100 seed IDs with 12 workers on 2026-10-15. This is a
post-pilot expansion, not a claim that 100 resamples were committed before
seeing the pilot results. The pilot remains immutable and separately visible.

The question is unchanged: does the operational sampling change improve
per-resample raw-MI ranking against the fixed reconstructed THP-1 perturbation
response reference, before significance filtering, DPI or consensus?

## Matched design and reuse

- Evaluate every seed ID from 1 through 100 in both arms: 200 total jobs.
- Retain the original 20 seed pairs (40 jobs), after verifying their frozen
  plan, executed commands, artifact paths and hashes. Run only the other 80
  seed pairs (160 new jobs). Reused outputs retain their original locations
  and executed commands; they are not represented as newly executed jobs.
- Before: the same pinned paper-era proxy, 121 draws with replacement.
  After: the same sampling-only backport, 97 distinct metacells at 80%.
- Keep the 17,971-gene, 121-NT-metacell expression matrix, original 6,951-SIG
  annotation, reference labels and all estimator settings fixed.
- Use the verified 272-eligible-source computation, not a new full-SIG run.
  The source-row equivalence argument applies only without DPI.
- Keep the fixed universe of 4,887,840 non-self pairs: 1,177,495 response
  positives and 3,710,345 operational negatives.
- Apply no MI significance cutoff, DPI or consensus. Rank each resample
  separately; do not average scores or pool edges across resamples.
- Keep **tie-expected TP@5,000** as the primary endpoint. The same secondary
  top-k budgets (1,000; 10,000; 50,000; 100,000) and full-ranking AUROC remain.
  Equal serialized-MI scores remain ties; the random precision stays fixed.
- Report paired differences, medians/IQRs and counts of improved, worse and
  unchanged resamples. Do not choose seeds, cutoffs or endpoints by outcome.

## Execution and preservation

The extension uses new orchestration code; the original `run_pilot.py`,
`score.py`, pilot plan and pilot artifacts are not rewritten. A new frozen
100-seed plan and an extension record bind the reused pilot and new execution
code. The extension validates the old and new scientific protocol before reuse.
Native inference still uses the same two unchanged executables.

From the repository root, the new wrapper is invoked as follows:

```powershell
python benchmarks/thp1_perturbseq/raw_mi/extend_pilot.py plan --pilot-plan runs/thp1_raw_mi_20261015/plan.json --out runs/thp1_raw_mi_20261015_full100
python benchmarks/thp1_perturbseq/raw_mi/extend_pilot.py run --plan runs/thp1_raw_mi_20261015_full100/plan.json --workers 12 --report-out runs/thp1_raw_mi_20261015_full100/report_20261015
```

Planning verifies the reused pilot without launching native jobs. The run
command schedules missing seeds and generates the report only after all
200 job records are complete. If necessary, `extend_pilot.py report --plan
PLAN --out FRESH_REPORT_DIRECTORY` generates a report from completed outputs
without running inference.

The local output directory is
`D:/GitHub/sjaracne_benchmark/runs/thp1_raw_mi_20261015_full100/`.
Large native adjacencies, score arrays and logs remain ignored and local.
The extension has its own lock and completion record; Windows status-file
replacement retries do not alter scientific calculations. Incomplete native
job directories require inspection rather than silent overwriting.

Use **12 workers**, as requested. At launch, the machine had 8 physical cores /
16 logical threads, approximately 93 GiB available WSL RAM and 656 GiB free
on D:. The completed pilot suggests approximately 30–45 minutes for the
160 new jobs, plus validation/reporting; this is an estimate, not a guarantee.

The reporting step must require all 100 matched pairs and consume the 40
original and 160 new metric artifacts explicitly. It must not launch inference
or silently omit failed/missing seeds. The completed report is linked above;
the pilot report is not rewritten or removed.

## What the extension can and cannot establish

One hundred resamples better describe the consistency and size of the effect
on these fixed inputs. They do not supply independent biological replication,
resolve reference-label uncertainty or demonstrate general improvement across
datasets. The 100-pair summary includes the pilot; it is not independent
confirmation of that pilot.

The two protocols differ in sample count and RNG consumption as well as
replacement. Response-positive pairs may be indirect, and operational negatives
are not verified absence of regulation. Any conclusion remains about raw-MI
response-associated ranking, not direct-edge accuracy or the complete
threshold/DPI/consensus workflow. Earlier mixed end-to-end results remain intact.
