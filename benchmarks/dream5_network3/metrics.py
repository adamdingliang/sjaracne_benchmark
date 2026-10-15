"""Strict Network3 native-output validation and explicit-label pilot scoring.

No inference, reference-derived hub selection or implicit-negative expansion.
Native zero suppression is accepted only after a complete successful traversal.
The runner proves process exit zero; this module additionally verifies logs,
headers and stage relationships before scoring the released explicit labels.
"""
from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np

import prepare


STAGES = ("raw", "nominal_pre", "nominal_post", "fixed_pre", "fixed_post")
ARMS = ("legacy", "u64", "u80", "u90")
KS = (100, 500, 1000, 5000, 10000, 20000, 50000, 100000)


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


def verify_record(value):
    path = Path(value["path"]).resolve(strict=True)
    if path.stat().st_size != value["bytes"] or digest(path) != value["sha256"]:
        raise ValueError("Frozen artifact changed: " + str(path))
    return path


def normalized_path(value):
    value = str(value).replace("\\", "/")
    if re.match(r"^/mnt/[A-Za-z]/", value):
        value = value[5].lower() + ":" + value[6:]
    if re.match(r"^[A-Za-z]:/", value):
        value = value[0].lower() + value[1:]
    return value.rstrip("/")


def serialization_tolerance(value):
    """Half a sixth-significant-digit unit, plus floating-point guard."""
    return .51 * 10 ** (math.floor(math.log10(abs(value))) - 5) + 1e-14 if value else 1e-14


@lru_cache(maxsize=8)
def _identifiers(expression_path, hubs_path, expression_sha, hubs_sha):
    genes = []
    with Path(expression_path).open(encoding="utf-8", newline="") as stream:
        reader = csv.reader(stream, delimiter="\t")
        header = next(reader)
        profiles = len(header) - 2
        if header[:2] != ["isoformId", "geneSymbol"] or profiles <= 0:
            raise ValueError("Unexpected prepared expression header")
        for row in reader:
            if len(row) != len(header) or not row[0] or row[0] != row[1]:
                raise ValueError("Prepared expression contains ragged rows or gene aliases")
            genes.append(row[0])
    hubs = Path(hubs_path).read_text(encoding="utf-8").splitlines()
    if not genes or len(set(genes)) != len(genes) or not hubs or len(set(hubs)) != len(hubs) or not set(hubs) <= set(genes):
        raise ValueError("Duplicate/unknown prepared gene or TF")
    return tuple(genes), tuple(hubs), profiles


def native_identifiers(plan):
    expression, hubs = plan["inputs"]["expression"], plan["inputs"]["hubs"]
    genes, sources, profiles = _identifiers(expression["path"], hubs["path"], expression["sha256"], hubs["sha256"])
    expected = plan["dataset"]
    if (len(genes), len(sources), profiles) != (expected["genes"], expected["TFs"], expected["profiles"]):
        raise ValueError("Prepared native input dimensions disagree with plan")
    return genes, sources


def expected_cutoff(plan, arm, stage):
    if stage == "raw":
        return 0.0
    return plan["parameters"]["fixed_mi"] if stage.startswith("fixed") else plan["parameters"]["nominal_cutoffs"][arm]


@dataclass
class ParsedStage:
    values: np.ndarray
    emitted: np.ndarray
    headers: dict
    source_rows: int
    validation: dict


_HEADER_NAMES = ("Input file", "MI threshold", "MI P-value", "DPI tolerance", "Subnetwork file",
                 "Sampling method", "Sampling request", "Eligible observations", "Sampled observations", "Resample draws")


