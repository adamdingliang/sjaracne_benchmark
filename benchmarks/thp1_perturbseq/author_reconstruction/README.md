# THP-1 author-style Fig. 6a reconstruction

This workflow reconstructs a legacy baseline from public `GSM6858449` data and
the active [scMINER analysis code](https://github.com/jyyulab/scMINER_analysis/tree/c39f0aaffc22be81ae425adf9e7617504ae9ee33).
It is **not an exact reproduction** of the missing author-prepared inputs, and
it is not the earlier three-seed sampling pilot. No reconstruction results are
claimed until preparation, all bootstrap jobs, consensus and scoring complete.
This baseline contains no PR70 sampling change, PR71 null calibration, or
minimum-recurrence cutoff.

The reference measures perturbation-induced expression responses. A positive
response does not prove a direct regulatory edge; absence from this reference
does not establish that an inferred edge is biologically false.

## What is known, and what is reconstructed

| Step | Public evidence / reconstruction used here |
| --- | --- |
| Input | Conventional CRISPRi THP-1 screen, `GSM6858449`; untransformed counts are read from H5AD `/raw/X`, not its normalized `X` or the FR-Perturb CSV. |
| QC | The paper names scater QC. Exact author flags/intermediate selections are unavailable. Default reconstruction uses 3 MADs, two-sided count/detected-gene outliers, upper-tail mitochondrial outliers, no log transformation of QC metrics, and genes detected in at least two QC-passing cells. |
| Guides | Reconstruction accepts one distinct collapsed target, including repeated guides to that target. Distinct-target and control-plus-target labels are excluded. Original guide preprocessing is unavailable. |
| Normalization | Paper specifies log2(CPM+1). Reconstruction defaults to libraries summed across all raw genes before the detection filter. The original denominator is unknown; no truth-driven choice between `raw` and `filtered` is made. |
| Inference cells | QC-passing pure non-targeting cells only, pooled across replicates. All genes with NT expression are retained; there is no top-2,000-gene panel or assayed-source-only hub restriction. |
| Metacells | Paper: SuperCell 1.0, gamma 20, 10 PCs. Pinned core sources use their recorded defaults; seed 12345 is a reconstruction choice, not a recovered author seed. Expression is the unweighted mean of supplied log2(CPM+1), not log-transformed mean raw counts. |
| Inference hubs | Public scMINER generator uses `isSIG == TRUE`; combined TF/SIG annotations remain included. |
| Reference sources | Active author analysis uses strict `funcType == 'SIG'`. Reconstruction additionally requires at least 20 QC-passing perturbed cells and self `logFC.NT < -0.1`; the missing eligibility intermediate cannot be recovered exactly. |
| Response positives | `scran::findMarkers()` per perturbation versus NT, package defaults, no FDR filter; strict `abs(logFC.NT) > 0.25` follows the active author code. |
| Native runtime | SJARACNe 0.2.1, commit `2922ec9a57d3da4e88b849b840643f543f49807c`, is a paper-era proxy supported by a public scMINER example, not the known original THP-1 executable. |
| Bootstrap | 100 runs, seeds 1–100, legacy full-size sampling **with replacement**, AP depth 40 and DPI tolerance 0. `p_b = 1e-7` is inferred from the paper-era wrapper default; the original THP-1 bootstrap command is unavailable. No numeric MI override is supplied. |
| Consensus | Primary `p_c = 0.01` follows the [paper methods](https://www.nature.com/articles/s41467-025-59620-6). Secondary `p_c = 0.001` follows the author analysis folder label `sig_0.001`; that label does not establish `p_b = 0.001`. Both use the **same 100 adjacency files**, with the original 0.2.1 probability-based consensus script, not K. |
| Score population | Full emitted SIG consensus edge list, not restricted to perturbation-eligible sources. Positives are reference membership; every other emitted pair is negative for this author-style score. |

Historical generator defaults differ: pinned scMINER v1.0.0 emits `p_c=1e-5`,
while later generators distinguish already-aggregated versus internally
aggregated inputs. None recovers the missing THP-1 generation command. The two
consensus cutoffs above are declared provenance alternatives, not a sweep to
select the best published score.

## Environment and external files

Keep the H5AD, workbook, resources, native source/build, R environment and
generated outputs outside Git, under the paths below or equivalent locations.
Existing inputs are read-only. Download/preparation/publication/scoring output
directories must be fresh; only the native runner has verified resume support.

Python needs the dependencies in the parent `requirements.txt`; the examples
use the existing Windows Miniconda interpreter. Native inference uses WSL
Ubuntu. R is isolated at `_datasets/THP1_reconstruction/toolchain/r44`, with
the paper-version overlay at `toolchain/paper_r_library`.

The requested overlay versions are scran 1.32.0, scater 1.32.1 and pROC 1.18.5.
Other dependencies are the recorded prebuilt Bioconductor 3.20 environment,
**not a fully historical Bioconductor 3.19 dependency lock**. The overlay
installation manifest and preparation `sessionInfo.txt` record what actually
ran. Preparation refuses named scran/scater mismatches by default; using
`--allow-version-mismatch TRUE` changes the reconstruction and records that
deviation.

For a fresh isolated environment, the provisioning request used here is below
(WSL Bash; `micromamba` 2.9.0 is obtained from its official release). These
top-level constraints do not freeze all transitive package versions:

```bash
thp1_base=/mnt/d/GitHub/_datasets/THP1_reconstruction
"$thp1_base/toolchain/micromamba" create \
  --root-prefix "$thp1_base/toolchain/mamba-root" \
  --prefix "$thp1_base/toolchain/r44" \
  --channel conda-forge --channel bioconda \
  --strict-channel-priority --override-channels --yes \
  r-base=4.4 bioconductor-scran=1.34 bioconductor-scater=1.34 \
  bioconductor-singlecellexperiment bioconductor-rhdf5 bioconductor-hdf5array \
  bioconductor-delayedmatrixstats=1.28 bioconductor-sparsematrixstats=1.18 \
  r-jsonlite r-digest r-igraph r-rann r-plyr r-irlba r-rcpp r-matrix \
  r-proc r-prroc make compilers
```

Place the official source archives `scran_1.32.0.tar.gz`,
`scater_1.32.1.tar.gz` and `pROC_1.18.5.tar.gz` in
`toolchain/paper_archives` before the overlay installation below. Their actual
SHA256 values are recorded by `install_paper_packages.R`; the helper does not
download or install into an existing user/system R environment.
`DelayedMatrixStats` and `sparseMatrixStats` are explicit prerequisites of the
older scran overlay; they must be present before installing its source archive.

Use the pristine 0.2.1 source/build at
`sources/SJARACNe-v0.2.1`. Its `build_record.json` records the pinned Git commit,
literal-LF export, compiler, build command, source verification and hashes.
The runner requires that record and checks the binary, original consensus
script and both configuration files against it. A rebuilt binary needs a new
verified build record; do not reuse an old binary hash.

## Reproducible stages

The following examples are PowerShell, executed from this repository. Change
the variables together if using another workspace. Do not point these commands
at the earlier pilot output directory.

```powershell
$thp1_python = 'C:\Users\adamd\miniconda3\python.exe'
$thp1_code = 'D:\GitHub\SJARACNe\benchmarks\thp1_perturbseq\author_reconstruction'
$thp1_base = 'D:\GitHub\_datasets\THP1_reconstruction'
$thp1_data = 'E:\SpaGRN\SJARACNe\Perturb-seq\THP1_GSM6858449'
$thp1_code_linux = '/mnt/d/GitHub/SJARACNe/benchmarks/thp1_perturbseq/author_reconstruction'
$thp1_base_linux = '/mnt/d/GitHub/_datasets/THP1_reconstruction'
$thp1_data_linux = '/mnt/e/SpaGRN/SJARACNe/Perturb-seq/THP1_GSM6858449'
$thp1_mamba_linux = "$thp1_base_linux/toolchain/micromamba"
$thp1_env_linux = "$thp1_base_linux/toolchain/r44"
$thp1_library_linux = "$thp1_base_linux/toolchain/paper_r_library"
```

1. Fetch the pinned annotation and three official SuperCell core sources;
export H5AD metadata without copying counts; freeze the available publication
points. Skip an already completed verified stage instead of overwriting it.

```powershell
& $thp1_python "$thp1_code\fetch_resources.py" --output "$thp1_base\resources"
& $thp1_python "$thp1_code\export_metadata.py" `
  --h5ad "$thp1_data\GSM6858449_KD_conventional.h5ad" `
  --output "$thp1_base\metadata"
& $thp1_python "$thp1_code\extract_publication.py" `
  --workbook "$thp1_data\Source_Data_Figure_6.xlsx" `
  --out "$thp1_base\publication"
```

2. Install the paper-version overlay, then prepare the metacell matrix, full
SIG hubs and strict-SIG perturbation-response positives. Defaults are recorded
in `prepare_manifest.json`; the command explicitly repeats consequential
reconstruction choices.

```powershell
& wsl.exe -d Ubuntu -- $thp1_mamba_linux run --prefix $thp1_env_linux `
  env "R_LIBS_USER=$thp1_library_linux" Rscript `
  "$thp1_code_linux/install_paper_packages.R" `
  "$thp1_base_linux/toolchain/paper_archives" $thp1_library_linux

& wsl.exe -d Ubuntu -- $thp1_mamba_linux run --prefix $thp1_env_linux `
  env "R_LIBS_USER=$thp1_library_linux" Rscript `
  "$thp1_code_linux/prepare_author.R" `
  --h5ad "$thp1_data_linux/GSM6858449_KD_conventional.h5ad" `
  --metadata-dir "$thp1_base_linux/metadata" `
  --resources-dir "$thp1_base_linux/resources" `
  --output "$thp1_base_linux/prepared_author" `
  --qc-mad 3 --qc-log-counts FALSE --min-detected-cells 2 `
  --min-perturbed-cells 20 --self-logfc -0.1 --response-logfc 0.25 `
  --gamma 20 --n-pc 10 --seed 12345 --cpm-library raw
```

3. Inspect the immutable 100-job plan, run bootstraps, then run both original
consensus cutoffs. Use the **completed** preparation manifest for this full
pipeline; scoring requires completed response preparation. The runner also
accepts `inference_inputs_ready.json` for a separate staged inference-only run,
but it cannot silently replace that frozen context on resume.

```powershell
$thp1_source = "$thp1_base\sources\SJARACNe-v0.2.1"
$thp1_run_args = @(
  '--expression', "$thp1_base\prepared_author\expression.exp",
  '--hubs', "$thp1_base\prepared_author\hubs.txt",
  '--prepare-manifest', "$thp1_base\prepared_author\prepare_manifest.json",
  '--out', "$thp1_base\legacy_0.2.1",
  '--binary', "$thp1_source\SJARACNe\bin\sjaracne.exe",
  '--config', "$thp1_source\SJARACNe\config",
  '--consensus-script', "$thp1_source\SJARACNe\bin\create_consensus_network.py",
  '--component-manifest', "$thp1_source\build_record.json",
  '--python', $thp1_python,
  '--bootstrap-count', '100', '--bootstrap-p', '1e-7',
  '--consensus-p', '0.01', '0.001', '--npar', '40', '--workers', '2'
)
& $thp1_python "$thp1_code\run_legacy.py" plan @thp1_run_args
& $thp1_python "$thp1_code\run_legacy.py" bootstrap @thp1_run_args
& $thp1_python "$thp1_code\run_legacy.py" consensus @thp1_run_args --resume
```

The Windows consensus interpreter needs NumPy, SciPy and pandas. The native
ELF executable is invoked through WSL automatically. `--consensus-wsl` is
available if instead supplying a Linux Python interpreter with those packages.
For a performance smoke test, use a **different fresh output directory** and
`--bootstrap-count 1`; that is not the 100-bootstrap baseline.

Native outputs are `adj/bootstrap_001.adj` through `bootstrap_100.adj`.
`consensus_pc1e-02/edges.tsv` and `consensus_pc1e-03/edges.tsv` are exact copies
of the corresponding original 3-column consensus output, including its order
and four-decimal MI values. The runner does not impose a new edge sort.
`run_manifest.json` binds preparation expression/hub hashes, actual paths,
runtime/config/script hashes, parameters, completed artifacts and attempt logs.
Failed attempts are retained; unknown existing outputs are not adopted or
overwritten. A stale `.runner.lock` requires inspecting whether its process is
still running before any manual recovery.

4. Score each declared consensus alternative with the original R metric
definitions and compare the available published points. Both scoring output
directories must be fresh.

```powershell
foreach ($thp1_pc in @('1e-02', '1e-03')) {
  & wsl.exe -d Ubuntu -- $thp1_mamba_linux run --prefix $thp1_env_linux `
    env "R_LIBS_USER=$thp1_library_linux" Rscript `
    "$thp1_code_linux/score_author.R" `
    "$thp1_base_linux/legacy_0.2.1/consensus_pc$thp1_pc/edges.tsv" `
    "$thp1_base_linux/prepared_author/reference_positive_edges.tsv" `
    "$thp1_base_linux/publication" `
    "$thp1_base_linux/score_pc$thp1_pc" `
    "$thp1_base_linux/legacy_0.2.1/run_manifest.json"
}
```

## Automatic durable completion

For the current result-root layout, `run_full_baseline.py` is an alternative
to manually launching stages 3–4. It requires completed preparation at
`prepared/`, frozen publication points at `publication/`, a passing
`independent_audit.json`, and an already-started separate one-bootstrap run at
`legacy_smoke/run_manifest.json`. It waits for that actual smoke test to pass,
then launches a fresh 100-bootstrap legacy run, both original consensuses, and
the scoring/comparison helper. Do not run it alongside a manual native run
using the same output paths.

```powershell
$thp1_result_root = 'D:\GitHub\SJARACNe\benchmarks\thp1_perturbseq\results\author_reconstruction_20261011'
& $thp1_python "$thp1_code\run_full_baseline.py" `
  --result-root $thp1_result_root --assets-root $thp1_base --workers 8
```

The process can be launched in the background by the operator. Its fresh
`driver/status.json` records its PID, current stage and active child PID;
stage logs are retained in `driver/`. Completed output is
`comparison/REPORT.md` and `comparison/summary.json`, with both scored edge
pools and plots underneath. Neither driver nor comparison helper overwrites
or resumes its own existing output directory. If a stage fails, inspect its
status/logs; native `run_legacy.py` checkpoints support explicit manual resume
with unchanged settings. Do not delete a live process's lock or outputs.

If the native 100-run process is already managed separately, use only
`complete_baseline.py`. It can wait for completion with 30-second polls and
then score/report automatically; it never starts or retries native inference.
The output directory must be fresh, and an observed native failure terminates
completion rather than being ignored.

```powershell
& $thp1_python "$thp1_code\complete_baseline.py" `
  --run-manifest "$thp1_result_root\legacy\run_manifest.json" `
  --prepared-dir "$thp1_result_root\prepared" `
  --publication-dir "$thp1_result_root\publication" `
  --audit-file "$thp1_result_root\independent_audit.json" `
  --out "$thp1_result_root\comparison" `
  --wsl-r-env $thp1_env_linux --wsl-r-library $thp1_library_linux `
  --wait-for-run
```

The helper requires the independent PASS audit to bind this completed
preparation; exactly 100 completed legacy seeds and both declared consensus
artifacts must match the same prepared inputs. It checks R scorer input/output
hashes, then writes published-versus-reconstructed TP/EPR at 1,000, 5,000,
10,000, 50,000 and 100,000 edges plus the AUROC comparison. Its own
`status.json` distinguishes waiting/scoring/complete/failed. It does not launch
an after-PR70 arm or choose parameters from the comparison.

### Recovering the interrupted Windows/WSL native stage

`resume_full_baseline.py` is a separate recovery helper for an interrupted
`run_full_baseline.py` native stage. It does not modify the frozen stage code
or reuse the old driver directory. It requires the old driver/child PIDs and
all native WSL workers to be absent, verifies the original source, input and
completed-output hashes, and preserves the old manifest and stale runner lock
inside a fresh recovery directory. The original native command is replayed
with only `--resume` added; completed bootstraps are skipped and interrupted
attempt logs are retained. Both original consensuses and scoring follow
automatically. It refuses existing comparison output rather than adopting it.

```powershell
& $thp1_python "$thp1_code\resume_full_baseline.py" `
  --result-root $thp1_result_root --assets-root $thp1_base `
  --recovery-name driver_resume_20261012 --verify-only

& $thp1_python "$thp1_code\resume_full_baseline.py" `
  --result-root $thp1_result_root --assets-root $thp1_base `
  --recovery-name driver_resume_20261012
```

The first command is read-only and checks the native checkpoint; the second
performs recovery and also validates the response/publication scoring inputs
before launching children. Use a fresh recovery name. Its
`<recovery-name>/status.json` records the new coordinator and child PIDs and
is the status authority for the recovered execution. The old
`driver/status.json` is preserved interruption evidence, not live status.
For background execution, launch the helper as a detached hidden Windows
process with separate stdout/stderr logs. Detaching is not protection from
Windows/WSL shutdown, sleep or a future restart; checkpoints remain the
recovery mechanism. Never run two coordinators against the same baseline.

## Metric interpretation and verification

### Primary eligible-source predictions and two secondary views

The current reporting choice is **eligible-source emitted predictions as
primary**, with full emitted SIG edges and the fixed eligible universe as
secondary views. This changes scoring populations only, not the full SIG
inference, response labels, DPI or consensus settings. The original
author-style scoring stage below is retained as a compatibility result.

See [Three-population scoring](THREE_POPULATION_SCORING.md) for the separate
additive scorer, reproducible command, MI-tie handling, population-specific
random expectations, and conditional-versus-fixed-reference denominators.
The three-population report does not start the after-sampling arm or modify
the frozen baseline artifacts.

### Supplementary fixed-universe sensitivity, specificity and AUROC

`score_fixed_universe.py` adds a separate evaluation without changing
`score_author.R` or its saved results. The frozen universe is eligible assayed
strict-SIG sources intersected with inference hubs/genes, crossed with all
frozen NT inference genes, excluding self-pairs. Unassayed-source predictions
are excluded from this supplementary evaluation, not labeled negative.

Both consensus networks use the same positive and negative denominators.
Emitted pairs rank by their raw consensus MI, with equal MI treated as a tie.
All omitted pairs share one bottom score below every emitted pair, including
emitted MI=0. This is an explicit evaluation policy, not an estimate of missing
MI. ROC thresholds advance by whole tie groups, then include the omitted
group. AUROC is verified using both ROC integration and positive-negative
pair counting. A large omitted tied group can dominate this AUROC; it is not
unthresholded all-pair MI AUROC.

The original ordinal **AUROC within emitted edges** is preserved separately.
The two AUROCs differ in both evaluation population and MI-tie handling, and
must not be presented as interchangeable. New top-k rows are ranked within
eligible-source predictions, not the original all-source network. Split ties
have expected fractional TP and a min/max range; k above the number of
eligible emitted pairs is unavailable rather than padded with missing pairs.

```powershell
& $thp1_python "$thp1_code\score_fixed_universe.py" `
  --prepared-dir "$thp1_result_root\prepared" `
  --run-manifest "$thp1_result_root\legacy\run_manifest.json" `
  --author-comparison-dir "$thp1_result_root\comparison" `
  --out "$thp1_result_root\fixed_universe_20261012_verified"
```

The scorer refuses existing output and checks frozen preparation, native
consensus and preserved author-score hashes. It writes `universe.json`,
`metrics.json`, whole-tie-group ROC tables, top-k tables and `REPORT.md` to a
fresh supplementary directory. It launches no inference or after-sampling arm.
Keep this exact universe/reference fixed for any subsequent matched comparison.
The calculation uses NumPy; the synthetic tests additionally use scikit-learn
for an independent AUROC check. The completed workstation calculation used
Python 3.13.0, NumPy 2.4.4 and scikit-learn 1.8.0.

### Original author-style scoring

`score_author.R` preserves author-style R decreasing-MI sorting, ordinal
edge ranks for `pROC::roc(..., direction='>')`, and the seed-1 R shuffle of
the **same emitted edge pool**. TP and EPR are evaluated every 1,000 ranks;
`EPR(k) = TP_method(k) / TP_shuffle(k)`, with undefined zero-denominator values
reported as NA. This is not the earlier pilot's expected-random EPR or
tie-grouped/common-universe MI AUROC. Reported MI ties and split-tie boundaries
are retained/audited rather than converted to a different ROC definition.

The publication workbook has TP/EPR points but only a partial scMINER ROC
segment. It cannot supply an independently reconstructed full published
AUROC; the comparison reports the paper's rounded 0.75 separately. Output
`metrics.json`, `comparison_to_publication.tsv`, `ranked_curves.tsv`,
`roc_curves.tsv` and `comparison_to_fig6a.png` describe the reconstructed
baseline, not a claim that missing author intermediates have been recovered.

To run the small Python protocol tests without native inference:

```powershell
& $thp1_python -m unittest discover -s $thp1_code -p 'test_*.py' -v
```

Do not select parameters, labels or a consensus alternative solely because it
matches the published curves. Any subsequent PR70 before/after comparison
needs its own matched protocol and declared baseline after this reconstruction
has been evaluated.

The user-selected conditional follow-up is documented in
[SAMPLING_COMPARISON.md](SAMPLING_COMPARISON.md): apply only PR70's native
sampling additions to this same paper-era code, with a separate build and
output directory. On 2026-10-12 the user authorized the after arm using the
fixed reconstructed reference despite the known Figure 6a mismatch. A
hash-bound decision still records that scope; this does not establish exact
publication reproduction or alter the frozen baseline artifacts.

## Completed matched sampling comparison

On 2026-10-13, both completed consensus networks from the sampling-only
80%-without-replacement arm were scored against the frozen reconstructed
response reference. The primary view remains eligible-source emitted
predictions. The result is **mixed, not an overall improvement**: slightly
higher top-5,000 TP counts coexist with lower AUROC, EPR and overall
response-positive coverage. See the results and limitations in
[SAMPLING_COMPARISON.md](SAMPLING_COMPARISON.md) and the
[complete comparison report](../results/author_reconstruction_20261011/sampling_comparison_20261013/REPORT.md).

`score_sampling_after.py` scores already completed native output; it does not
launch inference. It verifies the sampling-only build/protocol, all 100
checkpoints, both consensus artifacts and the common prepared inputs before
calling the unchanged R, fixed-universe, three-population and eligible-EPR
helpers. It does not relax the baseline-only guard in `complete_baseline.py`.
The fresh output contains `scoring_manifest.json`, `status.json`, stage logs,
all component scores and `summary.json`. Its manifest explicitly identifies
the after arm because some reused historical report templates retain
baseline-only labels.

The following commands recompute scores and plots into **new** directories.
They assume the completed current result-root layout and the variables above;
choose different output names if these repeat directories already exist.
The original completed outputs are `sampling_scoring_20261013/` and
`sampling_comparison_20261013/`, which must not be overwritten.

```powershell
$thp1_score_out = "$thp1_result_root\sampling_scoring_repeat"
$thp1_plot_out = "$thp1_result_root\sampling_comparison_repeat"
& $thp1_python "$thp1_code\score_sampling_after.py" `
  --result-root $thp1_result_root --out $thp1_score_out `
  --wsl-r-env $thp1_env_linux --wsl-r-library $thp1_library_linux

& $thp1_python "$thp1_code\plot_sampling_comparison.py" `
  --before-metrics "$thp1_result_root\three_populations_20261012" `
  --after-metrics "$thp1_score_out\three_populations" `
  --before-epr "$thp1_result_root\eligible_epr_20261012" `
  --after-epr "$thp1_score_out\eligible_epr" `
  --prepared-dir "$thp1_result_root\prepared" --out $thp1_plot_out
```

The comparison verifies common reference/universe definitions, eligible-EPR
R/RNG settings and matched nonsampling settings; it recounts whole-MI-tie ROC
curves from the consensus edges. It writes deterministic PNG/PDF overlays,
all-population summaries, ranked/ROC coordinates, `comparison.json`,
`REPORT.md` and an input/output hash manifest. TP plots show MI-tie expected
counts with attainable ranges; EPR preserves integer TP divided by the actual
own-pool seed-1 shuffled TP. Omitted pairs are excluded from the primary ROC
and included only in the separately labeled fixed-universe analysis. No curve
is padded beyond its emitted pool.
