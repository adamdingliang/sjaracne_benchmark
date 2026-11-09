"""Plot the four requested comparisons from the frozen parent report table.

Run ``python plot_bars.py`` in this directory. No inference, graph reads or
metric recalculation are performed. Rates are displayed as percentages.
"""

import csv
import hashlib
import json
import math
import os
import platform
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
METHODS = ("Legacy SJARACNe", "SJARACNe2")
LABELS = ("SJARACNe (legacy)", "SJARACNe2")
COLORS = ("#0072B2", "#D55E00")
CLASSIC = ["DREAM5_N1", "DREAM5_N3", "DREAM5_N4"]
DREAM = CLASSIC + [f"DREAM5_SysGenA{profiles}_Network{network}"
                   for profiles in (100, 300, 999) for network in range(1, 6)]
BULK = [(dataset, network) for dataset in ("BRCA100", "LUAD517", "BLCA406")
        for network in ("TF", "SIG")]


def load_values(parent):
    """Read matched methods and preserve all 18 DREAM and six bulk pairs."""
    path = parent / "comparison.tsv"
    with path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    assert len(rows) == 48
    by_key = {(r["dataset"], r["network"], r["method"]): r for r in rows}
    assert len(by_key) == 48
    groups, export = {}, []
    for metric, category, factor, unit in (
        ("precision", "DREAM", 100, "%"), ("f1", "DREAM", 100, "%"),
        ("median_targets", "bulk", 1, "targets"),
        ("adjusted_scale_free_r2", "bulk", 1, "adjusted R2"),
    ):
        pairs = [(d, "TF" if d in CLASSIC else "all genes") for d in DREAM] if category == "DREAM" else BULK
        matrix = []
        for dataset, network in pairs:
            pair = [by_key[dataset, network, method] for method in METHODS]
            assert len({(r["profiles"], r["features"], r["requested_hubs"]) for r in pair}) == 1
            values = [float(r[metric]) * factor for r in pair]
            assert all(math.isfinite(value) and value >= 0 for value in values)
            if metric == "adjusted_scale_free_r2":
                assert all(value <= 1 for value in values)
            matrix.append(values)
            for method, value in zip(METHODS, values):
                export.append({"category": category, "dataset": dataset, "network": network,
                               "method": method, "metric": metric, "value": value, "unit": unit})
        groups[metric] = np.asarray(matrix)
    assert len(export) == 96
    return groups, export, hashlib.sha256(path.read_bytes()).hexdigest()


def create_figures(groups, output):
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir()) / "sjaracne_bar_mpl_20261109"))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "pdf.fonttype": 42, "svg.fonttype": "none"})
    output_files = []

    def save(fig, stem):
        for suffix in ("png", "pdf", "svg"):
            path = output / f"{stem}.{suffix}"
            fig.savefig(path, dpi=240, facecolor="white")
            if suffix == "svg":
                text = "\n".join(line.rstrip() for line in path.read_text(encoding="utf-8").splitlines()) + "\n"
                path.write_bytes(text.encode("utf-8"))
            output_files.append(path.name)
        plt.close(fig)

    names = ["DREAM5 N1", "DREAM5 N3 (E. coli)", "DREAM5 N4 (yeast)"]
    names += [f"A{profiles} network {network}" for profiles in (100, 300, 999) for network in range(1, 6)]
    for metric, title, xlabel in (("precision", "DREAM precision", "Precision (%)"),
                                 ("f1", "DREAM F1", "F1 (%)")):
        values = groups[metric]
        fig, ax = plt.subplots(figsize=(11.5, 10.8))
        fig.suptitle(title, fontsize=20, y=.975)
        y = np.arange(len(DREAM))
        for low, high in ((2.5, 7.5), (12.5, 17.5)):
            ax.axhspan(low, high, facecolor="#F4F6F8", zorder=0)
        for boundary in (2.5, 7.5, 12.5):
            ax.axhline(boundary, color="#CBD0D7", linewidth=.8, zorder=0)
        for i, (label, color) in enumerate(zip(LABELS, COLORS)):
            bars = ax.barh(y + (i - .5) * .34, values[:, i], height=.31,
                           color=color, label=label, zorder=3)
            assert np.array_equal(np.array([b.get_width() for b in bars]), values[:, i])
            ax.bar_label(bars, labels=[f"{v:.2f}" for v in values[:, i]], padding=4, fontsize=9.5)
        ax.set_yticks(y, names, fontsize=10)
        ax.set_ylim(-.65, len(DREAM) - .35)
        ax.invert_yaxis()
        upper = math.ceil(float(values.max()) * 1.15 / 5) * 5
        ax.set_xlim(0, upper)
        ax.set_xlabel(xlabel, fontsize=12, labelpad=10)
        ax.xaxis.set_major_locator(MaxNLocator(6))
        ax.grid(axis="x", color="#E1E5EA", linewidth=.8, zorder=0)
        handles, labels = ax.get_legend_handles_labels()
        fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(.57, .945), ncol=2,
                   frameon=False, fontsize=12)
        fig.text(.5, .016, "A100/A300/A999: Systems Genetics A profile counts. Each simulation is shown separately.",
                 ha="center", fontsize=10)
        fig.subplots_adjust(left=.245, right=.965, top=.90, bottom=.075)
        save(fig, "dream_precision" if metric == "precision" else "dream_f1")

    xlabels = [f"{dataset}\n{panel}" for dataset, panel in BULK]
    xlabels = [label.replace("LUAD517", "TCGA-LUAD517").replace("BLCA406", "TCGA-BLCA406") for label in xlabels]
    for metric, title, ylabel, stem in (
        ("median_targets", "Bulk median targets", "Median targets per requested hub", "bulk_median_targets"),
        ("adjusted_scale_free_r2", "Bulk adjusted scale-free R²", "Adjusted scale-free R²", "bulk_adjusted_scale_free_r2"),
    ):
        values = groups[metric]
        fig, ax = plt.subplots(figsize=(13.2, 6.1))
        fig.suptitle(title, fontsize=20, y=.975)
        x = np.arange(len(BULK))
        for i, (label, color) in enumerate(zip(LABELS, COLORS)):
            bars = ax.bar(x + (i - .5) * .36, values[:, i], width=.34, label=label,
                          color=color, zorder=3)
            assert np.array_equal(np.array([b.get_height() for b in bars]), values[:, i])
            text = [f"{v:g}" for v in values[:, i]] if metric == "median_targets" else [f"{v:.4f}" for v in values[:, i]]
            ax.bar_label(bars, labels=text, padding=5, fontsize=10)
        ax.set_xticks(x, xlabels, fontsize=11)
        ax.set_ylabel(ylabel, fontsize=12, labelpad=12)
        ax.set_ylim(0, math.ceil(float(values.max()) * 1.15 / 50) * 50 if metric == "median_targets" else 1.05)
        if metric == "adjusted_scale_free_r2":
            ax.set_yticks(np.arange(0, 1.01, .2))
        else:
            ax.yaxis.set_major_locator(MaxNLocator(7, integer=True))
        for boundary in (1.5, 3.5):
            ax.axvline(boundary, color="#CBD0D7", lw=.8, zorder=0)
        ax.grid(axis="y", color="#E1E5EA", lw=.8, zorder=0)
        handles, labels = ax.get_legend_handles_labels()
        fig.legend(handles, labels, loc="upper center", bbox_to_anchor=(.53, .92), ncol=2,
                   frameon=False, fontsize=12)
        footer = "Median includes every requested hub, including hubs with zero targets." if metric == "median_targets" else "NetBID2 total-degree fit. Adjusted scale-free R² describes topology; it does not measure edge accuracy."
        fig.text(.5, .018, footer, ha="center", fontsize=10)
        fig.subplots_adjust(left=.085, right=.985, top=.815, bottom=.17)
        save(fig, stem)
    return matplotlib.__version__, output_files


