#!/usr/bin/env python3
"""Compare frozen sampling arms without rerunning inference or changing labels.

Eligible-source emitted predictions are primary. TP retains MI boundary-tie
expectations/ranges, EPR uses the realized R seed-1 rank shuffle, and ROC is
independently recounted with whole MI ties. Each arm stops at its own pool.
"""

from __future__ import annotations

import argparse
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


POPULATIONS = ("eligible_emitted", "full_emitted", "fixed_eligible_universe")
COLORS = {"before": "#0072B2", "after": "#D55E00"}
PREPARED_FILES = ("prepare_manifest.json", "gene_selection.tsv",
                  "reference_eligible_sources.tsv", "reference_positive_edges.tsv",
                  "hubs.txt", "expression.exp")
MATCHED_PARAMETERS = ("bootstrap_count", "seeds", "bootstrap_p", "consensus_p",
                      "npar", "dpi_tolerance", "algorithm", "explicit_mi_override")


def local_path(value):
    value = str(value)
    match = re.match(r"^/mnt/([a-zA-Z])/(.*)$", value)
    if os.name == "nt" and match:
        value = match[1].upper() + ":/" + match[2]
    return fixed.record_path(value)


def metric_path(value):
    path = Path(value)
    return (path / "metrics.json" if path.is_dir() else path).resolve(strict=True)


def bind(path, expected, hashes):
    path = local_path(path)
    if str(path) in hashes and hashes[str(path)] != expected:
        raise ValueError(f"Conflicting input hashes: {path}")
    if str(path) not in hashes and fixed.digest(path) != expected:
        raise ValueError(f"Frozen checksum mismatch: {path}")
    hashes[str(path)] = expected
    return path


def verify_manifest(path, hashes):
    path = metric_path(path)
    bind(path, fixed.digest(path), hashes)
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("status") != "complete" or data.get("primary_population") != "eligible_emitted":
        raise ValueError(f"Require completed eligible-primary score: {path}")
    for name, expected in data["input_sha256"].items():
        bind(name, expected, hashes)
    for name, expected in data["output_sha256"].items():
        bind(path.parent / name, expected, hashes)
    return path, data


def check_inputs(hashes):
    if any(fixed.digest(Path(path)) != expected for path, expected in hashes.items()):
        raise ValueError("Frozen artifacts changed during comparison")


def eligible_roc(groups, positive, negative, expected_auc):
    if (sum(p for _, p, _ in groups), sum(n for _, _, n in groups)) != (positive, negative):
        raise ValueError("ROC groups differ from eligible emitted population")
    score, curve = fixed.fixed_roc(groups, positive, negative)
    if not math.isclose(score["AUROC_fixed_universe_MI_ties"], expected_auc, abs_tol=1e-12):
        raise ValueError("Recounted MI-tied AUROC differs from frozen score")
    if any(row["threshold_kind"] == "omitted_bottom" for row in curve):
        raise ValueError("Omitted pairs cannot enter the eligible emitted ROC")
    return curve


