#!/usr/bin/env python3
"""Aggregate matched, per-resample raw-MI scores without pooling MI values.

This module consumes compact scoring dictionaries, not native adjacencies. It
does not launch inference, construct consensus networks, or re-score edges.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable


METRICS = {
    "TP": "TP_tie_expected",
    "FP": "FP_tie_expected",
    "precision": "precision_tie_expected",
    "sensitivity": "sensitivity_tie_expected",
    "specificity": "specificity_tie_expected",
    "EPR": "EPR_tie_expected",
}
UNIVERSE_FIELDS = (
    "candidate_pairs", "reference_positive_pairs", "reference_negative_pairs",
    "random_positive_fraction",
)


def percentile(values: Iterable[float], probability: float) -> float:
    """Linear-interpolated sample percentile (NumPy's default convention)."""
    ordered = sorted(float(value) for value in values)
    if not ordered or not 0 <= probability <= 1:
        raise ValueError("Need nonempty values and a percentile in [0, 1]")
    if any(not math.isfinite(value) for value in ordered):
        raise ValueError("Nonfinite metric")
    offset = (len(ordered) - 1) * probability
    lower = int(offset)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (offset - lower)


def describe(values: Iterable[float]) -> dict[str, float]:
    values = list(values)
    return {
        "median": percentile(values, .5),
        "q25": percentile(values, .25),
        "q75": percentile(values, .75),
        "min": min(values),
        "max": max(values),
    }


def _top_map(result: dict[str, Any]) -> dict[int, dict[str, Any]]:
    rows = result["top_k"]
    mapped = {int(row["k"]): row for row in rows}
    if len(mapped) != len(rows):
        raise ValueError("Duplicate top-k row")
    return mapped


def aggregate_results(
    results: list[dict[str, Any]],
    plan: dict[str, Any],
    *,
    before_arm: str = "before",
    after_arm: str = "after",
    primary_k: int = 5000,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Validate a complete matched pilot and summarize its paired metrics.

    Identical integer seed IDs are pairing labels, not assertions that the
    sampled observations or RNG realizations are identical between protocols.
    """
    if before_arm == after_arm:
        raise ValueError("Before and after arms must differ")
    declared = plan.get("seeds", plan.get("selected_seeds"))
    if not isinstance(declared, list) or not declared:
        raise ValueError("plan.json must declare nonempty seeds or selected_seeds")
    seeds = sorted(int(seed) for seed in declared)
    if len(set(seeds)) != len(seeds):
        raise ValueError("Duplicate declared seed")
    expected = {(arm, seed) for arm in (before_arm, after_arm) for seed in seeds}
    indexed: dict[tuple[str, int], dict[str, Any]] = {}
    for result in results:
        if result.get("status") != "complete":
            raise ValueError("Only complete score results may be aggregated")
        key = (str(result["arm"]), int(result["seed"]))
        if key in indexed:
            raise ValueError(f"Duplicate score result: {key}")
        indexed[key] = result
    if set(indexed) != expected:
        raise ValueError(
            f"Matched result set incomplete or unexpected; "
            f"missing={sorted(expected-set(indexed))}, "
            f"extra={sorted(set(indexed)-expected)}"
        )
    first = indexed[(before_arm, seeds[0])]
    universe = {key: first[key] for key in UNIVERSE_FIELDS}
    declared_universe = plan.get("universe", {})
    if any(key in declared_universe and declared_universe[key] != universe[key]
           for key in UNIVERSE_FIELDS):
        raise ValueError("Score universe differs from the frozen plan")
    if "definition_sha256" in declared_universe:
        universe["definition_sha256"] = declared_universe["definition_sha256"]
    declared_primary = plan.get("parameters", {}).get("primary_k", primary_k)
    if declared_primary != primary_k:
        raise ValueError("Primary k differs from the frozen plan")
    if universe["candidate_pairs"] != (
        universe["reference_positive_pairs"] + universe["reference_negative_pairs"]
    ):
        raise ValueError("Universe positive and negative counts do not sum")
    prevalence = universe["reference_positive_pairs"] / universe["candidate_pairs"]
    if not math.isclose(universe["random_positive_fraction"], prevalence, abs_tol=1e-12):
        raise ValueError("Incorrect fixed-universe prevalence")
    top_ks = sorted(_top_map(first))
    if primary_k not in top_ks:
        raise ValueError(f"Primary k={primary_k} missing")
    curve_ks = [int(row["k"]) for row in first["curve"]]
    if curve_ks != sorted(set(curve_ks)):
        raise ValueError("Curve k values must be unique and increasing")
    for result in indexed.values():
        if any(result[key] != universe[key] for key in UNIVERSE_FIELDS):
            raise ValueError("Results do not use one fixed reference universe")
        if sorted(_top_map(result)) != top_ks:
            raise ValueError("Results have different top-k evaluation grids")
        if [int(row["k"]) for row in result["curve"]] != curve_ks:
            raise ValueError("Results have different curve evaluation grids")
        auc = float(result["AUROC_MI_ties"])
        if not math.isfinite(auc) or not 0 <= auc <= 1:
            raise ValueError("Invalid AUROC")
        for row in result["top_k"]:
            for key in METRICS.values():
                if not math.isfinite(float(row[key])):
                    raise ValueError("Nonfinite top-k metric")
            if not math.isclose(
                row["EPR_tie_expected"], row["precision_tie_expected"] / prevalence,
                rel_tol=1e-10, abs_tol=1e-10,
            ):
                raise ValueError("EPR inconsistent with fixed reference prevalence")

    paired: list[dict[str, Any]] = []
    top_summary: dict[str, Any] = {}
    for k in top_ks:
        rows_at_k: list[dict[str, Any]] = []
        for seed in seeds:
            before = _top_map(indexed[(before_arm, seed)])[k]
            after = _top_map(indexed[(after_arm, seed)])[k]
            row: dict[str, Any] = {"seed": seed, "k": k}
            for name, score_key in METRICS.items():
                row[f"before_{name}"] = before[score_key]
                row[f"after_{name}"] = after[score_key]
                row[f"delta_{name}"] = after[score_key] - before[score_key]
            row["before_AUROC"] = indexed[(before_arm, seed)]["AUROC_MI_ties"]
            row["after_AUROC"] = indexed[(after_arm, seed)]["AUROC_MI_ties"]
            row["delta_AUROC"] = row["after_AUROC"] - row["before_AUROC"]
            row["before_TP_min"] = before["TP_min"]
            row["before_TP_max"] = before["TP_max"]
            row["after_TP_min"] = after["TP_min"]
            row["after_TP_max"] = after["TP_max"]
            rows_at_k.append(row)
            paired.append(row)
        top_summary[str(k)] = {
            name: {
                "before": describe(row[f"before_{name}"] for row in rows_at_k),
                "after": describe(row[f"after_{name}"] for row in rows_at_k),
                "paired_delta": describe(row[f"delta_{name}"] for row in rows_at_k),
            }
            for name in METRICS
        }
    primary_rows = [row for row in paired if row["k"] == primary_k]
    improved = sum(row["delta_TP"] > 0 for row in primary_rows)
    reduced = sum(row["delta_TP"] < 0 for row in primary_rows)
    unchanged = len(seeds) - improved - reduced
    auc_summary = {
        "before": describe(row["before_AUROC"] for row in primary_rows),
        "after": describe(row["after_AUROC"] for row in primary_rows),
        "paired_delta": describe(row["delta_AUROC"] for row in primary_rows),
    }
    if improved == len(seeds):
        conclusion = "All selected resamples have higher response-positive TP at the primary k."
    elif reduced == len(seeds):
        conclusion = "All selected resamples have lower response-positive TP at the primary k."
    elif unchanged == len(seeds):
        conclusion = "All selected resamples have unchanged response-positive TP at the primary k."
    else:
        conclusion = "The primary-k direction is mixed across selected resamples."
    return {
        "schema_version": 1,
        "status": "complete",
        "scope": "matched per-resample raw-MI ranking pilot",
        "arms": {"before": before_arm, "after": after_arm},
        "seeds": seeds,
        "seed_selection": plan.get("selection"),
        "n_matched_seeds": len(seeds),
        "primary_k": primary_k,
        "universe": universe,
        "top_k": top_summary,
        "AUROC": auc_summary,
        "primary_TP_direction_counts": {
            "higher": improved, "lower": reduced, "unchanged": unchanged,
        },
        "descriptive_conclusion": conclusion,
        "uncertainty": "IQR describes selected computational resamples, not biological replication or a confidence interval.",
        "ROC_plot_policy": "Individual sampled ROC curves (common-FPR interpolation when available, otherwise common rank budgets); AUROC is calculated using all exact-MI tie groups, not numerical integration of the plotted samples.",
    }, paired


def plot_comparison(
    results: list[dict[str, Any]], summary: dict[str, Any], output: Path,
) -> None:
    """Write one three-panel static plot without averaging ROC curves."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    arms = summary["arms"]
    colors = {"before": "#4c72b0", "after": "#dd8452"}
    labels = {"before": "Before: replacement", "after": "After: 80% without replacement"}
    max_rank_budget = max(int(k) for k in summary["top_k"])
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.3))
    for role, arm in arms.items():
        arm_results = sorted((r for r in results if r["arm"] == arm), key=lambda r: r["seed"])
        for panel, key in ((0, "TP_tie_expected"), (1, "EPR_tie_expected")):
            grid = [row["k"] for row in arm_results[0]["curve"] if 0 < row["k"] <= max_rank_budget]
            values = [
                [row[key] for row in result["curve"] if 0 < row["k"] <= max_rank_budget]
                for result in arm_results
            ]
            median = [percentile(column, .5) for column in zip(*values)]
            q25 = [percentile(column, .25) for column in zip(*values)]
            q75 = [percentile(column, .75) for column in zip(*values)]
            axes[panel].plot(grid, median, color=colors[role], label=labels[role])
            axes[panel].fill_between(grid, q25, q75, color=colors[role], alpha=.2)
        for index, result in enumerate(arm_results):
            roc = result.get("roc_curve")
            fpr = roc["FPR"] if roc else [row["FPR_tie_expected"] for row in result["curve"]]
            sensitivity = roc["sensitivity"] if roc else [row["sensitivity_tie_expected"] for row in result["curve"]]
            axes[2].plot(
                fpr, sensitivity,
                color=colors[role], alpha=.22, lw=.8,
                label=(f"{labels[role]} (median AUROC {summary['AUROC'][role]['median']:.4f})"
                       if index == 0 else None),
            )
    for axis in axes[:2]:
        axis.set_xscale("log")
        axis.set_xlabel("Top-ranked eligible pairs, k (log scale)")
        axis.axvline(summary["primary_k"], color=".45", ls=":", lw=.8)
        axis.grid(alpha=.15)
    axes[0].set_ylabel("Response-positive TP (tie-expected)")
    axes[0].set_title("TP at equal prediction budgets")
    axes[1].set_ylabel("EPR (fixed reference prevalence)")
    axes[1].set_title("Median and interquartile range")
    axes[1].axhline(1, color=".45", ls="--", lw=.8)
    axes[2].plot([0, 1], [0, 1], "--", color=".55", lw=.8)
    axes[2].set(xlabel="False-positive rate", ylabel="Sensitivity", xlim=(0, 1), ylim=(0, 1))
    axes[2].set_title("Individual sampled ROC curves")
    axes[0].legend(fontsize=8)
    axes[2].legend(fontsize=7, loc="lower right")
    fig.suptitle(f"THP-1 raw MI: {summary['n_matched_seeds']} matched seed IDs; no threshold, DPI or consensus")
    fig.tight_layout()
    fig.savefig(output, dpi=170)
    plt.close(fig)


