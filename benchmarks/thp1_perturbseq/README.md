# THP-1 Perturb-seq walkthrough and sampling benchmark

This directory was imported from `adamdingliang/SJARACNe` into the dedicated
benchmark repository. SJARACNe remains the external inference engine; raw
data, native builds and the full historical run archive were not moved here.
The [migration record](../../docs/MIGRATION.md) explains the imported files
and the limits of historical path portability.

## Latest completed evidence

Both matched 100-bootstrap arms and their original probability-based
consensuses completed before this migration. The after arm is a sampling-only
PR70 backport to the paper-era baseline, not PR71 or minimum-recurrence
consensus. The reference is a reconstructed perturbation-response reference,
not direct-edge biological ground truth or an exact Fig. 6a reproduction.

- [Before/after consensus comparison](evidence/author_reconstruction_20261011/sampling_comparison_20261013/REPORT.md): eligible-source emitted predictions are primary; full emitted predictions and the fixed eligible universe are secondary. Precision improves modestly, while overall response-positive coverage falls and AUROC/EPR do not improve.
- [Individual post-DPI bootstrap diagnostic](evidence/author_reconstruction_20261011/bootstrap_tp_fp_20261013/REPORT.md): median precision increases from 27.78% to 37.35%, but median TP falls 50.50% and FP falls 68.34%. TP loss is already present before consensus.
- [Historical baseline versus Fig. 6a](AUTHOR_RECONSTRUCTION.md): the reconstruction does not reproduce the paper's numerical performance. That limitation remains unchanged by migration or the after-arm comparison.

The operational arms also differ in sample count and affine MI cutoff:
121 replacement draws / MI 0.136987 versus 97 distinct metacells / MI
0.155902, both at nominal bootstrap p=1e-7. They do not isolate replacement
alone. MI-cutoff tuning and new pre-DPI inference remain deferred.

## Exploratory notebooks

Open [01_data_and_figure6_walkthrough.ipynb](01_data_and_figure6_walkthrough.ipynb)
to understand the conventional CRISPRi dataset `GSM6858449` and the scMINER
Figure 6 source-data workbook. This is an exploratory notebook, not an
end-to-end reproduction or a comparison of SJARACNe versions.

The notebook covers AnnData structure, gene-name lookup, raw counts versus
normalized expression, guide assignments and controls, the separate
perturbation matrix, the FR-Perturb effect table, and Figure 6a's TP/EPR/ROC
coordinates. It checks the EPR calculation and explains the author-code path
from expression data to those summaries.

## Run