def validate_ranked(rows, total, positive, anchors, groups):
    expected = sorted(set(range(1000, total + 1, 1000)) |
                      {k for k in anchors if k <= total} | {total})
    if [int(row["k"]) for row in rows] != expected:
        raise ValueError("Eligible trajectory must contain checkpoints, anchors and own endpoint")
    tied = fixed.topk_points(groups, positive, total - positive, expected)
    result = []
    previous_tp = previous_random = 0
    for row, independent in zip(rows, tied):
        k, tp, shuffled = (int(row[name]) for name in ("k", "TP", "Random_TP"))
        if not previous_tp <= tp <= min(k, positive) or not previous_random <= shuffled <= min(k, positive):
            raise ValueError("Invalid cumulative TP or shuffled TP")
        previous_tp, previous_random = tp, shuffled
        observed = None if row["EPR_R_seed1_shuffle"] in ("NA", "", None) else float(row["EPR_R_seed1_shuffle"])
        if shuffled == 0:
            if observed is not None:
                raise ValueError("Zero shuffled TP requires unavailable EPR")
        elif observed is None or not math.isclose(observed, tp / shuffled, abs_tol=1e-12):
            raise ValueError("EPR is not integer TP / realized shuffled TP")
        low, high = int(row["TP_min"]), int(row["TP_max"])
        tie_expected = float(row["TP_tie_expected"])
        if (low, high) != (independent["TP_min"], independent["TP_max"]) or not low <= tp <= high:
            raise ValueError("Saved TP range differs from independently recounted MI tie")
        if not math.isclose(tie_expected, independent["TP_tie_expected"], abs_tol=1e-9):
            raise ValueError("Saved tie-expected TP differs from independently recounted MI tie")
        result.append({"k": k, "TP": tp, "Random_TP": shuffled,
                       "EPR_R_seed1_shuffle": observed, "TP_tie_expected": tie_expected,
                       "TP_min": low, "TP_max": high,
                       "split_MI_tie": independent["split_MI_tie"]})
    if (result[-1]["TP"], result[-1]["Random_TP"]) != (positive, positive):
        raise ValueError("Full-pool endpoint must retain every eligible positive")
    return result


def load_arm(key, label, three_path, epr_path, prepared, universe, hashes):
    three_path, three = verify_manifest(three_path, hashes)
    epr_path, epr = verify_manifest(epr_path, hashes)
    if str(three_path) not in {str(local_path(p)) for p in epr["input_sha256"]}:
        raise ValueError("Eligible EPR is not bound to the requested three-population score")
    for filename, expected in (("score_fixed_universe.py", three["helper_sha256"]),
                               ("score_three_populations.py", three["script_sha256"]),
                               ("score_eligible_epr.R", epr["script_sha256"])):
        bind(Path(__file__).with_name(filename), expected, hashes)
    bound = {str(local_path(p)) for p in three["input_sha256"]}
    for name in PREPARED_FILES:
        if str(prepared / name) not in bound:
            raise ValueError(f"Prepared input is not bound to requested score: {name}")
    u = three["universe"]
    if (tuple(u["sources"]), tuple(u["targets"]), u["candidate_pairs"], u["reference_positive_pairs"]) != (
        universe.sources, universe.targets, universe.size, len(universe.positives)
    ):
        raise ValueError("Frozen prepared universe differs from score")
    candidates = [Path(path) for path in bound if Path(path).name == "run_manifest.json"]
    if len(candidates) != 1:
        raise ValueError("Require exactly one bound inference run manifest")
    run_path = candidates[0]
    run = json.loads(run_path.read_text(encoding="utf-8"))
    if run.get("status") != "complete" or set(run["consensus"]) != set(three["scores"]) or set(epr["scores"]) != set(three["scores"]):
        raise ValueError("Incomplete inference or different consensus alternatives")
    ranked_path = epr_path.parent / "ranked_curves.tsv"
    if "ranked_curves.tsv" not in epr["output_sha256"]:
        raise ValueError("EPR trajectory is not hash-bound")
    ranked_rows = list(fixed.rows(ranked_path))
    if {row["consensus"] for row in ranked_rows} != set(three["scores"]):
        raise ValueError("Trajectory consensus alternatives differ")
    hubs = set((prepared / "hubs.txt").read_text(encoding="utf-8").splitlines())
    curves = {}
    for name, score in three["scores"].items():
        job = run["consensus"][name]
        if job.get("status") != "complete":
            raise ValueError("Incomplete consensus")
        network = bind(job["artifacts"]["edges.tsv"]["path"], job["artifacts"]["edges.tsv"]["sha256"], hashes)
        if str(network) not in bound:
            raise ValueError("Network is not bound to requested population score")
        population = score["populations"]["eligible_emitted"]
        total, positive = population["candidate_pairs"], population["reference_positive_pairs_in_population"]
        saved_epr = epr["scores"][name]
        if (total, positive, score["consensus_p"]) != (saved_epr["eligible_emitted_pairs"], saved_epr["reference_positive_emitted_pairs"], saved_epr["consensus_p"]):
            raise ValueError("Eligible EPR and AUROC populations differ")
        groups, full_count, full_positive = fixed.read_network(network, universe, hubs)
        if (full_count, full_positive) != (score["populations"]["full_emitted"]["candidate_pairs"], positive):
            raise ValueError("Recounted full network differs from frozen score")
        ranked = validate_ranked([row for row in ranked_rows if row["consensus"] == name],
                                 total, positive, three["top_k_prespecified"], groups)
        for anchor in population["top_k"]:
            if anchor["status"] == "complete":
                actual = next(row for row in ranked if row["k"] == anchor["k"])
                if not math.isclose(actual["TP_tie_expected"], anchor["TP_tie_expected"], abs_tol=1e-9):
                    raise ValueError("Three-population and EPR tie-expected anchors differ")
        curves[name] = {"arm": key, "label": label, "color": COLORS[key],
                        "consensus_p": score["consensus_p"], "N": total, "P": positive,
                        "AUROC": population["AUROC_MI_ties"], "ranked": ranked,
                        "roc": eligible_roc(groups, positive, total - positive, population["AUROC_MI_ties"])}
    return {"key": key, "label": label, "metrics_path": str(three_path), "epr_path": str(epr_path),
            "run_manifest": str(run_path), "run_profile": run["frozen"].get("profile", "legacy_reconstruction"),
            "run_label": run["frozen"].get("label"), "parameters": run["frozen"]["parameters"],
            "observations": run["frozen"]["observations"], "three": three, "epr": epr, "curves": curves}