def report_markdown(summary: dict[str, Any]) -> str:
    """Describe the actual observed direction without significance claims."""
    n = summary["n_matched_seeds"]
    k = summary["primary_k"]
    universe = summary["universe"]
    direction = summary["primary_TP_direction_counts"]
    lines = [
        "# THP-1 per-resample raw-MI pilot", "",
        "This is a sampling-stage ranking benchmark against a frozen Perturb-seq "
        "response reference, not an exact reproduction of scMINER Fig. 6a and not "
        "a direct-regulatory-edge gold-standard benchmark.", "",
        "## Matched design", "",
        f"- {n} seed IDs selected before scoring: {', '.join(map(str, summary['seeds']))}.",
        "- Before: 121 draws with replacement from 121 NT-cell metacells. "
        "After: 97 distinct metacells (80% fixed-size sampling without replacement).",
        "- Same metacell matrix, genes, full SIG hub list and eligible-source response reference.",
        "- No MI thresholding, DPI pruning or consensus construction in either arm; "
        "raw MI is ranked separately for each resample, never averaged across resamples.",
        f"- Fixed scoring universe: {universe['candidate_pairs']:,} non-self eligible pairs; "
        f"{universe['reference_positive_pairs']:,} response-positive and "
        f"{universe['reference_negative_pairs']:,} operational negatives.",
        f"- Fixed random precision is {universe['random_positive_fraction']:.8f}; "
        "EPR@k = (TP@k / k) / random precision. No random graph simulation is needed.",
        f"- Primary endpoint: tie-expected TP@{k:,}. Other declared top-k metrics "
        "and full-ranking AUROC are secondary.",
        "- Exact equal serialized native MI scores are ties (native output has approximately "
        "six significant digits). A boundary tie contributes expected TP proportionally; "
        "paired TSV also records feasible TP minimum and maximum. AUROC awards half-credit to tied positive/negative pairs.",
        "", "## Results", "",
        f"{summary['descriptive_conclusion']} Higher: {direction['higher']}; "
        f"lower: {direction['lower']}; unchanged: {direction['unchanged']}.", "",
        "Numbers below are medians across selected resamples. The delta column is "
        "the median of paired after-minus-before differences, not the difference of marginal medians.", "",
        "| k | TP before | TP after | Paired TP delta | Precision before | Precision after | EPR before | EPR after |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for top_k, metrics in summary["top_k"].items():
        med = lambda metric, role: metrics[metric][role]["median"]
        lines.append(
            f"| {int(top_k):,} | {med('TP', 'before'):.2f} | {med('TP', 'after'):.2f} "
            f"| {med('TP', 'paired_delta'):+.2f} | {med('precision', 'before'):.4f} "
            f"| {med('precision', 'after'):.4f} | {med('EPR', 'before'):.4f} "
            f"| {med('EPR', 'after'):.4f} |"
        )
    auc = summary["AUROC"]
    lines += [
        "", f"Full-ranking AUROC median: {auc['before']['median']:.6f} before; "
        f"{auc['after']['median']:.6f} after; paired median delta "
        f"{auc['paired_delta']['median']:+.6f}.", "",
        "At fixed k, FP = k - TP: a TP increase implies an equal FP decrease. "
        "Precision, sensitivity and EPR share the same TP numerator and fixed "
        "denominators, so their directions are not independent confirmations.", "",
        "![TP, EPR and sampled ROC comparison](raw_mi_comparison.png)", "",
        "TP/EPR lines show medians; bands show the interquartile range. ROC lines "
        "are individual resamples (common-FPR interpolation when available, "
        "otherwise common rank budgets), not an averaged "
        "ROC. AUROC values use all MI tie groups, not sparse plotted coordinates.", "",
        "TP/EPR panels stop at the largest prespecified top-k budget; the ROC "
        "panel and AUROC cover the entire eligible universe.", "",
        "## Limits and defensible interpretation", "",
        "- These are computational resamples of the same cells, not independent "
        "biological replicates. IQR is descriptive, not a biological confidence interval; "
        "no significance claim or p-value is inferred from the number of resamples.",
        "- This is an initial pilot. Mixed or small effects remain inconclusive; "
        "do not choose additional seeds or thresholds because they improve the result.",
        "- The two protocols also differ in observation count (121 draws versus 97 "
        "distinct metacells) and RNG consumption. This does not isolate replacement "
        "alone at equal sample counts. Matching integer seed IDs does not mean matching sampled cells.",
        "- Response-positive pairs may be indirect. Operational negatives mean absence "
        "of the defined response label, not proven biological non-regulation. MI in NT "
        "cells is association, not causal perturbation effect.",
        "- Any result here concerns raw-MI response-associated ranking, not accuracy "
        "or improvement of the whole threshold/DPI/consensus workflow. Existing "
        "unfavorable end-to-end results are retained as separate evidence.", "",
        "Compact numerical artifacts: `paired_seed_metrics.tsv` and `summary.json`. "
        "No multi-million-edge ranked CSV is generated by this reporting step.", "",
    ]
    return "\n".join(lines)


def build_report(
    results: list[dict[str, Any]], plan: dict[str, Any], output: Path,
    *, before_arm: str = "before", after_arm: str = "after", primary_k: int = 5000,
    plots: bool = True,
) -> dict[str, Any]:
    summary, paired = aggregate_results(
        results, plan, before_arm=before_arm, after_arm=after_arm, primary_k=primary_k,
    )
    output = Path(output)
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Report output must be fresh or empty: {output}")
    output.mkdir(parents=True, exist_ok=True)
    with (output / "paired_seed_metrics.tsv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(paired[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(paired)
    if plots:
        plot_comparison(results, summary, output / "raw_mi_comparison.png")
    summary["plots_generated"] = plots
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    report = report_markdown(summary)
    if not plots:
        report = report.replace("![TP, EPR and sampled ROC comparison](raw_mi_comparison.png)", "Plot generation was disabled for this report.")
    (output / "REPORT.md").write_text(report, encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--results", type=Path, nargs="+", help="Explicit compact JSON score files; otherwise jobs/*/seed_*/metrics.json")
    parser.add_argument("--before-arm", default="before")
    parser.add_argument("--after-arm", default="after")
    parser.add_argument("--primary-k", type=int, default=5000)
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    plan_path = args.run_root / "plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    paths = args.results or sorted((args.run_root / "jobs").glob("*/seed_*/metrics.json"))
    results = [json.loads(path.read_text(encoding="utf-8")) for path in paths]
    summary = build_report(
        results, plan, args.out, before_arm=args.before_arm, after_arm=args.after_arm,
        primary_k=args.primary_k, plots=not args.no_plots,
    )
    provenance = {
        "plan": {"path": str(plan_path), "sha256": hashlib.sha256(plan_path.read_bytes()).hexdigest()},
        "score_results": [{"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()} for path in paths],
        "report_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    (args.out / "report_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": summary["status"], "matched_seeds": summary["n_matched_seeds"], "out": str(args.out)}))


if __name__ == "__main__":
    main()
