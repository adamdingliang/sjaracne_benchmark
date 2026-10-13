#!/usr/bin/env python3
"""Draw eligible-only TP, realized shuffled EPR and MI-tied ROC panels.

Uses frozen legacy inference/reference artifacts without changing any scores.
The output is Fig. 6a-style, not an exact reproduction or a sampling comparison.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator, StrMethodFormatter

import score_fixed_universe as fixed


PAPER = "https://www.nature.com/articles/s41467-025-59620-6"
NETWORKS = [("consensus_pc1e-02", "#4477AA"), ("consensus_pc1e-03", "#228833")]


def local_path(value: str) -> Path:
    """Resolve saved Windows and WSL drive paths on either interpreter."""
    match = re.match(r"^/mnt/([a-zA-Z])/(.*)$", value)
    if os.name == "nt" and match:
        value = match[1].upper() + ":/" + match[2]
    return fixed.record_path(value)


def verify_manifest(path: Path, hashes: dict[str, str]) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("status") != "complete":
        raise ValueError(f"Incomplete scoring manifest: {path}")
    hashes[str(path)] = fixed.digest(path)
    for recorded, expected in data["input_sha256"].items():
        source = local_path(recorded)
        if fixed.digest(source) != expected:
            raise ValueError(f"Frozen input checksum mismatch: {source}")
        hashes[str(source)] = expected
    for name, expected in data["output_sha256"].items():
        source = path.parent / name
        if fixed.digest(source) != expected:
            raise ValueError(f"Frozen score checksum mismatch: {source}")
        hashes[str(source)] = expected
    return data


def validate_ranked(rows: list[dict[str, str]], total: int, positive: int):
    """Validate saved 1k checkpoints and endpoint; never invent EPR at zero."""
    k = [int(row["k"]) for row in rows]
    expected = list(range(1000, total + 1, 1000))
    if not expected or expected[-1] != total:
        expected.append(total)
    if k != expected:
        raise ValueError("Saved eligible ranks do not match complete 1k checkpoints/end")
    tp = [int(row["TP"]) for row in rows]
    random_tp = [int(row["Random_TP"]) for row in rows]
    epr = [float(row["EPR_R_seed1_shuffle"]) if row["EPR_R_seed1_shuffle"] != "NA"
           else math.nan for row in rows]
    for values in (tp, random_tp):
        if any(value < 0 or value > rank for rank, value in zip(k, values)):
            raise ValueError("TP outside zero-to-k bounds")
        if any(b < a for a, b in zip(values, values[1:])):
            raise ValueError("Cumulative TP decreases")
        if values[-1] != positive:
            raise ValueError("Full-pool TP differs from saved population")
    for observed, numerator, denominator in zip(epr, tp, random_tp):
        if denominator == 0:
            if not math.isnan(observed):
                raise ValueError("EPR must be unavailable when shuffled TP is zero")
        elif not math.isclose(observed, numerator / denominator, abs_tol=1e-12):
            raise ValueError("Saved EPR is not TP / realized shuffled TP")
    return {"k": k, "TP": tp, "Random_TP": random_tp, "EPR": epr}


def eligible_roc(groups, positive: int, negative: int, expected_auc: float):
    """ROC denominators are only emitted eligible pairs; omitted pairs excluded."""
    if sum(p for _, p, _ in groups) != positive or sum(n for _, _, n in groups) != negative:
        raise ValueError("MI groups do not equal the eligible emitted population")
    score, curve = fixed.fixed_roc(groups, positive, negative)
    auc = score["AUROC_fixed_universe_MI_ties"]
    if not math.isclose(auc, expected_auc, abs_tol=1e-12):
        raise ValueError("Eligible ROC differs from frozen AUROC")
    if any(row["threshold_kind"] == "omitted_bottom" for row in curve):
        raise ValueError("Eligible-only ROC must not include omitted pairs")
    if (curve[0]["FPR"], curve[0]["sensitivity"]) != (0, 0) or (
        curve[-1]["FPR"], curve[-1]["sensitivity"]
    ) != (1, 1):
        raise ValueError("Incomplete eligible ROC")
    return auc, curve


def style_axes(ax):
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#dddddd", linewidth=.6)
    ax.tick_params(labelsize=10)


def draw_panel(ax, panel, curves):
    style_axes(ax)
    if panel in ("tp", "epr"):
        maximum = max(c["ranked"]["k"][-1] for c in curves)
        ax.set_xlim(0, maximum * 1.035)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
        ax.xaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
        ax.set_xlabel(r"Top-ranked eligible edges, $k$")
        for c in curves:
            rank = c["ranked"]
            if panel == "tp":
                ax.plot([0, *rank["k"]], [0, *rank["Random_TP"]],
                        color=c["color"], lw=1.6, ls="--", alpha=.75)
                ax.plot([0, *rank["k"]], [0, *rank["TP"]], color=c["color"], lw=2)
                ax.plot(rank["k"][-1], rank["TP"][-1], "o", color=c["color"], ms=4)
            else:
                ax.plot(rank["k"], rank["EPR"], color=c["color"], lw=2)
                ax.plot(rank["k"][-1], rank["EPR"][-1], "o", color=c["color"], ms=4)
        if panel == "tp":
            ax.set_title("TP counts", loc="left", pad=12)
            ax.set_ylabel("Response-positive edges (TP)")
            ax.set_ylim(bottom=0)
            ax.yaxis.set_major_locator(MaxNLocator(nbins=5, integer=True))
            ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
            ax.legend(handles=[
                Line2D([0], [0], color="#444444", lw=2, label="MI-ranked"),
                Line2D([0], [0], color="#444444", lw=1.6, ls="--", label="Rank shuffle"),
            ], loc="upper left", fontsize=9, frameon=False)
        else:
            ax.set_title("Early precision ratio", loc="left", pad=12)
            ax.set_ylabel("EPR = TP / shuffled TP")
            ax.axhline(1, color="#777777", lw=1.2, ls="--")
            values = [v for c in curves for v in c["ranked"]["EPR"] if math.isfinite(v)]
            ax.set_ylim(min(1, min(values)) - .06, max(1, max(values)) + .06)
    else:
        for c in curves:
            ax.plot([r["FPR"] for r in c["roc"]], [r["sensitivity"] for r in c["roc"]],
                    color=c["color"], lw=2,
                    label=rf"$p_c={c['consensus_p']:g}$: AUROC {c['AUROC']:.4f}")
        ax.plot([0, 1], [0, 1], color="#777777", lw=1.2, ls="--", label="Random expectation")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_aspect("equal", adjustable="box")
        ax.set_title("ROC (eligible emitted edges)", loc="left", pad=12)
        ax.set_xlabel("1 − specificity (within emitted pool)")
        ax.set_ylabel("Sensitivity (within emitted pool)")
        ax.legend(loc="lower right", fontsize=9, frameon=False)


def render(curves, out):
    plt.rcParams.update({
        "font.family": "DejaVu Sans", "font.size": 11,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.labelsize": 10, "axes.titlesize": 12, "svg.fonttype": "none",
    })
    fig, axes = plt.subplots(1, 3, figsize=(14.6, 5.6))
    fig.subplots_adjust(left=.065, right=.985, bottom=.23, top=.74, wspace=.30)
    fig.suptitle("THP-1 perturbation-response benchmark", y=.99, fontsize=16)
    fig.text(.5, .905, "Eligible-source predictions, reconstructed legacy baseline", ha="center", fontsize=11)
    handles = [Line2D([0], [0], color=c["color"], lw=2,
                      label=rf"$p_c={c['consensus_p']:g}$: {c['N']:,} edges, {c['P']:,} positives")
               for c in curves]
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, .873),
               ncol=2, frameon=False, fontsize=10)
    for ax, panel in zip(axes, ("tp", "epr", "roc")):
        draw_panel(ax, panel, curves)
    fig.text(.065, .105,
             "TP/EPR: saved 1,000-edge checkpoints and full-pool endpoints; saved MI tie order; eligible-only R seed-1 rank shuffle.",
             fontsize=9, color="#444444")
    fig.text(.065, .065,
             "ROC retains MI ties. Full SIG inference is unchanged; evaluation uses eligible sources only. Labels describe responses, not direct regulation.",
             fontsize=9, color="#444444")
    paths = []
    for extension in ("png", "svg"):
        path = out / f"eligible_source_fig6a_style.{extension}"
        fig.savefig(path, dpi=220, facecolor="white")
        paths.append(path)
    plt.close(fig)
    for panel in ("tp", "epr", "roc"):
        fig, ax = plt.subplots(figsize=(5.8, 5.4))
        fig.subplots_adjust(left=.17, right=.965, bottom=.21, top=.70)
        draw_panel(ax, panel, curves)
        fig.suptitle("THP-1 eligible-source predictions", y=.98, fontsize=14)
        fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, .93),
                   ncol=1, frameon=False, fontsize=9)
        note = ("Saved checkpoints; eligible-only R seed-1 rank shuffle.\n"
                "TP/EPR preserve saved MI tie order; no extrapolation.") if panel != "roc" else (
                    "MI-tied ROC within emitted eligible predictions only.\n"
                    "The diagonal is the random expectation, not a realized shuffle.")
        fig.text(.5, .075, note, ha="center", fontsize=8.5, color="#444444")
        for extension in ("png", "svg"):
            path = out / f"eligible_{panel}.{extension}"
            fig.savefig(path, dpi=220, facecolor="white")
            paths.append(path)
        plt.close(fig)
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-root", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    root, out = args.result_root.resolve(strict=True), args.out.resolve()
    if out.exists():
        raise FileExistsError(f"Refusing to overwrite output: {out}")
    hashes = {}
    three = verify_manifest(root / "three_populations_20261012" / "metrics.json", hashes)
    epr = verify_manifest(root / "eligible_epr_20261012" / "metrics.json", hashes)
    if three["primary_population"] != "eligible_emitted" or epr["primary_population"] != "eligible_emitted":
        raise ValueError("Wrong primary scoring population")
    for filename, expected in [("score_fixed_universe.py", three["helper_sha256"]),
                               ("score_three_populations.py", three["script_sha256"]),
                               ("score_eligible_epr.R", epr["script_sha256"])]:
        path = Path(__file__).with_name(filename)
        if fixed.digest(path) != expected:
            raise ValueError(f"Changed scorer: {path}")
        hashes[str(path)] = expected
    universe = fixed.make_universe(root / "prepared")
    if universe.size != three["universe"]["candidate_pairs"] or len(universe.positives) != three["universe"]["reference_positive_pairs"]:
        raise ValueError("Eligible reference differs from frozen score")
    hubs = set((root / "prepared" / "hubs.txt").read_text(encoding="utf-8").splitlines())
    ranked_path = root / "eligible_epr_20261012" / "ranked_curves.tsv"
    rows = list(fixed.rows(ranked_path))
    curves, roc_rows = [], []
    for name, color in NETWORKS:
        score = three["scores"][name]
        population = score["populations"]["eligible_emitted"]
        total, positive = population["candidate_pairs"], population["reference_positive_pairs_in_population"]
        er = epr["scores"][name]
        if (total, positive, score["consensus_p"]) != (er["eligible_emitted_pairs"], er["reference_positive_emitted_pairs"], er["consensus_p"]):
            raise ValueError("Eligible EPR and ROC populations differ")
        ranked = validate_ranked([r for r in rows if r["consensus"] == name], total, positive)
        groups, full_count, full_positive = fixed.read_network(root / "legacy" / name / "edges.tsv", universe, hubs)
        if full_count != score["populations"]["full_emitted"]["candidate_pairs"] or full_positive != positive:
            raise ValueError("Frozen full SIG network differs from score")
        auc, roc = eligible_roc(groups, positive, total - positive, population["AUROC_MI_ties"])
        roc_rows.extend({"consensus": name, "consensus_p": score["consensus_p"], **row} for row in roc)
        curves.append({"name": name, "color": color, "consensus_p": score["consensus_p"],
                       "N": total, "P": positive, "AUROC": auc, "ranked": ranked, "roc": roc})
    if any(fixed.digest(Path(path)) != value for path, value in hashes.items()):
        raise ValueError("Frozen artifacts changed while plotting")
    out.mkdir(parents=True, exist_ok=False)
    outputs = render(curves, out)
    roc_path = out / "eligible_roc_curves.tsv"
    fixed.write_tsv(roc_path, roc_rows)
    outputs.append(roc_path)
    report = out / "README.md"
    report.write_text(
        "# Eligible-source predictions: Fig. 6a-style plots\n\n"
        "Combined and individual TP, EPR and ROC panels use the reconstructed legacy baseline. "
        "Full SIG inference and frozen perturbation-response labels are unchanged. This is neither an exact Fig. 6a reproduction nor a before/after comparison.\n\n"
        "TP/EPR use saved 1,000-edge checkpoints plus full-pool endpoints, preserving saved MI tie order. "
        "Dashed TP curves are the actual R seed-1 eligible-only rank shuffle. EPR = TP / shuffled TP. "
        "No EPR at k=0 is invented and neither network is padded beyond its emitted eligible pool.\n\n"
        "ROC is independently recounted from consensus MI, retaining ties. Only emitted eligible pairs enter its denominators, "
        "with no omitted bottom-score group. The gray diagonal is the random expectation, not the realized shuffled ROC. "
        "Response-reference nonmembers are operational negatives, not established biological negatives.\n\n"
        "| Consensus p_c | Eligible edges | Positive matches | AUROC |\n|---:|---:|---:|---:|\n" +
        "".join(f"| {c['consensus_p']:g} | {c['N']:,} | {c['P']:,} | {c['AUROC']:.6f} |\n" for c in curves) +
        f"\nPanel arrangement follows [scMINER Figure 6a]({PAPER}). PNG files are raster figures; SVG files retain vector lines and editable text.\n",
        encoding="utf-8",
    )
    outputs.append(report)
    if any(fixed.digest(Path(path)) != value for path, value in hashes.items()):
        raise ValueError("Frozen artifacts changed while writing plots")
    manifest = {
        "created_utc": datetime.now(timezone.utc).isoformat(), "status": "complete",
        "scope": "eligible_source_emitted_predictions_legacy_baseline_only", "paper": PAPER,
        "eligible_source_count": len(universe.sources),
        "script_sha256": fixed.digest(Path(__file__)), "matplotlib_version": matplotlib.__version__,
        "input_sha256": hashes,
        "curves": [{key: c[key] for key in ("name", "consensus_p", "N", "P", "AUROC")} |
                   {"ranked_checkpoints": len(c["ranked"]["k"]), "ROC_points": len(c["roc"])} for c in curves],
        "definitions": {
            "TP_EPR": "Saved MI tie order, integer prefix TP, eligible-only realized R seed-1 rank shuffle",
            "ROC": "Raw consensus MI ties retained; emitted eligible-pool positives/nonmembers only",
            "ROC_random": "Expected diagonal, not a realized shuffled ROC",
            "labels": "Perturbation-response membership, not direct regulatory-edge truth",
        },
        "output_sha256": {path.name: fixed.digest(path) for path in outputs},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(out), "curves": manifest["curves"]}, indent=2))


if __name__ == "__main__":
    main()