def validate_matched(before, after):
    for name in ("universe", "top_k_prespecified", "definitions", "script_sha256", "helper_sha256"):
        if before["three"][name] != after["three"][name]:
            raise ValueError(f"Scoring definitions/universe differ: {name}")
    for name in ("seed", "RNGkind", "R_version", "script_sha256", "definitions"):
        if before["epr"][name] != after["epr"][name]:
            raise ValueError(f"EPR provenance differs: {name}")
    if before["epr"]["seed"] != 1:
        raise ValueError("This comparison requires realized R seed-1 shuffled EPR")
    for name in MATCHED_PARAMETERS:
        if before["parameters"][name] != after["parameters"][name]:
            raise ValueError(f"Non-sampling inference setting differs: {name}")
    if before["observations"] != after["observations"]:
        raise ValueError("Prepared observation counts differ")
    if set(before["curves"]) != set(after["curves"]):
        raise ValueError("Consensus alternatives differ")
    for name in before["curves"]:
        if before["curves"][name]["consensus_p"] != after["curves"][name]["consensus_p"]:
            raise ValueError("Consensus cutoff differs between arms")


def draw_panel(ax, panel, curves):
    ax.set_axisbelow(True)
    ax.grid(axis="y", color="#dddddd", linewidth=.6)
    if panel in ("tp", "epr"):
        for c in curves:
            rows = c["ranked"]
            k = [r["k"] for r in rows]
            if panel == "tp":
                ax.plot([0, *k], [0, *[r["TP_tie_expected"] for r in rows]], color=c["color"], lw=2)
                ax.fill_between(k, [r["TP_min"] for r in rows], [r["TP_max"] for r in rows],
                                color=c["color"], alpha=.20)
                ax.plot([0, *k], [0, *[r["Random_TP"] for r in rows]], color=c["color"], ls="--", lw=1.2, alpha=.8)
            else:
                ax.plot(k, [r["EPR_R_seed1_shuffle"] if r["EPR_R_seed1_shuffle"] is not None else math.nan for r in rows],
                        color=c["color"], lw=2)
            ax.plot(k[-1], c["P"] if panel == "tp" else 1, "o", ms=4, color=c["color"])
        ax.set_xlabel("Top-ranked eligible edges, k")
        if panel == "tp":
            ax.set_title("TP counts (MI-tie expectation)", loc="left")
            ax.set_ylabel("Response-positive edges")
            ax.set_xlim(0, max(c["N"] for c in curves) * 1.04)
            ax.set_ylim(bottom=0)
            ax.xaxis.set_major_locator(MaxNLocator(5, integer=True))
            ax.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
            ax.xaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
            ax.legend(handles=[Line2D([0], [0], color="#444444", lw=2, label="MI-ranked; shaded tie range"),
                               Line2D([0], [0], color="#444444", lw=1.2, ls="--", label="Actual rank shuffle")],
                      loc="upper left", frameon=False, fontsize=8)
        else:
            ax.set_title("Realized shuffled EPR", loc="left")
            ax.set_ylabel("Integer TP / shuffled TP")
            ax.set_xscale("log")
            ax.axhline(1, color="#777777", ls="--", lw=1)
            ax.xaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    else:
        for c in curves:
            ax.plot([r["FPR"] for r in c["roc"]], [r["sensitivity"] for r in c["roc"]],
                    color=c["color"], lw=2, label=f"{c['label']}: {c['AUROC']:.4f}")
        ax.plot([0, 1], [0, 1], color="#777777", ls="--", lw=1)
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_title("ROC within emitted eligible pool", loc="left")
        ax.set_xlabel("1 - specificity (own emitted pool)")
        ax.set_ylabel("Sensitivity (own emitted pool)")
        ax.legend(loc="lower right", frameon=False, fontsize=8)


