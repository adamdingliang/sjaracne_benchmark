# DREAM5 Network 4: yeast benchmark dataset

This adds the released **Saccharomyces cerevisiae expression data and experimental TF-target reference** alongside DREAM5 Networks 1 and 3. Source acquisition, integrity checks and value-preserving input preparation are complete. No SJARACNe inference, DPI sweep, consensus construction or prediction scoring has been run for Network 4 in this addition.

## Inputs and reference

The original challenge matrix contains **536 microarray profiles and 5,950 genes**. The supplied candidate list contains **333 TFs**, all present in the matrix. Keep all released genes, profiles and candidate TFs for inference; the gold labels do not select the inference universe.

The supplied reference contains **227,202 explicitly labeled directed non-self pairs**: **3,940 positive edges and 223,262 operational negatives**. Its scored universe comprises 114 source TFs and 1,994 target genes, excluding 114 self-pairs. Inference over all 333 candidate TFs and all other genes covers 1,981,017 possible pairs. The remaining **1,753,815 pairs are unlabeled and excluded from scoring**, not false positives.

The yeast reference was built from stringent TF-binding and motif-conservation evidence. It is incomplete biological knowledge: a zero label is not proof that the interaction is biologically absent, and binding evidence need not imply regulation active in every measured condition. Use N4 as an additional experimental validation benchmark, rather than treating its precision or F1 as exact biological accuracy. See the [DREAM5 methods supplement](https://dream.broadinstitute.org/papers/Marbach2012_SI.pdf).

## Source files and storage

The original Network4 directory is stored externally, consistently with the repository's [data policy](../../docs/DATA.md):

```text
D:/GitHub/_datasets/DREAM5_Network4/
  data/
    provenance.json
    Network4/
      input data/net4_expression_data.tsv
      input data/net4_transcription_factors.tsv
      input data/net4_chip_features.tsv
      gold standard/DREAM5_NetworkInference_GoldStandard_Network4.tsv
      gold standard/SOURCE_GOLD_STANDARD_README.txt
      anonymization/net4_gene_ids.tsv
      SOURCE_CHALLENGE_README.txt
  prepared/
    dream5_net4.exp
    all333_tfs.txt
    provenance.json
```

The seven source files are exact original archive members, including the two original notices. Their relative paths, ZIP member names, byte sizes and SHA256 hashes are recorded in the compact [source manifest](data/provenance.json). Raw data, the complete source ZIP and the generated expression transpose are **not bundled in this repository**. See [source terms and attribution](DATA_LICENSE.md).

The source was copied from the already cached checksum-verified [DREAM5 challenge archive](https://zenodo.org/records/17854236); no duplicate archive download is claimed. The external prepared copy preserves every original numeric token and all 333 candidate TFs. Its generated sample names identify profile order, not independent biological replicates; the source chip metadata retains experiment, time and replicate context.

## Verify and prepare

Use Python 3.11+ and run from the benchmark repository root. These commands use only Python's standard library and do not launch inference or download data:

```powershell
python benchmarks/dream5_network4/prepare.py verify --data-root D:/GitHub/_datasets/DREAM5_Network4/data/Network4
python benchmarks/dream5_network4/prepare.py prepare --data-root D:/GitHub/_datasets/DREAM5_Network4/data/Network4 --out runs/dream5_network4_prepared
python scripts/check_benchmarks.py --group dream5_network4
```

For another machine, replace `--data-root` with its local copy. Alternatively, use `--archive PATH_TO_1_Challenge_Data_Supplement.zip` instead of `--data-root`. The published archive MD5 and exact selected source-member SHA256 hashes are checked. Only exact known members are read; arbitrary ZIP paths are never extracted.

Preparation requires a fresh child directory under ignored `runs/`. It writes `dream5_net4.exp`, `all333_tfs.txt` and `provenance.json`. Expression is transposed from profile-by-gene to SJARACNe gene-by-profile format with no normalization, rounding, gene filtering or reference-based source selection. The hub list uses literal LF newlines. Source files are never rewritten.

Verification checks hashes, dimensions, finite expression values, identifiers, full candidate TF coverage, chip metadata/profile alignment, gene-ID order, unique binary non-self labels and the pinned scored universe. Preparation is not a completed inference benchmark or a validated parameter recommendation.

## Results status

**Data and preparation only; inference results pending.** No network precision, recall, F1, AUROC, Average Precision or NetBID2 QC result is claimed for N4 here. Future runs should use fresh output paths, pin the SJARACNe engine and model configuration, preserve the full 333-TF inference list, and retain the fixed explicit-label scoring universe.

The full candidate hub count is 333, below the current dynamic-DPI reference count of 479. Therefore that schedule resolves to epsilon zero for this dataset; testing explicit fixed tolerances is a separate experiment and cannot by itself establish the larger-hub schedule used for bulk SIG networks.
