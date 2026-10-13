#!/usr/bin/env python3
"""Supplementary frozen-universe ROC; do not change the Fig. 6a scorer.

Eligible assayed SIG sources x frozen inference genes, excluding self-pairs.
Emitted pairs rank by raw consensus MI (ties stay tied); omitted pairs form
one shared bottom-score group. No missing MI values are imputed or inferred.
The large omitted group is counted analytically, not materialized.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import sys

import numpy as np


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def record_path(value: str) -> Path:
    if os.name != "nt" and re.match(r"^[A-Za-z]:[/\\]", value):
        value = "/mnt/" + value[0].lower() + value[2:].replace("\\", "/")
    return Path(value).resolve(strict=True)


def rows(path: Path):
    with path.open(encoding="utf-8", newline="") as stream:
        yield from csv.DictReader(stream, delimiter="\t")


def unique(values, label: str) -> tuple[str, ...]:
    result = tuple(values)
    if not result or any(not x for x in result) or len(set(result)) != len(result):
        raise ValueError(f"Empty/duplicate identifiers in {label}")
    return result


@dataclass
class Universe:
    sources: tuple[str, ...]
    targets: tuple[str, ...]
    gene_ids: dict[str, int]
    positives: set[int]
    full_reference_count: int
    excluded_reference: dict[str, int]

    @property
    def size(self) -> int:
        return len(self.sources) * len(self.targets) - len(set(self.sources) & set(self.targets))

    def key(self, source: str, target: str) -> int:
        # Integer pairing avoids ambiguous hyphen-joined gene symbols.
        return self.gene_ids[source] * len(self.gene_ids) + self.gene_ids[target]


def make_universe(prepared_dir: Path) -> Universe:
    genes = list(rows(prepared_dir / "gene_selection.tsv"))
    raw = unique((row["gene"] for row in genes), "raw genes")
    targets = unique((row["gene"] for row in genes if row["used_for_network"] == "TRUE"), "targets")
    eligible = unique((row["source"] for row in rows(prepared_dir / "reference_eligible_sources.tsv")), "eligible sources")
    hubs = unique((prepared_dir / "hubs.txt").read_text(encoding="utf-8").splitlines(), "hubs")
    source_set = set(eligible) & set(hubs) & set(targets)
    sources = tuple(sorted(source_set))
    if not sources:
        raise ValueError("No eligible inference sources")
    if not set(hubs) <= set(targets):
        raise ValueError("Inference hubs absent from frozen targets")
    strict = {row["gene"] for row in genes if row["strict_SIG_reference_annotation"] == "TRUE"}
    if not set(eligible) <= strict:
        raise ValueError("Eligible source is not a strict SIG")
    ids = {gene: i for i, gene in enumerate(raw)}
    reference = set()
    excluded_keys = set()
    excluded = {"source_not_eligible_inference_hub": 0, "target_not_inference_gene": 0, "self_pair": 0}
    target_set = set(targets)
    for row in rows(prepared_dir / "reference_positive_edges.tsv"):
        source, target = row["source"], row["target"]
        if source not in ids or target not in ids:
            raise ValueError("Reference identifier absent from frozen gene panel")
        key = ids[source] * len(ids) + ids[target]
        if key in reference:
            raise ValueError("Duplicate reference pair")
        reference.add(key)
        reason = ("source_not_eligible_inference_hub" if source not in source_set else
                  "target_not_inference_gene" if target not in target_set else
                  "self_pair" if source == target else None)
        if reason:
            excluded[reason] += 1
            excluded_keys.add(key)
    full_count = len(reference)
    reference.difference_update(excluded_keys)
    universe = Universe(sources, targets, ids, reference, full_count, excluded)
    if not 0 < len(reference) < universe.size:
        raise ValueError("Fixed-universe ROC requires both positive and negative pairs")
    return universe


def group_scores(scores, labels) -> list[tuple[float, int, int]]:
    scores = np.asarray(scores, dtype=float)
    labels = np.asarray(labels, dtype=bool)
    if scores.ndim != 1 or labels.shape != scores.shape:
        raise ValueError("Scores and labels must be equal-length vectors")
    if np.any(~np.isfinite(scores)) or np.any(scores < 0):
        raise ValueError("Invalid emitted MI")
    if not len(scores):
        return []
    order = np.argsort(-scores, kind="stable")
    scores, labels = scores[order], labels[order]
    starts = np.r_[0, np.flatnonzero(np.diff(scores) != 0) + 1]
    sizes = np.diff(np.r_[starts, len(scores)])
    positives = np.add.reduceat(labels.astype(np.int64), starts)
    return [(float(scores[i]), int(p), int(n - p)) for i, p, n in zip(starts, positives, sizes)]


def fixed_roc(groups, total_positive: int, total_negative: int):
    if total_positive <= 0 or total_negative <= 0:
        raise ValueError("ROC requires both classes")
    if any(p < 0 or n < 0 or p + n == 0 for _, p, n in groups):
        raise ValueError("Invalid score-group counts")
    if any(groups[i][0] <= groups[i + 1][0] for i in range(len(groups) - 1)):
        raise ValueError("Emitted groups must have strictly decreasing distinct MI")
    emitted_p = sum(p for _, p, _ in groups)
    emitted_n = sum(n for _, _, n in groups)
    absent_p, absent_n = total_positive - emitted_p, total_negative - emitted_n
    if absent_p < 0 or absent_n < 0:
        raise ValueError("Emitted counts exceed fixed universe")
    curve = []

    def point(kind, mi, tp, fp):
        return {"threshold_kind": kind, "threshold_MI": mi, "selected_pairs": tp + fp,
                "TP": tp, "FP": fp, "FN": total_positive - tp, "TN": total_negative - fp,
                "sensitivity": tp / total_positive, "specificity": 1 - fp / total_negative,
                "FPR": fp / total_negative}

    curve.append(point("above_all", None, 0, 0))
    tp = fp = twice_w = negatives_before = 0
    for mi, p, n in groups:
        # Positive beats lower-scoring emitted negatives; MI ties get half credit.
        twice_w += 2 * p * (emitted_n - negatives_before - n) + p * n
        negatives_before += n
        tp += p
        fp += n
        curve.append(point("emitted_MI", mi, tp, fp))
    if absent_p + absent_n:
        curve.append(point("omitted_bottom", None, total_positive, total_negative))
    emitted_auc = twice_w / (2 * emitted_p * emitted_n) if emitted_p and emitted_n else None
    positive_coverage, negative_coverage = emitted_p / total_positive, emitted_n / total_negative
    selection_auc = .5 + .5 * (positive_coverage - negative_coverage)
    twice_w += 2 * emitted_p * absent_n + absent_p * absent_n
    auc = twice_w / (2 * total_positive * total_negative)
    integrated = math.fsum((left["sensitivity"] + right["sensitivity"]) *
                           (right["FPR"] - left["FPR"]) / 2
                           for left, right in zip(curve, curve[1:]))
    if not math.isclose(auc, integrated, abs_tol=1e-12):
        raise ValueError("Pairwise and integrated AUROC disagree")
    endpoint = point("all_emitted", None, emitted_p, emitted_n)
    return {"AUROC_fixed_universe_MI_ties": auc, "AUROC_ROC_integral_check": integrated,
            "diagnostic_AUROC_emitted_eligible_MI_ties": emitted_auc,
            "diagnostic_AUROC_selection_only": selection_auc,
            "diagnostic_MI_ranking_contribution": auc - selection_auc,
            "emitted_reference_positive": emitted_p, "emitted_reference_negative": emitted_n,
            "omitted_reference_positive": absent_p, "omitted_reference_negative": absent_n,
            "operating_point_all_emitted": endpoint}, curve


def topk_points(groups, total_positive: int, total_negative: int, ks):
    """Top-k expected TP under uniform ordering within a boundary MI tie.

    Also report attainable min/max TP. No arbitrary row-order tie breaking.
    Requested k above emitted eligible edges is unavailable, not padded.
    """
    emitted = sum(p + n for _, p, n in groups)
    result = []
    for k in ks:
        if k <= 0:
            raise ValueError("Top-k must be positive")
        if k > emitted:
            result.append({"k": k, "status": "exceeds_emitted_eligible_pairs"})
            continue
        before = tp_before = 0
        for mi, p, n in groups:
            if before + p + n >= k:
                take = k - before
                expected = tp_before + take * p / (p + n)
                low = tp_before + max(0, take - n)
                high = tp_before + min(take, p)
                fp = k - expected
                result.append({"k": k, "status": "complete", "TP_tie_expected": expected,
                               "TP_min": low, "TP_max": high, "FP_tie_expected": fp,
                               "precision_tie_expected": expected / k,
                               "sensitivity_tie_expected": expected / total_positive,
                               "specificity_tie_expected": 1 - fp / total_negative,
                               "FPR_tie_expected": fp / total_negative,
                               "boundary_MI": mi, "boundary_group_size": p + n,
                               "split_MI_tie": take < p + n})
                break
            before += p + n
            tp_before += p
    return result


def read_network(path: Path, universe: Universe, hubs):
    sources, targets = set(universe.sources), set(universe.targets)
    seen = set()
    scores, labels = [], []
    full_positive = 0
    for row in rows(path):
        source, target, mi = row["source"], row["target"], float(row["MI"])
        if source not in hubs or target not in targets or source == target:
            raise ValueError("Predicted pair outside frozen inference inputs or self-loop")
        if not math.isfinite(mi) or mi < 0:
            raise ValueError("Invalid network MI")
        key = universe.key(source, target)
        if key in seen:
            raise ValueError("Duplicate predicted pair")
        seen.add(key)
        positive = key in universe.positives
        full_positive += positive
        if source in sources:
            scores.append(mi)
            labels.append(positive)
    return group_scores(scores, labels), len(seen), full_positive


def write_tsv(path: Path, records):
    fields = list(dict.fromkeys(key for row in records for key in row))
    with path.open("x", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(records)


def calculate(args):
    if args.out.exists():
        raise FileExistsError("Refusing to overwrite fixed-universe output")
    prepared_dir = args.prepared_dir.resolve(strict=True)
    prepare_path = prepared_dir / "prepare_manifest.json"
    run_path = args.run_manifest.resolve(strict=True)
    run = json.loads(run_path.read_text(encoding="utf-8"))
    prepared = json.loads(prepare_path.read_text(encoding="utf-8"))
    if run.get("status") != "complete" or prepared.get("status") != "complete":
        raise ValueError("Preparation and native run must be complete")
    prepare_record = run["frozen"]["inputs"]["prepare_manifest"]
    if record_path(prepare_record["path"]) != prepare_path or digest(prepare_path) != prepare_record["sha256"]:
        raise ValueError("Preparation manifest differs from frozen native run")
    input_hashes = {str(run_path): digest(run_path), str(prepare_path): digest(prepare_path)}

    def verify(path: Path, expected: str):
        path = path.resolve(strict=True)
        value = digest(path)
        if value != expected:
            raise ValueError(f"Input hash mismatch: {path}")
        input_hashes[str(path)] = value

    for name in ("gene_selection.tsv", "reference_eligible_sources.tsv", "reference_positive_edges.tsv", "hubs.txt", "expression.exp"):
        verify(prepared_dir / name, prepared["outputs"][name]["sha256"])
    for key, name in (("expression", "expression.exp"), ("hubs", "hubs.txt")):
        record = run["frozen"]["inputs"][key]
        if record_path(record["path"]) != prepared_dir / name:
            raise ValueError("Run uses different frozen inference inputs")
        verify(prepared_dir / name, record["sha256"])
    universe = make_universe(prepared_dir)
    positive, negative = len(universe.positives), universe.size - len(universe.positives)
    expected = prepared["gene_panel"]
    if len(universe.targets) != expected["n_NT_nonzero_inference_genes"] or universe.full_reference_count != prepared["reference"]["n_positive_pairs"]:
        raise ValueError("Prepared counts differ from verified input files")
    hubs = set((prepared_dir / "hubs.txt").read_text(encoding="utf-8").splitlines())
    results, curves, topks = {}, {}, {}
    for name, job in run["consensus"].items():
        if job["status"] != "complete":
            raise ValueError("Incomplete consensus")
        net_record = job["artifacts"]["edges.tsv"]
        network = record_path(net_record["path"])
        verify(network, net_record["sha256"])
        author_dir = args.author_comparison_dir / f"score_pc{job['p']:.0e}"
        author_path = author_dir / "metrics.json"
        author = json.loads(author_path.read_text(encoding="utf-8"))
        input_hashes[str(author_path.resolve())] = digest(author_path)
        if author["input_sha256"]["network"] != net_record["sha256"] or author["input_sha256"]["run_manifest"] != input_hashes[str(run_path)]:
            raise ValueError("Author-style score is from a different native run")
        if author["input_sha256"]["reference"] != prepared["outputs"]["reference_positive_edges.tsv"]["sha256"]:
            raise ValueError("Author-style score is from a different reference")
        for filename, expected_hash in author["output_sha256"].items():
            verify(author_dir / filename, expected_hash)
        groups, full_edges, full_positive = read_network(network, universe, hubs)
        if full_edges != author["reported_edges"] or full_positive != author["reference_positive_reported_edges"]:
            raise ValueError("Predicted counts disagree with preserved author score")
        score, curves[name] = fixed_roc(groups, positive, negative)
        topks[name] = topk_points(groups, positive, negative, args.top_k)
        results[name] = {"consensus_p": job["p"], "full_emitted_network_edges": full_edges,
                         "emitted_eligible_pairs": sum(p + n for _, p, n in groups),
                         "excluded_unassayed_source_predictions": full_edges - sum(p + n for _, p, n in groups),
                         "distinct_emitted_MI_groups": len(groups),
                         "preserved_AUROC_within_emitted_edges_author_ordinal": author["AUROC"], **score}
    if not results:
        raise ValueError("No completed consensus networks")
    if any(digest(Path(path)) != value for path, value in input_hashes.items()):
        raise ValueError("Frozen inputs changed during scoring")
    universe_record = {"sources": list(universe.sources), "targets": list(universe.targets),
                       "n_sources": len(universe.sources), "n_targets": len(universe.targets),
                       "self_pairs_excluded": len(set(universe.sources) & set(universe.targets)),
                       "candidate_pairs": universe.size, "reference_positive_pairs": positive,
                       "reference_negative_pairs": negative, "positive_prevalence": positive / universe.size,
                       "full_prepared_reference_positive_pairs": universe.full_reference_count,
                       "excluded_reference_pairs": universe.excluded_reference}
    canonical = json.dumps(universe_record, sort_keys=True, separators=(",", ":")).encode()
    universe_record["definition_sha256"] = hashlib.sha256(canonical).hexdigest()
    report = ["# Supplementary fixed-universe THP-1 ROC", "",
              "This is the completed reconstructed legacy baseline, not a sampling-change comparison or exact Fig. 6a reproduction.", "",
              f"Universe: {len(universe.sources):,} eligible assayed strict-SIG inference sources x {len(universe.targets):,} frozen NT inference targets, excluding self-pairs.",
              f"Fixed totals: {universe.size:,} candidate pairs; {positive:,} reference-positive; {negative:,} operational reference-negative.", "",
              "Emitted pairs rank by consensus MI; equal MI stays tied. Every omitted pair has one shared bottom score, below every emitted pair, including emitted MI=0. This is an evaluation policy, not estimated missing MI.",
              "Sensitivity=TP/fixed positives; specificity=TN/fixed negatives. ROC uses whole tied groups and includes the omitted group. AUROC is checked independently by positive-negative pair counting.", "",
              "| Consensus p | Eligible emitted pairs | TP | FP | Sensitivity | Specificity | Fixed-universe AUROC | Preserved emitted-edge ordinal AUROC |",
              "|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for score in results.values():
        point = score["operating_point_all_emitted"]
        report.append(f"| {score['consensus_p']:g} | {score['emitted_eligible_pairs']:,} | {point['TP']:,} | {point['FP']:,} | {point['sensitivity']:.6f} | {point['specificity']:.6f} | {score['AUROC_fixed_universe_MI_ties']:.6f} | {score['preserved_AUROC_within_emitted_edges_author_ordinal']:.6f} |")
    report.extend(["", "The two AUROC columns differ in population AND tie handling. They are different estimands, not a corrected version of the same metric.",
                   "The fixed-universe AUROC measures thresholded-network selection plus ranking. A large unscored/omitted tied group limits resolution; it is not unthresholded all-pair MI AUROC.",
                   "Reference positives represent perturbation responses, not proven direct edges; nonmembers are operational negatives, not verified biological negatives.",
                   "Top-k is ranked within the eligible-source universe, not the full author-style SIG network. Tied boundaries report expected TP plus its min/max range. Top-k above eligible emitted counts is unavailable, not padded with arbitrary missing pairs.",
                   "Do not select labels, source filters or thresholds to match the publication. Preserve this exact universe/reference across any future matched sampling comparison.", ""])
    args.out.mkdir(parents=True, exist_ok=False)
    for name in results:
        write_tsv(args.out / f"{name}_roc.tsv", curves[name])
        write_tsv(args.out / f"{name}_topk.tsv", topks[name])
    (args.out / "REPORT.md").write_text("\n".join(report), encoding="utf-8")
    (args.out / "universe.json").write_text(json.dumps(universe_record, indent=2) + "\n", encoding="utf-8")
    result = {"status": "complete", "scope": "supplementary_reconstructed_legacy_fixed_universe",
              "definitions": {"universe": "eligible strict-SIG sources intersect inference hubs/genes x frozen inference genes; exclude self-pairs",
                              "scores": "emitted consensus MI with ties; all omitted pairs tied below every emitted pair",
                              "negatives": "reference nonmembers, not established biological negatives",
                              "topk": "eligible-source ranking; expected fractional TP plus range for split MI ties"},
              "universe": universe_record, "scores": results, "input_sha256": input_hashes,
              "script_sha256": digest(Path(__file__)), "Python": sys.version,
              "platform": platform.platform(), "numpy": np.__version__,
              "output_sha256": {path.name: digest(path) for path in args.out.iterdir()}}
    if any(digest(Path(path)) != value for path, value in input_hashes.items()):
        raise ValueError("Frozen inputs changed while writing supplementary scores")
    with (args.out / "metrics.json").open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return result


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    for name in ("prepared-dir", "run-manifest", "author-comparison-dir", "out"):
        result.add_argument("--" + name, type=Path, required=True)
    result.add_argument("--top-k", type=int, nargs="+", default=[1000, 5000, 10000, 50000, 100000])
    return result


if __name__ == "__main__":
    completed = calculate(parser().parse_args())
    print(json.dumps({"status": completed["status"], "universe": completed["universe"]["candidate_pairs"],
                      "AUROCs": {name: value["AUROC_fixed_universe_MI_ties"] for name, value in completed["scores"].items()}}))