def save_figure(fig, out, name):
    paths = []
    for ext in ("png", "pdf"):
        path = out / f"{name}.{ext}"
        metadata = {"Creator": "plot_sampling_comparison.py", "CreationDate": None, "ModDate": None} if ext == "pdf" else {"Software": "plot_sampling_comparison.py"}
        fig.savefig(path, dpi=200, facecolor="white", metadata=metadata)
        paths.append(path)
    plt.close(fig)
    return paths


def render(arms, out):
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.titlesize": 11, "axes.labelsize": 9})
    names = sorted(arms[0]["curves"], key=lambda n: arms[0]["curves"][n]["consensus_p"], reverse=True)
    fig, axes = plt.subplots(len(names), 3, figsize=(14.6, 4.5 * len(names) + 1.2), squeeze=False)
    fig.subplots_adjust(left=.075, right=.985, bottom=.09, top=.87, hspace=.55, wspace=.28)
    fig.suptitle("THP-1 sampling comparison: eligible-source predictions", y=.975, fontsize=16)
    fig.text(.5, .938, "Frozen reconstructed perturbation-response reference; not exact Figure 6a reproduction", ha="center", fontsize=10)
    fig.legend(handles=[Line2D([0], [0], color=COLORS[a["key"]], lw=2, label=a["label"]) for a in arms],
               loc="upper center", bbox_to_anchor=(.5, .916), ncol=2, frameon=False)
    paths = []
    for row, name in enumerate(names):
        curves = [a["curves"][name] for a in arms]
        for ax, panel in zip(axes[row], ("tp", "epr", "roc")):
            draw_panel(ax, panel, curves)
        axes[row, 0].text(0, 1.16, f"p_c = {curves[0]['consensus_p']:g}  |  " + "  vs  ".join(
            f"{c['N']:,} eligible edges / {c['P']:,} positives" for c in curves), transform=axes[row, 0].transAxes,
            fontsize=10, weight="bold")
        single, single_axes = plt.subplots(1, 3, figsize=(14.6, 5.3))
        single.subplots_adjust(left=.075, right=.985, bottom=.19, top=.75, wspace=.28)
        single.suptitle(f"THP-1 sampling comparison: p_c = {curves[0]['consensus_p']:g}", y=.97, fontsize=15)
        single.legend(handles=[Line2D([0], [0], color=c["color"], lw=2,
                                    label=f"{c['label']}: {c['N']:,} edges, {c['P']:,} positives") for c in curves],
                      loc="upper center", bbox_to_anchor=(.5, .90), ncol=2, frameon=False, fontsize=9)
        for ax, panel in zip(single_axes, ("tp", "epr", "roc")):
            draw_panel(ax, panel, curves)
        single.text(.075, .07, "Each arm stops at its own emitted pool. EPR uses its own realized R seed-1 shuffle; ROC retains MI ties.", fontsize=9)
        paths += save_figure(single, out, f"{name}_sampling_comparison")
    fig.text(.075, .035, "Each arm stops at its own pool. Emitted-pool AUROC is conditional; response membership does not establish direct regulation.", fontsize=9)
    return save_figure(fig, out, "eligible_sampling_comparison") + paths


