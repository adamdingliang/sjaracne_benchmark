#!/usr/bin/env python3
"""Opt-in, public-data THP-1 PR70 sampling pilot; not an exact Fig. 6a reproduction."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np

import metrics


PRE_COMMIT = "e59973a1891672a14f06d7847545c53368f3066c"
PR70_COMMIT = "8c5f26c4fb5e05c7b280bcaa7d5a6461125a6aa3"
FORK_DEVELOP = "1638e8f4eb3d7ffe5057922fa9f9bd1043d466ac"
PINNED_BINARY_SHA256 = "8264118ea83b8c37b16000ce0c36087e3fe03a28cb1687eba5329370abb8c33e"
PINNED_PRE_BINARY_SHA256 = "eda4f07465160f9d2d536715023d439b36628b1e094dab8b7afed511efa24e11"
ARMS = ("legacy", "without_replacement_80pct")
STAGES = ("all_mi", "cutoff_raw", "final")


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def save_json(path: Path, data) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")


def wsl_path(path: Path) -> str:
    absolute = path.resolve()
    if os.name != "nt":
        return str(absolute)
    drive = absolute.drive
    if len(drive) != 2 or drive[1] != ":":
        raise ValueError("WSL execution requires a drive-letter path, not a UNC path")
    return "/mnt/" + drive[0].lower() + absolute.as_posix()[2:]


def affine_cutoff(config: Path, observations: int, nominal_p: float) -> float:
    """Freeze the legacy affine threshold at the NEW arm's m, before scoring."""
    rows = [line for line in (config / "config_threshold.txt").read_text().splitlines()
            if line.strip() and not line.startswith(">")]
    alpha, beta, gamma = map(float, rows[0].split())
    value = (alpha - math.log(nominal_p)) / (-beta - gamma * observations)
    if not math.isfinite(value) or value <= 0:
        raise ValueError("Invalid affine MI cutoff")
    return value


def prepared_input(out: Path) -> dict:
    path = out / "prepare_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    required = ("expression.exp", "hubs.txt", "reference.tsv")
    for name in required:
        if not (out / name).is_file():
            raise FileNotFoundError(out / name)
    return manifest


def expression_dimensions(path: Path) -> tuple[int, int]:
    with path.open(encoding="utf-8") as stream:
        header = stream.readline().rstrip("\r\n").split("\t")
        if header[:2] != ["isoformId", "geneSymbol"]:
            raise ValueError("Invalid SJARACNe expression header")
        n = len(header) - 2
        genes = sum(1 for line in stream if line.strip())
    if n < 2 or genes < 2:
        raise ValueError("At least two observations and genes are required")
    return n, genes


def native_header(path: Path) -> dict:
    result = {}
    with path.open(encoding="utf-8") as stream:
        for line in stream:
            if not line.startswith(">"):
                break
            text = line[1:].strip()
            for key in ("MI threshold", "DPI tolerance", "Sampling method", "Sampling request",
                        "Eligible observations", "Sampled observations", "Resample draws"):
                if text.startswith(key):
                    result[key] = text[len(key):].strip()
    return result


