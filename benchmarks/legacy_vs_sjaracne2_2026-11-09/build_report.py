"""Render the frozen legacy/SJARACNe2 comparison; no inference is launched."""

import csv
import io
import json
import math
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent
METHODS = ("Legacy SJARACNe", "SJARACNe2")


def load_rows(root=ROOT):
    """Join saved accuracy/coverage rows with the dated DREAM topology QC."""
    bulk = json.loads((root / "bulk_rows.json").read_text(encoding="utf-8"))["rows"]
    dream = json.loads((root / "dream_rows.json").read_text(encoding="utf-8"))["rows"]
    with (root / "dream_topology.tsv").open(encoding="utf-8", newline="") as handle:
        topology = list(csv.DictReader(handle, delimiter="\t"))
    keyed = {(r["dataset"], r["method"]): r for r in topology}
    assert len(keyed) == len(topology) == 36
    for row in dream:
        key = (row["dataset"], "legacy" if row["method"] == METHODS[0] else "new_relaxed")
        qc = keyed[key]
        for field in ("edges", "active_hubs", "requested_hubs", "median_targets"):
            assert float(qc[field]) == row[field], (key, field, qc[field], row[field])
        token = qc["adjusted_scale_free_r2"]
        row["adjusted_scale_free_r2"] = None if token in ("NA", "", "NaN") else float(token)
    rows = dream + bulk
    assert len(rows) == 48
    groups = defaultdict(list)
    for row in rows:
        assert row["method"] in METHODS
        assert row["active_hubs"] <= row["requested_hubs"]
        assert row["edges"] >= row["active_hubs"]
        groups[(row["dataset"], row["network"])].append(row)
        if row["category"].lower() == "dream":
            assert row["TP"] + row["FP"] <= row["edges"]
            expected = {
                "precision": row["TP"] / (row["TP"] + row["FP"]),
                "recall": row["TP"] / (row["TP"] + row["FN"]),
                "f1": 2 * row["TP"] / (2 * row["TP"] + row["FP"] + row["FN"]),
            }
            for metric, value in expected.items():
                assert math.isclose(row[metric], value, rel_tol=1e-13, abs_tol=1e-15)
        else:
            assert all(row[k] is None for k in ("TP", "FP", "FN", "precision", "recall", "f1"))
    assert len(groups) == 24
    for key, pair in groups.items():
        assert {r["method"] for r in pair} == set(METHODS), key
        assert len({(r["profiles"], r["features"], r["requested_hubs"]) for r in pair}) == 1, key
        if pair[0]["category"].lower() == "dream":
            assert len({r["TP"] + r["FN"] for r in pair}) == 1, key
    return rows, groups


def count(value):
    return "N/A" if value is None else f"{value:,d}"


def median(value):
    return "N/A" if value is None else f"{value:,.1f}".removesuffix(".0")


def rate(value):
    return "N/A" if value is None else f"{100 * value:.2f}"


def display_name(row):
    name = row["dataset"]
    if name.startswith("DREAM5_SysGenA"):
        sample, number = name.removeprefix("DREAM5_SysGenA").split("_Network")
        return f"A{sample} network {number}"
    return {"DREAM5_N1": "DREAM5 N1", "DREAM5_N3": "DREAM5 N3", "DREAM5_N4": "DREAM5 N4", "LUAD517": "TCGA-LUAD517", "BLCA406": "TCGA-BLCA406"}.get(name, name)


