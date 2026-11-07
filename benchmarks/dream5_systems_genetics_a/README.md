# DREAM5 Systems Genetics A: simulated network benchmark sources

**Status: GOLD_AVAILABLE_INPUTS_PENDING.** All 15 gold networks have been acquired and audited. The three original expression/genotype archives have not yet been recovered through authorized download, so this is not a prepared or runnable expression benchmark. No inference or scoring results are claimed.

This is DREAM5 Challenge 3A (SysGenA), distinct from the Network Inference challenge containing Networks 1, 3 and 4. SysGenSIM generated 15 1,000-gene networks, with five datasets each at expected population sizes of 100, 300 and 999 recombinant inbred lines. Expression dimensions and identifier alignment remain to be checked against the actual input archives. See the [author dataset page](https://sysgensim.sourceforge.net/datasets.html) and [original challenge study](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0029165).

## Gold reference and scoring scope

The gold files list positive directed edges from the complete generating models. The original README explicitly says that absent non-self pairs are non-edges and that evaluation scripts enumerate them. For each fixed 1,000-gene universe, there are **999,000 ordered non-self pairs**. Zero labels need not be stored as another million-line file. This complete simulated truth differs from the incomplete experimental references for E. coli and yeast.

| Network | A100 true edges | A300 true edges | A999 true edges |
| --- | ---: | ---: | ---: |
| 1 | 2,037 | 1,983 | 2,048 |
| 2 | 3,055 | 3,106 | 3,093 |
| 3 | 3,784 | 3,825 | 3,763 |
| 4 | 4,840 | 4,812 | 4,740 |
| 5 | 5,669 | 5,273 | 5,545 |

Each source file has unique non-self positive edges, valid G1 through G1000 identifiers, and all 1,000 nodes represented in its endpoint union. The positive edge counts differ between all 15 files; these are not merely the same five graphs copied across sample-size groups. The archive hash, original member names, file sizes and SHA256 values are recorded in [data/provenance.json](data/provenance.json).

Use the complete gene universe when evaluating negatives and preserve it independently of source-degree counts. The gold's subset of genes with outgoing edges is **not** an independently supplied TF list and must not be used to select inference sources. Until another regulator prior is specified independently, an expression-only benchmark would treat all 1,000 genes as candidate sources. MI association alone has limited edge-orientation information in this setting, so report undirected recovery alongside directed scores.

The original challenge included both genotype and expression data. An expression-only SJARACNe experiment would deliberately omit genotype information and should not be presented as an equivalent reproduction of genotype-assisted leaderboard methods. The simulated network is fully known, but that does not establish biological realism or optimal TCGA parameters.

## Acquired sources and organization

Raw data remain external under the same source/prepared/run separation used by the other benchmark datasets:

```text
D:/GitHub/_datasets/DREAM5_SysGenA/
  archives/DREAM5_SysGenA_GoldStandard.zip
  gold_download_receipt.json
  gold_audit.json
  data/
    SOURCE_GOLD_STANDARD_README.txt
    A100/Network1/gold standard/DREAM5_SysGenA100_Edges_Network1.tsv
    ... Network2 through Network5 ...
    A300/Network1/gold standard/DREAM5_SysGenA300_Edges_Network1.tsv
    ... Network2 through Network5 ...
    A999/Network1/gold standard/DREAM5_SysGenA999_Edges_Network1.tsv
    ... Network2 through Network5 ...
```

The original Columbia gold archive was retrieved from its public Internet Archive capture at timestamp **20131211103624**, preserving its original bytes. The archive SHA256 is `7ea861c57a05d5dd7e504d67506076f2ed97fa0c348e3fb01efc604572c2c68f`; retrieval provenance also records the original URL and archive capture digest. It contains 15 graph files and the original reference README; metadata-only Mac resource-fork entries are not treated as dataset inputs. [Archived original gold ZIP](https://web.archive.org/web/20131211103624id_/http://wiki.c2b2.columbia.edu/dream/data/upload/dream5/analyze/goldstandard/DREAM5_SysGenA_GoldStandard.zip)

This repository stores only source metadata, documentation and the verifier. Gold edge lists, input archives, generated expression matrices and inferred networks are not committed. See [source terms and attribution](DATA_LICENSE.md).

## Verify the gold files

Use Python 3.11+ from the repository root:

```powershell
python benchmarks/dream5_systems_genetics_a/verify_gold.py --data-root D:/GitHub/_datasets/DREAM5_SysGenA/data
python benchmarks/dream5_systems_genetics_a/verify_gold.py --archive D:/GitHub/_datasets/DREAM5_SysGenA/archives/DREAM5_SysGenA_GoldStandard.zip
python scripts/check_benchmarks.py --group dream5_systems_genetics_a
```

Replace local paths for another machine. Verification checks exact source hashes, graph identifiers, unique positive edges, self-edge exclusion and the complete fixed model universe. Archive mode reads only named members and never extracts arbitrary paths. It does not download data, prepare expression inputs, infer a network or score predictions. Its success status remains **GOLD_AVAILABLE_INPUTS_PENDING**. The [completed gold verification record](gold_verification_2026-11-07.json) records both source routes and the offline checks.

## Expression/genotype acquisition still required

The original source mirror currently fails DNS, and the archived original public input ZIPs have not been recovered. Synapse lists the three inputs under the DREAM5 collection, but anonymous file download requires authorized authentication:

| Expected source archive | Expected profiles per network | Synapse entity | Status |
| --- | ---: | --- | --- |
| DREAM5_SysGenA100.zip | 100 | [syn2867592](https://www.synapse.org/Synapse:syn2867592) | Pending authorized download |
| DREAM5_SysGenA300.zip | 300 | [syn2867593](https://www.synapse.org/Synapse:syn2867593) | Pending authorized download |
| DREAM5_SysGenA999.zip | 999 | [syn2867594](https://www.synapse.org/Synapse:syn2867594) | Pending authorized download |

Do not substitute gold edge files, predictions or the gold ZIP for missing expression measurements. After acquisition, verify each archive's bytes, profile/gene dimensions, gene ordering, expression/genotype alignment and numerical values before creating the value-preserving SJARACNe inputs. Update source manifests and dataset status only after those checks. Engine settings, DPI tolerances and benchmark outcomes remain unchanged.
