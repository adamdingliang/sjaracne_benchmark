#!/usr/bin/env python3
"""Report three scoring populations without modifying frozen inference or labels.

Eligible emitted predictions are primary. Full emitted predictions and the
fixed eligible universe are secondary. All new AUROCs retain consensus MI
ties. Precision lift uses the exact random-selection expectation, not one
realized shuffle; the original author-style scores remain unchanged.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import math
from pathlib import Path
import platform
import sys

import numpy as np

import score_fixed_universe as fixed


POPULATIONS = ("eligible_emitted", "full_emitted", "fixed_eligible_universe")
TITLES = {
    "eligible_emitted": "Eligible-source predictions (primary)",
    "full_emitted": "All emitted SIG edges",
    "fixed_eligible_universe": "Fixed eligible universe",
}


def network_groups(path, universe, hubs):
    """Validate each pair once and count labels per MI, without breaking ties."""
    sources, targets = set(universe.sources), set(universe.targets)
    full, eligible = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    seen = set()
    for row in fixed.rows(path):
        source, target, mi = row["source"], row["target"], float(row["MI"])
        if source not in hubs or target not in targets or source == target:
            raise ValueError("Network pair outside frozen inputs or self-pair")
        if not math.isfinite(mi) or mi < 0:
            raise ValueError("Invalid network MI")
        key = universe.key(source, target)
        if key in seen:
            raise ValueError("Duplicate predicted pair")
        seen.add(key)
        label_index = 0 if key in universe.positives else 1
        full[mi][label_index] += 1
        if source in sources:
            eligible[mi][label_index] += 1

    def grouped(counts):
        return [(mi, *counts[mi]) for mi in sorted(counts, reverse=True)]

    return grouped(full), grouped(eligible)


def population_metrics(groups, positive, negative, fixed_positive, fixed_negative,
                       ks, population):
    score, _ = fixed.fixed_roc(groups, positive, negative)
    emitted_positive = sum(p for _, p, _ in groups)
    emitted_negative = sum(n for _, _, n in groups)
    total = positive + negative
    topk = []
    for original in fixed.topk_points(groups, positive, negative, ks):
        if original["status"] != "complete":
            topk.append({"k": original["k"], "status": "exceeds_emitted_pairs"})
            continue
        expected_random = original["k"] * positive / total
        row = {key: value for key, value in original.items()
               if key not in ("sensitivity_tie_expected", "specificity_tie_expected", "FPR_tie_expected")}
        row.update({
            "sensitivity_within_population_at_k": original["sensitivity_tie_expected"],
            "specificity_within_population_at_k": original["specificity_tie_expected"],
            "fixed_reference_sensitivity_at_k": original["TP_tie_expected"] / fixed_positive,
            "random_TP_expectation_at_k": expected_random,
            "precision_lift_over_random_expectation": original["TP_tie_expected"] / expected_random,
        })
        if population != "full_emitted":
            row["fixed_reference_specificity_at_k"] = 1 - original["FP_tie_expected"] / fixed_negative
        topk.append(row)
    return {
        "role": "primary" if population == "eligible_emitted" else "secondary",
        "candidate_pairs": total,
        "reference_positive_pairs_in_population": positive,
        "operational_reference_negative_pairs_in_population": negative,
        "random_positive_fraction": positive / total,
        "AUROC_MI_ties": score["AUROC_fixed_universe_MI_ties"],
        "AUROC_ROC_integral_check": score["AUROC_ROC_integral_check"],
        "emitted_pairs": emitted_positive + emitted_negative,
        "emitted_reference_positive": emitted_positive,
        "emitted_reference_nonmember": emitted_negative,
        "emitted_positive_match_fraction": emitted_positive / (emitted_positive + emitted_negative)
        if emitted_positive + emitted_negative else None,
        "fixed_reference_sensitivity_all_emitted": emitted_positive / fixed_positive,
        "omitted_positive_pairs_in_population": positive - emitted_positive,
        "omitted_negative_pairs_in_population": negative - emitted_negative,
        "top_k": topk,
    }


def calculate(args):
    if args.out.exists():
        raise FileExistsError("Refusing to overwrite three-population output")
    metrics_path = args.fixed_metrics.resolve(strict=True)
    frozen = json.loads(metrics_path.read_text(encoding="utf-8"))
    if frozen.get("status") != "complete":
        raise ValueError("Fixed-universe score must be complete")
    input_hashes = {str(metrics_path): fixed.digest(metrics_path)}

    def verify(path, expected):
        path = fixed.record_path(str(path))
        value = fixed.digest(path)
        if value != expected:
            raise ValueError(f"Input hash mismatch: {path}")
        input_hashes[str(path)] = value
        return path

    # Bind both the original inputs and its saved metrics/definition artifacts.
    for path, expected in frozen["input_sha256"].items():
        verify(path, expected)
    for name, expected in frozen["output_sha256"].items():
        verify(metrics_path.parent / name, expected)
    helper_path = Path(fixed.__file__).resolve()
    verify(helper_path, frozen["script_sha256"])
    prepared_dir = args.prepared_dir.resolve(strict=True)
    run_path = args.run_manifest.resolve(strict=True)
    for path in (run_path, prepared_dir / "prepare_manifest.json"):
        if str(path) not in input_hashes:
            raise ValueError("Requested run/preparation not bound to frozen score")
    run = json.loads(run_path.read_text(encoding="utf-8"))
    prepared = json.loads((prepared_dir / "prepare_manifest.json").read_text(encoding="utf-8"))
    if run.get("status") != "complete" or prepared.get("status") != "complete":
        raise ValueError("Native run and preparation must be complete")
    for name in ("gene_selection.tsv", "reference_eligible_sources.tsv", "reference_positive_edges.tsv", "hubs.txt", "expression.exp"):
        path = prepared_dir / name
        if str(path) not in input_hashes:
            raise ValueError("Requested prepared input not bound to frozen score")
        verify(path, prepared["outputs"][name]["sha256"])
    universe = fixed.make_universe(prepared_dir)
    u = frozen["universe"]
    if (tuple(u["sources"]), tuple(u["targets"]), u["candidate_pairs"], u["reference_positive_pairs"]) != (
        universe.sources, universe.targets, universe.size, len(universe.positives)
    ):
        raise ValueError("Reconstructed universe differs from frozen score")
    if set(run["consensus"]) != set(frozen["scores"]):
        raise ValueError("Consensus alternatives differ from frozen score")
    positive, negative = len(universe.positives), universe.size - len(universe.positives)
    hubs = set((prepared_dir / "hubs.txt").read_text(encoding="utf-8").splitlines())
    results = {}
    for name, job in run["consensus"].items():
        if job["status"] != "complete":
            raise ValueError("Incomplete consensus")
        record = job["artifacts"]["edges.tsv"]
        network = verify(record["path"], record["sha256"])
        if str(network) not in frozen["input_sha256"]:
            # Frozen paths may have Windows spelling under a WSL interpreter.
            if network not in {fixed.record_path(path) for path in frozen["input_sha256"]}:
                raise ValueError("Network not bound to frozen fixed-universe score")
        full, eligible = network_groups(network, universe, hubs)
        full_p, full_n = sum(p for _, p, _ in full), sum(n for _, _, n in full)
        eligible_p, eligible_n = sum(p for _, p, _ in eligible), sum(n for _, _, n in eligible)
        prior = frozen["scores"][name]
        if (full_p + full_n, full_p, eligible_p + eligible_n, eligible_p, job["p"]) != (
            prior["full_emitted_network_edges"], prior["emitted_reference_positive"],
            prior["emitted_eligible_pairs"], prior["emitted_reference_positive"], prior["consensus_p"]
        ):
            raise ValueError("Network counts/cutoff differ from frozen scores")
        populations = {
            "eligible_emitted": population_metrics(eligible, eligible_p, eligible_n, positive, negative, args.top_k, "eligible_emitted"),
            "full_emitted": population_metrics(full, full_p, full_n, positive, negative, args.top_k, "full_emitted"),
            "fixed_eligible_universe": population_metrics(eligible, positive, negative, positive, negative, args.top_k, "fixed_eligible_universe"),
        }
        for population, prior_key in (("eligible_emitted", "diagnostic_AUROC_emitted_eligible_MI_ties"),
                                      ("fixed_eligible_universe", "AUROC_fixed_universe_MI_ties")):
            if not math.isclose(populations[population]["AUROC_MI_ties"], prior[prior_key], abs_tol=1e-12):
                raise ValueError("AUROC disagrees with frozen independent checks")
        results[name] = {
            "consensus_p": job["p"], "populations": populations,
            "unassessed_source_predictions_in_full_pool": full_n - eligible_n,
            "preserved_author_style_full_emitted_ordinal_AUROC": prior["preserved_AUROC_within_emitted_edges_author_ordinal"],
            "fixed_reference_coverage": prior["operating_point_all_emitted"],
        }
    result = {
        "status": "complete", "scope": "three_population_reconstructed_legacy_baseline",
        "primary_population": "eligible_emitted", "top_k_prespecified": args.top_k,
        "definitions": {
            "labels": "Frozen perturbation-response membership, not direct-edge ground truth",
            "AUROC": "Consensus MI with equal MI tied; fixed universe additionally ties every omitted pair below all emitted pairs",
            "top_k": "Population-specific MI ranking; expected TP and attainable range if k splits an MI tie; no padding above emitted count",
            "conditional_rates": "Emitted-pool sensitivity/specificity at k are conditional rank rates, not full-reference coverage",
            "fixed_reference_sensitivity": "TP divided by the same frozen eligible reference-positive count in every view",
            "random_comparator": "Uniform selection without replacement from each population; expected TP=k*P/N",
            "precision_lift": "TP_at_k/(k*P/N); EPR against random expectation, not EPR against a realized seed-1 shuffle",
            "full_pool_nonmembers": "Includes unassessed-source pairs; operational negatives for compatibility, not proven biological negatives",
        },
        "universe": u, "scores": results, "input_sha256": input_hashes,
        "script_sha256": fixed.digest(Path(__file__)), "helper_sha256": fixed.digest(helper_path),
        "Python": sys.version, "platform": platform.platform(), "numpy": np.__version__,
    }
    check_inputs(input_hashes)
    report = render_report(result)
    args.out.mkdir(parents=True, exist_ok=False)
    report_path = args.out / "REPORT.md"
    with report_path.open("x", encoding="utf-8") as stream:
        stream.write(report)
    result["output_sha256"] = {"REPORT.md": fixed.digest(report_path)}
    check_inputs(input_hashes)
    with (args.out / "metrics.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return result


def check_inputs(hashes):
    if any(fixed.digest(Path(path)) != value for path, value in hashes.items()):
        raise ValueError("Frozen inputs changed during scoring")


def render_report(result):
    lines = ["# THP-1 baseline: three scoring populations", "",
             "Eligible-source emitted predictions are the primary evaluation. Full emitted SIG edges and the fixed eligible universe are secondary.", "",
             "These are three evaluations of the same reconstructed legacy baseline, not three inference runs or a before/after sampling comparison. No reference, hub list, MI threshold, DPI setting or consensus cutoff was changed.", "",
             "## AUROC and population sizes", "",
             "All new AUROCs use consensus MI and retain equal-MI ties. Reference positives describe perturbation responses, not established direct regulation.", "",
             "| Consensus p_c | Population | Candidate pairs | Reference-positive pairs | Positive fraction | AUROC |",
             "|---:|---|---:|---:|---:|---:|"]
    for score in result["scores"].values():
        for name in POPULATIONS:
            p = score["populations"][name]
            lines.append(f"| {score['consensus_p']:g} | {TITLES[name]} | {p['candidate_pairs']:,} | {p['reference_positive_pairs_in_population']:,} | {100*p['random_positive_fraction']:.2f}% | {p['AUROC_MI_ties']:.6f} |")
    lines += ["", "## TP, precision and enrichment at fixed k", "",
              "Ranks are recalculated within each population. TP is the expected count under uniform ordering within a boundary MI tie; the range gives attainable integer counts. Values above the emitted edge count are unavailable, including in the fixed-universe view: no arbitrary ordering of omitted pairs is introduced.", "",
              "Random TP expectation is k * P/N for that population. Precision lift = TP / random TP expectation. This is EPR against an expectation, not the original author-style EPR against one realized random shuffle. The original scoring artifacts are unchanged.", "",
              "| p_c | Population | k | TP (tie range) | Precision | Fixed-reference sensitivity | Random TP expectation | Precision lift |",
              "|---:|---|---:|---:|---:|---:|---:|---:|"]
    for score in result["scores"].values():
        for name in POPULATIONS:
            for row in score["populations"][name]["top_k"]:
                prefix = f"| {score['consensus_p']:g} | {TITLES[name]} | {row['k']:,}"
                if row["status"] != "complete":
                    lines.append(prefix + " | unavailable | unavailable | unavailable | unavailable | unavailable |")
                else:
                    lines.append(prefix + f" | {row['TP_tie_expected']:,.2f} ({row['TP_min']:,}-{row['TP_max']:,}) | {100*row['precision_tie_expected']:.2f}% | {100*row['fixed_reference_sensitivity_at_k']:.4f}% | {row['random_TP_expectation_at_k']:,.2f} | {row['precision_lift_over_random_expectation']:.3f} |")
    lines += ["", "## Coverage and denominator interpretation", "",
              "Conditional sensitivity/specificity at k in an emitted pool use the positives/operational negatives within that pool. They are saved under explicit names in metrics.json. At the whole emitted output those rates are mechanically 1 and 0, so they are not presented as evidence of recovery.", "",
              "Fixed-reference sensitivity always uses the same frozen eligible positive denominator. Fixed-universe specificity is assessed only within eligible sources. Unassessed-source predictions in the full pool cannot match the response reference and are compatibility-score nonmembers, not confirmed biological false positives.", "",
              "| p_c | Eligible emitted pairs | TP | Operational FP | Missed response-positive pairs | Fixed-reference sensitivity | Fixed-universe specificity | Unassessed-source predictions in full pool |",
              "|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for score in result["scores"].values():
        p = score["fixed_reference_coverage"]
        lines.append(f"| {score['consensus_p']:g} | {p['selected_pairs']:,} | {p['TP']:,} | {p['FP']:,} | {p['FN']:,} | {100*p['sensitivity']:.4f}% | {100*p['specificity']:.4f}% | {score['unassessed_source_predictions_in_full_pool']:,} |")
    lines += ["", "The fixed universe has a large omitted bottom-score group; its AUROC measures thresholded selection plus ranking, not unthresholded MI discrimination. The primary emitted pool changes if a method emits different edges. Report its size and fixed-reference coverage alongside its conditional AUROC, rather than treating a higher conditional AUROC alone as overall improvement.", "",
              "The older full-emitted ordinal AUROC is preserved separately in metrics.json. It is not interchangeable with the new MI-tied AUROC. These reconstructed labels and inputs are not an exact reproduction of Figure 6a.", "",
              "Inputs and outputs are SHA256-bound in metrics.json. Reference labels and the fixed-universe definition must remain identical across a future before/after sampling comparison.", ""]
    return "\n".join(lines)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("fixed-metrics", "prepared-dir", "run-manifest", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--top-k", type=int, nargs="+", default=[1000, 5000, 10000, 50000, 100000])
    return p


if __name__ == "__main__":
    completed = calculate(parser().parse_args())
    print(json.dumps({"status": completed["status"], "primary_population": completed["primary_population"],
                      "AUROCs": {name: {pop: value["AUROC_MI_ties"] for pop, value in score["populations"].items()}
                                 for name, score in completed["scores"].items()}}))