def comparison_rows(arms):
    summary, topk = [], []
    before, after = arms
    for name, bs in before["three"]["scores"].items():
        ats = after["three"]["scores"][name]
        for population in POPULATIONS:
            bp, ap = (s["populations"][population] for s in (bs, ats))
            item = {"consensus": name, "consensus_p": bs["consensus_p"], "population": population}
            for metric in ("candidate_pairs", "reference_positive_pairs_in_population", "emitted_pairs",
                           "emitted_positive_match_fraction", "AUROC_MI_ties", "fixed_reference_sensitivity_all_emitted"):
                item.update({f"before_{metric}": bp[metric], f"after_{metric}": ap[metric],
                             f"delta_{metric}": ap[metric] - bp[metric]})
            item.update({"before_fixed_reference_specificity": bs["fixed_reference_coverage"]["specificity"],
                         "after_fixed_reference_specificity": ats["fixed_reference_coverage"]["specificity"]})
            summary.append(item)
            for bpoint, apoint in zip(bp["top_k"], ap["top_k"]):
                if bpoint["k"] != apoint["k"]:
                    raise ValueError("Top-k order differs")
                row = {"consensus": name, "consensus_p": bs["consensus_p"], "population": population, "k": bpoint["k"]}
                for arm, point in ((before, bpoint), (after, apoint)):
                    prefix = arm["key"] + "_"
                    row[prefix + "status"] = point["status"]
                    for metric in ("TP_tie_expected", "TP_min", "TP_max", "precision_tie_expected",
                                   "fixed_reference_sensitivity_at_k", "precision_lift_over_random_expectation"):
                        row[prefix + metric] = point.get(metric)
                    if population == "eligible_emitted":
                        ranked = next((r for r in arm["curves"][name]["ranked"] if r["k"] == point["k"]), {})
                        for metric in ("TP", "Random_TP", "EPR_R_seed1_shuffle"):
                            row[prefix + metric] = ranked.get(metric)
                for metric in ("TP_tie_expected", "precision_tie_expected", "fixed_reference_sensitivity_at_k",
                               "precision_lift_over_random_expectation", "EPR_R_seed1_shuffle"):
                    b, a = row.get("before_" + metric), row.get("after_" + metric)
                    row["delta_" + metric] = a - b if a is not None and b is not None else None
                topk.append(row)
    return summary, topk