def parse_adjacency(path, genes, sources):
    """Parse native sparse rows without assigning biological labels."""
    path = Path(path)
    with path.open("rb") as stream:
        stream.seek(0, 2)
        if not stream.tell():
            raise ValueError("Empty adjacency file")
        stream.seek(-1, 2)
        if stream.read(1) != b"\n":
            raise ValueError("Adjacency missing final newline")
    gi, si = {gene: i for i, gene in enumerate(genes)}, {source: i for i, source in enumerate(sources)}
    values = np.zeros((len(sources), len(genes)), dtype=np.float64)
    emitted = np.zeros(values.shape, dtype=bool)
    headers, seen_sources = {}, set()
    data_started = False
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            line = line.rstrip("\r\n")
            if not line:
                raise ValueError("Empty adjacency line")
            if line.startswith(">"):
                if data_started:
                    raise ValueError("Header occurs after source rows")
                body = line[1:].strip()
                matches = [key for key in _HEADER_NAMES if body.startswith(key + " ")]
                if len(matches) != 1 or matches[0] in headers:
                    raise ValueError("Unknown or duplicate native header")
                headers[matches[0]] = body[len(matches[0]):].strip()
                continue
            data_started = True
            fields = line.split("\t")
            source = fields[0]
            if source not in si or source in seen_sources or len(fields) % 2 != 1:
                raise ValueError("Unknown/duplicate source or malformed native row")
            seen_sources.add(source)
            source_index = si[source]
            for offset in range(1, len(fields), 2):
                target = fields[offset]
                if target not in gi or target == source:
                    raise ValueError("Unknown/annotated target or self-pair")
                target_index = gi[target]
                if emitted[source_index, target_index]:
                    raise ValueError("Duplicate directed native edge")
                value = float(fields[offset + 1])
                if not math.isfinite(value) or value <= 0:
                    raise ValueError("Native stored MI must be finite and strictly positive")
                emitted[source_index, target_index] = True
                values[source_index, target_index] = value
    return ParsedStage(values, emitted, headers, len(seen_sources), {})


def validate_log(text, plan, arm, stage):
    dataset, sample = plan["dataset"], plan["sampling"][arm]
    matches = re.findall(r"Marker No:\s*(\d+)\s*\((\d+) active\), Array No:\s*(\d+)", text)
    expected = (str(dataset["genes"]), str(dataset["genes"]), str(sample["draws"]))
    if matches != [expected]:
        raise ValueError("Native active-gene/sample counts differ from plan")
    sources = dataset["TFs"]
    if not re.search(r"Gene:\s*" + str(sources) + r"\s+Time:\s*\d", text):
        raise ValueError("Native log lacks completed full-TF traversal")
    subnetwork = re.search(r"\[SUBNETWORK\]\s*Requested:\s*(\d+),\s*matched:\s*(\d+),\s*missing:\s*(\d+)", text)
    if not subnetwork or tuple(map(int, subnetwork.groups())) != (sources, sources, 0):
        raise ValueError("Native subnetwork did not match all supplied TFs")
    if "Cannot find probe" in text or "... ignored." in text or "Maximum observed npar:" not in text or "Writing matrix:" not in text:
        raise ValueError("Native identifiers/completion markers are invalid")
    is_post = stage.endswith("post")
    if ("Applying DPI" in text) != is_post:
        raise ValueError("DPI execution differs from requested stage")
    if ("MI threshold determined" in text) != stage.startswith("nominal"):
        raise ValueError("Affine threshold execution differs from requested stage")
    if arm != "legacy":
        expected_sampling = f"selected {sample['draws']} of {sample['population']} eligible observations (request: {sample['value']})"
        if expected_sampling not in text:
            raise ValueError("Native without-replacement sample selection differs from plan")


def validate_job_output(adj_path, log_path, *, plan, arm, stage):
    return _validated_stage(adj_path, log_path, plan=plan, arm=arm, stage=stage).validation


