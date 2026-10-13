#!/usr/bin/env python3
"""Matched PR70 sampling-only backport on the frozen paper-era baseline.

Plans do not launch inference. Every real action requires a completed, scored
100-bootstrap baseline and a separate, hash-bound decision to proceed with
the reconstructed-reference comparison, not a claim of publication agreement. This
does not change PR71 calibration, DPI, AP-MI or the original consensus script.
The 80% sample size also changes the legacy sample-count-dependent affine MI
threshold; this is a sampling-protocol comparison, not an MI-cutoff isolation.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

import run_legacy as legacy


BASE_COMMIT = legacy.SOURCE_COMMIT
SAMPLING_COMMIT = "3a93d10e862ba43229e60ca6491ee38143422379"
PROFILE = "sampling_only_backport"
PLATFORM = legacy.PLATFORM
SAMPLING_PERCENT = 80
PC = (0.01, 0.001)
MODIFIED_SOURCE_PATHS = {"SJARACNe/src/" + name for name in
                         ("main.cpp", "matrix.cpp", "matrix.h", "param.cpp", "param.h")}
SCORE_OUTPUTS = ("ranked_curves.tsv", "comparison_to_publication.tsv", "roc_curves.tsv",
                 "MI_ranked_edges.tsv", "comparison_to_fig6a.png")


def read_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"),
                      parse_constant=lambda text: (_ for _ in ()).throw(ValueError(text)))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def check_record(record: dict, expected: Path | None = None) -> None:
    path = Path(record["path"]).resolve()
    if expected is not None and path != expected.resolve():
        raise ValueError(f"Recorded path mismatch: {path} != {expected}")
    if legacy.digest(path) != record["sha256"]:
        raise ValueError(f"Recorded hash mismatch: {path}")


def baseline_binding(args, require_complete: bool = False) -> dict:
    """Inspect prerequisites; audit all completed native/scoring artifacts once.

    A plan can be made while the baseline is still running. Its hashes are a
    diagnostic snapshot, not permission to launch. Real execution performs the
    full artifact audit and freezes the final baseline and comparison records.
    """
    records = {}
    blockers = []
    run_path = args.baseline_run_manifest.resolve()
    summary_path = args.baseline_summary.resolve()
    if not run_path.is_file():
        blockers.append("Baseline run manifest is not present")
        if require_complete:
            raise ValueError(blockers[-1])
        return {"status": "not_ready", "records": records, "blockers": blockers}
    run = read_json(run_path)
    run_record = legacy.record_file(run_path)
    records["run_manifest"] = run_record
    frozen = run.get("frozen", {})
    expected = {"bootstrap_count": 100, "seeds": list(range(1, 101)),
                "bootstrap_p": 1e-7, "consensus_p": list(PC), "npar": 40,
                "dpi_tolerance": 0, "sampling": "legacy -r 1",
                "algorithm": "adaptive_partitioning", "explicit_mi_override": None}
    if frozen.get("source_commit") != BASE_COMMIT or any(
            frozen.get("parameters", {}).get(key) != value for key, value in expected.items()):
        raise ValueError("Baseline is not the fixed paper-era legacy protocol")
    for name, path in (("expression", args.expression), ("hubs", args.hubs),
                       ("prepare_manifest", args.prepare_manifest)):
        check_record(frozen["inputs"][name], path)
    if run.get("status") != "complete":
        blockers.append("Baseline native run is not complete")
    if not summary_path.is_file():
        blockers.append("Baseline completed scoring summary is not present")
    else:
        summary = read_json(summary_path)
        records["summary"] = legacy.record_file(summary_path)
        if summary.get("status") != "complete":
            blockers.append("Baseline scoring summary is not complete")
        elif summary.get("native_run", {}).get("sha256") != run_record["sha256"]:
            blockers.append("Baseline scoring does not bind the current native run manifest")
    if blockers:
        if require_complete:
            raise ValueError("; ".join(blockers))
        return {"status": "not_ready", "records": records, "blockers": blockers}
    if not require_complete:
        return {"status": "ready_for_audit", "records": records, "blockers": [],
                "baseline_components": frozen["components"],
                "baseline_observations": frozen["observations"],
                "baseline_affine_mi_cutoff": frozen["parameters"]["affine_mi_cutoff"]}

    # Hashing all baseline outputs is deliberately outside each native worker.
    legacy.verify_frozen(frozen)
    if set(run.get("bootstraps", {})) != {str(seed) for seed in range(1, 101)}:
        raise ValueError("Baseline must contain exactly the 100 expected bootstrap seeds")
    actual_adj = {path.resolve() for path in (run_path.parent / "adj").iterdir()}
    expected_adj = set()
    for seed in range(1, 101):
        job = run["bootstraps"][str(seed)]
        if job.get("seed") != seed or job.get("validation", {}).get("draws") != frozen["observations"]:
            raise ValueError("Baseline seed or native sampling validation mismatch")
        legacy.verify_completed(job)
        path = run_path.parent / "adj" / f"bootstrap_{seed:03d}.adj"
        check_record(job["artifacts"]["adjacency"], path)
        expected_adj.add(path.resolve())
    if actual_adj != expected_adj:
        raise ValueError("Baseline adjacency directory is not the exact completed bootstrap set")
    names = {legacy.consensus_name(p) for p in PC}
    if set(run.get("consensus", {})) != names:
        raise ValueError("Baseline requires exactly both original consensus alternatives")
    for p in PC:
        job = run["consensus"][legacy.consensus_name(p)]
        if job.get("p") != p:
            raise ValueError("Baseline consensus probability mismatch")
        legacy.verify_completed(job)
        check_record(job["artifacts"]["edges.tsv"],
                     run_path.parent / legacy.consensus_name(p) / "edges.tsv")
    check_record(summary["native_run"], run_path)
    if set(summary.get("consensus", {})) != {str(p) for p in PC}:
        raise ValueError("Baseline summary lacks both consensus scores")
    comparison_status = summary_path.parent / "status.json"
    status = read_json(comparison_status)
    if status.get("status") != "complete" or set(status.get("outputs", {})) != {"REPORT.md", "summary.json"}:
        raise ValueError("Baseline comparison did not publish complete scoring outputs")
    records["comparison_status"] = legacy.record_file(comparison_status)
    for filename, record in status["outputs"].items():
        check_record(record, summary_path.parent / filename)
        records[filename] = record
    completion_path = summary_path.parent / "completion_manifest.json"
    completion = read_json(completion_path)
    context = completion.get("inputs", {})
    scorer_path = Path(__file__).with_name("score_author.R")
    check_record(context["scorer"], scorer_path)
    check_record(context["preparation_manifest"], args.prepare_manifest)
    for name, record in context.items():
        check_record(record)
        records["comparison_context_" + name] = record
    records["completion_manifest"] = legacy.record_file(completion_path)
    publication = read_json(Path(context["publication_manifest"]["path"]))
    if publication.get("full_ROC_available") is not False or publication.get("published_AUROC_rounded") != 0.75:
        raise ValueError("Publication context is not the declared partial Fig. 6a source data")
    for filename in ("tp.tsv", "epr.tsv", "roc_segment.tsv"):
        record = context["publication_" + filename]
        if publication.get("outputs_sha256", {}).get(filename) != record["sha256"]:
            raise ValueError("Publication source-point hashes disagree with completion context")
    prepared = read_json(args.prepare_manifest)
    reference_sha = prepared["outputs"]["reference_positive_edges.tsv"]["sha256"]
    for p in PC:
        score = summary["consensus"][str(p)]
        metrics_record = score["metrics"]
        check_record(metrics_record)
        metrics_path = Path(metrics_record["path"])
        metrics = read_json(metrics_path)
        network = run["consensus"][legacy.consensus_name(p)]["artifacts"]["edges.tsv"]
        required = {"run_manifest": run_record["sha256"], "network": network["sha256"],
                    "prepare_manifest": legacy.digest(args.prepare_manifest), "reference": reference_sha,
                    "publication_manifest": context["publication_manifest"]["sha256"],
                    "publication_tp": context["publication_tp.tsv"]["sha256"],
                    "publication_epr": context["publication_epr.tsv"]["sha256"],
                    "publication_roc_segment": context["publication_roc_segment.tsv"]["sha256"]}
        if metrics.get("status") != "complete" or any(
                metrics.get("input_sha256", {}).get(key) != value for key, value in required.items()):
            raise ValueError("Baseline scorer input binding is incomplete or mismatched")
        if metrics.get("script_sha256") != context["scorer"]["sha256"]:
            raise ValueError("Baseline scorer hash differs from the completed scoring context")
        if set(metrics.get("output_sha256", {})) != set(SCORE_OUTPUTS):
            raise ValueError("Baseline score output hash coverage is incomplete")
        for name in ("AUROC", "Random_AUROC", "reported_edges", "reference_positive_reported_edges"):
            if score.get(name) != metrics.get(name):
                raise ValueError("Baseline summary metric disagrees with scorer artifact")
        records[f"metrics_pc{p}"] = metrics_record
        for filename, sha in metrics["output_sha256"].items():
            path = metrics_path.parent / filename
            if legacy.digest(path) != sha:
                raise ValueError(f"Baseline score output changed: {path}")
            records[f"pc{p}_{filename}"] = legacy.record_file(path)
    # Protect against coordinator/checkpoint changes during the audit.
    if legacy.digest(run_path) != run_record["sha256"]:
        raise ValueError("Baseline run manifest changed during its completed-artifact audit")
    if legacy.digest(summary_path) != records["summary"]["sha256"]:
        raise ValueError("Baseline comparison summary changed during audit")
    return {"status": "complete", "records": records, "blockers": [],
            "baseline_components": frozen["components"],
            "baseline_observations": frozen["observations"],
            "baseline_affine_mi_cutoff": frozen["parameters"]["affine_mi_cutoff"]}


def gate_binding(args, baseline: dict, required: bool = False) -> dict:
    blockers = []
    path = args.gate_decision
    if path is None or not path.is_file():
        blockers.append("Explicit reconstructed-benchmark gate decision is not present")
        if required:
            raise ValueError(blockers[-1])
        return {"status": "not_accepted", "record": None, "blockers": blockers}
    decision = read_json(path)
    records = baseline.get("records", {})
    expected = {"schema": 1, "status": "accepted_by_user_or_audit", "scope": PROFILE,
                "sampling_percent": SAMPLING_PERCENT,
                "baseline_run_manifest_sha256": records.get("run_manifest", {}).get("sha256"),
                "baseline_summary_sha256": records.get("summary", {}).get("sha256")}
    if any(decision.get(key) != value or value is None for key, value in expected.items()):
        blockers.append("Gate decision does not bind this completed baseline and sampling-only scope")
    if not isinstance(decision.get("reason"), str) or not decision["reason"].strip():
        blockers.append("Gate decision requires an explicit benchmark-acceptance reason")
    if baseline["status"] not in ("complete", "ready_for_audit"):
        blockers.append("Baseline has not reached completed scoring")
    if blockers and required:
        raise ValueError("; ".join(blockers))
    return {"status": "accepted" if not blockers else "not_accepted",
            "record": legacy.record_file(path), "decision": decision, "blockers": blockers}


def make_frozen(args) -> tuple[dict, set, set]:
    if args.workers < 1:
        raise ValueError("Workers must be positive")
    protocol = {"bootstrap_count": 100, "bootstrap_p": 1e-7, "consensus_p": list(PC),
                "npar": 40, "subsample_percent": SAMPLING_PERCENT}
    if any(getattr(args, key) != value for key, value in protocol.items()):
        raise ValueError("Only the prespecified 100-seed, 80% sampling comparison is supported")
    components = read_json(args.component_manifest)
    if (components.get("source_commit") != BASE_COMMIT or components.get("sampling_commit") != SAMPLING_COMMIT
            or components.get("profile") != PROFILE):
        raise ValueError("Requires the pinned sampling-only backport build record")
    if components.get("build_exit_code") != 0 or components.get("validation_status") != "passed":
        raise ValueError("Sampling-only backport build was not successful")
    if components.get("legacy_equivalence_case_count") != 16 or components.get("native_unique_index_case_count") != 100:
        raise ValueError("Backport must include the declared bounded native equivalence and sampling checks")
    paths = {"binary": args.binary, "consensus_script": args.consensus_script,
             **{name: args.config / name for name in legacy.CONFIG_FILES}}
    for name, path in paths.items():
        expected = (components.get("config_sha256", {}).get(name) if name in legacy.CONFIG_FILES
                    else components.get(name + "_sha256"))
        if expected != legacy.digest(path):
            raise ValueError(f"Sampling-only component hash mismatch: {name}")
    if not components.get("source_sha256") or set(components.get("modified_source_paths", [])) != MODIFIED_SOURCE_PATHS:
        raise ValueError("Backport must bind nonempty source provenance and the five declared sampling changes")
    if not MODIFIED_SOURCE_PATHS <= set(components["source_sha256"]):
        raise ValueError("Modified source files lack build hash coverage")
    source_records = {}
    for name, sha in components.get("source_sha256", {}).items():
        path = Path(components["source_root"]) / name
        root = Path(components["source_root"]).resolve()
        if not path.resolve().is_relative_to(root) or legacy.digest(path) != sha:
            raise ValueError(f"Backported source provenance mismatch: {name}")
        source_records[name] = legacy.record_file(path)
    build_artifacts = {}
    for key, hash_key in (("patchfile", "patch_sha256"), ("validation_artifact", "validation_artifact_sha256")):
        path = Path(components[key])
        if legacy.digest(path) != components[hash_key]:
            raise ValueError(f"Backport build artifact changed: {key}")
        build_artifacts[key] = legacy.record_file(path)
    if read_json(Path(components["validation_artifact"])).get("status") != "passed":
        raise ValueError("Backport native validation artifact is not passed")
    exp = legacy.expression_info(args.expression)
    hubs = legacy.hub_info(args.hubs, exp["ids"])
    inputs = {"expression": legacy.record_file(args.expression), "hubs": legacy.record_file(args.hubs),
              "prepare_manifest": legacy.record_file(args.prepare_manifest)}
    prepared = read_json(args.prepare_manifest)
    if prepared.get("status") != "complete":
        raise ValueError("The shared preparation must be complete")
    for name, key in (("expression.exp", "expression"), ("hubs.txt", "hubs")):
        if prepared.get("outputs", {}).get(name, {}).get("sha256") != inputs[key]["sha256"]:
            raise ValueError(f"Sampling input is not the frozen prepared artifact: {name}")
    reference = args.prepare_manifest.parent / "reference_positive_edges.tsv"
    if prepared.get("outputs", {}).get(reference.name, {}).get("sha256") != legacy.digest(reference):
        raise ValueError("Shared response reference differs from the preparation manifest")
    inputs["reference_positive_edges"] = legacy.record_file(reference)
    real_action = args.action != "plan"
    baseline = baseline_binding(args, require_complete=real_action)
    gate = gate_binding(args, baseline, required=real_action)
    if baseline.get("baseline_components") is not None:
        for name in ("consensus_script", *legacy.CONFIG_FILES):
            if baseline["baseline_components"][name]["sha256"] != legacy.digest(paths[name]):
                raise ValueError("Original consensus/configuration must remain byte-identical to the baseline")
    draws = math.ceil(exp["observations"] * SAMPLING_PERCENT / 100)
    if baseline.get("baseline_observations", exp["observations"]) != exp["observations"]:
        raise ValueError("The after arm must retain the exact baseline metacell population")
    frozen = {
        "schema": 1, "label": "matched sampling-only backport; author inputs remain reconstructed",
        "source_commit": BASE_COMMIT, "sampling_commit": SAMPLING_COMMIT, "profile": PROFILE,
        "component_manifest": legacy.record_file(args.component_manifest),
        "components": {name: legacy.record_file(path) for name, path in paths.items()},
        "build_record": components, "source_records": source_records, "build_artifacts": build_artifacts,
        "inputs": inputs,
        "preparation_binding": {"status": "complete", "manifest": inputs["prepare_manifest"],
                                "expression": inputs["expression"], "hubs": inputs["hubs"],
                                "reference": inputs["reference_positive_edges"]},
        "baseline_binding": baseline, "gate_binding": gate,
        "out": str(args.out.resolve()), "observations": exp["observations"],
        "genes": exp["genes"], "hubs": len(hubs),
        "parameters": {"bootstrap_count": 100, "seeds": list(range(1, 101)),
                       "bootstrap_p": 1e-7, "consensus_p": list(PC), "npar": 40,
                       "dpi_tolerance": 0, "sampling": "fixed-size without replacement -u 80%",
                       "sampling_percent": SAMPLING_PERCENT, "sampling_draws": draws,
                       "baseline_sampling_draws": exp["observations"],
                       "algorithm": "adaptive_partitioning", "explicit_mi_override": None,
                       "affine_mi_cutoff": legacy.affine_cutoff(args.config, draws, 1e-7),
                       "baseline_affine_mi_cutoff": legacy.affine_cutoff(args.config, exp["observations"], 1e-7)},
        "execution": {"platform": legacy.PLATFORM, "wsl_distro": args.wsl_distro,
                      "consensus_python": args.python, "consensus_wsl": args.consensus_wsl},
        "helper_sha256": legacy.digest(Path(__file__)),
        "reused_legacy_helper": legacy.record_file(Path(legacy.__file__)),
        "scope": "sampling-only backport; no PR71 or K-edge recurrence change; not exact Fig. 6a reproduction",
        "cutoff_provenance": "Same legacy affine coefficients and nominal p=1e-7; evaluated at 97 rather than 121 observations for the prepared THP-1 inputs",
    }
    return frozen, exp["ids"], hubs


def verify_frozen(frozen: dict) -> None:
    legacy.verify_frozen(frozen)
    records = [*frozen["source_records"].values(), *frozen["build_artifacts"].values(),
               *frozen["baseline_binding"]["records"].values(),
               frozen["reused_legacy_helper"]]
    if frozen["gate_binding"]["record"] is not None:
        records.append(frozen["gate_binding"]["record"])
    for record in records:
        check_record(record)
    if legacy.digest(Path(__file__)) != frozen["helper_sha256"]:
        raise ValueError("Sampling runner changed during execution")


def native_command(args, seed: int, output: Path) -> list[str]:
    path = legacy.wsl_path if legacy.PLATFORM == "nt" else lambda value: str(value.resolve())
    command = [path(args.binary), "-i", path(args.expression), "-l", path(args.hubs),
               "-s", path(args.hubs), "-H", path(args.config), "-a", "adaptive_partitioning",
               "-N", "40", "-S", str(seed), "-p", format(1e-7, ".17g"), "-e", "0",
               "-u", "80%", "-o", path(output)]
    if legacy.PLATFORM == "nt":
        command = ["wsl.exe", "-d", args.wsl_distro, "--", *command]
    return command


def plan(args, frozen: dict) -> dict:
    return {"frozen": frozen, "bootstrap_commands": [
        native_command(args, seed, args.out / "adj" / f"bootstrap_{seed:03d}.adj")
        for seed in frozen["parameters"]["seeds"]],
        "consensus_commands": [legacy.consensus_command(args, p, args.out / legacy.consensus_name(p)) for p in PC],
        "launch_blockers": [*frozen["baseline_binding"]["blockers"], *frozen["gate_binding"]["blockers"]],
        "note": "Plan runs no inference, writes no run directory, and is not an accepted baseline gate."}


def validate_adjacency(path: Path, genes: set, hubs: set, frozen: dict, log: Path) -> dict:
    header = {}
    sources = set()
    edges = 0
    numbers = ("MI threshold", "MI P-value", "DPI tolerance", "Eligible observations", "Sampled observations")
    strings = ("Sampling method", "Sampling request")
    with path.open(encoding="utf-8") as stream:
        for rowno, line in enumerate(stream, 1):
            if line.startswith(">"):
                value = line[1:].strip()
                for key in (*numbers, *strings):
                    if value.startswith(key):
                        if key in header:
                            raise ValueError(f"Duplicate adjacency header: {key}")
                        text = value[len(key):].strip()
                        header[key] = float(text) if key in numbers else text
                continue
            fields = line.rstrip("\r\n").split("\t")
            if not fields[0] or fields[0] not in hubs or fields[0] in sources or len(fields) % 2 != 1:
                raise ValueError(f"Invalid adjacency source/width at row {rowno}")
            sources.add(fields[0])
            targets = set()
            for index in range(1, len(fields), 2):
                target, mi = fields[index], float(fields[index + 1])
                if target not in genes or target == fields[0] or target in targets or not math.isfinite(mi) or mi < 0:
                    raise ValueError(f"Invalid adjacency target/MI at row {rowno}")
                targets.add(target)
                edges += 1
    params = frozen["parameters"]
    for key, expected in (("MI threshold", params["affine_mi_cutoff"]), ("MI P-value", 1e-7),
                          ("DPI tolerance", 0), ("Eligible observations", frozen["observations"]),
                          ("Sampled observations", params["sampling_draws"])):
        if key not in header or not math.isclose(header[key], expected, rel_tol=1e-5, abs_tol=1e-12):
            raise ValueError(f"Native {key} disagrees with frozen sampling parameters")
    if header.get("Sampling method") != "fixed-size without replacement" or header.get("Sampling request") != "80%":
        raise ValueError("Native sampling header disagrees with fixed-size without-replacement protocol")
    text = log.read_text(encoding="utf-8", errors="replace")
    counts = re.findall(r"Array No:\s*(\d+)", text)
    if not counts or any(int(value) != params["sampling_draws"] for value in counts):
        raise ValueError("Native Array No must equal the sampled matrix size")
    matches = re.findall(r"\[SAMPLING\] Fixed-size sampling without replacement: selected (\d+) of (\d+) eligible observations \(request: ([^)]+)\)\.", text)
    if matches != [(str(params["sampling_draws"]), str(frozen["observations"]), "80%")]:
        raise ValueError("Native sampling log does not bind sampled and eligible observation counts")
    return {"edges": edges, "source_rows": len(sources), "header": header,
            "draws": params["sampling_draws"], "eligible_observations": frozen["observations"],
            "sampling": "fixed-size without replacement"}


def bootstrap_job(args, frozen, genes, hubs, seed):
    final = args.out / "adj" / f"bootstrap_{seed:03d}.adj"
    attempt = legacy.next_attempt(args.out, f"bootstrap_{seed:03d}")
    temporary = attempt / final.name
    log = attempt / "native.log"
    command = native_command(args, seed, temporary)
    record = {"seed": seed, "status": "failed", "command": command, "attempt": str(attempt), "started": time.time()}
    try:
        if final.exists():
            raise FileExistsError(f"Uncheckpointed output will not be overwritten: {final}")
        verify_frozen(frozen)
        with log.open("x", encoding="utf-8") as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
        record["returncode"] = result.returncode
        if result.returncode != 0:
            raise RuntimeError(f"Sampling bootstrap {seed} failed; inspect {log}")
        record["validation"] = validate_adjacency(temporary, genes, hubs, frozen, log)
        verify_frozen(frozen)
        legacy.publish_file(temporary, final)
        record.update(status="complete", artifacts={"adjacency": legacy.record_file(final), "log": legacy.record_file(log)})
    except Exception as error:
        record["error"] = str(error)
    record["finished"] = time.time()
    return record


def consensus_job(args, state, genes, hubs, p):
    name = legacy.consensus_name(p)
    final = args.out / name
    if final.exists():
        raise FileExistsError(f"Uncheckpointed consensus will not be overwritten: {final}")
    attempt = legacy.next_attempt(args.out, name)
    output, log = attempt / "output", attempt / "consensus.log"
    command = legacy.consensus_command(args, p, output)
    record = {"p": p, "status": "failed", "command": command, "attempt": str(attempt), "started": time.time()}
    try:
        verify_frozen(state["frozen"])
        legacy.verify_bootstraps(args, state)
        record["adjacency_directory_order_host"] = os.listdir(args.out / "adj")
        with log.open("x", encoding="utf-8") as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
        record["returncode"] = result.returncode
        if result.returncode != 0:
            raise RuntimeError(f"Original consensus failed; inspect {log}")
        record["validation"] = legacy.validate_consensus(output, genes, hubs)
        counts = re.findall(r"Bootstrap No:\s*(\d+)", (output / "parameter_info_.txt").read_text(encoding="utf-8"))
        if counts != ["100"]:
            raise ValueError("Original consensus must use exactly 100 bootstraps")
        verify_frozen(state["frozen"])
        legacy.verify_bootstraps(args, state)
        final.mkdir()
        for source in output.iterdir():
            if not source.is_file():
                raise ValueError("Unexpected nested original consensus output")
            with source.open("rb") as src, (final / source.name).open("xb") as dst:
                shutil.copyfileobj(src, dst)
        with (final / legacy.CONSENSUS_FILES[0]).open("rb") as src, (final / "edges.tsv").open("xb") as dst:
            shutil.copyfileobj(src, dst)
        record.update(status="complete", artifacts={path.name: legacy.record_file(path) for path in final.iterdir()})
        record["artifacts"]["log"] = legacy.record_file(log)
    except Exception as error:
        record["error"] = str(error)
    record["finished"] = time.time()
    return record


def execute(args) -> dict:
    args.out = args.out.resolve()
    if args.action != "plan" and args.out.exists() and not args.resume:
        raise FileExistsError("Output must be fresh; use --resume only for a frozen matching checkpoint")
    frozen, genes, hubs = make_frozen(args)
    if args.action == "plan":
        return plan(args, frozen)
    path = args.out / "run_manifest.json"
    if args.resume and not path.is_file():
        raise FileNotFoundError("--resume requires an existing run_manifest.json")
    with legacy.run_lock(args.out):
        if path.exists():
            if not args.resume:
                raise FileExistsError("Run exists; --resume is required")
            state = read_json(path)
            if state.get("frozen") != frozen:
                raise ValueError("Resume configuration/input/component/gate/helper differs from frozen run")
            for collection in (state["bootstraps"], state["consensus"]):
                for record in collection.values():
                    if record.get("status") == "complete":
                        legacy.verify_completed(record)
        else:
            state = {"frozen": frozen, "bootstraps": {}, "consensus": {},
                     "created": time.time(), "status": "incomplete"}
            legacy.json_write(path, state)
        (args.out / "adj").mkdir(exist_ok=True)
        if args.action in ("bootstrap", "run"):
            pending = [seed for seed in range(1, 101) if state["bootstraps"].get(str(seed), {}).get("status") != "complete"]
            for seed in pending:
                final = args.out / "adj" / f"bootstrap_{seed:03d}.adj"
                if final.exists():
                    raise FileExistsError(f"Uncheckpointed output will not be overwritten: {final}")
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = [pool.submit(bootstrap_job, args, frozen, genes, hubs, seed) for seed in pending]
                for future in as_completed(futures):
                    record = future.result()
                    state["bootstraps"][str(record["seed"])] = record
                    legacy.json_write(path, state, replace=True)
                    print(f"bootstrap {record['seed']}: {record['status']}", file=sys.stderr, flush=True)
            if any(state["bootstraps"].get(str(seed), {}).get("status") != "complete" for seed in range(1, 101)):
                raise RuntimeError("One or more sampling bootstraps failed; inspect retained attempt logs")
        if args.action in ("consensus", "run"):
            legacy.verify_bootstraps(args, state)
            for p in PC:
                name = legacy.consensus_name(p)
                if state["consensus"].get(name, {}).get("status") == "complete":
                    continue
                record = consensus_job(args, state, genes, hubs, p)
                state["consensus"][name] = record
                legacy.json_write(path, state, replace=True)
                if record["status"] != "complete":
                    raise RuntimeError(record["error"])
        verify_frozen(frozen)
        state["status"] = ("complete" if set(state["consensus"]) == {legacy.consensus_name(p) for p in PC}
                           and all(row["status"] == "complete" for row in state["consensus"].values())
                           else "bootstraps_complete")
        state["updated"] = time.time()
        legacy.json_write(path, state, replace=True)
        return state


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("action", choices=("plan", "bootstrap", "consensus", "run"))
    for name in ("expression", "hubs", "out", "binary", "config", "consensus-script", "component-manifest",
                 "prepare-manifest", "baseline-run-manifest", "baseline-summary"):
        result.add_argument("--" + name, type=Path, required=True)
    result.add_argument("--gate-decision", type=Path)
    result.add_argument("--subsample-percent", type=float, default=80)
    result.add_argument("--bootstrap-count", type=int, default=100)
    result.add_argument("--bootstrap-p", type=float, default=1e-7)
    result.add_argument("--consensus-p", type=float, nargs="+", default=list(PC))
    result.add_argument("--npar", type=int, default=40)
    result.add_argument("--workers", type=int, default=2)
    result.add_argument("--python", default=sys.executable, help="Interpreter for unchanged original consensus")
    result.add_argument("--consensus-wsl", action="store_true")
    result.add_argument("--wsl-distro", default="Ubuntu")
    result.add_argument("--resume", action="store_true")
    return result


if __name__ == "__main__":
    arguments = parser().parse_args()
    result = execute(arguments)
    if arguments.action == "plan":
        print(json.dumps(result, indent=2, allow_nan=False))
    else:
        print(json.dumps({"status": result["status"], "manifest": str(arguments.out / "run_manifest.json")}))
