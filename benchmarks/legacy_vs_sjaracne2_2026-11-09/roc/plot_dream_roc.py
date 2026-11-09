"""Draw fixed-universe ROC curves for the final saved DREAM networks.

Run in this directory with ``python plot_dream_roc.py``. Only the small final
graphs, gold labels and gene/hub lists are read. No inference or raw MI reads
are performed. The parent report supplies the exact version and input paths.
"""

import csv
import gzip
import hashlib
import io
import json
import math
import os
import platform
import tempfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from sklearn.metrics import auc, roc_auc_score, roc_curve
import sklearn

ROOT = Path(__file__).resolve().parent
METHODS = ("Legacy SJARACNe", "SJARACNe2")
COLORS = {METHODS[0]: "#0072B2", METHODS[1]: "#D55E00"}


def read_bytes(path):
    """Read a saved input once and return its text and byte fingerprint."""
    data = Path(path).read_bytes()
    return data.decode("utf-8-sig"), hashlib.sha256(data).hexdigest()


def identifiers(path):
    text, fingerprint = read_bytes(path)
    names = [line.strip() for line in text.splitlines() if line.strip()]
    if not names or len(names) != len(set(names)):
        raise ValueError(f"Empty or duplicate identifier list: {path}")
    return names, fingerprint


def load_universe(execution, expected):
    """Use explicit classic labels or the complete simulated nonself universe."""
    paths = execution["local_input_paths"]
    genes, genes_hash = identifiers(paths["genes_file"])
    hubs, hubs_hash = identifiers(paths["hubs"])
    gene_index = {name: i for i, name in enumerate(genes)}
    assert len(genes) == expected["features"]
    assert len(hubs) == expected["requested_hubs"]
    assert set(hubs).issubset(gene_index)
    text, gold_hash = read_bytes(paths["gold_path"])
    labelled = {}
    size = len(genes)
    for line in text.splitlines():
        if not line.strip():
            continue
        source, target, label = line.split()
        assert source != target and source in hubs and target in gene_index
        assert label in ("0", "1")
        key = gene_index[source] * size + gene_index[target]
        assert key not in labelled, ("Duplicate gold pair", source, target)
        labelled[key] = int(label)
    complete = "SysGenA" in expected["dataset"]
    if complete:
        assert set(hubs) == set(genes)
        assert all(label == 1 for label in labelled.values())
        keys = np.arange(size * size, dtype=np.int64)
        keys = keys[keys // size != keys % size]
        labels = np.isin(keys, np.array(list(labelled), dtype=np.int64))
    else:
        keys = np.array(sorted(labelled), dtype=np.int64)
        labels = np.array([labelled[int(key)] for key in keys], dtype=bool)
    positives = int(labels.sum())
    negatives = len(labels) - positives
    assert positives == expected["TP"] + expected["FN"] and positives > 0 and negatives > 0
    return keys, labels, gene_index, set(hubs), {
        "universe": "complete directed nonself" if complete else "explicitly labelled directed pairs",
        "pairs": len(labels), "positives": positives, "negatives": negatives,
        "genes_sha256": genes_hash, "hubs_sha256": hubs_hash, "gold_sha256": gold_hash,
    }


def load_graph(execution, gene_index, hubs):
    """Read the actual saved MI numbers, preserving all serialization ties."""
    text, fingerprint = read_bytes(execution["local_network"])
    assert fingerprint == execution["recorded_network_sha256"], execution["row_id"]
    edges = {}
    tokens = []
    size = len(gene_index)

    def add(source, target, token):
        assert source in hubs and target in gene_index and source != target
        key = gene_index[source] * size + gene_index[target]
        assert key not in edges, ("Duplicate graph pair", source, target)
        weight = float(token)
        assert math.isfinite(weight) and weight > 0
        edges[key] = weight
        tokens.append(token)

    if execution["recorded_network_format"] == "native_adjacency":
        for line in text.splitlines():
            if not line.strip() or line.startswith(">"):
                continue
            fields = line.split("\t")
            assert len(fields) % 2 == 1
            for i in range(1, len(fields), 2):
                add(fields[0], fields[i], fields[i + 1])
    else:
        for row in csv.DictReader(io.StringIO(text), delimiter="\t"):
            add(row["source"], row["target"], row["MI"])
    return edges, {
        "row_id": execution["row_id"], "network_sha256": fingerprint,
        "network_fingerprint_matches_report": True,
        "minimum_emitted_MI": min(edges.values()), "maximum_emitted_MI": max(edges.values()),
        "unique_emitted_MI_values": len(set(edges.values())),
        "all_MI_tokens_four_decimals": all("." in t and len(t.split(".")[1]) == 4 for t in tokens),
    }


def mann_whitney(labels, scores):
    """Independently calculate AUROC with half credit for score ties."""
    order = np.argsort(scores, kind="stable")
    sorted_scores = scores[order]
    sorted_labels = labels[order].astype(np.int64)
    starts = np.r_[0, np.flatnonzero(np.diff(sorted_scores)) + 1]
    counts = np.diff(np.r_[starts, len(scores)])
    positive = np.add.reduceat(sorted_labels, starts)
    negative = counts - positive
    lower_negative = np.cumsum(negative) - negative
    favorable = np.sum(positive * (lower_negative + 0.5 * negative))
    return float(favorable / (int(labels.sum()) * int((~labels).sum())))


def compute(parent):
    source_rows = json.loads((parent / "dream_rows.json").read_text(encoding="utf-8"))["rows"]
    provenance = json.loads((parent / "dream_provenance.json").read_text(encoding="utf-8"))
    executions = {row["row_id"]: row for row in provenance["executions"]}
    grouped = defaultdict(list)
    for row in source_rows:
        grouped[row["dataset"]].append(row)
    metrics, curves, input_receipts = [], {}, []
    for dataset, pair in grouped.items():
        assert [row["method"] for row in pair] == list(METHODS)
        execution = executions[pair[0]["row_id"]]
        keys, labels, gene_index, hubs, universe = load_universe(execution, pair[0])
        for row in pair:
            current_execution = executions[row["row_id"]]
            assert current_execution["local_input_paths"] == execution["local_input_paths"]
            edges, receipt = load_graph(current_execution, gene_index, hubs)
            assert len(edges) == row["edges"]
            graph_keys = np.fromiter(edges, dtype=np.int64)
            graph_values = np.fromiter(edges.values(), dtype=np.float64)
            locations = np.searchsorted(keys, graph_keys)
            eligible = locations < len(keys)
            eligible[eligible] &= keys[locations[eligible]] == graph_keys[eligible]
            locations = locations[eligible]
            scores = np.zeros(len(keys), dtype=np.float64)
            scores[locations] = graph_values[eligible]
            true_positive = int(labels[locations].sum())
            false_positive = len(locations) - true_positive
            assert (true_positive, false_positive) == (row["TP"], row["FP"])
            fpr, tpr, thresholds = roc_curve(labels, scores, drop_intermediate=False)
            value = float(roc_auc_score(labels, scores))
            rank_value = mann_whitney(labels, scores)
            geometric = float(auc(fpr, tpr))
            assert abs(value - rank_value) < 1e-14 and abs(value - geometric) < 1e-14
            positives, negatives = universe["positives"], universe["negatives"]
            assert thresholds[-1] == 0 and fpr[-1] == tpr[-1] == 1
            assert math.isclose(fpr[-2], false_positive / negatives, abs_tol=1e-15)
            assert math.isclose(tpr[-2], true_positive / positives, abs_tol=1e-15)
            result = {
                "dataset": dataset, "method": row["method"], "profiles": row["profiles"],
                "universe": universe["universe"], "eligible_pairs": len(labels),
                "positives": positives, "negatives": negatives, "all_edges": len(edges),
                "TP": true_positive, "FP": false_positive,
                "unlabelled_emitted_edges": len(edges) - len(locations),
                "zero_tied_omitted_pairs": int(np.count_nonzero(scores == 0)),
                "AUROC": value, "AUROC_mann_whitney": rank_value,
                "AUROC_trapezoidal": geometric,
                "operating_FPR": false_positive / negatives,
                "operating_TPR": true_positive / positives,
                "F1": row["f1"], "score_thresholds": len(thresholds),
            }
            metrics.append(result)
            curves[(dataset, row["method"])] = (fpr, tpr, thresholds)
            input_receipts.append({**receipt, **universe})
            print(dataset, row["method"], f"AUROC={value:.9f}", flush=True)
    return metrics, curves, input_receipts, provenance["source_pins"]


def draw(metrics, curves, output):
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "sjaracne_roc_mpl_20261109"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.titlesize": 11,
                         "axes.labelsize": 10, "legend.fontsize": 9, "axes.spines.top": False,
                         "axes.spines.right": False, "pdf.fonttype": 42, "svg.fonttype": "none"})
    by_key = {(r["dataset"], r["method"]): r for r in metrics}

    def panel(ax, dataset, zoom=False, sysgen=False):
        ax.plot([0, 1], [0, 1], color="#9A9A9A", lw=0.9, ls="--", zorder=0)
        for method in METHODS:
            fpr, tpr, _ = curves[(dataset, method)]
            result = by_key[(dataset, method)]
            label = f"{method}: {result['AUROC']:.4f}" if not zoom else method
            ax.plot(fpr[:-1], tpr[:-1], color=COLORS[method], lw=1.8, label=label)
            ax.plot(fpr[-2:], tpr[-2:], color=COLORS[method], lw=1.4, ls=":")
            ax.scatter(result["operating_FPR"], result["operating_TPR"], s=24,
                       facecolor=COLORS[method], edgecolor="white", linewidth=0.45, zorder=5)
        if zoom:
            ax.set_xlim(0, 0.025 if sysgen else 0.05)
            maximum = max(by_key[(dataset, m)]["operating_TPR"] for m in METHODS)
            ax.set_ylim(0, min(1, math.ceil(maximum * 1.15 * 10) / 10))
            ax.set_xticks(np.linspace(0, 0.025 if sysgen else 0.05, 6))
            ax.yaxis.set_major_locator(MaxNLocator(4))
        else:
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.set_xticks([0, .5, 1])
            ax.set_yticks([0, .5, 1])
        ax.grid(color="#E5E7EB", lw=0.7, zorder=-5)
        ax.legend(loc="lower right", frameon=True, facecolor="white", framealpha=.94,
                  edgecolor="none", fontsize=8 if sysgen else 9)
        ax.set_xlabel("False positive rate")
        ax.set_ylabel("True positive rate (recall)")

    def save(fig, stem):
        for suffix in ("png", "pdf", "svg"):
            fig.savefig(output / f"{stem}.{suffix}", dpi=220, facecolor="white")
            if suffix == "svg":
                # Normalize generated XML whitespace for stable cross-platform diffs.
                path = output / f"{stem}.{suffix}"
                text = "\n".join(line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()) + "\n"
                path.write_bytes(text.encode("utf-8"))
        plt.close(fig)

    fig, axes = plt.subplots(2, 3, figsize=(14.8, 8.1))
    for i, dataset in enumerate(("DREAM5_N1", "DREAM5_N3", "DREAM5_N4")):
        for j in (0, 1):
            panel(axes[j, i], dataset, zoom=bool(j))
            axes[j, i].set_title(dataset.replace("DREAM5_", "DREAM5 ") + (" — early ROC" if j else " — full ROC"))
    fig.suptitle("Final-network ROC: legacy SJARACNe versus SJARACNe2", fontsize=17, y=.985)
    fig.text(.5, .94, "Final MI scores; non-retained labelled pairs share score 0. Legends report full-range AUROC.", ha="center", fontsize=11)
    fig.text(.5, .014, "Dots: all retained labelled edges. Dotted tails: the omitted-pair score tie. Early-ROC panels use different recall scales.", ha="center", fontsize=10)
    fig.subplots_adjust(left=.06, right=.985, top=.875, bottom=.095, hspace=.45, wspace=.28)
    save(fig, "dream_classic_roc")
    for zoom in (False, True):
        fig, axes = plt.subplots(3, 5, figsize=(19, 10.9))
        for j, profiles in enumerate((100, 300, 999)):
            for i in range(5):
                dataset = f"DREAM5_SysGenA{profiles}_Network{i + 1}"
                panel(axes[j, i], dataset, zoom=zoom, sysgen=True)
                axes[j, i].set_title(f"{profiles} profiles · network {i + 1}")
        title = "Systems Genetics A: early ROC" if zoom else "Systems Genetics A: final-network ROC"
        fig.suptitle(title, fontsize=18, y=.985)
        fig.text(.5, .948, "Legacy SJARACNe versus SJARACNe2. Each panel is a distinct 1,000-gene simulation.", ha="center", fontsize=12)
        footer = "Final MI scores; non-retained pairs tied at 0. Dots mark all retained edges. Dotted tails represent the omitted-pair tie."
        if zoom:
            footer += " Recall scales differ across panels."
        else:
            footer += " Legends show full-range AUROC."
        fig.text(.5, .012, footer, ha="center", fontsize=10)
        fig.subplots_adjust(left=.055, right=.99, top=.89, bottom=.075, hspace=.52, wspace=.35)
        save(fig, "dream_sysgen_a_roc_zoom" if zoom else "dream_sysgen_a_roc")
    return matplotlib.__version__


