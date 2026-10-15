"""Validate, plot and package compact Network3 pilot results after completion.

No native execution, threshold tuning or retrospective endpoint selection.
Raw files, logs, expression and native binaries remain local and are never
copied. This reporter is separately hash-bound to frozen scoring outputs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import shutil
import statistics
import sys


ARMS = ("legacy", "u64", "u80", "u90")
STAGES = ("raw", "nominal_pre", "nominal_post", "fixed_pre", "fixed_post")
KS = (100, 500, 1000, 5000, 10000, 20000, 50000, 100000)
P, N, U = 2066, 150214, 152280
FIELDS = ("edges_all", "edges_explicit_labelled", "edges_unlabelled", "TP", "FP", "precision", "sensitivity", "specificity",
          "AUROC_fixed_explicit_universe_MI_ties", "average_precision_fixed_explicit_universe")
PRUNE_FIELDS = ("global_pruning_fraction", "labelled_pruning_fraction", "TP_pruned", "FP_pruned", "TP_pruning_fraction", "FP_pruning_fraction", "TP_retention_fraction")


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def record(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "sha256": digest(path), "bytes": path.stat().st_size}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def verify_record(value, expected_path=None):
    path = Path(value["path"]).resolve(strict=True)
    if expected_path is not None and path != Path(expected_path).resolve():
        raise ValueError("Frozen artifact path differs from its expected provenance")
    if path.stat().st_size != value["bytes"] or digest(path) != value["sha256"]:
        raise ValueError("Frozen artifact hash/size changed: " + str(path))
    return path


def close(actual, expected, name, *, tolerance=1e-10):
    if isinstance(actual, bool) or not isinstance(actual, (int, float)) or not math.isfinite(actual):
        raise ValueError("Invalid finite numeric metric: " + name)
    if not math.isclose(actual, expected, rel_tol=0, abs_tol=tolerance):
        raise ValueError("Inconsistent metric: " + name)


def _fraction(numerator, denominator):
    return numerator / denominator if denominator else None


def _optional_close(actual, expected, name):
    if expected is None:
        if actual is not None:
            raise ValueError("Undefined zero-denominator metric must remain null: " + name)
    else:
        close(actual, expected, name)


def validate_stage(value, stage):
    for key in ("edges_all", "edges_explicit_labelled", "edges_unlabelled", "TP", "FP", "FN", "TN"):
        number = value[key]
        if isinstance(number, bool) or not isinstance(number, int) or number < 0:
            raise ValueError("Invalid count " + key)
    if value["TP"] + value["FN"] != P or value["FP"] + value["TN"] != N:
        raise ValueError("Stage changes the explicit gold class universe")
    emitted = value["TP"] + value["FP"]
    if emitted != value["edges_explicit_labelled"] or value["edges_all"] != emitted + value["edges_unlabelled"]:
        raise ValueError("Labelled/unlabelled emitted counts disagree")
    _optional_close(value["precision"], _fraction(value["TP"], emitted), "precision")
    close(value["sensitivity"], value["TP"] / P, "sensitivity")
    close(value["specificity"], value["TN"] / N, "specificity")
    close(value["random_precision"], P / U, "random precision")
    auc, ap = value["AUROC_fixed_explicit_universe_MI_ties"], value["average_precision_fixed_explicit_universe"]
    close(auc, auc, "AUROC")
    close(ap, ap, "AP")
    if not 0 <= auc <= 1 or not 0 <= ap <= 1:
        raise ValueError("Ranking metric outside [0,1]")
    close(value["AUROC_geometric_check"], auc, "AUROC integration", tolerance=1e-12)
    if [row["k"] for row in value["top_k"]] != list(KS):
        raise ValueError("Top-k budget population changed")
    for row in value["top_k"]:
        k = row["k"]
        available = stage == "raw" or k <= emitted
        if not available:
            if row.get("status") != "exceeds_labelled_emitted_pairs":
                raise ValueError("Post-threshold top-k must not pad omitted pairs")
            continue
        if row.get("status") != "complete":
            raise ValueError("Available top-k result is incomplete")
        tp, fp = row["TP_tie_expected"], row["FP_tie_expected"]
        close(tp, tp, "top-k TP")
        close(fp, fp, "top-k FP")
        if not 0 <= tp <= min(k, P) or not 0 <= fp <= min(k, N):
            raise ValueError("Top-k TP/FP exceed explicit class totals")
        close(tp + fp, k, "top-k TP+FP")
        close(row["precision"], tp / k, "top-k precision")
        close(row["sensitivity"], tp / P, "top-k sensitivity")
        close(row["specificity"], 1 - fp / N, "top-k specificity")
        close(row["EPR_fixed_universe"], tp / k / (P / U), "top-k EPR")
        if not 0 <= row["TP_min"] <= tp <= row["TP_max"] <= min(k, P):
            raise ValueError("Invalid attainable tied-boundary TP range")
    roc = value["roc_curve"]
    fpr, tpr = roc["FPR"], roc["sensitivity"]
    if len(fpr) != len(tpr) or not fpr or fpr[0] != 0 or fpr[-1] != 1 or tpr[-1] != 1:
        raise ValueError("Invalid sampled ROC endpoints/grid")
    if any(not isinstance(x, (int, float)) or not math.isfinite(x) or not 0 <= x <= 1 for x in [*fpr, *tpr]):
        raise ValueError("Invalid sampled ROC coordinate")
    if any(a >= b for a, b in zip(fpr, fpr[1:])) or any(a > b for a, b in zip(tpr, tpr[1:])):
        raise ValueError("Sampled ROC grid must increase and sensitivity must not decrease")


def build_report_data(payload, plan):
    """Independently reaggregate validated compact metrics; no files written."""
    if payload.get("status") != "complete" or plan.get("arms") != list(ARMS) or plan.get("seeds") != [1, 2, 3] or plan.get("stages") != list(STAGES):
        raise ValueError("Report requires the complete prospective four-arm/three-seed design")
    if plan.get("primary") != {"contrast": ["legacy", "u80"], "stage": "nominal_post", "endpoint": "average_precision"}:
        raise ValueError("Prospective primary endpoint changed")
    results = payload["results"]
    expected = {(arm, seed) for arm in ARMS for seed in (1, 2, 3)}
    identities = [(row["arm"], row["seed"]) for row in results]
    if len(identities) != 12 or set(identities) != expected or any(isinstance(seed, bool) or not isinstance(seed, int) for arm, seed in identities):
        raise ValueError("Missing/duplicate arm-seed result")
    lookup = {(row["arm"], row["seed"]): row for row in results}
    roc_grid = None
    for result in results:
        if set(result["stages"]) != set(STAGES) or set(result["DPI_pruning"]) != {"nominal", "fixed"}:
            raise ValueError("Stage/control population changed")
        for stage, value in result["stages"].items():
            validate_stage(value, stage)
            grid = value["roc_curve"]["FPR"]
            if roc_grid is None:
                roc_grid = grid
            elif grid != roc_grid:
                raise ValueError("Sampled ROC grids differ")
            validation = result["validation"][stage]
            if validation.get("status") != "passed" or validation.get("arm") != result["arm"] or validation.get("stage") != stage:
                raise ValueError("Native stage validation identity changed")
        for prefix in ("nominal", "fixed"):
            pre, post = result["stages"][prefix + "_pre"], result["stages"][prefix + "_post"]
            if any(post[key] > pre[key] for key in ("edges_all", "edges_explicit_labelled", "TP", "FP")):
                raise ValueError("Post-DPI counts exceed pre-DPI counts")
            expected_pruning = {"global_pruning_fraction": 1 - post["edges_all"] / pre["edges_all"] if pre["edges_all"] else None,
                                "labelled_pruning_fraction": 1 - post["edges_explicit_labelled"] / pre["edges_explicit_labelled"] if pre["edges_explicit_labelled"] else None,
                                "TP_pruned": pre["TP"] - post["TP"], "FP_pruned": pre["FP"] - post["FP"],
                                "TP_pruning_fraction": 1 - post["TP"] / pre["TP"] if pre["TP"] else None,
                                "FP_pruning_fraction": 1 - post["FP"] / pre["FP"] if pre["FP"] else None}
            for key, value in expected_pruning.items():
                _optional_close(result["DPI_pruning"][prefix][key], value, "DPI " + key)
    def med(values):
        return statistics.median(values) if all(value is not None for value in values) else None
    stage_rows = [{"arm": arm, "stage": stage, "resamples": 3,
                   **{key: med([lookup[(arm, seed)]["stages"][stage][key] for seed in (1, 2, 3)]) for key in FIELDS}}
                  for arm in ARMS for stage in STAGES]
    def pruning_value(result, prefix, key):
        if key == "TP_retention_fraction":
            return _fraction(result["stages"][prefix + "_post"]["TP"], result["stages"][prefix + "_pre"]["TP"])
        return result["DPI_pruning"][prefix][key]
    pruning_rows = [{"arm": arm, "branch": prefix, "resamples": 3,
                     **{key: med([pruning_value(lookup[(arm, seed)], prefix, key) for seed in (1, 2, 3)]) for key in PRUNE_FIELDS}}
                    for arm in ARMS for prefix in ("nominal", "fixed")]
    paired = []
    for seed in (1, 2, 3):
        before = lookup[("legacy", seed)]["stages"]["nominal_post"]
        after = lookup[("u80", seed)]["stages"]["nominal_post"]
        paired.append({"seed": seed, "legacy_AP": before["average_precision_fixed_explicit_universe"],
                       "u80_AP": after["average_precision_fixed_explicit_universe"],
                       "paired_AP_delta": after["average_precision_fixed_explicit_universe"] - before["average_precision_fixed_explicit_universe"],
                       "legacy_TP": before["TP"], "u80_TP": after["TP"], "legacy_FP": before["FP"], "u80_FP": after["FP"]})
    deltas = [row["paired_AP_delta"] for row in paired]
    summary = {"status": "complete", "matched_seeds": 3, "primary": plan["primary"],
               "primary_paired_AP_delta_median": med(deltas), "primary_after_higher": sum(value > 0 for value in deltas),
               "primary_after_equal": sum(value == 0 for value in deltas), "primary_after_lower": sum(value < 0 for value in deltas),
               "explicit_gold": {"pairs": U, "positive": P, "negative": N, "random_precision": P / U},
               "stage_medians": stage_rows, "DPI_pruning_medians": pruning_rows, "paired_primary": paired,
               "limitations": ["Three matched computational resamples are exploratory, not independent biological replicates; IQR is descriptive, not a confidence interval",
                               "Only 152,280 explicitly labelled directed pairs are evaluated; 1,354,060 other full-TF pairs remain unlabelled and never count as false positives",
                               "The regulatory reference is incomplete; explicit zero labels are benchmark negatives, not proof that biological regulation is absent",
                               "The 805 expression profiles span heterogeneous conditions and may be correlated; resampling does not turn them into independent biological replicates",
                               "Sampling draw counts and nominal affine MI cutoffs change together; fixed-cutoff stages and raw ranking are supporting controls, not a new selected primary endpoint",
                               "Arms also differ in selected sample identities, draw counts, RNG consumption and tie-noise realizations; replacement alone is not isolated",
                               "All 334 TFs and 4,511 genes remain in native inference; labels do not select hubs or genes",
                               "MI is symmetric while evaluation labels are directed; these local AP/AUROC metrics are not the official DREAM5 calibrated challenge score",
                               "An AP gain accompanied by TP loss is a precision/coverage tradeoff, not blanket improvement; report TP retention alongside pruning",
                               "No consensus step, parameter optimization, significance test or automatic superiority conclusion"]}
    original = payload["summary"]
    for key in ("primary_paired_AP_delta_median", "primary_after_higher", "primary_after_equal", "primary_after_lower"):
        close(original[key], summary[key], "frozen versus independently aggregated " + key)
    for row in stage_rows:
        frozen = original["medians"][row["arm"]][row["stage"]]
        for key in FIELDS:
            _optional_close(frozen[key], row[key], "frozen stage median " + key)
    return summary, stage_rows, pruning_rows, paired


def plot_comparison(payload, summary, output):
    """Raw ranking and the prospective primary endpoint; no MI pooling."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    figure, axes = plt.subplots(2, 2, figsize=(11, 8), constrained_layout=True)
    colors = {"legacy": "#444444", "u64": "#1b9e77", "u80": "#d95f02", "u90": "#7570b3"}
    for arm in ARMS:
        rows = [row["stages"]["raw"] for row in payload["results"] if row["arm"] == arm]
        tp = np.array([[point["TP_tie_expected"] for point in row["top_k"]] for row in rows])
        epr = np.array([[point["EPR_fixed_universe"] for point in row["top_k"]] for row in rows])
        for axis, array in ((axes[0, 0], tp), (axes[0, 1], epr)):
            q1, middle, q3 = np.percentile(array, [25, 50, 75], axis=0)
            axis.plot(KS, middle, color=colors[arm], label=arm)
            axis.fill_between(KS, q1, q3, color=colors[arm], alpha=.13)
            axis.set_xscale("log")
            axis.set_xlabel("Top-k explicit labelled pairs")
        fpr = rows[0]["roc_curve"]["FPR"]
        roc = np.array([row["roc_curve"]["sensitivity"] for row in rows])
        q1, middle, q3 = np.percentile(roc, [25, 50, 75], axis=0)
        axes[1, 0].plot(fpr, middle, color=colors[arm], label=arm)
        axes[1, 0].fill_between(fpr, q1, q3, color=colors[arm], alpha=.13)
    axes[0, 0].plot(KS, [k * P / U for k in KS], "--", color=".65", label="Uniform ranking")
    axes[0, 0].set(title="Raw MI: reference-edge ranking", ylabel="TP@k")
    axes[0, 1].axhline(1, ls="--", color=".65")
    axes[0, 1].set(title="Raw MI: fixed-reference enrichment", ylabel="EPR@k")
    axes[1, 0].plot([0, 1], [0, 1], "--", color=".65")
    axes[1, 0].set(title="Raw MI: sampled ROC", xlabel="1 − specificity", ylabel="Sensitivity", xlim=(0, 1), ylim=(0, 1))
    for row in summary["paired_primary"]:
        axes[1, 1].plot([0, 1], [row["legacy_AP"], row["u80_AP"]], marker="o", label=f"Seed {row['seed']}")
    axes[1, 1].set(xticks=[0, 1], xticklabels=["legacy", "u80"], ylabel="Average precision",
                   title="Primary: nominal post-DPI paired AP")
    axes[0, 0].legend(fontsize=8)
    axes[1, 1].legend(fontsize=8)
    figure.suptitle("DREAM5 Network 3: three matched computational resamples\nRaw panels: median/IQR (not confidence intervals); paired AP: one line per seed")
    figure.savefig(output, dpi=160)
    plt.close(figure)


