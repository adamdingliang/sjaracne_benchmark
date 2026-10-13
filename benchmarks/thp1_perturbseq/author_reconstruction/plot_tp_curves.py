#!/usr/bin/env python3
"""Plot frozen Fig. 6a and reconstructed legacy TP counts, without rescoring."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator, StrMethodFormatter


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verified_rows(path: Path, manifest: Path, hash_key: str) -> list[dict[str, str]]:
    recorded = json.loads(manifest.read_text(encoding="utf-8"))[hash_key][path.name]
    if sha256(path) != recorded:
        raise ValueError(f"Input checksum mismatch: {path}")
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def counts(rows: list[dict[str, str]], column: str) -> tuple[list[int], list[int]]:
    k = [int(row["k"]) for row in rows]
    tp = [int(row[column]) for row in rows]
    if not k or k != list(range(1000, k[-1] + 1, 1000)):
        raise ValueError("Expected contiguous saved 1,000-edge checkpoints")
    if any(value < 0 or value > rank for rank, value in zip(k, tp)):
        raise ValueError("TP counts must lie between zero and k")
    if any(b < a for a, b in zip(tp, tp[1:])):
        raise ValueError("Cumulative TP counts must be nondecreasing")
    # TP(0)=0 is exact. No points are added beyond the saved endpoints.
    return [0, *k], [0, *tp]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    root = args.result_root.resolve()
    out = args.out.resolve()
    if out.exists():
        raise FileExistsError(f"Refusing to overwrite an existing output directory: {out}")

    publication = root / "publication" / "tp.tsv"
    published_rows = verified_rows(
        publication, publication.with_name("manifest.json"), "outputs_sha256"
    )
    curves = []
    published = counts([r for r in published_rows if r["method"] == "scMINER"], "TP")
    published_random = counts([r for r in published_rows if r["method"] == "Random"], "TP")
    if published[0] != published_random[0]:
        raise ValueError("Published method and random ranks differ")
    curves.append({
        "label": "Published scMINER Fig. 6a", "color": "#CC6677",
        "ranked": published, "random": published_random, "input": publication,
    })
    for cutoff, color in [("1e-02", "#4477AA"), ("1e-03", "#228833")]:
        path = root / "comparison" / f"score_pc{cutoff}" / "ranked_curves.tsv"
        rows = verified_rows(path, path.with_name("metrics.json"), "output_sha256")
        curves.append({
            "label": rf"Legacy reconstruction, $p_c={float(cutoff):g}$",
            "color": color, "ranked": counts(rows, "TP"),
            "random": counts(rows, "Random_TP"), "input": path,
        })

    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 11,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.labelsize": 11, "axes.titlesize": 12,
        "pdf.fonttype": 42, "svg.fonttype": "none",
    })
    fig, axes = plt.subplots(1, 2, figsize=(13.5, 6.2))
    fig.subplots_adjust(left=0.075, right=0.985, bottom=0.255, top=0.785, wspace=0.22)
    for ax, limit, title in zip(
        axes, [100_000, max(c["ranked"][0][-1] for c in curves)],
        ["Early ranks: first 100,000 edges", "Full available trajectories"],
    ):
        for curve in curves:
            for key, style, width, alpha in [
                ("random", "--", 1.5, 0.65), ("ranked", "-", 2.0, 1.0)
            ]:
                k, tp = curve[key]
                selected = [(x, y) for x, y in zip(k, tp) if x <= limit]
                ax.plot(
                    [p[0] for p in selected], [p[1] for p in selected],
                    color=curve["color"], linestyle=style, linewidth=width, alpha=alpha,
                )
        ax.set_xlim(0, limit)
        ax.set_ylim(bottom=0)
        ax.set_title(title, pad=12)
        ax.set_xlabel(r"Top-ranked edges, $k$")
        ax.xaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
        ax.yaxis.set_major_locator(MaxNLocator(nbins=6, integer=True))
        ax.xaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
        ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
        ax.grid(axis="y", color="#d9d9d9", linewidth=0.6, alpha=0.8)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("Reference-positive edges (TP count)")
    fig.suptitle("THP-1 perturbation-response benchmark: TP counts versus rank", y=0.97, fontsize=16)
    fig.legend(
        handles=[Line2D([0], [0], color=c["color"], lw=2, label=c["label"]) for c in curves],
        loc="upper center", bbox_to_anchor=(0.5, 0.915), ncol=3, frameon=False,
        columnspacing=2.0,
    )
    fig.legend(
        handles=[
            Line2D([0], [0], color="#444444", lw=2, label="MI-ranked predictions"),
            Line2D([0], [0], color="#444444", lw=1.5, ls="--", label="Saved random comparator"),
        ], loc="lower center", bbox_to_anchor=(0.5, 0.145), ncol=2, frameon=False,
    )
    fig.text(
        0.5, 0.095,
        "Published and reconstructed response references are not matched; higher TP is not evidence of improved inference.",
        ha="center", fontsize=10, color="#444444",
    )
    fig.text(
        0.5, 0.055,
        "Saved 1,000-edge checkpoints, with TP(0) = 0. Curves stop at saved endpoints. Both reconstructions use legacy sampling.",
        ha="center", fontsize=10, color="#444444",
    )

    out.mkdir(parents=True, exist_ok=False)
    output_paths = [out / "tp_counts_vs_k.png", out / "tp_counts_vs_k.pdf"]
    for path in output_paths:
        fig.savefig(path, dpi=200, facecolor="white")
    plt.close(fig)
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "script_sha256": sha256(Path(__file__)),
        "matplotlib_version": matplotlib.__version__,
        "data_scope": "Original global emitted-network TP checkpoints, not fixed-universe eligible-only rankings",
        "limitations": [
            "Published and reconstructed response references are not matched",
            "Both reconstructions use legacy sampling; no after-change arm is included",
            "Line segments connect saved checkpoints, without extrapolation",
            "Most reconstructed top-k boundaries split MI ties; small differences may depend on tie order",
            "Response-positive pairs are not a direct regulatory-edge gold standard",
        ],
        "curves": [{
            "label": c["label"], "input": str(c["input"]),
            "input_sha256": sha256(c["input"]),
            "saved_checkpoints": len(c["ranked"][0]) - 1,
            "last_saved_k": c["ranked"][0][-1],
            "last_saved_TP": c["ranked"][1][-1],
            "last_saved_Random_TP": c["random"][1][-1],
        } for c in curves],
        "outputs_sha256": {p.name: sha256(p) for p in output_paths},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(out), "curves": manifest["curves"]}, indent=2))


if __name__ == "__main__":
    main()
