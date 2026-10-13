#!/usr/bin/env python3
"""Score a completed sampling-only arm without changing frozen baseline helpers.

Only postprocessing is launched. Historical component report templates still
say legacy; this driver's arm label and the matched comparison are authoritative.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import time

import complete_baseline as completion
import run_legacy as legacy
import run_sampling_backport as sampling


SCOPE = "completed sampling-only after arm; frozen reconstructed response reference"
CODE = Path(__file__).resolve().parent


def native_arguments(manifest: Path, frozen: dict):
    """Reconstruct the original protocol for read-only native preflight only."""
    paths = {
        "expression": frozen["inputs"]["expression"]["path"],
        "hubs": frozen["inputs"]["hubs"]["path"],
        "prepare-manifest": frozen["inputs"]["prepare_manifest"]["path"],
        "out": manifest.parent,
        "binary": frozen["components"]["binary"]["path"],
        "config": completion.local_path(frozen["components"]["config_threshold.txt"]["path"]).parent,
        "consensus-script": frozen["components"]["consensus_script"]["path"],
        "component-manifest": frozen["component_manifest"]["path"],
        "baseline-run-manifest": frozen["baseline_binding"]["records"]["run_manifest"]["path"],
        "baseline-summary": frozen["baseline_binding"]["records"]["summary"]["path"],
        "gate-decision": frozen["gate_binding"]["record"]["path"],
    }
    options = ["run", "--resume", "--workers", "1", "--python", frozen["execution"]["consensus_python"],
               "--wsl-distro", frozen["execution"]["wsl_distro"]]
    if frozen["execution"]["consensus_wsl"]:
        options.append("--consensus-wsl")
    for name, path in paths.items():
        options.extend(["--" + name, str(completion.local_path(str(path)))])
    return sampling.parser().parse_args(options)


def verify_checkpoints(manifest: Path, run: dict) -> dict:
    if run.get("status") != "complete":
        raise ValueError("After run must be complete")
    if (manifest.parent / ".runner.lock").exists():
        raise ValueError("After runner still has a lock; do not score a live run")
    expected_seeds = {str(seed) for seed in range(1, 101)}
    if set(run.get("bootstraps", {})) != expected_seeds:
        raise ValueError("Require exactly 100 checkpointed sampling seeds")
    expected_adjacencies = set()
    for seed in range(1, 101):
        job = run["bootstraps"][str(seed)]
        if job.get("status") != "complete" or job.get("seed") != seed or job.get("returncode") != 0:
            raise ValueError("Incomplete or failed sampling checkpoint")
        for record in job["artifacts"].values():
            completion.check_record(record)
        path = completion.local_path(job["artifacts"]["adjacency"]["path"])
        expected = (manifest.parent / "adj" / f"bootstrap_{seed:03d}.adj").resolve()
        if path != expected:
            raise ValueError("Sampling adjacency is outside the declared run")
        expected_adjacencies.add(path)
    if {path.resolve() for path in (manifest.parent / "adj").iterdir()} != expected_adjacencies:
        raise ValueError("Unexpected or missing sampling adjacency")
    if set(run.get("consensus", {})) != {legacy.consensus_name(p) for p in completion.PC}:
        raise ValueError("Require both declared consensus alternatives")
    networks = {}
    for p in completion.PC:
        job = run["consensus"][legacy.consensus_name(p)]
        if job.get("status") != "complete" or job.get("p") != p or job.get("returncode") != 0:
            raise ValueError("Incomplete or failed sampling consensus")
        for record in job["artifacts"].values():
            completion.check_record(record)
        network = completion.local_path(job["artifacts"]["edges.tsv"]["path"])
        if network != (manifest.parent / legacy.consensus_name(p) / "edges.tsv").resolve():
            raise ValueError("Sampling consensus is outside the declared run")
        networks[p] = network
    return networks


def verify_records(records: dict) -> None:
    for record in records.values():
        completion.check_record(record)


def r_command(args, script: str, paths: list[Path]) -> list[str]:
    mamba = args.wsl_micromamba or str(PurePosixPath(args.wsl_r_env).parent / "micromamba")
    command = [mamba, "run", "--prefix", args.wsl_r_env]
    if args.wsl_r_library:
        command += ["env", "R_LIBS_USER=" + args.wsl_r_library]
    command += ["Rscript", legacy.wsl_path(CODE / script), *[legacy.wsl_path(p) for p in paths]]
    return ["wsl.exe", "-d", args.wsl_distro, "--", *command] if os.name == "nt" else command


def execute(args) -> dict:
    for name in ("result_root", "out"):
        setattr(args, name, getattr(args, name).resolve())
    if args.out.exists():
        raise FileExistsError("After scoring output must be fresh; no existing results are overwritten")
    args.run_manifest = args.result_root / "sampling_after_80pct_20261012" / "run_manifest.json"
    args.prepared_dir = args.result_root / "prepared"
    args.publication_dir = args.result_root / "publication"
    args.audit_file = args.result_root / "independent_audit.json"
    for name in ("wsl_r_env", "wsl_r_library", "wsl_micromamba"):
        setattr(args, name, completion.linux_argument(getattr(args, name)))
    run = completion.read_json(args.run_manifest)
    if run["frozen"].get("profile") != sampling.PROFILE:
        raise ValueError("Require the sampling-only backport profile")
    native_args = native_arguments(args.run_manifest, run["frozen"])
    reconstructed, _, _ = sampling.make_frozen(native_args)
    if reconstructed != run["frozen"]:
        raise ValueError("Sampling frozen protocol/build/baseline/gate differs from current verified inputs")
    sampling.verify_frozen(run["frozen"])
    networks = verify_checkpoints(args.run_manifest, run)
    context, prepared, _ = completion.freeze_context(args)
    baseline_path = completion.local_path(run["frozen"]["baseline_binding"]["records"]["run_manifest"]["path"])
    baseline = completion.read_json(baseline_path)
    baseline_args = argparse.Namespace(run_manifest=baseline_path, prepared_dir=args.prepared_dir)
    completion.validate_native(baseline_args, baseline)
    for key in ("expression", "hubs", "prepare_manifest"):
        if run["frozen"]["inputs"][key] != baseline["frozen"]["inputs"][key]:
            raise ValueError("Matched input records differ between the two arms")
    baseline_metrics = args.result_root / "three_populations_20261012" / "metrics.json"
    baseline_epr = args.result_root / "eligible_epr_20261012" / "metrics.json"
    records = {**context["inputs"], "native_run": legacy.record_file(args.run_manifest),
               "baseline_metrics": legacy.record_file(baseline_metrics), "baseline_epr": legacy.record_file(baseline_epr)}
    for name in ("complete_baseline.py", "run_sampling_backport.py", "run_legacy.py", "score_fixed_universe.py",
                 "score_three_populations.py", "score_eligible_epr.R", Path(__file__).name):
        records["helper_" + name] = legacy.record_file(CODE / name)
    verify_records(records)
    run_sha = records["native_run"]["sha256"]
    provenance = {
        "schema": 1, "scope": SCOPE, "inputs_and_helpers": records,
        "native_profile": run["frozen"]["profile"], "native_parameters": run["frozen"]["parameters"],
        "matched_design": "Identical frozen preparation, full SIG inference context, reference and scoring definitions; sampling protocol changes sample count, affine MI cutoff and RNG consumption.",
        "historical_template_warning": "Unchanged component calculators have legacy-only textual labels. These describe their original templates, not this arm. This driver and the matched comparison record the actual sampling-only after profile; no component metric is redefined.",
        "exact_reproduction_established": False, "reference": "perturbation responses, not established direct regulatory edges",
    }
    args.out.mkdir(parents=True, exist_ok=False)
    legacy.json_write(args.out / "scoring_manifest.json", provenance)
    state = {"status": "starting", "pid": os.getpid(), "created": time.time(), "scope": SCOPE, "stages": []}
    legacy.json_write(args.out / "status.json", state)

    def stage(name, command):
        verify_records(records)
        state.update(status=name, updated=time.time())
        legacy.json_write(args.out / "status.json", state, replace=True)
        started = time.time()
        log = args.out / (name + ".log")
        with log.open("x", encoding="utf-8") as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
        state["stages"].append({"name": name, "command": command, "started": started, "finished": time.time(),
                                "returncode": result.returncode, "log": legacy.record_file(log)})
        legacy.json_write(args.out / "status.json", state, replace=True)
        if result.returncode:
            raise RuntimeError(f"Postprocessing stage {name} failed; inspect {log}")
        verify_records(records)
        print(name + ": complete", file=sys.stderr, flush=True)

    try:
        author = args.out / "author_compatibility"
        author.mkdir()
        author_scores = {}
        for p in completion.PC:
            output = author / ("score_pc" + legacy.consensus_name(p).removeprefix("consensus_pc"))
            stage(output.name, completion.score_command(args, networks[p], output))
            metrics, _ = completion.validate_score(output, networks[p], args, context, run_sha)
            author_scores[legacy.consensus_name(p)] = {key: metrics[key] for key in (
                "reported_edges", "reference_positive_reported_edges", "AUROC", "Random_AUROC")}
        fixed = args.out / "fixed_universe"
        stage("fixed_universe", [sys.executable, str(CODE / "score_fixed_universe.py"),
              "--prepared-dir", str(args.prepared_dir), "--run-manifest", str(args.run_manifest),
              "--author-comparison-dir", str(author), "--out", str(fixed)])
        three = args.out / "three_populations"
        stage("three_populations", [sys.executable, str(CODE / "score_three_populations.py"),
              "--fixed-metrics", str(fixed / "metrics.json"), "--prepared-dir", str(args.prepared_dir),
              "--run-manifest", str(args.run_manifest), "--out", str(three)])
        epr = args.out / "eligible_epr"
        stage("eligible_epr", r_command(args, "score_eligible_epr.R", [three / "metrics.json", args.prepared_dir, author, epr]))
        after_metrics = completion.read_json(three / "metrics.json")
        before_metrics = completion.read_json(baseline_metrics)
        if (after_metrics["universe"] != before_metrics["universe"] or
            after_metrics["definitions"] != before_metrics["definitions"] or
            after_metrics["top_k_prespecified"] != before_metrics["top_k_prespecified"]):
            raise ValueError("Scoring universe, definitions or prespecified k differ from baseline")
        epr_metrics = completion.read_json(epr / "metrics.json")
        old_epr = completion.read_json(baseline_epr)
        if any(epr_metrics[key] != old_epr[key] for key in ("seed", "RNGkind", "definitions", "R_version", "package_versions")):
            raise ValueError("Eligible shuffled EPR implementation/RNG/environment differs from baseline")
        outputs = {str(path.relative_to(args.out)): legacy.record_file(path)
                   for path in args.out.rglob("*") if path.is_file() and path.name != "status.json"}
        summary = {"status": "complete", "scope": SCOPE, "primary_population": "eligible_emitted",
                   "author_compatibility": author_scores, "metrics": legacy.record_file(three / "metrics.json"),
                   "eligible_epr": legacy.record_file(epr / "metrics.json"), "universe_identical_to_baseline": True,
                   "definitions_and_rng_identical_to_baseline": True, "outputs": outputs,
                   "historical_template_warning": provenance["historical_template_warning"], "completed": time.time()}
        legacy.json_write(args.out / "summary.json", summary)
        verify_records(records)
        state.update(status="complete", updated=time.time(), summary=legacy.record_file(args.out / "summary.json"))
        legacy.json_write(args.out / "status.json", state, replace=True)
        return summary
    except BaseException as error:
        state.update(status="failed", error=str(error), updated=time.time())
        legacy.json_write(args.out / "status.json", state, replace=True)
        raise


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--result-root", type=Path, required=True)
    result.add_argument("--out", type=Path, required=True)
    result.add_argument("--wsl-r-env", required=True)
    result.add_argument("--wsl-r-library")
    result.add_argument("--wsl-micromamba")
    result.add_argument("--wsl-distro", default="Ubuntu")
    return result


if __name__ == "__main__":
    completed = execute(parser().parse_args())
    print(json.dumps({"status": completed["status"], "scope": completed["scope"], "metrics": completed["metrics"]}))
