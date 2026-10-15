# DREAM5 Network 3: E. coli benchmark dataset

This adds a **real-expression, experimentally supported TF-target reference**
alongside the simulated DREAM5 Network 1 benchmark. Data preparation and
validation are implemented here; a before/after SJARACNe comparison has **not**
yet been run. This is an external benchmark dataset, not an engine dependency
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

## Benchmark status and next comparison

[Results](RESULTS.md) currently reports **dataset-readiness checks only**.
No TP/FP, AUROC, AP or sampling-improvement result exists for Network 3 yet.
When a comparison is authorized, freeze the engine/sampling protocols and use
the same labeled universe in both arms. Report raw-MI ranking separately from
threshold/DPI/consensus results. Custom full-ranking AUROC/AP is not
automatically interchangeable with the original DREAM5 top-100,000 ranked-list
evaluation. Do not tune against this reference and describe the same results
as independent validation.