def report(arms, summary, topk):
    lines = ["# THP-1 before/after sampling comparison", "",
             "Eligible-source emitted predictions are primary; full emitted SIG predictions and the fixed eligible universe are secondary. All arms use the same frozen reconstructed perturbation-response reference. This is not exact Figure 6a reproduction or direct-edge validation.", "",
             "## Operational comparison", "",
             "| Arm | Inference profile | Sampling | Draws | Nominal p_b | Affine MI cutoff |",
             "|---|---|---|---:|---:|---:|"]
    for arm in arms:
        p = arm["parameters"]
        lines.append(f"| {arm['label']} | {arm['run_profile']} | {p['sampling']} | {p.get('sampling_draws', arm['observations'])} | {p['bootstrap_p']:g} | {p['affine_mi_cutoff']:.9f} |")
    lines += ["", "The expression/metacells, full SIG hub list, response labels, eligible universe, DPI setting, nominal bootstrap p-value, seed numbers, and original consensus settings are fixed. Sample count, sample-size-dependent affine MI cutoff and sampling/tie-noise RNG consumption change together. This does not isolate replacement alone at a common numerical MI cutoff. PR71 and K-based consensus are excluded.", "",
              "## Primary eligible-source emitted predictions", "",
              "| p_c | Arm | Eligible edges | Response-positive matches | Positive fraction | MI-tied AUROC | Fixed-reference sensitivity |",
              "|---:|---|---:|---:|---:|---:|---:|"]
    for row in summary:
        if row["population"] != "eligible_emitted":
            continue
        for arm in arms:
            k = arm["key"]
            lines.append(f"| {row['consensus_p']:g} | {arm['label']} | {row[k+'_candidate_pairs']:,} | {row[k+'_reference_positive_pairs_in_population']:,} | {100*row[k+'_emitted_positive_match_fraction']:.2f}% | {row[k+'_AUROC_MI_ties']:.6f} | {100*row[k+'_fixed_reference_sensitivity_all_emitted']:.4f}% |")
    lines += ["", "Conditional emitted-pool AUROC compares different emitted pools, not the same all-pair ranking. Its changes must be read alongside pool size and fixed-reference coverage. No statistical uncertainty or independent repeated-batch significance is inferred from a single matched batch.", "",
              "## Primary top-k comparison", "",
              "TP below is the MI-tie expectation and attainable range. EPR uses saved integer prefix TP divided by the actual eligible-pool R seed-1 shuffled TP; it is not the analytic random-expectation lift. Each shuffle operates on its own arm's emitted pool.", "",
              "| p_c | k | Before TP (range) | After TP (range) | Before EPR | After EPR |",
              "|---:|---:|---:|---:|---:|---:|"]
    def tp(row, arm):
        if row[arm + "_status"] != "complete":
            return "unavailable"
        return f"{row[arm+'_TP_tie_expected']:,.2f} ({row[arm+'_TP_min']:,}-{row[arm+'_TP_max']:,})"
    def ratio(value):
        return "unavailable" if value is None else f"{value:.4f}"
    for row in topk:
        if row["population"] == "eligible_emitted":
            lines.append(f"| {row['consensus_p']:g} | {row['k']:,} | {tp(row, 'before')} | {tp(row, 'after')} | {ratio(row.get('before_EPR_R_seed1_shuffle'))} | {ratio(row.get('after_EPR_R_seed1_shuffle'))} |")
    lines += ["", "Top-k above an arm's emitted pool is unavailable, never padded or extrapolated. TP curves retain the tie-expected counts/ranges and show the realized shuffle as dashed lines; EPR uses integer TP. ROC recounts entire equal-MI groups and excludes omitted pairs. The ROC diagonal is random expectation, not one realized shuffle.", "",
              "## Secondary MI-tied AUROCs", "",
              "| p_c | Population | Before AUROC | After AUROC | After - before |",
              "|---:|---|---:|---:|---:|"]
    for row in summary:
        if row["population"] != "eligible_emitted":
            lines.append(f"| {row['consensus_p']:g} | {row['population']} | {row['before_AUROC_MI_ties']:.6f} | {row['after_AUROC_MI_ties']:.6f} | {row['delta_AUROC_MI_ties']:+.6f} |")
    lines += ["", "The fixed-universe AUROC includes every omitted eligible pair in one shared bottom-score tie and therefore measures thresholded selection plus ranking, not unthresholded MI discrimination. Full-emitted scoring includes unassessed sources as operational reference nonmembers. These are not established biological negatives.", "",
              "PNG and deterministic PDF figures, complete ranked and ROC coordinates, all-population summary/top-k tables and comparison.json are saved here. manifest.json binds the unchanged score inputs, scripts and new outputs by SHA256. Historical scoring templates retain baseline-only wording; this additive report identifies each actual inference arm from its bound run manifest.", ""]
    return "\n".join(lines)