def _validated_stage(adj_path, log_path, *, plan, arm, stage):
    if arm not in plan["arms"] or stage not in STAGES:
        raise ValueError("Arm or stage is outside the frozen design")
    genes, sources = native_identifiers(plan)
    validate_log(Path(log_path).read_text(encoding="utf-8"), plan, arm, stage)
    parsed = parse_adjacency(adj_path, genes, sources)
    headers, sample = parsed.headers, plan["sampling"][arm]
    required = set(_HEADER_NAMES[:8]) | {"Eligible observations"}
    if not required <= set(headers):
        raise ValueError("Missing required native headers")
    if normalized_path(headers["Input file"]) != normalized_path(plan["inputs"]["expression"]["path"]) or normalized_path(headers["Subnetwork file"]) != normalized_path(plan["inputs"]["hubs"]["path"]):
        raise ValueError("Native input/subnetwork path differs from frozen full input")
    cutoff = expected_cutoff(plan, arm, stage)
    actual_cutoff = float(headers["MI threshold"])
    if not math.isfinite(actual_cutoff) or abs(actual_cutoff - cutoff) > serialization_tolerance(cutoff):
        raise ValueError("Native cutoff header differs beyond six-digit serialization tolerance")
    pvalue = plan["parameters"]["nominal_p"] if stage.startswith("nominal") else 1.0
    if float(headers["MI P-value"]) != pvalue or float(headers["DPI tolerance"]) != (0 if stage.endswith("post") else 1):
        raise ValueError("Native P-value/DPI headers differ from requested stage")
    if headers["Sampling method"] != sample["method"] or headers["Sampling request"] != ("legacy -r 1" if arm == "legacy" else sample["value"]):
        raise ValueError("Native sampling method/request differs from frozen arm")
    count_key = "Resample draws" if arm == "legacy" else "Sampled observations"
    other_key = "Sampled observations" if arm == "legacy" else "Resample draws"
    if headers.get(count_key) != str(sample["draws"]) or headers.get("Eligible observations") != str(sample["population"]) or other_key in headers:
        raise ValueError("Native sampling count headers differ from plan")
    minimum = float(parsed.values[parsed.emitted].min()) if parsed.emitted.any() else None
    if minimum is not None and minimum + serialization_tolerance(cutoff) < cutoff:
        raise ValueError("Stored edge is below cutoff beyond serialization tolerance")
    parsed.validation = {"status": "passed", "arm": arm, "stage": stage,
                         "source_rows_present": parsed.source_rows, "completed_source_traversal": len(sources),
                         "active_genes": len(genes), "sampled_observations": sample["draws"],
                         "edges_all": int(parsed.emitted.sum()), "minimum_emitted_MI": minimum,
                         "expected_MI_cutoff": cutoff, "serialized_MI_cutoff": actual_cutoff,
                         "headers": headers, "zero_policy": "Native omitted pairs have MI=0 only after caller-proven exit zero and validated complete traversal; empty source rows may be omitted"}
    return parsed


def _arm_data(plan, arm, seed, jobpaths):
    if seed not in plan["seeds"] or set(jobpaths) != set(STAGES):
        raise ValueError("Seed/stage population differs from frozen design")
    parsed = {stage: _validated_stage(Path(jobpaths[stage]) / "raw.adj", Path(jobpaths[stage]) / "stdout.log",
                                     plan=plan, arm=arm, stage=stage) for stage in STAGES}
    raw = parsed["raw"]
    for stage in STAGES[1:]:
        value = parsed[stage]
        if np.any(value.emitted & ~raw.emitted) or not np.array_equal(value.values[value.emitted], raw.values[value.emitted]):
            raise ValueError("Stage MI differs from raw same-arm/same-seed MI")
    for prefix in ("nominal", "fixed"):
        pre, post = parsed[prefix + "_pre"], parsed[prefix + "_post"]
        if np.any(post.emitted & ~pre.emitted) or not np.array_equal(post.values[post.emitted], pre.values[post.emitted]):
            raise ValueError("Post-DPI stage is not an exact-weight subset of pre-DPI")
        # Clearly above/below cutoffs must agree; the native six-digit boundary
        # band is not re-filtered because the internal MI is unavailable.
        cutoff = expected_cutoff(plan, arm, prefix + "_pre")
        tolerance = serialization_tolerance(cutoff)
        if np.any(raw.emitted & (raw.values > cutoff + tolerance) & ~pre.emitted):
            raise ValueError("Pre-DPI stage omitted a raw edge clearly above its cutoff")
    return parsed


def validate_arm_stages(plan, arm, seed, jobpaths):
    parsed = _arm_data(plan, arm, seed, jobpaths)
    return {"status": "passed", "arm": arm, "seed": seed,
            "stage_validation": {stage: value.validation for stage, value in parsed.items()},
            "exact_shared_MI_identity": True, "exact_post_subset_pre": True,
            "nominal_cutoff_membership_outside_serialization_band": True,
            "fixed_cutoff_membership_outside_serialization_band": True}


