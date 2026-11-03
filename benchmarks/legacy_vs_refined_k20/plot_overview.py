#!/usr/bin/env python3
"""Plot compact summaries from frozen evidence, without rerunning inference.

Requires matplotlib. Original NetBID2 PNGs are imported separately without
pixel changes; these overview charts plot the already-recorded metric values.
"""

from __future__ import annotations

import argparse
import io
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from package_evidence import DEFAULT_OUTPUT, read_json, sha256, validate


COLORS = {"legacy": "#4477AA", "current": "#EE7733"}


def save_immutable(figure, destination):
    """Write a deterministic PNG, refusing a different existing artifact."""
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=170,
                   metadata={"Software": "SJARACNe benchmark summary"})
    data = buffer.getvalue()
    if destination.exists() and destination.read_bytes() != data:
        raise ValueError(f"Refusing different existing plot: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if not destination.exists():
        destination.write_bytes(data)
    plt.close(figure)


def dream_comparison(report, destination):
    """Distinguish historical consensus from matched-K20 accuracy comparisons."""
    figure, axes = plt.subplots(2, 2, figsize=(10, 7), layout="constrained")
    for row, (group, title) in enumerate((("primary_dream", "Historical final consensus vs refined K20"),
                                          ("matched_dream", "Matched K20 on both sets of resamples"))):
        records = {(r["dataset"], r["version"]): r for r in report[group]}
        for column, metric in enumerate(("precision", "recall")):
            axis = axes[row, column]
            for offset, version in ((-.18, "legacy"), (.18, "current")):
                values = [100 * records[(dataset, version)]["metrics"][metric]
                          for dataset in ("DREAM5_N1", "DREAM5_N3")]
                bars = axis.bar([offset, 1 + offset], values, width=.34,
                                color=COLORS[version], label="Legacy" if version == "legacy" else "Refined")
                axis.bar_label(bars, labels=[f"{value:.2f}" for value in values], padding=3, fontsize=9)
            axis.set_xticks([0, 1], ["Network 1 (simulated)", "Network 3 (E. coli)"])
            axis.set_ylim(0, 20 if metric == "precision" else 50)
            axis.set_ylabel(metric.capitalize() + " (%)")
            axis.set_title(title, fontsize=10)
            axis.grid(axis="y", alpha=.2)
            axis.set_axisbelow(True)
            if row == 0 and column == 0:
                axis.legend(frameon=False, loc="upper right")
    figure.suptitle("DREAM5 final networks: precision / recall trade-off", fontsize=14)
    save_immutable(figure, destination)


def bulk_comparison(report, destination):
    """Plot all-hub target medians and adjusted scale-free fits separately."""
    figure, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    records = {(r["dataset"], r["network"], r["version"]): r for r in report["primary_bulk"]}
    cases = [(dataset, network) for dataset in ("BRCA100", "LUAD517", "BLCA406")
             for network in ("TF", "SIG")]
    for axis, metric, title, limit in zip(axes, ("median_targets", "scale_free_adjusted_r2"),
                                         ("Median targets (all candidate hubs)", "Adjusted scale-free R²"),
                                         (330, 1.08)):
        for offset, version in ((-.18, "legacy"), (.18, "current")):
            values = [records[(dataset, network, version)]["metrics"][metric] for dataset, network in cases]
            bars = axis.bar([i + offset for i in range(len(cases))], values, width=.34,
                            color=COLORS[version], label="Legacy pc=1e-5" if version == "legacy" else "Refined K20")
            axis.bar_label(bars, labels=[f"{v:.0f}" if metric == "median_targets" else f"{v:.3f}"
                                        for v in values], padding=3, fontsize=8,
                           rotation=0 if metric == "median_targets" else 90)
        axis.set_xticks(range(len(cases)), [dataset + "\n" + network for dataset, network in cases], fontsize=9)
        axis.set_title(title)
        axis.set_ylim(0, limit)
        axis.grid(axis="y", alpha=.2)
        axis.set_axisbelow(True)
    axes[0].legend(frameon=False, loc="upper right")
    figure.suptitle("Bulk final-network coverage and topology — not biological accuracy", fontsize=13)
    save_immutable(figure, destination)


def main():
    """Generate two charts and record their source/code hashes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = args.output.resolve()
    validate(output)
    source = output / "evidence/report_data.json"
    report = read_json(source)
    destinations = [output / "figures/dream5_comparison.png", output / "figures/bulk_qc_comparison.png"]
    dream_comparison(report, destinations[0])
    bulk_comparison(report, destinations[1])
    provenance = {"source": "evidence/report_data.json", "source_sha256": sha256(source),
                  "plot_code": "plot_overview.py", "plot_code_sha256": sha256(__file__),
                  "matplotlib_version": matplotlib.__version__,
                  "plots": [{"path": p.relative_to(output).as_posix(), "sha256": sha256(p)} for p in destinations],
                  "scope": "Recorded metric visualization only; no inference, fitting or biological validation."}
    target = output / "figures/overview_manifest.json"
    data = (json.dumps(provenance, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if target.exists() and target.read_bytes() != data:
        raise ValueError("Refusing different existing overview provenance")
    if not target.exists():
        target.write_bytes(data)
    print(json.dumps(provenance, indent=2))


if __name__ == "__main__":
    main()