def table(rows, bulk=False):
    headers = ["Dataset"] + (["Panel"] if bulk else []) + [
        "Method", "Profiles", "Edges", "Active / requested hubs", "TP", "FP",
        "Precision (%)", "Recall (%)", "F1 (%)", "Median targets", "Adjusted scale-free R2",
    ]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * (3 if bulk else 2) + ["---:"] * 10) + " |"]
    for row in rows:
        values = [display_name(row)] + ([row["network"]] if bulk else []) + [
            row["method"], count(row["profiles"]), count(row["edges"]),
            f"{row['active_hubs']:,} / {row['requested_hubs']:,}", count(row["TP"]), count(row["FP"]),
            rate(row["precision"]), rate(row["recall"]), rate(row["f1"]), median(row["median_targets"]),
            "N/A" if row["adjusted_scale_free_r2"] is None else f"{row['adjusted_scale_free_r2']:.4f}",
        ]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def render(root=ROOT):
    rows, groups = load_rows(root)
    dream = [r for r in rows if r["category"].lower() == "dream"]
    bulk = [r for r in rows if r["category"].lower() == "bulk"]
    classic = [r for r in dream if not r["dataset"].startswith("DREAM5_SysGenA")]
    sysgen = [r for r in dream if r["dataset"].startswith("DREAM5_SysGenA")]
    dream_pairs = [pair for key, pair in groups.items() if key[0].startswith("DREAM5")]
    wins = sum(next(r for r in p if r["method"] == METHODS[1])["f1"] > next(r for r in p if r["method"] == METHODS[0])["f1"] for p in dream_pairs)
    assert wins == 17
    assert all(next(r for r in p if r["method"] == METHODS[1])["recall"] < next(r for r in p if r["method"] == METHODS[0])["recall"] for p in dream_pairs)
    assert all(next(r for r in p if r["method"] == METHODS[1])["precision"] > next(r for r in p if r["method"] == METHODS[0])["precision"] for p in dream_pairs)
    text = f"""# Legacy SJARACNe versus SJARACNe2

Final comparison dated **2026-11-09**. The four DREAM index entries expand to
18 scored networks: N1, N3, N4 and all 15 Systems Genetics A simulations.
The three bulk datasets contribute separate TF and SIG networks. The tables
contain 48 method rows with matched expression inputs and requested hub panels.

[Bar plots](bars/README.md) · [Classic DREAM](#classic-dream) · [Systems Genetics A](#systems-genetics-a) ·
[Bulk](#bulk) · [Definitions](#definitions) · [Execution and provenance](#execution-and-provenance)

Download [the complete table](comparison.tsv). Rates in that TSV are fractions;
rates in the tables below are percentages. `TP` is interpreted from the requested
accuracy-column label `TF`.

See [ROC curves and AUROC comparisons](roc/README.md) for the same final DREAM
networks ranked by saved MI.

## Compared workflows

| Setting | Legacy SJARACNe | SJARACNe2 develop |
| --- | --- | --- |
| Resampling | 100 full-size bootstraps with replacement | 100 resamples, each using 80% without replacement |
| MI cutoff | Original affine calibration, p=1e-7 | PCHIP calibration, TF/DREAM p=0.001 and SIG p=0.0005 |
| Consensus and DPI | Strict DPI epsilon=0 in each run, then historical probability consensus pc=1e-5 | K20 candidate edges, supporting-run mean MI, then dynamic DPI |
| Dynamic tolerance | Not used | min(0.30, 0.025 + 0.05 * max(0, log2(H / 479))) |
| Shared settings | Npar=40, seeds 1-100 | Npar=40, seeds 1-100 |

The legacy baseline is the actual pre-sampling-change implementation, not
the legacy-plus-K20 control. The SJARACNe2 scientific settings match
[develop at 7c1e71f](https://github.com/adamdingliang/SJARACNe2/tree/7c1e71f36cd4ae1d4f377668b62015fa722c5b2a).
Execution-version distinctions are recorded below.

## Classic DREAM

{table(classic)}

## Systems Genetics A

Each row pair is a distinct 1,000-gene simulated network. A100, A300 and A999
denote expression profile counts. The five networks within each group are
different generating graphs. All 1,000 genes are requested sources, not
1,000 validated TFs. Zero median targets means at least half of the requested
sources have no retained outgoing targets.

{table(sysgen)}

## Bulk

TCGA cohorts contain primary tumors. These are LUAD517 and BLCA406, not the
separate LUAD100 or BLCA MIBC372 subsets. Bulk accuracy columns are N/A
because no independent edge-level gold standard was used.

{table(bulk, bulk=True)}

## What the comparison supports

- SJARACNe2 improves F1 in **{wins}/18** DREAM settings. Precision rises and
  recall falls in all 18. Fewer reference false positives come with fewer true
  positives. Yeast N4 is the F1 exception: 4.51% to 3.28%.
- Target coverage falls substantially. Classic DREAM medians decline from
  63 to 35, 113.5 to 46 and 126 to 63. In A100, two networks have a median
  of zero. Higher F1 does not imply larger regulons.
- Bulk TF medians fall in all three datasets. BRCA100 is particularly sparse:
  TF 283 to 9 and SIG 71 to 4. TCGA SIG coverage increases: LUAD517 median
  53 to 117 and BLCA406 median 49 to 133, with more than twice as many edges.
- Adjusted scale-free R2 improves for three of six bulk networks: BRCA TF/SIG
  and BLCA TF. It falls for LUAD TF/SIG and BLCA SIG. This topology statistic
  does not establish biological accuracy. N4 illustrates the distinction:
  its R2 improves while its F1 falls.

These are descriptive comparisons of complete workflows. Sampling, MI
calibration/cutoffs, consensus and DPI all differ. The table cannot attribute
improvement to any one change. The 15 Systems Genetics simulations share one
simulation framework and are not 15 independent biological cohorts.

## Definitions

- **Profiles:** expression columns, not resample count. **Edges:** all emitted
  directed nonself edges. **Active hubs:** requested sources with at least one
  target. H and the requested count include zero-target sources.
- **TP/FP:** reference-labelled directed pairs. N1/N3/N4 unlabelled predictions
  are excluded from TP/FP and precision, but included in Edges and target counts.
  Thus Edges can exceed TP + FP. N3/N4 references are incomplete, and a labelled
  FP is not proof that the association is biologically false. SysGenA uses the
  complete generating-model nonself universe.
- **Precision:** TP/(TP+FP). **Recall:** TP/(TP+FN). **F1:**
  2TP/(2TP+FP+FN). **Median targets:** median unique outgoing nonself targets
  over the entire requested matched panel, including zero-target hubs.
- **Adjusted scale-free R2:** the existing NetBID2 QC fit on total degree
  (in+out) of nodes present in the emitted graph. For k=1 through the maximum
  degree, fit log10(p(k)+1/V) against log10(k), with an intercept. V is the
  incident-node count. Zero-target requested hubs are not inserted as isolated
  nodes. Finite negative fits are retained; undefined fits are N/A.

## Execution and provenance

**Legacy:** N1/N3/N4/SysGenA/LUAD/BLCA use historical commit
[`e59973a`](https://github.com/adamdingliang/SJARACNe2/commit/e59973a1891672a14f06d7847545c53368f3066c).
BRCA100 reused actual commit `12113fbc`; its `SJARACNe` source tree is
identical to e59973a. Recorded expression and hub SHA-256 fingerprints match
within every legacy/current pair. Input normalization only changes line endings.

**DREAM:** accuracy and target-count values are inherited from the
[frozen scored comparison](../consensus_before_dpi/per_dataset.tsv), selecting
`legacy` and `new_relaxed`. The initial native implementation reproduced all
18 relaxed graphs with exact directed edges and binary64 MI values on saved
inputs. Its broader [receipt](../consensus_before_dpi/native_equivalence.json)
also covers offset zero (36 comparisons total). The later sequential reader
preserves manifest-order sums and passed three byte-identical long-row
comparisons plus 22 native tests, documented in
[the pinned implementation validation](https://github.com/adamdingliang/SJARACNe2/blob/7c1e71f36cd4ae1d4f377668b62015fa722c5b2a/docs/native_consensus_validation.md#sequential-input-revision).
The DREAM rows are therefore saved-input native-equivalent results, not a claim
that the latest binary reran all 18 datasets. N1/N3 raw files retain historical
MI serialization precision. Lost input precision cannot be recovered. Accuracy
scores were not independently rescored for this report.

**Bulk:** the [completed native batch](../native_bulk_2026-11-09/README.md)
provides all six SJARACNe2 rows. Four arms used the initial native implementation.
LUAD SIG and BLCA SIG replayed their saved raw MI through the later sequential
reader on HDD. No MI inference was rerun for recovery or this report.

**Topology:** DREAM R2 was newly calculated from the 36 saved final graphs
using the same R/igraph method as the bulk NetBID2 QC. Edge counts, active and
requested hubs, and zero-inclusive medians were checked against the scored
tables. Bulk counts and medians were also independently checked against all
12 saved target-size tables. Input/raw graph hashes quoted in provenance are
existing recorded receipts, not fresh rereads of every expression/raw MI file.

Reproduce the presentation without inference:

```bash
python build_report.py
```

The builder validates row coverage, matching dimensions, QC counts/medians and
the accuracy equations, then regenerates this README and `comparison.tsv`.
See [DREAM provenance](dream_provenance.json), [bulk provenance](bulk_provenance.json),
[topology provenance](topology_provenance.json) and
[the topology calculation](compute_dream_topology.R) for exact sources and versions.
The external input graphs are not distributed with this report.
"""
    fields = ["category", "dataset", "network", "method", "profiles", "features", "edges", "active_hubs", "requested_hubs", "TP", "FP", "FN", "precision", "recall", "f1", "median_targets", "adjusted_scale_free_r2"]
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=fields, delimiter="\t", lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows({k: "NA" if row.get(k) is None else row[k] for k in fields} for row in rows)
    (root / "comparison.tsv").write_text(buffer.getvalue(), encoding="utf-8", newline="\n")
    (root / "README.md").write_text(text, encoding="utf-8", newline="\n")
    return {"method_rows": len(rows), "dream_pairs": len(dream_pairs), "bulk_pairs": len(bulk) // 2, "f1_improved": wins}


if __name__ == "__main__":
    print(json.dumps(render(), sort_keys=True))