def ranking_metrics(scores, labels, *, emitted=None, raw=False, ks=KS):
    scores, labels = np.asarray(scores, dtype=float), np.asarray(labels, dtype=bool)
    if scores.ndim != 1 or labels.shape != scores.shape or not np.isfinite(scores).all() or np.any(scores < 0):
        raise ValueError("Invalid score/label vectors")
    positive, negative = int(labels.sum()), int((~labels).sum())
    if not positive or not negative:
        raise ValueError("Ranking requires both explicit gold classes")
    order = np.argsort(-scores, kind="stable")
    values, truth = scores[order], labels[order]
    starts = np.r_[0, np.flatnonzero(values[1:] != values[:-1]) + 1]
    sizes = np.diff(np.r_[starts, len(scores)])
    gp = np.add.reduceat(truth.astype(np.int64), starts)
    gn = sizes - gp
    cp, cn = np.cumsum(gp), np.cumsum(gn)
    auc = float(np.sum(gp * (negative - cn + .5 * gn)) / (positive * negative))
    ap = float(np.sum((gp / positive) * (cp / (cp + cn))))
    fpr, tpr = np.r_[0., cn / negative], np.r_[0., cp / positive]
    geometric = float(np.sum((tpr[1:] + tpr[:-1]) * np.diff(fpr) / 2))
    if not math.isclose(auc, geometric, rel_tol=0, abs_tol=1e-12):
        raise ValueError("AUROC independent geometric check failed")
    eligible = np.ones(len(scores), bool) if raw else np.asarray(emitted, dtype=bool)
    if eligible.shape != scores.shape:
        raise ValueError("Emitted-pair vector shape differs")
    selected = order[eligible[order]]
    selected_scores, selected_labels = scores[selected], labels[selected]
    selected_count = len(selected)
    topk = []
    for k in ks:
        if not isinstance(k, int) or isinstance(k, bool) or k <= 0:
            raise ValueError("Top-k must be a positive integer")
        if k > selected_count:
            topk.append({"k": k, "status": "exceeds_labelled_emitted_pairs"})
            continue
        boundary = selected_scores[k - 1]
        above = selected_scores > boundary
        tied = selected_scores == boundary
        before_tp, take = int(selected_labels[above].sum()), k - int(above.sum())
        p, n = int(selected_labels[tied].sum()), int((~selected_labels[tied]).sum())
        tp = before_tp + take * p / (p + n)
        topk.append({"k": k, "status": "complete", "TP_tie_expected": tp, "FP_tie_expected": k - tp,
                     "TP_min": before_tp + max(0, take - n), "TP_max": before_tp + min(take, p),
                     "precision": tp / k, "sensitivity": tp / positive,
                     "specificity": 1 - (k - tp) / negative, "EPR_fixed_universe": (tp / k) / (positive / len(labels))})
    grid = np.linspace(0, 1, 1001)
    return {"AUROC_fixed_explicit_universe_MI_ties": auc, "AUROC_geometric_check": geometric,
            "average_precision_fixed_explicit_universe": ap, "random_precision": positive / len(labels),
            "top_k": topk, "top_k_population": "all explicit pairs" if raw else "explicit labelled emitted pairs only; unavailable budgets are not padded",
            "roc_curve": {"FPR": grid.tolist(), "sensitivity": np.interp(grid, fpr, tpr).tolist()}}


def score_stage(parsed, label_rows, label_cols, labels, *, raw=False):
    emitted = parsed.emitted[label_rows, label_cols]
    values = parsed.values[label_rows, label_cols]
    positive, negative = int(labels.sum()), int((~labels).sum())
    tp, fp = int(labels[emitted].sum()), int((~labels[emitted]).sum())
    called = tp + fp
    return {"edges_all": int(parsed.emitted.sum()), "edges_explicit_labelled": called,
            "edges_unlabelled": int(parsed.emitted.sum()) - called,
            "TP": tp, "FP": fp, "FN": positive - tp, "TN": negative - fp,
            "precision": tp / called if called else None, "sensitivity": tp / positive,
            "specificity": 1 - fp / negative,
            **ranking_metrics(values, labels, emitted=emitted, raw=raw)}