def main(output=ROOT):
    output.mkdir(parents=True, exist_ok=True)
    metrics, curves, receipts, pins = compute(output.parent)
    mpl_version = draw(metrics, curves, output)
    with (output / "auroc.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(metrics[0]), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(metrics)
    with gzip.open(output / "roc_points.tsv.gz", "wt", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["dataset", "method", "FPR", "TPR", "MI_threshold"])
        for (dataset, method), (fpr, tpr, thresholds) in curves.items():
            writer.writerows((dataset, method, x, y, t) for x, y, t in zip(fpr, tpr, thresholds))
    paired = []
    for dataset in dict.fromkeys(r["dataset"] for r in metrics):
        pair = [r for r in metrics if r["dataset"] == dataset]
        paired.append({"dataset": dataset, "legacy_AUROC": pair[0]["AUROC"],
                       "SJARACNe2_AUROC": pair[1]["AUROC"],
                       "delta_AUROC": pair[1]["AUROC"] - pair[0]["AUROC"]})
    assert len(paired) == 18 and all(p["delta_AUROC"] < 0 for p in paired)
    summary = {"schema": "sjaracne-final-network-roc-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
               "source_pins": pins, "stage": "final consensus and DPI output; not raw MI",
               "score": "saved final supporting-run mean MI, preserving serialized precision",
               "missing_score": 0, "tie_handling": "whole equal-score groups, half credit in AUROC",
               "legacy_precision": "all saved legacy MI values are formatted to four decimals",
               "modern_precision": "saved adjacency values; N1/N3 inherit six-digit raw MI inputs",
               "unlabelled_pairs": "excluded for N1/N3/N4; complete generating nonself universe for SysGenA",
               "verification": {"rows": len(metrics), "datasets": len(paired), "all_TP_FP_match_report": True,
                                "sklearn_rank_geometric_AUROC_agree_tolerance": 1e-14,
                                "all_final_network_hashes_match_recorded_report": True},
               "environment": {"Python": platform.python_version(), "numpy": np.__version__,
                               "scikit-learn": sklearn.__version__, "matplotlib": mpl_version},
               "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "source_receipts": receipts, "comparisons": paired}
    (output / "provenance.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8", newline="\n")
    rows = ["| Dataset | Profiles | Legacy AUROC | SJARACNe2 AUROC | Difference |",
            "| --- | ---: | ---: | ---: | ---: |"]
    for pair in paired:
        profile_count = next(r["profiles"] for r in metrics if r["dataset"] == pair["dataset"])
        rows.append(f"| {pair['dataset']} | {profile_count} | {pair['legacy_AUROC']:.6f} | {pair['SJARACNe2_AUROC']:.6f} | {pair['delta_AUROC']:+.6f} |")
    text = """# DREAM ROC curves

ROC curves compare the same final networks as the [main report](../README.md):
actual pre-sampling-change legacy SJARACNe and the SJARACNe2 consensus-first
K20, supporting-run mean MI, dynamic DPI offset +0.025 method.

## Classic DREAM

![Classic DREAM full-range and early ROC curves](dream_classic_roc.png)

Download [PDF](dream_classic_roc.pdf) or [SVG](dream_classic_roc.svg).

## Systems Genetics A

![Systems Genetics A full-range ROC curves](dream_sysgen_a_roc.png)

Download [PDF](dream_sysgen_a_roc.pdf) or [SVG](dream_sysgen_a_roc.svg).

![Systems Genetics A early ROC curves](dream_sysgen_a_roc_zoom.png)

Download the early-ROC [PDF](dream_sysgen_a_roc_zoom.pdf) or [SVG](dream_sysgen_a_roc_zoom.svg).
Each panel is a separate simulation. Early-ROC panels have different recall
scales to show their retained-edge rankings.

## AUROC comparison

""" + "\n".join(rows) + """

Download [all metrics](auroc.tsv) and [exact ROC points](roc_points.tsv.gz).

## Interpretation and scoring

Legacy final-network AUROC is higher in all 18 settings. This differs from
the F1 comparison, where SJARACNe2 wins in 17/18 settings. SJARACNe2 reduces
false positives, but also retains fewer true positives. Most eligible pairs
are omitted by both methods and share a bottom score. Full-range AUROC
therefore reflects final-network selection and recall as well as MI ranking.
Earlier raw-MI ROC results evaluate a different stage.

- Scores are the actual saved final MI values. MI thresholds are swept over
  retained edges; all non-retained eligible pairs have score zero. Dots mark
  the operating point using every retained labelled edge. Dotted tails show
  the large zero-score tie. Ties receive half credit; no ordering is invented
  within them. The grey diagonal is AUROC 0.5.
- N1/N3/N4 use only explicitly labelled directed reference pairs. Unlabelled
  calls are excluded rather than assigned negative truth. Systems Genetics A
  uses all 999,000 directed nonself pairs, with negatives inferred from its
  complete generating-model gold network. Both versions use identical labels.
- Legacy final MI was serialized to four decimals. These ties are preserved.
  Modern adjacency precision is retained; N1/N3 raw inputs retain their older
  six-digit serialization. No scores were jittered or regenerated.
- These are local fixed-universe AUROCs, not the official DREAM calibrated
  challenge score. N3/N4 references are incomplete. No pooled ROC or confidence
  interval is inferred from these distinct networks.

All 36 TP/FP counts reproduce the main report. AUROC agrees between
scikit-learn, an independent tie-aware Mann–Whitney calculation and integration
of the exact ROC points to within 1e-14. Final graph SHA-256 hashes match the
recorded report. No inference, raw-MI reads or environment changes were needed.

[Provenance and exact versions](provenance.json) ·
[Reproducible plotting script](plot_dream_roc.py)

```bash
python plot_dream_roc.py
```

The script reads the external final graphs and gold/input lists identified in
the parent report's `dream_provenance.json`. NumPy, scikit-learn and Matplotlib
must already be installed. Numeric plotting points are included for reuse.
"""
    (output / "README.md").write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps({"datasets": 18, "curves": 36, "all_latest_AUROC_lower": True}))


if __name__ == "__main__":
    main()
