"""Extend the frozen 20-resample experiment to all 100 seeds without reruns.

Original completed jobs remain in their original directories. Their exact
artifact records and executed commands are bound in extension.json; only the
remaining 160 native jobs are scheduled through the unchanged pilot runner.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import time
import uuid

import run_pilot as pilot
import score


ARTIFACTS = ("raw.adj", "stdout.log", "stderr.log", "time.tsv", "metrics.json", "scores.npz")
CODE = Path(__file__).resolve().parent


def write_checkpoint(path, value, *, attempts=100, delay=.1):
    """Atomic JSON replacement with bounded retries for Windows reader handles."""
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
        for attempt in range(attempts):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt + 1 == attempts:
                    raise
                time.sleep(delay)
    finally:
        if temporary.exists():
            temporary.unlink()


def protocol_signature(plan):
    def content(value):
        return value["sha256"], value["bytes"]
    return {
        "inputs": {name: content(value) for name, value in plan["inputs"].items()},
        "components": {arm: {"binary": content(component["binary"]),
                             "config": {name: content(value) for name, value in component["config"].items()},
                             "historical_run": content(component["historical_run"]),
                             "build_record": content(component["build_record"])}
                       for arm, component in plan["components"].items()},
        "parameters": plan["parameters"], "source_scope": plan["source_scope"],
        "evaluated_source_count": plan["evaluated_source_count"],
        "evaluated_sources": content(plan["evaluated_sources"]),
        "labels": content(plan["labels"]), "universe": plan["universe"],
        "wsl_distro": plan["execution"]["wsl_distro"],
    }


def check_prepared_binding(plan):
    prepared = pilot.read_json(plan["inputs"]["prepare_manifest"]["path"])
    mapping = {"expression": "expression.exp", "full_sig_hubs": "hubs.txt",
               "gene_selection": "gene_selection.tsv", "eligible_sources": "reference_eligible_sources.tsv",
               "positive_edges": "reference_positive_edges.tsv"}
    for key, name in mapping.items():
        if plan["inputs"][key]["sha256"] != prepared["outputs"][name]["sha256"]:
            raise ValueError("Reference/input differs from original prepared-output hash: " + key)


def checked_job(plan, arm, seed):
    directory = Path(plan["out"]) / "jobs" / arm / f"seed_{seed:03d}"
    job_path = directory / "job.json"
    job = pilot.read_json(job_path)
    if job.get("status") != "complete" or (job.get("arm"), job.get("seed")) != (arm, seed):
        raise ValueError("Completed job identity differs from its source plan")
    expected_command = pilot.native_command(plan, arm, seed, directory)
    if job.get("command") != expected_command:
        raise ValueError("Completed job executed command differs from its frozen source plan")
    if set(job.get("artifacts", {})) != set(ARTIFACTS):
        raise ValueError("Completed job requires exactly the six frozen artifacts")
    for name in ARTIFACTS:
        artifact = job["artifacts"][name]
        if Path(artifact["path"]).resolve() != (directory / name).resolve():
            raise ValueError("Job artifact path is not its original named artifact")
        pilot.verify_record(artifact)
    metrics = pilot.read_json(directory / "metrics.json")
    if metrics.get("status") != "complete" or (metrics.get("arm"), metrics.get("seed")) != (arm, seed):
        raise ValueError("Metric identity differs from completed native job")
    if any(metrics.get(key) != plan["universe"][key] for key in
           ("candidate_pairs", "reference_positive_pairs", "reference_negative_pairs", "random_positive_fraction")):
        raise ValueError("Completed metrics use a different scoring universe")
    if [row["k"] for row in metrics["top_k"]] != plan["parameters"]["ks"]:
        raise ValueError("Completed metrics use different prespecified k values")
    pilot.validate_log((directory / "stdout.log").read_text(encoding="utf-8"),
                       sources=plan["evaluated_source_count"],
                       genes=pilot.read_json(plan["universe_file"]["path"])["n_targets"], arm=arm)
    return job_path, job


def create_extension(pilot_plan, out):
    old_path = Path(pilot_plan).resolve(strict=True)
    old = pilot.verify_plan(old_path)
    if len(old["seeds"]) != 20 or old["selection"]["count"] != 20:
        raise ValueError("Reuse requires the original completed 20-resample pilot")
    if (old_path.parent / ".run.lock").exists():
        raise ValueError("Original pilot still has an active/stale run lock")
    check_prepared_binding(old)
    source_records = []
    # Verify every original artifact before creating any new run directory.
    for seed in old["seeds"]:
        for arm in pilot.ARMS:
            path, job = checked_job(old, arm, seed)
            source_records.append({"arm": arm, "seed": seed, "job_record": pilot.record(path),
                                   "executed_command": job["command"], "artifacts": job["artifacts"]})
    historical_root = Path(old["components"]["before"]["historical_run"]["path"]).parents[1]
    new = pilot.create_plan(historical_root, out, old["smoke_proof"]["path"], count=100,
                            selection_seed=old["selection"]["random_seed"],
                            source_scope=old["source_scope"], wsl_distro=old["execution"]["wsl_distro"])
    if protocol_signature(new) != protocol_signature(old):
        raise ValueError("New 100-seed protocol differs from the original pilot")
    new["label"] = "THP-1 full 100-resample raw-MI sampling comparison; reconstructed response reference"
    new["limitations"] = ["One hundred computational resamples are not independent biological replicates."] + [
        text for text in new["limitations"] if "20-resample" not in text]
    new["selection"]["interpretation"] = "All original seeds 1 through 100; no further result-dependent selection"
    new["code"]["extend_pilot.py"] = pilot.record(Path(__file__))
    new["code"]["report.py"] = pilot.record(CODE / "report.py")
    new_path = Path(out).resolve() / "plan.json"
    write_checkpoint(new_path, new)
    extension = {"schema": 1, "status": "ready", "new_plan": pilot.record(new_path),
                 "original_pilot_plan": pilot.record(old_path),
                 "extension_script": pilot.record(Path(__file__)),
                 "reused_job_count": len(source_records), "new_native_job_count": 200 - len(source_records),
                 "reused_jobs": source_records,
                 "reuse_policy": "Reference original immutable job/artifact paths; no copying, hardlinking, native rerun, or original modification"}
    pilot.write_json(new_path.parent / "extension.json", extension)
    return new, extension


def verify_extension(path):
    path = Path(path).resolve(strict=True)
    plan = pilot.verify_plan(path)
    extension = pilot.read_json(path.parent / "extension.json")
    if extension.get("schema") != 1 or extension.get("status") != "ready":
        raise ValueError("Unknown extension schema/state")
    if Path(extension["new_plan"]["path"]).resolve() != path:
        raise ValueError("Extension points to a different new plan")
    pilot.verify_record(extension["new_plan"])
    pilot.verify_record(extension["extension_script"])
    old_path = pilot.verify_record(extension["original_pilot_plan"])
    old = pilot.verify_plan(old_path)
    check_prepared_binding(old)
    check_prepared_binding(plan)
    if plan["seeds"] != list(range(1, 101)) or len(old["seeds"]) != 20:
        raise ValueError("Extension must cover all 100 original seeds and reuse the fixed 20")
    if protocol_signature(plan) != protocol_signature(old):
        raise ValueError("Extension protocol changed")
    expected = {(arm, seed) for seed in old["seeds"] for arm in pilot.ARMS}
    observed = [(row["arm"], row["seed"]) for row in extension["reused_jobs"]]
    if set(observed) != expected or len(observed) != len(expected):
        raise ValueError("Reused-job population changed")
    if extension["reused_job_count"] != 40 or extension["new_native_job_count"] != 160:
        raise ValueError("Unexpected extension job counts")
    for row in extension["reused_jobs"]:
        pilot.verify_record(row["job_record"])
        original_dir = Path(old["out"]) / "jobs" / row["arm"] / f"seed_{row['seed']:03d}"
        if Path(row["job_record"]["path"]).resolve() != (original_dir / "job.json").resolve():
            raise ValueError("Reused job record is outside the original pilot")
        if row["executed_command"] != pilot.native_command(old, row["arm"], row["seed"], original_dir):
            raise ValueError("Reused command binding changed")
    return plan, extension, old


def _reused_results(extension, old):
    results = []
    for row in extension["reused_jobs"]:
        path, job = checked_job(old, row["arm"], row["seed"])
        if job["command"] != row["executed_command"] or job["artifacts"] != row["artifacts"]:
            raise ValueError("Original cached job differs from bound extension record")
        results.append({**job, "reuse_origin": {"pilot_plan": extension["original_pilot_plan"],
                                                "job_record": row["job_record"],
                                                "native_rerun": False}})
    return results


def run_or_verify_job(plan, universe, arm, seed):
    """Resume only after strict command, path, input-universe and hash checks."""
    complete = Path(plan["out"]) / "jobs" / arm / f"seed_{seed:03d}" / "job.json"
    if complete.is_file():
        _, job = checked_job(plan, arm, seed)
        print(f"VERIFIED {arm} seed {seed}", flush=True)
        return job
    return pilot.run_job(plan, universe, arm, seed)


def make_report(plan_path, output, *, plots=True):
    import report
    plan, extension, old = verify_extension(plan_path)
    jobs = _reused_results(extension, old)
    reused = {(row["arm"], row["seed"]) for row in extension["reused_jobs"]}
    for seed in plan["seeds"]:
        for arm in pilot.ARMS:
            if (arm, seed) not in reused:
                _, job = checked_job(plan, arm, seed)
                jobs.append(job)
    paths = [Path(job["artifacts"]["metrics.json"]["path"]) for job in jobs]
    results = [pilot.read_json(path) for path in paths]
    summary = report.build_report(results, plan, Path(output), plots=plots)
    provenance = {"plan": pilot.record(plan_path),
                  "extension": pilot.record(Path(plan_path).parent / "extension.json"),
                  "original_pilot_plan": extension["original_pilot_plan"],
                  "score_results": [pilot.record(path) for path in paths],
                  "report_script_sha256": pilot.digest(CODE / "report.py"),
                  "reused_jobs": 40, "new_jobs": 160}
    pilot.write_json(Path(output) / "report_provenance.json", provenance)
    return summary


def run_extension(path, *, workers=12, report_out=None, plots=True):
    if not 1 <= workers <= 16:
        raise ValueError("Workers must be between 1 and 16")
    plan, extension, old = verify_extension(path)
    out = Path(plan["out"])
    lock, token = out / ".run.lock", uuid.uuid4().hex
    with lock.open("x", encoding="utf-8") as stream:
        json.dump({"pid": os.getpid(), "token": token}, stream)
    try:
        completed = _reused_results(extension, old)
        reused = {(row["arm"], row["seed"]) for row in extension["reused_jobs"]}
        pending = [(arm, seed) for seed in plan["seeds"] for arm in pilot.ARMS if (arm, seed) not in reused]
        universe = score.load_universe(Path(plan["inputs"]["expression"]["path"]).parent)
        if universe.definition_sha256 != plan["universe"]["definition_sha256"]:
            raise ValueError("Loaded universe differs from frozen full plan")
        failures = []
        write_checkpoint(out / "status.json", {"status": "running", "workers": workers,
                                               "completed": len(completed), "total": 200,
                                               "reused_jobs": 40, "new_jobs_scheduled": len(pending)})
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(run_or_verify_job, plan, universe, arm, seed): (arm, seed) for arm, seed in pending}
            for future in as_completed(futures):
                arm, seed = futures[future]
                try:
                    completed.append(future.result())
                except Exception as error:
                    failures.append({"arm": arm, "seed": seed, "error": str(error)})
                    print(f"FAIL {arm} seed {seed}: {error}", flush=True)
                write_checkpoint(out / "status.json", {"status": "running", "workers": workers,
                                                       "completed": len(completed), "total": 200,
                                                       "reused_jobs": 40, "failures": failures})
        result = {"status": "failed" if failures else "complete", "plan": pilot.record(path),
                  "extension": pilot.record(out / "extension.json"), "jobs": completed,
                  "completed": len(completed), "total": 200, "reused_jobs": 40,
                  "new_jobs_scheduled": len(pending), "failures": failures}
        write_checkpoint(out / "status.json", result)
        if failures:
            raise RuntimeError(f"{len(failures)} extension jobs failed; artifacts retained for inspection")
        if report_out is not None:
            make_report(path, report_out, plots=plots)
        return result
    finally:
        if lock.exists() and pilot.read_json(lock).get("token") == token:
            lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan")
    plan.add_argument("--pilot-plan", required=True, type=Path)
    plan.add_argument("--out", required=True, type=Path)
    run = commands.add_parser("run")
    run.add_argument("--plan", required=True, type=Path)
    run.add_argument("--workers", type=int, default=12)
    run.add_argument("--report-out", type=Path)
    run.add_argument("--no-plots", action="store_true")
    report = commands.add_parser("report")
    report.add_argument("--plan", required=True, type=Path)
    report.add_argument("--out", required=True, type=Path)
    report.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    if args.command == "plan":
        _, extension = create_extension(args.pilot_plan, args.out)
        print(json.dumps({"status": "planned", "reused_jobs": extension["reused_job_count"],
                          "new_native_jobs": extension["new_native_job_count"], "out": str(args.out)}))
    elif args.command == "run":
        result = run_extension(args.plan, workers=args.workers, report_out=args.report_out, plots=not args.no_plots)
        print(json.dumps({"status": result["status"], "completed": result["completed"]}))
    else:
        result = make_report(args.plan, args.out, plots=not args.no_plots)
        print(json.dumps({"status": result["status"], "matched_seeds": result["n_matched_seeds"]}))


if __name__ == "__main__":
    main()