def score_arm_stages(plan, arm, seed, jobpaths, gold):
    parsed = _arm_data(plan, arm, seed, jobpaths)
    genes, sources = native_identifiers(plan)
    gi, si = {gene: i for i, gene in enumerate(genes)}, {source: i for i, source in enumerate(sources)}
    rows = np.array([si[source] for source, target, label in gold])
    cols = np.array([gi[target] for source, target, label in gold])
    labels = np.array([label for source, target, label in gold], dtype=bool)
    stages = {stage: score_stage(value, rows, cols, labels, raw=stage == "raw") for stage, value in parsed.items()}
    pruning = {}
    for prefix in ("nominal", "fixed"):
        pre, post = stages[prefix + "_pre"], stages[prefix + "_post"]
        pruning[prefix] = {"global_pruning_fraction": 1 - post["edges_all"] / pre["edges_all"] if pre["edges_all"] else None,
                           "labelled_pruning_fraction": 1 - post["edges_explicit_labelled"] / pre["edges_explicit_labelled"] if pre["edges_explicit_labelled"] else None,
                           "TP_pruned": pre["TP"] - post["TP"], "FP_pruned": pre["FP"] - post["FP"],
                           "TP_pruning_fraction": 1 - post["TP"] / pre["TP"] if pre["TP"] else None,
                           "FP_pruning_fraction": 1 - post["FP"] / pre["FP"] if pre["FP"] else None}
    return {"arm": arm, "seed": seed, "stages": stages, "DPI_pruning": pruning,
            "validation": {stage: value.validation for stage, value in parsed.items()}}


def aggregate(results):
    identities = {(row["arm"], row["seed"]) for row in results}
    if (any(isinstance(row["seed"], bool) or not isinstance(row["seed"], int) for row in results)
            or len(identities) != len(results) or identities != {(arm, seed) for arm in ARMS for seed in (1, 2, 3)}):
        raise ValueError("Scoring requires all twelve matched arm/seed groups")
    fields = ("edges_all", "edges_explicit_labelled", "edges_unlabelled", "TP", "FP", "precision", "sensitivity", "specificity",
              "AUROC_fixed_explicit_universe_MI_ties", "average_precision_fixed_explicit_universe")
    medians = {arm: {stage: {key: float(np.median([row["stages"][stage][key] for row in results if row["arm"] == arm]))
                                    if all(row["stages"][stage][key] is not None for row in results if row["arm"] == arm) else None
                            for key in fields} for stage in STAGES} for arm in ARMS}
    lookup = {(row["arm"], row["seed"]): row for row in results}
    deltas = [lookup[("u80", seed)]["stages"]["nominal_post"]["average_precision_fixed_explicit_universe"] -
              lookup[("legacy", seed)]["stages"]["nominal_post"]["average_precision_fixed_explicit_universe"] for seed in (1, 2, 3)]
    prune_fields = ("global_pruning_fraction", "labelled_pruning_fraction", "TP_pruned", "FP_pruned", "TP_pruning_fraction", "FP_pruning_fraction")
    pruning = {arm: {prefix: {key: float(np.median([row["DPI_pruning"][prefix][key] for row in results if row["arm"] == arm]))
                              if all(row["DPI_pruning"][prefix][key] is not None for row in results if row["arm"] == arm) else None
                              for key in prune_fields} for prefix in ("nominal", "fixed")} for arm in ARMS}
    return {"status": "complete", "matched_seeds": 3, "gold_pairs": 152280, "gold_positives": 2066, "gold_negatives": 150214,
            "primary_endpoint": "u80 versus legacy nominal post-DPI average precision over fixed explicit gold labels",
            "primary_paired_AP_deltas": deltas, "primary_paired_AP_delta_median": float(np.median(deltas)),
            "primary_after_higher": sum(delta > 0 for delta in deltas), "primary_after_equal": sum(delta == 0 for delta in deltas),
            "primary_after_lower": sum(delta < 0 for delta in deltas), "medians": medians,
            "median_DPI_pruning": pruning,
            "limitations": ["Three exploratory computational resamples, not independent biological replicates or confidence intervals",
                            "Only explicitly labelled directed pairs scored; unlabelled predictions are not false positives",
                            "Undirected MI associations are evaluated against directed gold labels; this is not the official DREAM5 probability-density score",
                            "Stage/control analyses are supporting diagnostics, not evidence selected to guarantee improvement"]}