def run(args) -> dict:
    out = args.out.resolve()
    prepared_input(out)
    if not args.binary.is_file() or not args.config.is_dir():
        raise FileNotFoundError("Supply an existing PR70-only --binary and --config")
    binary_hash = digest(args.binary)
    if binary_hash != PINNED_BINARY_SHA256 and not args.allow_unpinned_binary:
        raise ValueError("Binary SHA256 is not the verified PR70 build. Rebuild/pin explicitly, "
                         "or use --allow-unpinned-binary with known PR70-only code.")
    pre_binary = getattr(args, "pre_binary", None)
    pre_binary_hash = digest(pre_binary) if pre_binary is not None else None
    if pre_binary_hash is not None and pre_binary_hash != PINNED_PRE_BINARY_SHA256:
        raise ValueError("Before binary does not match the verified pre-PR70 build")
    n, genes = expression_dimensions(out / "expression.exp")
    m = math.ceil(0.8 * n)
    threshold = (args.mi_cutoff if args.mi_cutoff is not None else
                 affine_cutoff(args.config, m, args.anchor_p))
    runs = out / "runs"
    runs.mkdir(exist_ok=False)
    manifest_path = out / "run_manifest.json"
    if manifest_path.exists():
        raise FileExistsError(manifest_path)
    path_arg = wsl_path if args.wsl_distro else lambda path: str(path.resolve())
    prefix = (["wsl.exe", "--distribution", args.wsl_distro, "--exec"]
              if args.wsl_distro else [])
    immutable_hashes = {name: digest(out / name) for name in
                        ("expression.exp", "hubs.txt", "reference.tsv", "prepare_manifest.json")}
    config_hashes = {name: digest(args.config / name) for name in
                     ("config_kernel.txt", "config_threshold.txt")}
    manifest = {
        "status": "running", "benchmark_kind": "single-cell per-seed pilot, no consensus",
        "pre_pr70_commit": PRE_COMMIT,
        "pr70_source_commit": PR70_COMMIT if binary_hash == PINNED_BINARY_SHA256 else None,
        "fork_develop_verified": FORK_DEVELOP,
        "runtime_same_as_fork_develop": True if binary_hash == PINNED_BINARY_SHA256 else None,
        "binary": str(args.binary.resolve()), "binary_sha256": binary_hash,
        "binary_pin_verified": binary_hash == PINNED_BINARY_SHA256,
        "legacy_binary": str(pre_binary.resolve()) if pre_binary is not None else str(args.binary.resolve()),
        "legacy_binary_sha256": pre_binary_hash or binary_hash,
        "legacy_execution": "verified pre-PR70 binary" if pre_binary is not None else "unchanged PR70 -r 1 compatibility path",
        "config": str(args.config.resolve()), "config_sha256": config_hashes,
        "input_sha256": immutable_hashes,
        "implementation_sha256": {"benchmark.py": digest(Path(__file__)),
                                  "metrics.py": digest(Path(metrics.__file__))},
        "genes": genes, "nt_cells": n,
        "new_arm_draws": m, "legacy_arm_draws": n,
        "arms": list(ARMS), "seeds": args.seeds, "stages": list(STAGES),
        "common_mi_cutoff": threshold, "cutoff_anchor_nominal_p": args.anchor_p,
        "cutoff_anchor_m": m, "npar": args.npar,
        "final_dpi_epsilon": 0, "wsl_distro": args.wsl_distro,
        "scope": "Operational before/after includes draw count and native tie-noise differences. "
                 "Same seed numbers are NOT identical samples or identical tie-noise streams. "
                 "The nominal affine p is not an estimator-matched calibrated p-value.",
        "jobs": [],
    }
    # A checkpoint is deliberately written before native inference, so an interrupted
    # run remains identifiable. Only this run's own checkpoint is updated below.
    save_json(manifest_path, manifest)

    def run_job(arm: str, seed: int, stage: str) -> dict:
        target = runs / f"{arm}_seed{seed}_{stage}.adj"
        log = target.with_suffix(".log")
        threshold_args = ["-p", "1", "-t", "0" if stage == "all_mi" else repr(threshold),
                          "-e", "0" if stage == "final" else "1"]
        sampler = ["-r", "1"] if arm == "legacy" else ["-u", "80%"]
        selected_binary = pre_binary if arm == "legacy" and pre_binary is not None else args.binary
        command = prefix + [path_arg(selected_binary), "-i", path_arg(out / "expression.exp"),
                            "-l", path_arg(out / "hubs.txt"), "-s", path_arg(out / "hubs.txt"),
                            "-H", path_arg(args.config), "-N", str(args.npar), "-S", str(seed),
                            *threshold_args, *sampler, "-o", path_arg(target)]
        started = time.perf_counter()
        with log.open("x", encoding="utf-8") as stream:
            completed = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
        elapsed = time.perf_counter() - started
        if completed.returncode or not target.is_file():
            raise RuntimeError(f"Native inference failed ({completed.returncode}); see {log}")
        header = native_header(target)
        if "Eligible observations" in header and int(header["Eligible observations"]) != n:
            raise ValueError("Native eligible population disagrees with prepared input")
        draw_key = "Resample draws" if arm == "legacy" else "Sampled observations"
        if draw_key in header and int(header[draw_key]) != (n if arm == "legacy" else m):
            raise ValueError("Native draw count disagrees with the matched design")
        print(f"{arm} seed={seed} {stage}: {elapsed:.1f}s", flush=True)
        return {"arm": arm, "seed": seed, "stage": stage, "seconds": elapsed,
                "command": command, "adjacency_sha256": digest(target), "header": header}

    jobs = [(arm, seed, stage) for seed in args.seeds for arm in ARMS for stage in STAGES]
    try:
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(run_job, *job) for job in jobs]
            for future in as_completed(futures):
                manifest["jobs"].append(future.result())
        for name, expected in immutable_hashes.items():
            if digest(out / name) != expected:
                raise ValueError(f"Prepared input changed during inference: {name}")
        if digest(args.binary) != binary_hash or (pre_binary is not None and digest(pre_binary) != pre_binary_hash):
            raise ValueError("Native binary changed during inference")
        for name, expected in config_hashes.items():
            if digest(args.config / name) != expected:
                raise ValueError(f"Configuration changed during inference: {name}")
        manifest["status"] = "complete"
    except Exception as error:
        manifest["status"] = "failed"
        manifest["error"] = str(error)
        raise
    finally:
        manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return manifest


