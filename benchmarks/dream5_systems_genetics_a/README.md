# DREAM5 Systems Genetics A: simulated network benchmark

**Status: INPUTS_PREPARED.** All three user-downloaded Synapse archives, 15 expression/genotype pairs and 15 gold networks have been validated. Value-preserving SJARACNe expression inputs and an all-1,000-gene candidate-source list are prepared locally. No inference or scoring has been run.

This is DREAM5 Challenge 3A (SysGenA), distinct from the Network Inference challenge containing Networks 1, 3 and 4. SysGenSIM generated 15 separate 1,000-gene networks: five datasets each with 100, 300 and 999 recombinant inbred lines. Each expression dataset has its own generating graph; the five networks in a group have progressively more edges. The sample-size groups do not reuse identical graphs, so comparisons across groups also change topology. See the [author dataset page](https://sysgensim.sourceforge.net/datasets.html) and [original challenge study](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0029165).

## Validated inputs

| Group | Datasets | Expression per dataset | Genotype per dataset | Source archive |
| --- | ---: | --- | --- | --- |
| A100 | 5 | 100 profiles x 1,000 genes | 100 profiles x 1,000 genes | [syn2867592](https://www.synapse.org/Synapse:syn2867592), version 1 |
| A300 | 5 | 300 profiles x 1,000 genes | 300 profiles x 1,000 genes | [syn2867593](https://www.synapse.org/Synapse:syn2867593), version 1 |
| A999 | 5 | 999 profiles x 1,000 genes | 999 profiles x 1,000 genes | [syn2867594](https://www.synapse.org/Synapse:syn2867594), version 1 |

ZIP CRC checks, exact member inventories and locally recorded SHA256 values pass. The hashes pin the files supplied by the user; they are not represented as independently verified remote checksums. See [input source metadata](data/input_provenance.json) and [validation](input_preparation_2026-11-07.json).

Each original matrix has quoted gene headers G1 through G1000, profiles in rows, genes in columns, and one terminal empty field caused by a final tab on every row. The importer requires that exact empty-field format, parses the header quotes, and transposes expression to genes in rows. Every numeric token is preserved; there is no normalization, log transform, filtering or rounding. Genotypes remain separate original files and are not used for expression-only inference.

There are no individual/sample IDs in the source files. Expression and genotype have the same gene order and row counts, but correspondence can only be represented by original row ordinal; identity cannot be independently confirmed using sample identifiers. Generated sample names and a sample-order mapping record that limitation. The full 1,000-gene candidate-source list comes from expression headers, independently of the gold graph.

## Gold reference and scoring scope

The gold files list positive directed edges from complete generating models. The original README explicitly says absent non-self pairs are non-edges. Each fixed 1,000-gene universe therefore has **999,000 ordered non-self pairs**. Zero labels need not be stored as another million-line file. This complete simulated truth differs from the incomplete experimental references for E. coli and yeast.

| Network | A100 true edges | A300 true edges | A999 true edges |
| --- | ---: | ---: | ---: |
| 1 | 2,037 | 1,983 | 2,048 |
| 2 | 3,055 | 3,106 | 3,093 |
| 3 | 3,784 | 3,825 | 3,763 |
| 4 | 4,840 | 4,812 | 4,740 |
| 5 | 5,669 | 5,273 | 5,545 |

Each reference has unique non-self positive edges, valid G1 through G1000 identifiers, and all 1,000 nodes represented in its endpoint union. All 15 edge counts differ. [Gold provenance](data/provenance.json) pins exact source members and hashes. A reference's subset of genes with outgoing edges must not be used as a candidate TF list. Report undirected recovery alongside directed scores because expression-only MI carries limited orientation information.

The original challenge included both genotype and expression. An expression-only SJARACNe experiment omits genotype information and is not an equivalent reproduction of genotype-assisted leaderboard methods. Complete model truth does not establish biological realism or optimal TCGA parameters. Reserve whole networks for validation when selecting parameters; resamples of one graph are not independent benchmark datasets.

## Local organization

Raw sources and prepared files remain external:

```text
D:/GitHub/_datasets/DREAM5_SysGenA/
  README.md
  archives/
    DREAM5_SysGenA100.zip
    DREAM5_SysGenA300.zip
    DREAM5_SysGenA999.zip
    DREAM5_SysGenA_GoldStandard.zip
  data/
    SOURCE_GOLD_STANDARD_README.txt
    A100/Network1/
      input data/DREAM5_SysGenA100_Network1_Expression.tsv
      input data/DREAM5_SysGenA100_Network1_Genotype.tsv
      gold standard/DREAM5_SysGenA100_Edges_Network1.tsv
    ... Network2 through Network5; likewise A300 and A999 ...
  prepared/
    A100/Network1/  # expression input, all-gene sources, sample mapping, receipt
    ... all 15 datasets ...
  input_download_receipt.json
  input_preparation.json
```

All original ZIP and extracted source bytes are retained. The gold ZIP was recovered from the public Internet Archive capture of the original Columbia download at timestamp **20131211103624**, SHA256 `7ea861c57a05d5dd7e504d67506076f2ed97fa0c348e3fb01efc604572c2c68f`. [Archived original gold ZIP](https://web.archive.org/web/20131211103624id_/http://wiki.c2b2.columbia.edu/dream/data/upload/dream5/analyze/goldstandard/DREAM5_SysGenA_GoldStandard.zip)

The repository stores metadata, code, tests and compact verification records. Raw archives, expression/genotype matrices, gold edge lists and generated expression inputs are not committed. See [source terms and attribution](DATA_LICENSE.md).

## Verify and prepare

Use Python 3.11+ from the repository root:

```powershell
python benchmarks/dream5_systems_genetics_a/prepare.py verify --archives-root D:/GitHub/_datasets/DREAM5_SysGenA/archives
python benchmarks/dream5_systems_genetics_a/prepare.py verify --data-root D:/GitHub/_datasets/DREAM5_SysGenA/data
python benchmarks/dream5_systems_genetics_a/prepare.py prepare --data-root D:/GitHub/_datasets/DREAM5_SysGenA/data --out runs/sysgena_prepared
python scripts/check_benchmarks.py --group dream5_systems_genetics_a
```

Replace paths for another machine. Preparation requires a fresh output directory under the repository's ignored `runs/`; existing outputs are never overwritten. The source/archive routes check pinned hashes and validate expression, genotype and gold graphs. Exact ZIP members are read without arbitrary extraction. Preparation writes all 15 expression inputs separately.

For a gold-only check:

```powershell
python benchmarks/dream5_systems_genetics_a/verify_gold.py --data-root D:/GitHub/_datasets/DREAM5_SysGenA/data
python benchmarks/dream5_systems_genetics_a/verify_gold.py --archive D:/GitHub/_datasets/DREAM5_SysGenA/archives/DREAM5_SysGenA_GoldStandard.zip
```

Gold-only success is `GOLD_VERIFIED` and explicitly leaves expression/genotype unchecked. The [earlier gold-only record](gold_verification_2026-11-07.json) is a historical snapshot taken before the user supplied input archives; the current complete-bundle status is in [input_preparation_2026-11-07.json](input_preparation_2026-11-07.json). None of these commands runs SJARACNe or changes DPI/consensus parameters.