def main(output=ROOT):
    output.mkdir(parents=True, exist_ok=True)
    groups, export, source_hash = load_values(output.parent)
    matplotlib_version, figures = create_figures(groups, output)
    with (output / "plot_values.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(export[0]), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(export)
    provenance = {"schema": "sjaracne-comparison-bar-plots-v1", "created_utc": datetime.now(timezone.utc).isoformat(),
                  "source": "../comparison.tsv", "source_sha256": source_hash,
                  "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  "methods": list(METHODS), "DREAM_pairs": 18, "bulk_pairs": 6,
                  "plotted_values": len(export), "rate_conversion": "precision and F1 multiplied by 100",
                  "median_definition": "Median across all requested hubs including zero-target hubs",
                  "aggregation": "None; all 15 Systems Genetics A simulations retained separately",
                  "axes": "Linear and zero-based within every metric; bulk R2 shown from 0 to 1.05 for label space",
                  "data_check": "Every bar width or height exactly equals its source-derived plotted value",
                  "environment": {"Python": platform.python_version(), "numpy": np.__version__, "matplotlib": matplotlib_version},
                  "figures": figures}
    (output / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8", newline="\n")
    text = """# Comparison bar plots

Paired bars compare pre-sampling-change **SJARACNe (legacy)** with **SJARACNe2**
using the [main report](../README.md)'s matched inputs and workflow definitions.
Blue denotes legacy SJARACNe and orange denotes SJARACNe2.

## DREAM precision

![Precision for all 18 DREAM settings](dream_precision.png)

Download [PDF](dream_precision.pdf) or [SVG](dream_precision.svg).

## DREAM F1

![F1 for all 18 DREAM settings](dream_f1.png)

Download [PDF](dream_f1.pdf) or [SVG](dream_f1.svg).

Precision and F1 are percentages. N1/N3/N4 and all 15 Systems Genetics A
simulations are shown separately. A100/A300/A999 denote simulation profile
counts. No averaging or pooling across networks is applied.

## Bulk median targets

![Median targets for the six bulk TF/SIG networks](bulk_median_targets.png)

Download [PDF](bulk_median_targets.pdf) or [SVG](bulk_median_targets.svg).

Median targets includes all requested hubs, including zero-target hubs.

## Bulk adjusted scale-free R²

![Adjusted scale-free R2 for the six bulk TF/SIG networks](bulk_adjusted_scale_free_r2.png)

Download [PDF](bulk_adjusted_scale_free_r2.pdf) or [SVG](bulk_adjusted_scale_free_r2.svg).

Adjusted scale-free R² is the existing NetBID2 degree-fit statistic. It describes
network topology and does not establish biological edge accuracy. Both bulk
figures use BRCA100, TCGA-LUAD517 and TCGA-BLCA406, with separate TF/SIG panels.

All bar axes start at zero. Labels show two decimal places for percentages,
the recorded median counts and four decimal places for R². Exact values are in
[plot_values.tsv](plot_values.tsv), copied from [comparison.tsv](../comparison.tsv)
with only percentage conversion. No networks or metrics were recomputed.

[Provenance](provenance.json) · [Plotting script](plot_bars.py)

```bash
python plot_bars.py
```

The script requires NumPy and Matplotlib and reads only the parent comparison
table. It writes PNG, PDF and SVG versions of all four figures.
"""
    (output / "README.md").write_text(text, encoding="utf-8", newline="\n")
    print(json.dumps({"figures": 4, "formats": ["PNG", "PDF", "SVG"], "bars": len(export)}))


if __name__ == "__main__":
    main()