def load_reference(path: Path) -> dict:
    labels = {}
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream, delimiter="\t")
        if not {"source", "target", "logFC", "label"} <= set(reader.fieldnames or []):
            raise ValueError("Reference needs source, target, logFC, label columns")
        for row in reader:
            pair = (row["source"], row["target"])
            if pair in labels or pair[0] == pair[1] or not all(pair):
                raise ValueError(f"Duplicate, self, or empty reference pair: {pair}")
            if row["label"] not in ("0", "1") or not math.isfinite(float(row["logFC"])):
                raise ValueError("Invalid reference label/effect")
            labels[pair] = row["label"] == "1"
    if not labels or not 0 < sum(labels.values()) < len(labels):
        raise ValueError("Reference must contain both positive and negative pairs")
    return labels


def median_values(rows: list[dict], key: str):
    values = [row[key] for row in rows if row.get(key) is not None]
    return statistics.median(values) if values else None


def score(args) -> dict:
    out = args.out.resolve()
    prepared_input(out)
    run_manifest = json.loads((out / "run_manifest.json").read_text())
    if run_manifest["status"] != "complete":
        raise ValueError("Only complete inference runs can be scored")
    for name, expected in run_manifest["input_sha256"].items():
        if digest(out / name) != expected:
            raise ValueError(f"Frozen input hash mismatch: {name}")
    expected_jobs = {(arm, seed, stage) for arm in ARMS for seed in run_manifest["seeds"] for stage in STAGES}
    found_jobs = set()
    for job in run_manifest["jobs"]:
        key = (job["arm"], job["seed"], job["stage"])
        if key in found_jobs or key not in expected_jobs:
            raise ValueError("Duplicate or unexpected inference job in manifest")
        found_jobs.add(key)
        path = out / "runs" / f"{job['arm']}_seed{job['seed']}_{job['stage']}.adj"
        if digest(path) != job["adjacency_sha256"]:
            raise ValueError(f"Frozen adjacency hash mismatch: {path.name}")
    if found_jobs != expected_jobs:
        raise ValueError("Missing inference job in manifest")
    labels = load_reference(out / "reference.tsv")
    rows = []
    curves = {}
    for seed in run_manifest["seeds"]:
        for arm in ARMS:
            networks = {stage: metrics.adjacency(out / "runs" / f"{arm}_seed{seed}_{stage}.adj")
                        for stage in STAGES}
            for smaller, larger in (("cutoff_raw", "all_mi"), ("final", "cutoff_raw")):
                if any(networks[larger].get(pair) != mi for pair, mi in networks[smaller].items()):
                    raise ValueError(f"{smaller} output is not an MI-preserving subset of {larger}")
            for stage, edges in networks.items():
                if not set(edges) <= labels.keys():
                    raise ValueError("Output contains a source/target outside the frozen candidate universe")
                evaluated = metrics.evaluate(edges, labels)
                common, reported = evaluated["all_candidates"], evaluated["reported_only"]
                row = {"arm": arm, "seed": seed, "stage": stage, **evaluated,
                       "reported_edges": common["reported_pairs"], "tp": common["tp"],
                       "precision": common["precision"], "sensitivity": common["sensitivity"],
                       "specificity": common["specificity"],
                       "auroc_reported": reported["auroc"], "auroc_common": common["auroc"]}
                if stage == "final":
                    row["pre_dpi_edges"] = len(networks["cutoff_raw"])
                    row["dpi_pruning_fraction"] = (1 - len(edges) / len(networks["cutoff_raw"])
                                                   if networks["cutoff_raw"] else None)
                rows.append(row)
                pairs = sorted(edges, key=lambda pair: (-edges[pair], pair))
                scores = [edges[pair] for pair in pairs]
                truth = [labels[pair] for pair in pairs]
                k_values = (sorted(set(k for k in args.top_k if k <= len(pairs)) |
                                   set(range(1000, len(pairs) + 1, 1000)) | {len(pairs)})
                            if pairs else [])
                curves[(arm, seed, stage)] = metrics.ranked_curve(scores, truth, k_values, random_seed=1)
    result = {
        "scoring_implementation_sha256": {"benchmark.py": digest(Path(__file__)),
                                          "metrics.py": digest(Path(metrics.__file__))},
        "design": run_manifest,
        "reference": {"candidate_pairs": len(labels), "positive_pairs": sum(labels.values()),
                      "negative_pairs": len(labels) - sum(labels.values()),
                      "positive_definition": "abs(reconstructed mean log2(CPM+1) KD-minus-NT)>0.25",
                      "negative_meaning": "Does not meet reference response cutoff; not proven non-regulation"},
        "per_seed": rows,
        "requested_top_k": args.top_k,
        "definitions": {
            "reported_only": "Fig6a-style conditional universe: only emitted edges, ranked by MI",
            "common_universe": "ALL frozen assayed-source/selected-target nonself pairs; absent edges score0",
            "epr_shuffle": "One seed1 permutation of each emitted edge list; undefined denominator->null",
            "epr_expected": "Precision@k divided by exact expected random precision within emitted list",
            "auroc": "MI-score ROC with ties grouped/half credit; not arbitrary ordinal tie-breaking",
            "consensus": "None in this small per-seed pilot; no K-edge or consensus-p changes",
        },
    }
    save_json(out / "metrics.json", result)
    write_report(out, result, curves)
    draw_plots(out, result, curves, labels)
    return result