def markdown(summary, plan, *, plots):
    def fmt(value, digits=6):
        return "NA" if value is None else f"{value:.{digits}f}"
    lines = ["# DREAM5 Network 3: exploratory sampling and DPI benchmark", "",
             "The prospective primary endpoint is nominal post-DPI average precision (AP), u80 versus legacy, across three matched seeds. All other arms, stages and metrics are supporting diagnostics. No consensus was applied.", "",
             "Inference uses all 334 TFs, 4,511 genes and 805 original profiles. Scoring uses only 152,280 explicitly labelled directed pairs (2,066 positive; 150,214 negative); other predicted pairs are unlabelled, not false positives. AP is tied-threshold stepwise average precision, not trapezoidal area under a precision–recall curve.", "",
             "## Prospective primary comparison", "", "| Seed | Legacy AP | u80 AP | Paired AP difference |", "|---|---:|---:|---:|"]
    for row in summary["paired_primary"]:
        lines.append(f"| {row['seed']} | {fmt(row['legacy_AP'])} | {fmt(row['u80_AP'])} | {fmt(row['paired_AP_delta'])} |")
    lines += ["", f"Median paired AP difference: {fmt(summary['primary_paired_AP_delta_median'])}; u80 higher/equal/lower in {summary['primary_after_higher']}/{summary['primary_after_equal']}/{summary['primary_after_lower']} seeds. These are descriptive computational comparisons, not significance tests.", "",
              "## Sampling and MI cutoffs", "", "| Arm | Draws | Sampling | Nominal MI cutoff | Fixed-control MI cutoff |", "|---|---:|---|---:|---:|"]
    for arm in ARMS:
        lines.append(f"| {arm} | {plan['sampling'][arm]['draws']} | {plan['sampling'][arm]['method']} | {plan['parameters']['nominal_cutoffs'][arm]:.9f} | {plan['parameters']['fixed_mi']:.9f} |")
    lines += ["", "Nominal p=10⁻⁷ uses the existing affine cutoff. Raw stages use p=1, MI cutoff 0 and no DPI. The fixed cutoff is the prospectively specified u80 nominal MI cutoff; it is not selected using Network3 labels.", "",
              "## All arms and stages", "", "Medians across three resamples. AUROC/AP use the same explicit labelled universe, with omitted pairs in a shared MI=0 bottom tie. Raw top-k includes every labelled pair; filtered-stage top-k stops at the labelled emitted count and never pads missing pairs.", "",
              "| Arm | Stage | All edges | Labelled edges | Unlabelled edges | TP | FP | Precision | Sensitivity | Specificity | AUROC | AP |", "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in summary["stage_medians"]:
        numbers = [fmt(row[key], 0) for key in ("edges_all", "edges_explicit_labelled", "edges_unlabelled", "TP", "FP")]
        numbers += [fmt(row[key]) for key in ("precision", "sensitivity", "specificity", "AUROC_fixed_explicit_universe_MI_ties", "average_precision_fixed_explicit_universe")]
        lines.append("| " + " | ".join([row["arm"], row["stage"], *numbers]) + " |")
    lines += ["", "## DPI pruning diagnostics", "", "Each pruning fraction is computed within a resample before taking its median; it is not a ratio of table medians.", "",
              "| Arm | Branch | Global fraction pruned | Labelled fraction pruned | TP pruned | FP pruned | TP fraction pruned | FP fraction pruned | TP fraction retained |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for row in summary["DPI_pruning_medians"]:
        lines.append("| " + " | ".join([row["arm"], row["branch"], *[fmt(row[key], 0 if key in ("TP_pruned", "FP_pruned") else 6) for key in PRUNE_FIELDS]]) + " |")
    if plots:
        lines += ["", "![Raw ranking and prospective primary endpoint](network3_comparison.png)", ""]
    lines += ["", "## Interpretation limits", "", *["- " + text for text in summary["limitations"]], "",
              "Exact MI identity and raw→pre-DPI→post-DPI subset checks are verified within each arm/seed. Six-significant-digit native cutoff rounding is allowed without re-filtering serialized output. Fixed-budget TP, precision, sensitivity and EPR are related views, not independent evidence.", "",
              "Replotting inputs: `metrics.json`, `all_arm_stage_medians.tsv`, `DPI_pruning_medians.tsv`, and `paired_primary_AP.tsv`. The package preserves compact frozen provenance but not native networks, logs or expression.", ""]
    return "\n".join(lines)


def validate_run(run_root, metrics_path):
    import run_benchmark as runner
    run_root = Path(run_root).resolve(strict=True)
    metrics_path = Path(metrics_path).resolve(strict=True)
    plan = runner.verify_plan(run_root / "plan.json")
    runner.verify_smoke(plan)
    status = read_json(run_root / "status.json")
    if status.get("status") != "complete" or status.get("completed") != 60 or status.get("total") != 60 or status.get("failures"):
        raise ValueError("Report packaging requires the completed 60-job pilot")
    expected = {(arm, seed, stage) for arm in ARMS for seed in (1, 2, 3) for stage in STAGES}
    identities = [(job["arm"], job["seed"], job["stage"]) for job in status.get("jobs", [])]
    if len(identities) != 60 or set(identities) != expected:
        raise ValueError("Status does not identify all sixty completed jobs")
    verify_record(status["plan"], run_root / "plan.json")
    payload = read_json(metrics_path)
    provenance = payload["provenance"]
    verify_record(provenance["plan"], run_root / "plan.json")
    verify_record(provenance["metrics_script"], Path(__file__).with_name("metrics.py"))
    job_records = provenance["native_job_records"]
    expected_paths = {str(runner.job_directory(plan, arm, seed, stage) / "job.json") for arm, seed, stage in expected}
    if len(job_records) != 60 or {str(Path(value["path"]).resolve()) for value in job_records} != expected_paths:
        raise ValueError("Metric provenance does not identify the exact sixty native job records")
    for value in job_records:
        verify_record(value)
    for arm, seed, stage in sorted(expected):
        runner.checked_job(plan, arm, seed, stage)
    for value in provenance["source_data"]["source_files"].values():
        verify_record(value)
    return plan, payload, job_records


def _tsv(path, rows):
    with Path(path).open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def package(run_root, metrics_path, out, *, plots=True):
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError("Report output must be fresh; existing evidence is never overwritten")
    run_root, metrics_path = Path(run_root).resolve(strict=True), Path(metrics_path).resolve(strict=True)
    plan, payload, job_records = validate_run(run_root, metrics_path)
    summary, stages, pruning, paired = build_report_data(payload, plan)
    copies = {"metrics.json": metrics_path, "provenance/plan.json": run_root / "plan.json",
              "provenance/status.json": run_root / "status.json", "provenance/smoke_gate.json": run_root / "smoke_gate.json",
              "provenance/preparation.json": Path(plan["inputs"]["preparation"]["path"])}
    protocol = Path(__file__).with_name("PLAN_2026-10-15.md")
    if not protocol.is_file():
        raise FileNotFoundError("Prospective written protocol is missing")
    copies["provenance/PLAN_2026-10-15.md"] = protocol
    for value in job_records:
        source = Path(value["path"])
        relative = source.relative_to(run_root)
        copies["provenance/" + relative.as_posix()] = source
    for name, destination in (("REPORT.md", "provenance/generated_score_REPORT.md"),
                              ("summary.json", "provenance/generated_score_summary.json"),
                              ("per_seed_stage_metrics.tsv", "per_seed_stage_metrics.tsv")):
        source = metrics_path.parent / name
        if source.is_file():
            copies[destination] = source
    source_records = {name: record(source) for name, source in copies.items()}
    # Complete run, provenance and numerical validation all finish before mkdir.
    out.mkdir(parents=True)
    for destination, source in copies.items():
        target = out / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        if digest(target) != source_records[destination]["sha256"]:
            raise ValueError("Frozen source changed during compact copying")
    _tsv(out / "all_arm_stage_medians.tsv", stages)
    _tsv(out / "DPI_pruning_medians.tsv", pruning)
    _tsv(out / "paired_primary_AP.tsv", paired)
    (out / "analysis_summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if plots:
        plot_comparison(payload, summary, out / "network3_comparison.png")
    (out / "REPORT.md").write_text(markdown(summary, plan, plots=plots), encoding="utf-8")
    generated = ["all_arm_stage_medians.tsv", "DPI_pruning_medians.tsv", "paired_primary_AP.tsv", "analysis_summary.json", "REPORT.md"]
    if plots:
        generated.append("network3_comparison.png")
    def version(name):
        try:
            return importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            return None
    manifest = {"status": "complete", "schema": 1, "report_script": record(__file__),
                "environment": {"python": sys.version, "numpy": version("numpy"), "matplotlib": version("matplotlib")},
                "input_metrics": record(metrics_path), "source_copies": source_records,
                "copied_sha256": {name: digest(out / name) for name in copies},
                "generated_outputs": {name: record(out / name) for name in generated},
                "excluded_large_artifacts": ["raw.adj", "stdout.log", "stderr.log", "time.tsv", "native executable", "expression"],
                "native_inference_performed_by_report": False}
    (out / "package_manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", required=True, type=Path)
    parser.add_argument("--metrics", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    metrics_path = args.metrics or args.run_root / "scoring_20261015/metrics.json"
    result = package(args.run_root, metrics_path, args.out, plots=not args.no_plots)
    print(json.dumps({"status": result["status"], "matched_seeds": result["matched_seeds"], "out": str(args.out)}))


if __name__ == "__main__":
    main()