def calculate(args):
    out = args.out.resolve()
    if out.exists():
        raise FileExistsError(f"Refusing to overwrite comparison output: {out}")
    prepared = args.prepared_dir.resolve(strict=True)
    universe = fixed.make_universe(prepared)
    hashes = {}
    arms = [load_arm("before", args.before_label, args.before_metrics, args.before_epr, prepared, universe, hashes),
            load_arm("after", args.after_label, args.after_metrics, args.after_epr, prepared, universe, hashes)]
    validate_matched(*arms)
    summary, topk = comparison_rows(arms)
    check_inputs(hashes)
    out.mkdir(parents=True, exist_ok=False)
    outputs = render(arms, out)
    for name, rows in (("population_summary.tsv", summary), ("topk_comparison.tsv", topk),
                       ("eligible_ranked_curves.tsv", [{"arm": a["key"], "consensus": n, "consensus_p": c["consensus_p"], **r}
                                                     for a in arms for n, c in a["curves"].items() for r in c["ranked"]]),
                       ("eligible_roc_curves.tsv", [{"arm": a["key"], "consensus": n, "consensus_p": c["consensus_p"], **r}
                                                   for a in arms for n, c in a["curves"].items() for r in c["roc"]])):
        path = out / name
        fixed.write_tsv(path, rows)
        outputs.append(path)
    comparison = {"status": "complete", "scope": "matched_sampling_protocol_reconstructed_response_benchmark",
                  "primary_population": "eligible_emitted",
                  "universe": {k: arms[0]["three"]["universe"][k] for k in ("definition_sha256", "candidate_pairs", "reference_positive_pairs", "n_sources", "n_targets")},
                  "arms": [{k: a[k] for k in ("key", "label", "metrics_path", "epr_path", "run_manifest", "run_profile", "run_label", "parameters", "observations")} |
                           {"population_scores": a["three"]["scores"], "eligible_EPR_scores": a["epr"]["scores"]} for a in arms],
                  "population_comparison": summary, "top_k_comparison": topk}
    path = out / "comparison.json"
    path.write_text(json.dumps(comparison, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    outputs.append(path)
    path = out / "REPORT.md"
    path.write_text(report(arms, summary, topk), encoding="utf-8")
    outputs.append(path)
    check_inputs(hashes)
    manifest = {"status": "complete", "created_utc": datetime.now(timezone.utc).isoformat(),
                "scope": comparison["scope"], "primary_population": "eligible_emitted",
                "script_sha256": fixed.digest(Path(__file__)), "helper_sha256": fixed.digest(Path(fixed.__file__)),
                "matplotlib_version": matplotlib.__version__, "input_sha256": hashes,
                "definitions": {"TP": "MI-tie expected TP and attainable range; integer TP retained separately",
                                "EPR": "Integer prefix TP / actual own-pool R seed-1 shuffled TP; zero shuffled TP is unavailable",
                                "ROC": "Whole consensus-MI ties within each emitted eligible pool; no omitted group",
                                "missing_topk": "Unavailable beyond own emitted pool; no padding or extrapolation",
                                "labels": "Frozen perturbation responses, not direct regulatory-edge truth"},
                "output_sha256": {p.name: fixed.digest(p) for p in outputs}}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return comparison


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("before-metrics", "after-metrics", "before-epr", "after-epr", "prepared-dir", "out"):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--before-label", default="Legacy with replacement")
    p.add_argument("--after-label", default="80% without replacement")
    return p


if __name__ == "__main__":
    result = calculate(parser().parse_args())
    print(json.dumps({"status": result["status"], "population_comparison": result["population_comparison"]}, indent=2))