def display(value, digits=4):
    if value is None:
        return "n.a."
    return str(value) if isinstance(value, int) else f"{value:.{digits}f}"


def write_report(out: Path, result: dict, curves: dict) -> None:
    lines = ["# THP-1 sampling pilot", "",
             "This is a matched public-data sampling benchmark, not an exact scMINER Fig. 6a reproduction.",
             "Single cells (no SuperCell), reduced NT-variance-selected gene panel, assayed eligible SIG hubs, "
             "and per-seed subnetworks (no consensus) are deliberate pilot limitations.", "",
             "Both arms use identical expression/reference inputs, hub panel, numeric MI cutoff and DPI tolerance. "
             "Legacy is N-draw bootstrap; PR70 is ceil(0.8*N) distinct cells. Seeds index paired operational runs, "
             "not identical sample sets or tie-noise realizations.", "",
             f"Common MI cutoff: `{result['design']['common_mi_cutoff']:.12g}`. "
             f"NT cells: {result['design']['nt_cells']}; genes: {result['design']['genes']}. "
             f"Seeds: {result['design']['seeds']}.", "",
             f"Frozen reference positives: {result['reference']['positive_pairs']:,} of "
             f"{result['reference']['candidate_pairs']:,} candidate pairs "
             f"({result['reference']['positive_pairs'] / result['reference']['candidate_pairs']:.2%}). "
             "This reference prevalence is not the prevalence in the published inferred-edge pool.", "",
             "## Median per-seed final-network results", "",
             "| Metric | Before: legacy bootstrap | After: without replacement 80% |", "|---|---:|---:|"]
    # evaluate() returns these scalar keys; report both denominators rather than concealing pool changes.
    keys = [("Reported edges", "reported_edges"), ("Reported reference positives", "tp"),
            ("Precision, reported edges", "precision"), ("Sensitivity, common universe", "sensitivity"),
            ("Specificity, common universe", "specificity"),
            ("AUROC, reported-edge MI", "auroc_reported"),
            ("AUROC, common-universe final MI", "auroc_common"),
            ("Pre-DPI threshold-passing edges", "pre_dpi_edges"),
            ("DPI pruning fraction", "dpi_pruning_fraction")]
    final_rows = {arm: [row for row in result["per_seed"] if row["arm"] == arm and row["stage"] == "final"]
                  for arm in ARMS}
    for label, key in keys:
        values = [display(median_values(final_rows[arm], key)) for arm in ARMS]
        lines.append(f"| {label} | {' | '.join(values)} |")
    raw_rows = {arm: [row for row in result["per_seed"] if row["arm"] == arm and row["stage"] == "all_mi"]
                for arm in ARMS}
    for label, key in (("AUROC, unthresholded pre-DPI MI", "auroc"),
                       ("Average precision, unthresholded pre-DPI MI", "average_precision")):
        vals = [display(statistics.median(row["all_candidates"][key] for row in raw_rows[arm])) for arm in ARMS]
        lines.append(f"| {label} | {' | '.join(vals)} |")
    lines += ["", "## Top-ranked final edges", "",
              "TP@k is cumulative. EPR below uses the within-emitted-list expected random precision. "
              "The single-shuffle author-style EPR is also saved, but can be noisy/undefined at small k.", "",
              "| k | Before TP | After TP | Before EPR (within pool) | After EPR (within pool) | Before EPR (common baseline) | After EPR (common baseline) |", "|---:|---:|---:|---:|---:|---:|---:|"]
    common_k = set.intersection(*(set(curves[(arm, seed, "final")]["k"])
                                  for arm in ARMS for seed in result["design"]["seeds"]))
    common_k &= set(result["requested_top_k"])
    for k in sorted(common_k):
        values = []
        for key in ("tp", "epr_expected"):
            for arm in ARMS:
                vals = []
                for seed in result["design"]["seeds"]:
                    curve = curves[(arm, seed, "final")]
                    value = curve[key][curve["k"].index(k)]
                    if value is not None:
                        vals.append(value)
                values.append(display(statistics.median(vals)) if vals else "n.a.")
        prevalence = result["reference"]["positive_pairs"] / result["reference"]["candidate_pairs"]
        for arm in ARMS:
            vals = []
            for seed in result["design"]["seeds"]:
                curve = curves[(arm, seed, "final")]
                vals.append(curve["precision"][curve["k"].index(k)] / prevalence)
            values.append(display(statistics.median(vals)))
        lines.append(f"| {k} | {' | '.join(values)} |")
    lines += ["", "## Limits on interpretation", "",
              "Three paired seeds are exploratory, not statistical confirmation across datasets. "
              "A favorable result cannot establish direct regulatory-edge correctness or a pure replacement-only effect. "
              "A common numeric cutoff avoids an affine-cutoff confound, but draw size and native tie noise change too.",
              "Reported-only EPR/ROC have different edge pools in the two arms. Consult common-universe ROC and "
              "unthresholded pre-DPI MI before attributing a change to ranking quality. No cutoffs were tuned to these labels.",
              "", "Sources: GSM6858449; scMINER analysis commit c39f0aaffc22be81ae425adf9e7617504ae9ee33; "
              f"fork runtime {PR70_COMMIT} / develop {FORK_DEVELOP}. Full hashes and commands are in the JSON manifests.", ""]
    with (out / "REPORT.md").open("x", encoding="utf-8") as stream:
        stream.write("\n".join(lines))
    serial_curves = [{"arm": arm, "seed": seed, "stage": stage, **curve}
                     for (arm, seed, stage), curve in curves.items()]
    save_json(out / "ranked_curves.json", serial_curves)