def score_run(run_root, out, *, data_root=None):
    # Reuse the frozen runner's read-only command/exit/artifact gates. Import is
    # deliberately local: the runner dynamically loads this validator itself.
    import run_benchmark as runner
    run_root, out = Path(run_root).resolve(strict=True), Path(out).resolve()
    if out.exists():
        raise FileExistsError("Scoring output must be fresh")
    plan = runner.verify_plan(run_root / "plan.json")
    runner.verify_smoke(plan)
    status = read_json(run_root / "status.json")
    if status.get("status") != "complete" or status.get("completed") != 60 or status.get("total") != 60 or status.get("failures"):
        raise ValueError("All sixty native jobs must be complete before cohort scoring")
    completed_identities = [(job.get("arm"), job.get("seed"), job.get("stage")) for job in status.get("jobs", [])]
    expected_identities = {(arm, seed, stage) for arm in ARMS for seed in (1, 2, 3) for stage in STAGES}
    if len(completed_identities) != 60 or set(completed_identities) != expected_identities:
        raise ValueError("Coordinator records do not identify exactly the sixty completed jobs")
    if verify_record(status["plan"]) != run_root / "plan.json":
        raise ValueError("Completed coordinator status refers to another plan")
    if plan.get("arms") != list(ARMS) or plan.get("seeds") != [1, 2, 3] or plan.get("stages") != list(STAGES):
        raise ValueError("Unexpected frozen Network3 pilot population")
    for value in plan["inputs"].values():
        if isinstance(value, dict) and {"path", "sha256", "bytes"} <= value.keys():
            verify_record(value)
    contents, source_provenance = prepare.load_originals(data_root=data_root)
    genes, _, tfs, counts = prepare.validate_bundle(contents, expected_counts=prepare.EXPECTED)
    gold = prepare.parse_gold(contents[prepare.GOLD].decode("utf-8"), genes, tfs)
    results, records = [], []
    for seed in plan["seeds"]:
        for arm in plan["arms"]:
            paths = {}
            for stage in STAGES:
                directory = run_root / "jobs" / arm / f"seed_{seed:03d}" / stage
                runner.checked_job(plan, arm, seed, stage)
                records.append(record(directory / "job.json"))
                paths[stage] = directory
            results.append(score_arm_stages(plan, arm, seed, paths, gold))
    summary = aggregate(results)
    out.mkdir(parents=True)
    payload = {"status": "complete", "summary": summary, "results": results,
               "provenance": {"plan": record(run_root / "plan.json"), "native_job_records": records,
                              "source_data": source_provenance, "metrics_script": record(__file__)}}
    (out / "metrics.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    lines = ["# DREAM5 Network 3 exploratory sampling pilot", "", "Primary endpoint: u80 versus legacy nominal post-DPI fixed-explicit-universe average precision.", "",
             "| Arm | TP | FP | Precision | Sensitivity | Specificity | AUROC | AP |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for arm in ARMS:
        m = summary["medians"][arm]["nominal_post"]
        lines.append(f"| {arm} | {m['TP']:.0f} | {m['FP']:.0f} | {m['precision'] if m['precision'] is not None else 'NA'} | {m['sensitivity']:.6f} | {m['specificity']:.6f} | {m['AUROC_fixed_explicit_universe_MI_ties']:.6f} | {m['average_precision_fixed_explicit_universe']:.6f} |")
    lines += ["", "Values are medians of three computational resamples. Paired primary AP deltas: " + str(summary["primary_paired_AP_deltas"]), "", *["- " + text for text in summary["limitations"]], ""]
    (out / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    scalar_rows = [{"arm": row["arm"], "seed": row["seed"], "stage": stage,
                    **{key: value for key, value in data.items() if isinstance(value, (int, float)) or value is None}}
                   for row in results for stage, data in row["stages"].items()]
    with (out / "per_seed_stage_metrics.tsv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(scalar_rows[0]), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(scalar_rows)
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    sub = commands.add_parser("score")
    sub.add_argument("--run-root", required=True, type=Path)
    sub.add_argument("--out", required=True, type=Path)
    sub.add_argument("--data-root", type=Path)
    args = parser.parse_args()
    payload = score_run(args.run_root, args.out, data_root=args.data_root)
    print(json.dumps({"status": payload["status"], "matched_seeds": 3, "out": str(args.out)}))


if __name__ == "__main__":
    main()