For basic QC, PCA, UMAP, Leiden clustering and marker exploration, open
[02_scanpy_exploration.ipynb](02_scanpy_exploration.ipynb). It adapts the
[Scanpy clustering tutorial](https://scanpy.scverse.org/en/stable/tutorials/basics/clustering.html)
to THP-1 rather than applying PBMC cell-type labels. The default is a seeded,
uniform 10,000-cell preview with two CPU threads; set `MAX_CELLS = None` for
the full screen or `NT_ONLY = True` for pure non-targeting controls.
Raw counts are read from `raw.X`, biological-replicate/channel/guide labels
are preserved, and safe-targeting controls remain separate from biological
targets. Exploratory filters/normalization are not the scMINER benchmark's
preparation, and result export/doublet detection are off by default.

The notebook also imports `Figure_6g,h` from `Source_Data_Figure_6.xlsx` and
audits its cell identifiers. These 4,602 labels belong to the separate
**GSE213282 PBMC CITE-seq experiment**, not the THP-1 screen; the original files
have zero exact cell-ID matches. It displays the labels on the workbook's own
published PBMC UMAP, clearly separated from the computed THP-1 UMAPs. It does
not transfer these labels to THP-1 or replace its embedding. Override the
workbook location with `SJARACNE_THP1_FIGURE6` if necessary.

The original workstation used `C:\Users\adamd\miniconda3\python.exe` with
Scanpy 1.11.5 and clustering dependencies. This is not a bundled environment;
use your own notebook kernel or prepare a new environment:

```powershell
python -m pip install -r benchmarks/thp1_perturbseq/requirements_scanpy.txt
python -m jupyterlab benchmarks/thp1_perturbseq/02_scanpy_exploration.ipynb
```

Do not install packages into an environment while its benchmark processes
are running. The new notebook does not invoke SJARACNe or modify its frozen
inputs, raw H5AD, or publication workbook. It performs no download or
automatic cell-type annotation.

Before the published-label audit was added, the default 10,000-cell path was
executed end-to-end with Scanpy 1.11.5 on 2026-10-12: all 18 code cells
completed without errors, and the source H5AD's
size/mtime were unchanged. Scrublet and large result export remained disabled.
An executed notebook with plots is retained in the unchanged external
SJARACNe archive under
`benchmarks/thp1_perturbseq/results/scanpy_exploration/validation_20261012_preview10000/`.
The later published-label audit and PBMC plotting cells were separately
executed against the actual workbook, all 66,283 THP-1 cell identifiers and
the default 10,000-cell preview. Both cells passed, eight lightweight notebook
tests passed, and the new plot was visually checked. The source H5AD's
size/mtime and the workbook's SHA-256/size/mtime were unchanged. The older
executed notebook predates this addition; rerun the existing source notebook
to see the new section. No additional notebook was created for this change.

Use Python 3.11 or newer with a Jupyter or VS Code Python notebook kernel.
Install the dependencies into the environment used by that kernel:

```powershell
Set-Location 'D:\GitHub\sjaracne_benchmark'
python -m pip install -r benchmarks/thp1_perturbseq/requirements.txt
$env:SJARACNE_THP1_DATA = 'E:\SpaGRN\SJARACNe\Perturb-seq\THP1_GSM6858449'
python -m jupyterlab benchmarks/thp1_perturbseq/01_data_and_figure6_walkthrough.ipynb
```

The notebook defaults to that Windows directory, or its `/mnt/e/...`
equivalent under WSL. Set `SJARACNE_THP1_DATA` to override it. The variable can
also point to the parent `Perturb-seq` directory. Files remain external to Git:

- `GSM6858449_KD_conventional.h5ad`
- `GSM6858449_KD_conventional_perturbations.txt.gz`
- `GSM6858449_KD_conventional_FRPerturb_effect_sizes.csv.gz`
- `Source_Data_Figure_6.xlsx`
- Optional: the three downloaded author `.Rmd` files and the source-data ZIP.

Inputs are opened read-only. The notebook does not download data, rewrite the
H5AD/workbook, run SJARACNe, or compute the authors' full differential-expression
analysis. It uses backed sparse access and small expression slices. It closes
the H5AD handle in its final code cell.

## Important limits

The downloaded workbook's `Figure_6a` sheet contains TP and EPR summaries, but
only a **partial scMINER ROC segment**, not the complete ROC or its Random
comparator. The notebook detects the missing coverage and does not report a
full AUROC from it. `Figure_6c` contains a representative subnetwork, not the
complete pooled edge list used for Figure 6a.

The public code references prepared `.RData` inputs that are not in the current
bundle. It saves R objects and PNG/PDF figures, but the inspected scripts do not
document the final XLSX export. Consequently, we can trace calculations and
check exported values, but cannot establish the exact workbook-packaging step
or claim an exact H5AD-to-Figure-6 reproduction.

The GEO FR-Perturb CSV is a different analysis from scMINER's
`scran::findMarkers` response labels. Neither perturbation responses nor guide
assignments establish direct regulatory interactions.

## Author-style Fig. 6a legacy reconstruction

[author_reconstruction](author_reconstruction/README.md) is the separate,
full-panel reconstruction started after reviewing the pilot's mismatches.
It explicitly rebuilds NT SuperCell metacells, the pinned scMINER regulator
annotation, the `scran::findMarkers` perturbation-response reference, and
100 legacy bootstrap/DPI networks with the original probability-based
consensus. It uses the authors' active R TP/EPR/ordinal-rank ROC definitions
and compares them with the published workbook values. PR70, PR71 and
minimum recurrence are not used in this legacy-baseline step.

This is a reconstruction, not recovery of the missing author intermediate
files. Unknown QC flags, guide preprocessing, exact network version and
invocation are recorded rather than treated as verified author settings.
The individual-cell pilot below remains separate and is **not** a Fig. 6a
baseline.

The completed 100-bootstrap baseline and TP/EPR/AUROC comparison are summarized
in [AUTHOR_RECONSTRUCTION.md](AUTHOR_RECONSTRUCTION.md). The preserved
full-emitted author-style baseline AUROC is 0.573906 versus the paper's
approximately 0.75; this is not the eligible-source AUROC. On 2026-10-12 the
user authorized the sampling-only after arm as a reconstructed benchmark
despite that mismatch. Its 100 bootstraps, both consensuses and scoring are
complete; the latest evidence is linked above. No inference was rerun during
repository migration.

## Matched PR70 sampling pilot

`prepare.py`, `benchmark.py`, and `metrics.py` implement a separate, opt-in
public-data benchmark of the three Figure 6a metric families: cumulative
reference-positive counts (TP@k), early precision ratio (EPR), and ROC/AUROC.
This does **not** reproduce the published network or its reported AUROC.
The raw H5AD and generated networks remain outside tracked Git files.

The completed three-seed pilot is summarized in [RESULTS.md](RESULTS.md).
It did not demonstrate an overall improvement: unthresholded MI AUROC rose
slightly, but post-DPI TP@1,000, EPR@1,000 and reported-edge AUROC declined.

The verified fork `develop` snapshot is
`1638e8f4eb3d7ffe5057922fa9f9bd1043d466ac`. Its runtime/configuration files are
identical to PR70-only `8c5f26c4fb5e05c7b280bcaa7d5a6461125a6aa3`.
The pre-PR70 comparison is `e59973a1891672a14f06d7847545c53368f3066c`.
PR71 and minimum-recurrence consensus are not used.

### Frozen preparation

The preparation script reads `raw.X` in sparse chunks and records source and
output hashes. Original files are never rewritten. The reconstructed protocol
is fixed before inference:

- QC uses unlogged library size and detected genes, with both-side cutoffs at
  median +/- 3 scaled MAD. Mitochondrial fraction uses the upper cutoff only.
  Scaled MAD is `1.4826 * median(abs(x - median(x)))`. The available paper/code
  does not establish these as the authors' exact QC transformations.
- Genes must be detected in at least two QC-retained cells. Each evaluated SIG
  source must have at least 20 retained, exactly single-guide cells and its own
  reconstructed effect must be strictly below -0.1.
- Expression is `log2(1 + 1e6 * raw_count / total_raw_counts_per_cell)`.
  Response effect is mean KD log-expression minus mean NT log-expression.
  Reference positives satisfy strict `abs(effect) > 0.25`, with no FDR filter,
  matching the **active effect-only rule**, not the missing author RData.
- Only non-targeting cells enter network inference. By default, targets are
  the 2,000 highest-variance genes in those control cells, union all eligible
  SIG sources. Selection never uses response labels or benchmark results.
- The inference/DPI hub panel is the same eligible, assayed SIG-source panel
  in both arms. It is not the missing author SIG annotation/full hub panel.

This is an individual-cell, reduced-panel pilot: no SuperCell aggregation,
no 100-run production consensus. Three seeds are exploratory repeated
subnetworks, not three independent biological datasets. Use `--top-targets 0`
to retain all detection-qualified genes for a later, larger analysis.

### Before/after design

The before arm uses an N-draw legacy bootstrap with replacement (`-r 1`). The
after arm uses `ceil(0.8*N)` distinct observations (`-u 80%`). Both use the same
prepared input, hub list, `Npar=40`, numeric MI cutoff, and final DPI epsilon=0.
Each seed is run directly for unthresholded pre-DPI MI, thresholded pre-DPI
edges, and post-DPI edges. Serialized low-precision MI is not replayed for DPI.

The common MI cutoff is frozen from the legacy affine formula at the after
arm's m and nominal p=1e-7. Both arms receive that **same explicit numeric
threshold**, avoiding two different sample-size-dependent cutoffs. This is
an engineering anchor, not a calibrated PR71 null probability. Supply an
explicit `--mi-cutoff` if choosing a different predeclared operating point.
Do not tune it against the response labels.

The comparison measures the operational PR70 change, including sample size
and native tie-noise behavior. Paired seed numbers do not imply identical
selected observations or identical noise realizations. It does not isolate
replacement alone from every other consequence of the new sampling path.

### Metric denominators

The report provides two views, not interchangeable scores:

1. **Reported-only:** rank emitted edges by MI and evaluate within that pool,
   as in the inspected Figure 6a code. EPR uses a seeded shuffle of the same
   edge list; an exact expected-random-precision version is also reported.
   NumPy's shuffle is not claimed to reproduce R's specific permutation.
2. **Common candidate universe:** every frozen eligible-source/selected-target
   nonself pair is evaluated. Unreported pairs receive score zero. Both arms
   have identical labels and random precision here. This view helps expose
   changes masked by different emitted-edge pools.

AUROC groups equal MI scores (half credit for positive-negative ties).
Top-k tie splits are flagged in `ranked_curves.json`. Undefined quantities
(e.g. zero shuffled positives or a single-class emitted pool) are null, not
silently zero. Reference-negative means below the response threshold, not
proof of no regulation. These response labels can include indirect effects.

### Run the pilot

Use the Python environment installed for the walkthrough. Native inference
requires a PR70-only SJARACNe binary. The existing verified Linux builds can
be run through WSL Ubuntu from Windows. These historical workstation paths
refer to external engine/configuration files, not files included in this
repository. Supply your own matching inputs and build paths on another
machine. Use a fresh external output directory; these commands run new
inference and are not needed to read the imported evidence:

```powershell
Set-Location 'D:\GitHub\sjaracne_benchmark'
$python = 'C:\Users\adamd\miniconda3\python.exe'
$out = 'D:\GitHub\_datasets\THP1_reconstruction\my_fresh_pilot'
& $python benchmarks/thp1_perturbseq/prepare.py `
  --h5ad 'E:\SpaGRN\SJARACNe\Perturb-seq\THP1_GSM6858449\GSM6858449_KD_conventional.h5ad' `
  --sig-list 'D:\GitHub\SJARACNe-pr66-develop\SJARACNe\config\SIG_list.txt' `
  --output $out
& $python benchmarks/thp1_perturbseq/benchmark.py run --out $out `
  --binary 'D:\GitHub\_datasets\DREAM5_Network1\benchmark_pr70_small\build_post\SJARACNe\bin\sjaracne.exe' `
  --pre-binary 'D:\GitHub\_datasets\DREAM5_Network1\benchmark_pr70_small\build_pre\SJARACNe\bin\sjaracne.exe' `
  --config 'D:\GitHub\SJARACNe-pr66-develop\SJARACNe\config' `
  --wsl-distro Ubuntu --seeds 1 2 3 --workers 2
& $python benchmarks/thp1_perturbseq/benchmark.py score --out $out
```

Use a fresh output path. The scripts refuse overwrites. `run_manifest.json`
records an interrupted/failed run explicitly and scoring refuses incomplete
runs. The runner verifies frozen inputs, binary/configuration hashes and every
native adjacency hash. The before binary is optional: the PR70-only binary
retains the unchanged `-r 1` compatibility path. The verified build hashes are
pinned in the runner. For a freshly compiled PR70-only binary, explicitly use
`--allow-unpinned-binary`; its provenance is then recorded as unverified rather
than claiming the pinned source/build.

On Linux, omit `--wsl-distro` and supply native paths. To build from source,
check out PR70-only commit `8c5f26c` in an isolated clone/worktree and run
`make -C SJARACNe -j2`; do not use the current feature-branch binary, which
also contains PR71.

Outputs include `REPORT.md`, `metrics.json`, `ranked_curves.json`, and
`tp_epr_roc_reported.png` / `tp_epr_roc_common.png`. The plots use the analytic
expected random precision to avoid noisy single-shuffle denominators; both
EPR variants are retained in the curve data. Native `.adj` files/logs and
frozen preparation tables are kept in the chosen external output directory.

The imported author-style runners and evidence JSON preserve historical
absolute paths and hashes. They are not automatically portable merely
because the scripts are copied here. Keep the original archive and frozen
helpers unchanged; parameterize fresh runs rather than editing old manifests
or disabling hash guards. See [data policy](../../docs/DATA.md) and
[licensing/attribution](../../docs/LICENSING.md) for external dependencies and
the separate treatment of engine-derived patch material.

Run the small synthetic tests without real data or native inference:

```powershell
& $python -m unittest discover -s benchmarks/thp1_perturbseq -p 'test_*.py' -v
```

## Sources

- [GEO sample GSM6858449](https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM6858449)
- [Yao et al., compressed Perturb-seq](https://www.nature.com/articles/s41587-023-01964-9)
- [scMINER paper](https://www.nature.com/articles/s41467-025-59620-6)
- [Pinned author analysis directory](https://github.com/jyyulab/scMINER_analysis/tree/c39f0aaffc22be81ae425adf9e7617504ae9ee33/network_inference/CROP_Seq_GRN_evaluation/Yao_Regev_Cleary)