def draw_plots(out: Path, result: dict, curves: dict, labels: dict) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    colors = {ARMS[0]: "#3569A8", ARMS[1]: "#CC5538"}
    names = {ARMS[0]: "Before: legacy", ARMS[1]: "After: 80% distinct"}
    for universe in ("reported", "common"):
        fig, axes = plt.subplots(1, 3, figsize=(15, 4.6), constrained_layout=True)
        for arm in ARMS:
            for index, seed in enumerate(result["design"]["seeds"]):
                path = out / "runs" / f"{arm}_seed{seed}_final.adj"
                edges = metrics.adjacency(path)
                curve = curves[(arm, seed, "final")]
                label = names[arm] if index == 0 else None
                axes[0].plot(curve["k"], curve["tp"], color=colors[arm], alpha=.65, label=label)
                if universe == "reported":
                    epr = curve["epr_expected"]
                    scores, truth = zip(*[(edges[pair], labels[pair]) for pair in sorted(edges)]) if edges else ([], [])
                else:
                    prevalence = sum(labels.values()) / len(labels)
                    epr = [precision / prevalence for precision in curve["precision"]]
                    scores = [edges.get(pair, 0.0) for pair in labels]
                    truth = list(labels.values())
                axes[1].plot(curve["k"], epr, color=colors[arm], alpha=.65, label=label)
                roc = metrics.roc_curve(scores, truth)
                if all(value is not None for value in roc["fpr"] + roc["tpr"]):
                    axes[2].plot(roc["fpr"], roc["tpr"], color=colors[arm], alpha=.65, label=label)
        axes[0].set(xlabel="Top-ranked reported edges (k)", ylabel="Reference positives (TP@k)")
        axes[1].set(xlabel="Top-ranked reported edges (k)", ylabel="Early precision ratio")
        axes[1].axhline(1, color="gray", linestyle="--", linewidth=1)
        axes[2].set(xlabel="1 − specificity (FPR)", ylabel="Sensitivity (TPR)", xlim=(0, 1), ylim=(0, 1))
        axes[2].plot([0, 1], [0, 1], color="gray", linestyle="--", linewidth=1)
        for axis in axes:
            axis.legend(fontsize=8)
            axis.spines[["top", "right"]].set_visible(False)
        fig.suptitle("THP-1 per-seed sampling pilot — " +
                     ("reported-edge pool / within-pool random expectation" if universe == "reported" else
                      "common candidate universe / common random expectation"), fontsize=11)
        fig.savefig(out / f"tp_epr_roc_{universe}.png", dpi=160)
        plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "score"))
    parser.add_argument("--out", type=Path, required=True, help="Fresh prepared input/output directory")
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--pre-binary", type=Path, help="Optional verified pre-PR70 executable for the before arm")
    parser.add_argument("--config", type=Path)
    parser.add_argument("--wsl-distro", help="Run a Linux binary via WSL from Windows, e.g. Ubuntu")
    parser.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3])
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--npar", type=int, default=40)
    parser.add_argument("--anchor-p", type=float, default=1e-7,
                        help="Freeze affine threshold at m=ceil(.8*N); NOT a calibrated p-value")
    parser.add_argument("--mi-cutoff", type=float, help="Override frozen numeric threshold BEFORE inference")
    parser.add_argument("--allow-unpinned-binary", action="store_true")
    parser.add_argument("--top-k", type=int, nargs="+", default=[100, 1000, 5000, 10000, 20000, 50000, 100000])
    args = parser.parse_args()
    if args.action == "run" and (args.binary is None or args.config is None):
        parser.error("run requires --binary and --config")
    if not args.seeds or len(set(args.seeds)) != len(args.seeds) or any(seed < 0 for seed in args.seeds):
        parser.error("seeds must be unique nonnegative integers")
    if args.workers < 1 or args.npar < 1 or not 0 < args.anchor_p <= 1:
        parser.error("invalid workers, npar or nominal cutoff anchor")
    if args.mi_cutoff is not None and (not math.isfinite(args.mi_cutoff) or args.mi_cutoff <= 0):
        parser.error("mi-cutoff must be finite and positive")
    if not args.top_k or any(k <= 0 for k in args.top_k):
        parser.error("top-k values must be positive")
    result = run(args) if args.action == "run" else score(args)
    print(f"{args.action} complete: {args.out}", flush=True)


if __name__ == "__main__":
    main()
