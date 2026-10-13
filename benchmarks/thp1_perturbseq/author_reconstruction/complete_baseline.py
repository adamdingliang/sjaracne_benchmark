#!/usr/bin/env python3
"""Wait for a frozen 100-bootstrap legacy run, score it, and write its comparison.

Does not launch or retry native inference and does not run a PR70 after arm.
Existing output directories are never adopted or overwritten.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import time

import run_legacy as legacy


KS = (1000, 5000, 10000, 50000, 100000)
PC = (0.01, 0.001)
SCORE_OUTPUTS = ("ranked_curves.tsv", "comparison_to_publication.tsv", "roc_curves.tsv",
                 "MI_ranked_edges.tsv", "comparison_to_fig6a.png")


def read_json(path: Path) -> dict:
    with path.open(encoding="utf-8") as stream:
        result = json.load(stream, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    if not isinstance(result, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return result


def local_path(value: str) -> Path:
    if os.name != "nt" and re.match(r"^[A-Za-z]:[/\\]", value):
        value = value.replace("\\", "/")
        value = "/mnt/" + value[0].lower() + value[2:]
    return Path(value).resolve()


def linux_argument(value: str | None) -> str | None:
    if value is None:
        return None
    if re.match(r"^[A-Za-z]:[/\\]", value):
        value = (legacy.wsl_path(Path(value)) if os.name == "nt" else str(local_path(value)))
    if not PurePosixPath(value).is_absolute() or "\\" in value:
        raise ValueError("WSL environment, library and micromamba require absolute Linux or drive-letter paths")
    return value


def check_record(record: dict, expected: Path | None = None) -> None:
    path = local_path(record["path"])
    if expected is not None and path != expected.resolve():
        raise ValueError(f"Frozen path mismatch: {path} != {expected}")
    if legacy.digest(path) != record["sha256"]:
        raise ValueError(f"Artifact hash mismatch: {path}")


def freeze_context(args) -> tuple[dict, dict, dict]:
    prepared_path = args.prepared_dir / "prepare_manifest.json"
    prepared = read_json(prepared_path)
    audit = read_json(args.audit_file)
    publication = read_json(args.publication_dir / "manifest.json")
    if prepared.get("status") != "complete":
        raise ValueError("Preparation is not complete")
    if audit.get("status") != "pass" or audit.get("prepare_manifest_sha256") != legacy.digest(prepared_path):
        raise ValueError("Independent preparation audit is not PASS and bound to this preparation")
    for filename in ("expression.exp", "hubs.txt", "reference_positive_edges.tsv"):
        expected = prepared.get("outputs", {}).get(filename, {}).get("sha256")
        if expected != legacy.digest(args.prepared_dir / filename):
            raise ValueError(f"Prepared artifact mismatch: {filename}")
        audited = audit.get("prepared_files_sha256", {}).get(filename)
        if audited != expected:
            raise ValueError(f"Audit does not bind prepared artifact: {filename}")
    if publication.get("full_ROC_available") is not False:
        raise ValueError("Expected the declared partial publication ROC, not a substituted full curve")
    if publication.get("published_AUROC_rounded") != 0.75:
        raise ValueError("Publication rounded AUROC provenance differs from the declared paper value")
    paths = {"preparation_manifest": prepared_path, "audit": args.audit_file,
             "publication_manifest": args.publication_dir / "manifest.json",
             "scorer": Path(__file__).with_name("score_author.R")}
    paths.update({filename: args.prepared_dir / filename
                  for filename in ("expression.exp", "hubs.txt", "reference_positive_edges.tsv")})
    for filename in ("tp.tsv", "epr.tsv", "roc_segment.tsv"):
        path = args.publication_dir / filename
        if publication.get("outputs_sha256", {}).get(filename) != legacy.digest(path):
            raise ValueError(f"Publication artifact hash mismatch: {filename}")
        paths["publication_" + filename] = path
    frozen = {"inputs": {name: legacy.record_file(path) for name, path in paths.items()},
              "helper_sha256": legacy.digest(Path(__file__)),
              "execution": {"wsl_r_env": args.wsl_r_env, "wsl_r_library": args.wsl_r_library,
                            "wsl_micromamba": args.wsl_micromamba, "wsl_distro": args.wsl_distro},
              "scope": "legacy reconstruction only; no PR70 after arm"}
    return frozen, prepared, publication


def verify_context(frozen: dict) -> None:
    for record in frozen["inputs"].values():
        check_record(record)
    if legacy.digest(Path(__file__)) != frozen["helper_sha256"]:
        raise ValueError("Completion helper changed during execution")


def failed_run(run: dict) -> bool:
    return run.get("status") in ("failed", "error") or any(
        row.get("status") == "failed" for collection in ("bootstraps", "consensus")
        for row in run.get(collection, {}).values())


def await_run(args, frozen: dict, state: dict) -> dict:
    while True:
        if args.run_manifest.is_file():
            run = read_json(args.run_manifest)
            if failed_run(run):
                raise RuntimeError("Native bootstrap/consensus run contains a failure; completion will not retry it")
            if run.get("status") == "complete":
                return run
            state["native_progress"] = {
                "status": run.get("status"),
                "completed_bootstraps": sum(row.get("status") == "complete" for row in run.get("bootstraps", {}).values()),
                "completed_consensus": sum(row.get("status") == "complete" for row in run.get("consensus", {}).values())}
        else:
            state["native_progress"] = {"status": "manifest_not_present"}
        if not args.wait_for_run:
            raise RuntimeError("Native run is not complete; use --wait-for-run to wait without launching inference")
        verify_context(frozen)
        state.update(status="waiting_for_native", updated=time.time())
        legacy.json_write(args.out / "status.json", state, replace=True)
        print(json.dumps(state["native_progress"]), file=sys.stderr, flush=True)
        time.sleep(30)


def validate_native(args, run: dict) -> dict[float, Path]:
    frozen = run["frozen"]
    params = frozen["parameters"]
    if frozen.get("source_commit") != legacy.SOURCE_COMMIT:
        raise ValueError("Native source is not the declared paper-era 0.2.1 baseline")
    required = {"bootstrap_count": 100, "seeds": list(range(1, 101)), "bootstrap_p": 1e-7,
                "consensus_p": list(PC), "npar": 40, "dpi_tolerance": 0,
                "sampling": "legacy -r 1", "algorithm": "adaptive_partitioning",
                "explicit_mi_override": None}
    if any(params.get(name) != value for name, value in required.items()):
        raise ValueError("Native parameters differ from the declared 100-bootstrap legacy protocol")
    for key, filename in (("prepare_manifest", "prepare_manifest.json"),
                          ("expression", "expression.exp"), ("hubs", "hubs.txt")):
        check_record(frozen["inputs"][key], args.prepared_dir / filename)
    for record in [frozen["component_manifest"], *frozen["components"].values()]:
        check_record(record)
    if set(run.get("bootstraps", {})) != {str(seed) for seed in range(1, 101)}:
        raise ValueError("Native run does not contain exactly 100 expected seeds")
    adj_paths = set()
    for seed in range(1, 101):
        job = run["bootstraps"][str(seed)]
        if job.get("status") != "complete" or job.get("seed") != seed:
            raise ValueError("Incomplete or inconsistent bootstrap checkpoint")
        for record in job["artifacts"].values():
            check_record(record)
        path = local_path(job["artifacts"]["adjacency"]["path"])
        expected = args.run_manifest.parent / "adj" / f"bootstrap_{seed:03d}.adj"
        if path != expected.resolve():
            raise ValueError("Bootstrap does not belong to the expected frozen adjacency directory")
        adj_paths.add(path)
    if {path.resolve() for path in (args.run_manifest.parent / "adj").iterdir()} != adj_paths:
        raise ValueError("Extra or missing bootstrap input for consensus")
    expected_consensus = {legacy.consensus_name(p) for p in PC}
    if set(run.get("consensus", {})) != expected_consensus:
        raise ValueError("Expected exactly the two declared consensus alternatives")
    networks = {}
    for p in PC:
        job = run["consensus"][legacy.consensus_name(p)]
        if job.get("status") != "complete" or job.get("p") != p:
            raise ValueError("Incomplete or inconsistent consensus checkpoint")
        for record in job["artifacts"].values():
            check_record(record)
        network = local_path(job["artifacts"]["edges.tsv"]["path"])
        expected = args.run_manifest.parent / legacy.consensus_name(p) / "edges.tsv"
        if network != expected.resolve():
            raise ValueError("Consensus is outside the frozen run")
        networks[p] = network
    return networks


def score_command(args, network: Path, output: Path) -> list[str]:
    mamba = args.wsl_micromamba or str(PurePosixPath(args.wsl_r_env).parent / "micromamba")
    command = [mamba, "run", "--prefix", args.wsl_r_env]
    if args.wsl_r_library is not None:
        command += ["env", "R_LIBS_USER=" + args.wsl_r_library]
    command += ["Rscript", legacy.wsl_path(Path(__file__).with_name("score_author.R")),
                legacy.wsl_path(network),
                legacy.wsl_path(args.prepared_dir / "reference_positive_edges.tsv"),
                legacy.wsl_path(args.publication_dir), legacy.wsl_path(output),
                legacy.wsl_path(args.run_manifest)]
    if os.name == "nt":
        command = ["wsl.exe", "-d", args.wsl_distro, "--", *command]
    return command


def maybe_number(value, *, integer=False):
    if value in (None, "", "NA"):
        return None
    result = float(value)
    if not math.isfinite(result) or result < 0 or (integer and result != int(result)):
        raise ValueError("Invalid nonnegative metric")
    return int(result) if integer else result


def load_curves(path: Path, reported: int) -> dict:
    result = {}
    with path.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            k = maybe_number(row["k"], integer=True)
            tp, random_tp = maybe_number(row["TP"], integer=True), maybe_number(row["Random_TP"], integer=True)
            epr = maybe_number(row["EPR"])
            if k is None or k < 1000 or k % 1000 or k > reported or k in result:
                raise ValueError("Invalid/duplicate ranked-curve cutoff")
            if tp is None or random_tp is None or max(tp, random_tp) > k:
                raise ValueError("Invalid TP or shuffled TP")
            if random_tp == 0:
                if epr is not None:
                    raise ValueError("EPR should be undefined for a zero shuffled denominator")
            elif epr is None or not math.isclose(epr, tp / random_tp, rel_tol=1e-10, abs_tol=1e-12):
                raise ValueError("EPR disagrees with actual shuffled TP")
            result[k] = {"tp": tp, "random_tp": random_tp, "epr": epr}
    if set(result) != set(range(1000, reported + 1, 1000)):
        raise ValueError("Ranked curve is not the complete 1,000-step author trajectory")
    return result


def validate_score(output: Path, network: Path, args, frozen: dict, run_sha: str) -> tuple[dict, dict]:
    metrics = read_json(output / "metrics.json")
    if metrics.get("status") != "complete" or metrics.get("exact_reproduction_established") is not False:
        raise ValueError("Scorer did not establish a completed, explicitly reconstructed result")
    if metrics.get("script_sha256") != frozen["inputs"]["scorer"]["sha256"]:
        raise ValueError("Scorer version changed")
    expected_inputs = {"network": legacy.digest(network), "run_manifest": run_sha,
                       "reference": frozen["inputs"]["reference_positive_edges.tsv"]["sha256"],
                       "prepare_manifest": frozen["inputs"]["preparation_manifest"]["sha256"],
                       "publication_manifest": frozen["inputs"]["publication_manifest"]["sha256"],
                       "publication_tp": frozen["inputs"]["publication_tp.tsv"]["sha256"],
                       "publication_epr": frozen["inputs"]["publication_epr.tsv"]["sha256"],
                       "publication_roc_segment": frozen["inputs"]["publication_roc_segment.tsv"]["sha256"]}
    if metrics.get("input_sha256") != expected_inputs:
        raise ValueError("Scorer input hashes do not match frozen completion inputs")
    hashes = metrics.get("output_sha256", {})
    if set(hashes) != set(SCORE_OUTPUTS):
        raise ValueError("Scorer output hash coverage incomplete")
    for filename, expected in hashes.items():
        if legacy.digest(output / filename) != expected:
            raise ValueError(f"Scorer output changed: {filename}")
    for name in ("AUROC", "Random_AUROC"):
        value = metrics.get(name)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError(f"Invalid {name}")
    N, hits = metrics["reported_edges"], metrics["reference_positive_reported_edges"]
    if isinstance(N, bool) or not isinstance(N, int) or N < 1 or not isinstance(hits, int) or not 0 < hits < N:
        raise ValueError("Invalid reported population")
    return metrics, load_curves(output / "ranked_curves.tsv", N)


def publication_points(directory: Path) -> dict:
    result = {k: {"tp": None, "random_tp": None, "epr": None} for k in KS}
    with (directory / "tp.tsv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            k = int(row["k"])
            if k in result:
                key = "tp" if row["method"] == "scMINER" else "random_tp" if row["method"] == "Random" else None
                if key is None or result[k][key] is not None:
                    raise ValueError("Unsupported/duplicate publication TP point")
                result[k][key] = maybe_number(row["TP"], integer=True)
    with (directory / "epr.tsv").open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            k = int(row["k"])
            if k in result:
                if result[k]["epr"] is not None:
                    raise ValueError("Duplicate publication EPR point")
                result[k]["epr"] = maybe_number(row["EPR"])
    return result


def format_value(value) -> str:
    return "NA" if value is None else str(value) if isinstance(value, int) else format(value, ".6g")


def render_report(summary: dict) -> str:
    scores = summary["consensus"]
    lines = ["# Reconstructed THP-1 legacy baseline versus published Fig. 6a", "",
             "Completed 100-bootstrap legacy reconstruction; not an exact recovery of author-prepared inputs.", "",
             "Primary consensus p=0.01 follows the paper; secondary p=0.001 follows the scoped author folder clue. Both use the same 100 adjacency files, inferred bootstrap p=1e-7, DPI=0 and depth=40.", "",
             "| Metric | Published | Reconstructed pc=0.01 | Reconstructed pc=0.001 |",
             "| --- | ---: | ---: | ---: |",
             f"| AUROC | ~{summary['published_AUROC_rounded']:.2f} (paper) | {scores['0.01']['AUROC']:.6f} | {scores['0.001']['AUROC']:.6f} |",
             f"| R-shuffled AUROC | Not available in source workbook | {scores['0.01']['Random_AUROC']:.6f} | {scores['0.001']['Random_AUROC']:.6f} |",
             f"| Emitted edges | Not recovered | {scores['0.01']['reported_edges']} | {scores['0.001']['reported_edges']} |", "",
             "| Top k | Published TP | Published EPR | pc=0.01 TP | pc=0.01 EPR | pc=0.001 TP | pc=0.001 EPR |",
             "| ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for k in KS:
        pub = summary["published_points"][str(k)]
        first, second = scores["0.01"]["points"][str(k)], scores["0.001"]["points"][str(k)]
        row = [k, pub["tp"], pub["epr"], first["tp"], first["epr"], second["tp"], second["epr"]]
        lines.append("| " + " | ".join(map(format_value, row)) + " |")
    lines += ["", "TP counts thresholded perturbation-response positives; EPR divides TP by the actual seed-1 R-shuffled TP of the same emitted edge pool. Ordinal-rank R ROC and original MI tie order are retained. NA means the cutoff is unavailable or its shuffled denominator is zero.", "",
              "The workbook contains only a partial published ROC segment. Published AUROC ~0.75 is the paper's rounded value, not an area calculated from that segment. Missing author intermediates, exact native version/invocation, QC/guide details, CPM denominator and metacell seed remain reconstruction limitations. The independent preparation audit is a bounded technical check, not proof of exact author inputs or biological correctness.", "",
              "This comparison does not establish a PR70 improvement: no after-PR70 arm, PR71 calibration or minimum-recurrence rule is included. Neither consensus alternative was selected by matching the published score.", "",
              "Per-cutoff metrics, actual shuffled counts, plots and output hashes are in score_pc1e-02/ and score_pc1e-03/. Frozen input/artifact provenance is in summary.json and completion_manifest.json.", ""]
    return "\n".join(lines)


def complete(args) -> dict:
    args.run_manifest = args.run_manifest.resolve()
    args.prepared_dir = args.prepared_dir.resolve()
    args.publication_dir = args.publication_dir.resolve()
    args.audit_file = args.audit_file.resolve()
    args.out = args.out.resolve()
    args.wsl_r_env = linux_argument(args.wsl_r_env)
    args.wsl_r_library = linux_argument(args.wsl_r_library)
    args.wsl_micromamba = linux_argument(args.wsl_micromamba)
    if args.out.exists():
        raise FileExistsError("Comparison output must be fresh; completed/failed outputs are never overwritten")
    frozen, prepared, publication = freeze_context(args)
    args.out.mkdir(parents=True, exist_ok=False)
    state = {"status": "starting", "created": time.time(), "pid": os.getpid(), "scope": frozen["scope"]}
    legacy.json_write(args.out / "completion_manifest.json", frozen)
    legacy.json_write(args.out / "status.json", state)
    try:
        run = await_run(args, frozen, state)
        run_sha = legacy.digest(args.run_manifest)
        if read_json(args.run_manifest) != run:
            raise ValueError("Native manifest changed between completion detection and validation")
        networks = validate_native(args, run)
        if legacy.digest(args.run_manifest) != run_sha:
            raise ValueError("Native manifest changed while validating native artifacts")
        verify_context(frozen)
        state.update(status="scoring", native_run_sha256=run_sha, updated=time.time())
        legacy.json_write(args.out / "status.json", state, replace=True)
        scores = {}
        for p in PC:
            output = args.out / ("score_pc" + legacy.consensus_name(p).removeprefix("consensus_pc"))
            command = score_command(args, networks[p], output)
            log = args.out / f"{output.name}.log"
            with log.open("x", encoding="utf-8") as stream:
                result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
            if result.returncode != 0:
                raise RuntimeError(f"R scorer failed for pc={p}; inspect {log}")
            if legacy.digest(args.run_manifest) != run_sha:
                raise ValueError("Native run manifest changed during scoring")
            verify_context(frozen)
            metrics, curves = validate_score(output, networks[p], args, frozen, run_sha)
            scores[str(p)] = {name: metrics[name] for name in ("AUROC", "Random_AUROC", "reported_edges", "reference_positive_reported_edges")}
            scores[str(p)].update(points={str(k): curves.get(k, {"tp": None, "random_tp": None, "epr": None}) for k in KS},
                                  metrics=legacy.record_file(output / "metrics.json"),
                                  output_sha256=metrics["output_sha256"], command=command,
                                  log=legacy.record_file(log))
        verify_context(frozen)
        summary = {"status": "complete", "exact_reproduction_established": False,
                   "scope": frozen["scope"], "native_run": legacy.record_file(args.run_manifest),
                   "audit": frozen["inputs"]["audit"], "preparation": prepared,
                   "published_AUROC_rounded": publication["published_AUROC_rounded"],
                   "published_ROC_complete": False, "published_points": {str(k): row for k, row in publication_points(args.publication_dir).items()},
                   "consensus": scores, "completed": time.time()}
        with (args.out / "REPORT.md").open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(render_report(summary))
        legacy.json_write(args.out / "summary.json", summary)
        state.update(status="complete", updated=time.time(),
                     outputs={name: legacy.record_file(args.out / name) for name in ("REPORT.md", "summary.json")})
        legacy.json_write(args.out / "status.json", state, replace=True)
        return summary
    except BaseException as exc:
        state.update(status="failed", error=str(exc), updated=time.time())
        legacy.json_write(args.out / "status.json", state, replace=True)
        raise


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    for name in ("run-manifest", "prepared-dir", "publication-dir", "audit-file", "out"):
        result.add_argument("--" + name, type=Path, required=True)
    result.add_argument("--wsl-r-env", required=True, help="Linux path to isolated micromamba R prefix")
    result.add_argument("--wsl-r-library", help="Optional Linux path to paper-version R overlay")
    result.add_argument("--wsl-micromamba", help="Default: micromamba beside the R prefix")
    result.add_argument("--wsl-distro", default="Ubuntu")
    result.add_argument("--wait-for-run", action="store_true", help="Poll every 30 seconds; does not launch native jobs")
    return result


if __name__ == "__main__":
    arguments = parser().parse_args()
    finished = complete(arguments)
    print(json.dumps({"status": finished["status"], "summary": str(arguments.out / "summary.json")}))
