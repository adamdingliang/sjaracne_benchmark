# THP-1 scoring populations

The primary evaluation is **only eligible-source predictions**. Retain full
emitted SIG predictions and the fixed eligible universe as secondary views.
All three use the same frozen perturbation-response labels. None measures
proven direct regulation, and inference continues to use the full SIG hubs.

| Population | Included pairs | Interpretation |
| --- | --- | --- |
| Eligible emitted (primary) | Final consensus edges intersected with the fixed eligible universe | Conditional ranking and precision among experimentally assessable predictions |
| Full emitted (secondary) | All final SIG consensus edges | Compatibility view; reference nonmembers include unassessed sources |
| Fixed eligible universe (secondary) | Eligible perturbed sources x frozen inference genes, excluding self-pairs | Selection plus ranking, including omitted response-positive pairs |

Use consensus MI with ties retained consistently. Preserve the older author
ordinal AUROC separately. For a boundary MI tie, top-k TP is the expectation
under uniform within-tie ordering and also reports its attainable range.
Do not pad top-k beyond the number of emitted pairs with arbitrary ordering
of omitted pairs. Default k values remain 1,000, 5,000, 10,000, 50,000 and
100,000; unavailable rows are explicit.

Population-specific conditional recall/specificity use that population's
positive/nonmember denominators. Fixed-reference sensitivity always uses the
frozen eligible reference-positive denominator. Report emitted edge count
and fixed-reference coverage with the primary AUROC: dropping hard pairs can
improve conditional AUROC without improving recovery.

The random comparator must change with the population. Precision lift uses
the exact uniform-selection expectation, `TP_at_k / (k * P_population/N_population)`.
This is an EPR against random expectation, not the authors' original EPR
against a realized seed-1 permutation. Existing author-style EPR results are
preserved, not overwritten or relabeled.

`score_three_populations.py` independently recounts the consensus networks,
checks the frozen preparation/run/score hashes and independently verified
eligible/fixed AUROCs, and writes a fresh report and machine-readable JSON.
It changes neither inference nor the old scorers or frozen reports.

From this directory, with the existing benchmark interpreter:

```powershell
$thp1_result = 'D:\GitHub\SJARACNe\benchmarks\thp1_perturbseq\results\author_reconstruction_20261011'
& 'C:\Users\adamd\miniconda3\python.exe' .\score_three_populations.py `
  --fixed-metrics "$thp1_result\fixed_universe_20261012_verified\metrics.json" `
  --prepared-dir "$thp1_result\prepared" `
  --run-manifest "$thp1_result\legacy\run_manifest.json" `
  --out "$thp1_result\three_populations_20261012"
```

The current report is a reconstructed legacy baseline, not an exact Figure
6a reproduction or a completed before/after comparison. The after-sampling
arm has not been launched by this scoring step. Keep reference/universe,
declared k values, tie handling and random-comparator definitions unchanged
when scoring that future arm.

## Realized shuffled EPR within eligible-source predictions

`score_eligible_epr.R` separately calculates the author-style realized EPR
inside the eligible emitted pool. It filters the saved author-ranked edge
list to the frozen eligible universe, preserving the existing row order.
For each consensus network, it resets R seed 1 and uniformly permutes that
entire eligible list without replacement. EPR is integer prefix TP divided
by the actual shuffled prefix TP, not divided by its theoretical expectation.

MI boundary ties are flagged. Tie-expected TP, its attainable range and the
corresponding alternative ratio are saved separately. The analytic
expectation-based enrichment in the three-population report is unchanged.
The full 1,000-edge trajectory and the full-pool endpoint are saved; k above
the emitted count remains unavailable. Zero shuffled TP gives unavailable
EPR, not zero or infinity.

The command takes four positional paths: the completed three-population
`metrics.json`, the frozen preparation directory, the original author-score
comparison directory, and a fresh output directory. Use the existing isolated
R 4.4.3 environment with `jsonlite` and `digest`. It verifies bound input hashes
and eligible pool/positive counts before writing results, and never launches
inference or changes the original global scoring artifacts.

## Eligible-only Fig. 6a-style panels

`plot_eligible_fig6a.py` draws TP versus k, realized shuffled EPR versus k,
and ROC within emitted eligible edges. Both completed legacy consensus
alternatives are shown. It verifies the frozen scoring inputs, uses saved
integer TP/EPR checkpoints, and independently recounts the MI-tied eligible
ROC. The ROC diagonal is the random expectation, not the realized shuffled
curve. No omitted pairs enter the eligible ROC and no inference is launched.

```powershell
& 'C:\Users\adamd\miniconda3\python.exe' .\plot_eligible_fig6a.py `
  --result-root "$thp1_result" `
  --out "$thp1_result\eligible_fig6a_20261012"
```

The output directory must be new. Combined and individual PNG/SVG figures,
the eligible ROC coordinates and a provenance manifest are saved there.
These are reconstructed-baseline plots, not an exact paper reproduction or
evidence of improvement after the sampling change.
