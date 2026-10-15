# DREAM5 Network 3: E. coli benchmark dataset

This adds a **real-expression, experimentally supported TF-target reference**
alongside the simulated DREAM5 Network 1 benchmark. Data preparation and
validation are implemented here. The [approved three-seed pilot](PLAN_2026-10-15.md)
compares the retained legacy sampler with 64%, 80% and 90% fixed-size sampling.
The [completed results](RESULTS.md) show higher post-DPI AP/precision but not
uniformly improved recall or raw AUROC.
This is an external benchmark dataset, not an engine dependency
or a unit-test fixture containing native inference outputs.

## Inputs and reference

The released expression matrix contains **805 microarray profiles and 4,511
genes**. It is not RNA-seq or single-cell data. The supplied candidate-regulator
list contains **334 TFs**. Preserve all released genes, profiles and candidate
TFs; no regulator list or inference-gene selection is derived from the reference.

The reference contains **152,280 explicitly labeled directed non-self pairs**:
2,066 positives and 150,214 operational negatives. DREAM5 selected the positive
E. coli interactions using RegulonDB's strong-evidence annotations. Strong
evidence concerns experimental support, not MI magnitude, effect size or a
benchmark p-value. The reference is incomplete and does not establish that
every zero-labeled pair is biologically absent. See the
[DREAM5 paper, Online Methods](https://compbio.csail.mit.edu/marbach/papers/Marbach2012b.pdf).

**Inference scope and scoring scope differ.** The labeled universe is
141 source TFs by 1,081 target nodes, excluding 141 self-pairs. All 334 TFs by
all other released genes would yield 1,506,340 pairs; the remaining 1,354,060
pairs are **unlabeled and excluded from scoring**, not false positives. Keep
the full candidate-TF list for inference, especially when DPI is enabled.

## Included files and size

[data/Network3](data/Network3) contains byte-identical copies of five original
archive members: expression, candidate TFs, gold-standard labels, chip features
and gene-ID mapping. The latter two preserve experiment/identity context; they
are not used to select features or alter labels. Two original archive README
files are also retained, with descriptive destination filenames. Exact member
names, byte counts and SHA256 digests are in [data/provenance.json](data/provenance.json).

The three essential files total 38,758,696 bytes (36.96 MiB); metadata and
README copies add about 70 KiB. The generated `.exp` is **not** also stored in
Git, avoiding a second large expression copy. The complete source ZIP is not
vendored. See [source terms and attribution](DATA_LICENSE.md).

## Validate and prepare

Use Python 3.11+; this preparation code uses only the standard library and
does not build or run SJARACNe, download data, normalize expression, or score
predicted networks. Run from this repository's root:

```powershell
python benchmarks/dream5_network3/prepare.py verify
python benchmarks/dream5_network3/prepare.py prepare --out runs/dream5_network3_prepared
python scripts/check_benchmarks.py --group dream5_network3
```

The bundled data is the default. `--data-root PATH` selects another copy of
the same original Network3 directory. Alternatively, use
`--archive PATH_TO_1_Challenge_Data_Supplement.zip`; the published archive MD5
and the selected members' SHA256 values are checked before use. Only exact
known ZIP members are read; arbitrary archive paths are not extracted.

Preparation requires a fresh child directory under this repository's ignored
`runs/`. It writes
`dream5_net3.exp`, `all334_tfs.txt` and `provenance.json` under `--out`.
The expression table is transposed to SJARACNe's gene-by-profile format using
the original numeric strings, with no re-normalization or rounding. The
generated hub list uses literal LF newlines for native-parser compatibility.
Source files are never rewritten.

Validation checks source digests, dimensions, identifier alignment, finite
expression values, the TF list, binary/unique/non-self reference pairs and the
fixed labeled universe. The original matrix, not the gold file, determines
which genes are retained.

## Matched sampling and DPI pilot

The [prospective protocol](PLAN_2026-10-15.md) fixes three seeds, four sampling
arms and five stages: raw MI, nominal affine filtering before/after DPI, and a
common numerical MI cutoff before/after DPI. Every stage runs directly from
expression; serialized adjacencies are not replayed through DPI. The primary
comparison is **80% without replacement versus legacy, post-DPI AP at nominal
p=1e-7**. No PR71 calibration or consensus is included. Read the protocol for
the explicit-label universe, tie handling and limitations.

Use the same historical PR70 binary/configuration as Network 1, not an arbitrary
new build. The planner rejects a different executable, configuration, input or
source hash. Preparation uses only Python's standard library; inference
validation/scoring additionally requires NumPy; plotted reports require
Matplotlib. From the repository root:

```powershell
python benchmarks/dream5_network3/run_benchmark.py plan --prepared-root runs/dream5_network3_prepared_20261015 --binary PATH_TO_PINNED_BINARY --config PATH_TO_PINNED_CONFIG --out runs/dream5_network3_20261015_pilot3 --distro Ubuntu
python benchmarks/dream5_network3/run_benchmark.py run --plan runs/dream5_network3_20261015_pilot3/plan.json --workers 2 --smoke
python benchmarks/dream5_network3/run_benchmark.py run --plan runs/dream5_network3_20261015_pilot3/plan.json --workers 12
python benchmarks/dream5_network3/metrics.py score --run-root runs/dream5_network3_20261015_pilot3 --out runs/dream5_network3_20261015_pilot3/scoring_20261015
python benchmarks/dream5_network3/report.py --run-root runs/dream5_network3_20261015_pilot3 --out benchmarks/dream5_network3/results_2026-10-15_pilot3
```

The full batch requires a successful ten-job engineering smoke gate. It verifies
and reuses those jobs rather than running them again. Native failures and partial
directories are retained for inspection, never silently overwritten. Concurrent
coordinators are rejected. Commands, timings, process status, output hashes,
sample counts, thresholds and exact shared MI/subset relationships are recorded.

[Results](RESULTS.md) summarizes the completed pilot; the
[full compact evidence package](results_2026-10-15_pilot3/REPORT.md) includes
all arms/stages, paired primary AP, DPI/TP-retention diagnostics and plots.
Use fresh output paths when reproducing; published evidence is never overwritten.
Native adjacencies/logs remain local in `runs/dream5_network3_20261015_pilot3/`.
Custom AP/AUROC here is not the official DREAM5
leaderboard score. Do not tune against this reference and describe the same
results as independent validation.
