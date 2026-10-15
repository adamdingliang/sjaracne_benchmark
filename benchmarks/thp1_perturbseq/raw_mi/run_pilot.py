#!/usr/bin/env python3
"""Plan and run a matched raw-MI pilot with immutable inputs and per-job records.

The two old, pinned binaries are used unchanged. No threshold, DPI or consensus
is applied. Historical data, scripts and run manifests are never modified.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import re
import subprocess
import sys
import time
import uuid

import numpy as np

import score


BASE_COMMIT = "2922ec9a57d3da4e88b849b840643f543f49807c"
SAMPLING_COMMIT = "3a93d10e862ba43229e60ca6491ee38143422379"
UNIVERSE_SHA256 = "22705ef6ee9ab66230368c91c159376b51e8a66e5b135af72a74db4fe725ab95"
ARMS = ("before", "after")
KS = (1000, 5000, 10000, 50000, 100000)
CODE = Path(__file__).resolve().parent
REPO = CODE.parents[2]


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


def write_json(path, value, *, replace=False):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
    if replace:
        os.replace(temporary, path)
    else:
        try:
            os.link(temporary, path)
        finally:
            temporary.unlink()


def verify_record(value):
    path = Path(value["path"]).resolve(strict=True)
    if path.stat().st_size != value["bytes"] or digest(path) != value["sha256"]:
        raise ValueError(f"Frozen artifact changed: {path}")
    return path


def select_seeds(count=20, selection_seed=20261015):
    if not 1 <= count <= 100:
        raise ValueError("Pilot count must be between 1 and 100")
    return sorted(random.Random(selection_seed).sample(range(1, 101), count))


def wsl_path(path):
    path = Path(path).resolve()
    if os.name != "nt":
        return str(path)
    if not re.fullmatch(r"[A-Za-z]:", path.drive):
        raise ValueError("Native WSL jobs require a drive-letter path")
    return "/mnt/" + path.drive[0].lower() + path.as_posix()[2:]


def native_command(plan, arm, seed, jobdir):
    if arm not in ARMS or seed not in plan["seeds"]:
        raise ValueError("Job is outside the frozen pilot")
    component = plan["components"][arm]
    command = [wsl_path(component["binary"]["path"]),
               "-i", wsl_path(plan["inputs"]["expression"]["path"]),
               "-l", wsl_path(plan["inputs"]["full_sig_hubs"]["path"]),
               "-s", wsl_path(plan["evaluated_sources"]["path"]),
               "-H", wsl_path(component["config_dir"]),
               "-a", "adaptive_partitioning", "-N", "40", "-S", str(seed),
               "-p", "1", "-t", "0", "-e", "1", "-n", "0", "-f", "0", "0"]
    command += ["-r", "1"] if arm == "before" else ["-u", "80%"]
    command += ["-o", wsl_path(Path(jobdir) / "raw.adj")]
    measured = ["/usr/bin/time", "-f", "%e\t%M", "-o",
                wsl_path(Path(jobdir) / "time.tsv"), *command]
    if os.name == "nt":
        measured = ["wsl.exe", "-d", plan["execution"]["wsl_distro"], "--", *measured]
    return measured


def validate_log(text, *, sources, genes, arm):
    marker = re.search(r"Marker No:\s*(\d+)\s*\((\d+) active\)", text)
    if not marker or tuple(map(int, marker.groups())) != (genes, genes):
        raise ValueError("Native log does not confirm all inference genes active")
    if not re.search(r"Gene:\s*" + str(sources) + r"\s+Time:\s*\d", text):
        raise ValueError("Native log lacks completed traversal of every evaluated source")
    if "Maximum observed npar:" not in text:
        raise ValueError("Native writer did not report completion")
    if "Cannot find probe:" in text or "... ignored." in text:
        raise ValueError("Native parser ignored an expected source or annotation identifier")
    if "Applying DPI" in text or "MI threshold determined" in text:
        raise ValueError("Filtering or DPI unexpectedly executed")
    if arm == "after" and (
            "selected 97 of 121 eligible observations (request: 80%)" not in text):
        raise ValueError("After log does not confirm the frozen 97-of-121 sampling")


def checked_old_run(path, arm):
    run = read_json(path)
    frozen = run["frozen"]
    if run.get("status") != "complete" or frozen["source_commit"] != BASE_COMMIT:
        raise ValueError("Historical input is not the completed pinned baseline/backport")
    if arm == "after" and frozen.get("sampling_commit") != SAMPLING_COMMIT:
        raise ValueError("After arm is not the pinned sampling-only backport")
    if frozen["parameters"]["seeds"] != list(range(1, 101)):
        raise ValueError("Historical seed pool differs from 1 through 100")
    for value in frozen["inputs"].values():
        verify_record(value)
    binary = frozen["components"]["binary"]
    verify_record(binary)
    verify_record(frozen["component_manifest"])
    config = {}
    for name in ("config_threshold.txt", "config_kernel.txt"):
        config[name] = frozen["components"][name]
        verify_record(config[name])
    return frozen, {"historical_run": record(path), "binary": binary,
                    "config_dir": str(Path(config["config_threshold.txt"]["path"]).parent),
                    "config": config, "build_record": record(frozen["component_manifest"]["path"])}


def create_plan(historical_root, out, smoke_proof, *, count=20,
                selection_seed=20261015, source_scope="eligible", wsl_distro="Ubuntu"):
    historical_root = Path(historical_root).resolve(strict=True)
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError("Pilot output must be new; use run to resume an existing plan")
    if source_scope not in {"eligible", "full"}:
        raise ValueError("Unknown source-computation scope")
    proof = read_json(smoke_proof)
    if proof.get("status") != "passed":
        raise ValueError("Raw-MI equivalence smoke has not passed")
    before, before_components = checked_old_run(historical_root / "legacy/run_manifest.json", "before")
    after, after_components = checked_old_run(
        historical_root / "sampling_after_80pct_20261012/run_manifest.json", "after")
    for name in ("expression", "hubs", "prepare_manifest"):
        if before["inputs"][name]["sha256"] != after["inputs"][name]["sha256"]:
            raise ValueError("Historical arms did not use identical prepared inputs")
    for arm, component in (("before", before_components), ("after", after_components)):
        if proof["binaries"][arm]["sha256"] != component["binary"]["sha256"]:
            raise ValueError("Smoke proof used a different native executable")
    actual_proof = proof["cases"]["actual_full_expression"]
    if (actual_proof["expression"]["sha256"] != before["inputs"]["expression"]["sha256"]
            or actual_proof["annotation"]["sha256"] != before["inputs"]["hubs"]["sha256"]):
        raise ValueError("Smoke proof used different expression or full SIG annotation")
    for arm in ARMS:
        comparisons = [row for row in proof["comparisons"]
                       if row["arm"] == arm and row["case"] == "actual_full_expression"]
        if (len(comparisons) != 2 or any(row.get("status") != "passed"
                or not row.get("exact_serialized_mi_equality")
                or not row.get("exact_zero_pattern_equality") for row in comparisons)):
            raise ValueError("Source-scope equivalence was not verified for both arms")
    prepared = Path(before["inputs"]["expression"]["path"]).parent
    universe = score.load_universe(prepared)
    if universe.definition_sha256 != UNIVERSE_SHA256:
        raise ValueError("Eligible response-reference universe changed")
    input_paths = {"expression": prepared / "expression.exp", "full_sig_hubs": prepared / "hubs.txt",
                   "prepare_manifest": prepared / "prepare_manifest.json",
                   "gene_selection": prepared / "gene_selection.tsv",
                   "eligible_sources": prepared / "reference_eligible_sources.tsv",
                   "positive_edges": prepared / "reference_positive_edges.tsv"}
    full_hubs = (prepared / "hubs.txt").read_text(encoding="utf-8").splitlines()
    if len(full_hubs) != 6951 or len(set(full_hubs)) != len(full_hubs):
        raise ValueError("Unexpected original full SIG list")
    evaluated = [hub for hub in full_hubs if source_scope == "full" or hub in set(universe.sources)]
    expected_count = 272 if source_scope == "eligible" else 6951
    if len(evaluated) != expected_count:
        raise ValueError("Unexpected evaluated-source population")
    # Only generated files are written below the fresh output directory.
    (out / "inputs").mkdir(parents=True)
    evaluated_path = out / "inputs/evaluated_sources.txt"
    evaluated_path.write_text("\n".join(evaluated) + "\n", encoding="utf-8", newline="\n")
    np.save(out / "inputs/labels.npy", universe.labels, allow_pickle=False)
    write_json(out / "inputs/universe.json", universe.definition)
    try:
        git_head = subprocess.check_output(["git", "-c", "safe.directory=" + REPO.as_posix(),
                                            "-C", str(REPO), "rev-parse", "HEAD"], text=True).strip()
    except subprocess.CalledProcessError:
        git_head = None
    plan = {
        "schema": 1, "label": "THP-1 exploratory raw-MI sampling pilot; reconstructed response reference",
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "seeds": select_seeds(count, selection_seed), "arms": list(ARMS),
        "selection": {"pool_start": 1, "pool_end": 100, "count": count,
                      "random_seed": selection_seed, "algorithm": "python.random.Random.sample"},
        "source_scope": source_scope, "evaluated_source_count": len(evaluated),
        "evaluated_sources": record(evaluated_path), "out": str(out),
        "inputs": {key: record(path) for key, path in input_paths.items()},
        "labels": record(out / "inputs/labels.npy"),
        "universe_file": record(out / "inputs/universe.json"),
        "universe": {"candidate_pairs": universe.size, "reference_positive_pairs": universe.P,
                     "reference_negative_pairs": universe.N,
                     "random_positive_fraction": universe.P / universe.size,
                     "definition_sha256": universe.definition_sha256},
        "components": {"before": before_components, "after": after_components},
        "smoke_proof": record(smoke_proof),
        "code": {name: record(CODE / name) for name in ("run_pilot.py", "score.py")},
        "parameters": {"p_value": 1, "mi_threshold": 0, "dpi_tolerance": 1, "npar": 40,
                       "ks": list(KS), "primary_k": 5000, "consensus": "none",
                       "before_sampling": "121 draws with replacement",
                       "after_sampling": "97 distinct metacells; ceil(0.8*121)",
                       "native_MI_serialization": "six significant digits; MI ties retained"},
        "execution": {"wsl_distro": wsl_distro, "python": sys.version,
                      "platform": platform.platform(), "numpy": np.__version__,
                      "benchmark_git_commit": git_head},
        "limitations": ["Exploratory 20-resample pilot, not independent biological replicates.",
                        "Same seed IDs do not imply identical selected cells or tie-noise realizations.",
                        "Reconstructed perturbation-response positives, not direct regulatory truth.",
                        "This compares operational sampling protocols with different draw counts.",
                        "No MI cutoff, DPI, recurrence filter, or probability-based consensus.",
                        "Native exact/nonpositive MI zero omissions join the MI=0 tie only after validated completion."],
    }
    write_json(out / "plan.json", plan)
    return plan


def verify_plan(path):
    path = Path(path).resolve(strict=True)
    plan = read_json(path)
    if plan.get("schema") != 1 or plan.get("arms") != list(ARMS):
        raise ValueError("Unknown pilot schema or arms")
    selection = plan["selection"]
    if plan["seeds"] != select_seeds(selection["count"], selection["random_seed"]):
        raise ValueError("Seed selection changed")
    expected = {"p_value": 1, "mi_threshold": 0, "dpi_tolerance": 1,
                "npar": 40, "ks": list(KS), "primary_k": 5000, "consensus": "none"}
    if any(plan["parameters"].get(key) != value for key, value in expected.items()):
        raise ValueError("Raw-MI protocol changed")
    if Path(plan["out"]).resolve() != path.parent:
        raise ValueError("Plan cannot be silently relocated")
    records = [*plan["inputs"].values(), *plan["code"].values(), plan["evaluated_sources"],
               plan["labels"], plan["universe_file"], plan["smoke_proof"]]
    for component in plan["components"].values():
        records += [component["binary"], component["historical_run"], component["build_record"],
                    *component["config"].values()]
    for value in records:
        verify_record(value)
    return plan


def run_job(plan, universe, arm, seed):
    jobdir = Path(plan["out"]) / "jobs" / arm / f"seed_{seed:03d}"
    complete = jobdir / "job.json"
    if complete.is_file():
        job = read_json(complete)
        if job.get("status") != "complete" or (job["arm"], job["seed"]) != (arm, seed):
            raise ValueError("Existing job is not a matching completed artifact")
        for value in job["artifacts"].values():
            verify_record(value)
        print(f"VERIFIED {arm} seed {seed}", flush=True)
        return job
    if jobdir.exists():
        raise FileExistsError(f"Incomplete job directory requires inspection before retry: {jobdir}")
    jobdir.mkdir(parents=True)
    command = native_command(plan, arm, seed, jobdir)
    started = time.monotonic()
    print(f"START {arm} seed {seed}", flush=True)
    with (jobdir / "stdout.log").open("xb") as stdout, (jobdir / "stderr.log").open("xb") as stderr:
        process = subprocess.run(command, stdout=stdout, stderr=stderr,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if process.returncode != 0:
        raise RuntimeError(f"Native {arm} seed {seed} exited {process.returncode}; inspect {jobdir}")
    log = (jobdir / "stdout.log").read_text(encoding="utf-8")
    expected_sources = tuple(Path(plan["evaluated_sources"]["path"]).read_text().splitlines())
    validate_log(log, sources=len(expected_sources), genes=len(universe.targets), arm=arm)
    scores, validation = score.parse_adjacency(
        jobdir / "raw.adj", universe, expected_sources=expected_sources,
        expected_subnetwork=wsl_path(plan["evaluated_sources"]["path"]), arm=arm)
    metrics = score.score_arrays(scores, universe.labels, ks=plan["parameters"]["ks"])
    metrics.update(arm=arm, seed=seed, raw_validation=validation)
    write_json(jobdir / "metrics.json", metrics)
    np.savez_compressed(jobdir / "scores.npz", scores=scores)
    timing = (jobdir / "time.tsv").read_text().strip().split("\t")
    if len(timing) != 2:
        raise ValueError("Invalid GNU time output")
    job = {"status": "complete", "arm": arm, "seed": seed, "command": command,
           "native_wall_seconds": float(timing[0]), "native_peak_rss_kib": int(timing[1]),
           "total_wall_seconds": time.monotonic() - started,
           "artifacts": {name: record(jobdir / name) for name in
                         ("raw.adj", "stdout.log", "stderr.log", "time.tsv", "metrics.json", "scores.npz")}}
    write_json(complete, job)
    print(f"DONE {arm} seed {seed}: {job['total_wall_seconds']:.1f}s; "
          f"AUROC={metrics['AUROC_MI_ties']:.6f}", flush=True)
    return job


def run_plan(path, workers=8, limit=None):
    if not 1 <= workers <= 16:
        raise ValueError("Workers must be between 1 and 16")
    plan = verify_plan(path)
    out = Path(plan["out"])
    lock = out / ".run.lock"
    token = uuid.uuid4().hex
    with lock.open("x", encoding="utf-8") as stream:
        json.dump({"pid": os.getpid(), "token": token}, stream)
    try:
        universe = score.load_universe(Path(plan["inputs"]["expression"]["path"]).parent)
        if universe.definition_sha256 != plan["universe"]["definition_sha256"]:
            raise ValueError("Loaded reference universe differs from plan")
        all_jobs = [(arm, seed) for seed in plan["seeds"] for arm in ARMS]
        if limit is not None and not 1 <= limit <= len(all_jobs):
            raise ValueError("Execution limit must be between one and the frozen job count")
        jobs = all_jobs if limit is None else all_jobs[:limit]
        completed, failures = [], []
        write_json(out / "status.json", {"status": "running", "workers": workers,
                                        "completed": 0, "total": len(jobs)}, replace=True)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(run_job, plan, universe, arm, seed): (arm, seed) for arm, seed in jobs}
            for future in as_completed(futures):
                arm, seed = futures[future]
                try:
                    completed.append(future.result())
                except Exception as error:
                    failures.append({"arm": arm, "seed": seed, "error": str(error)})
                    print(f"FAIL {arm} seed {seed}: {error}", flush=True)
                write_json(out / "status.json", {"status": "running", "workers": workers,
                                                "completed": len(completed), "total": len(jobs),
                                                "failures": failures}, replace=True)
        state = ("complete" if len(jobs) == len(all_jobs) else "partial_complete") if not failures else "failed"
        result = {"status": state, "plan": record(path), "jobs": completed,
                  "failures": failures, "completed": len(completed), "total": len(all_jobs),
                  "scheduled": len(jobs)}
        write_json(out / "status.json", result, replace=True)
        if failures:
            raise RuntimeError(f"{len(failures)} pilot jobs failed; outputs preserved for inspection")
        return result
    finally:
        if lock.exists() and read_json(lock).get("token") == token:
            lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    make = commands.add_parser("plan", help="Freeze inputs and seed selection; do not launch inference")
    make.add_argument("--historical-root", required=True, type=Path)
    make.add_argument("--out", required=True, type=Path)
    make.add_argument("--smoke-proof", required=True, type=Path)
    make.add_argument("--count", type=int, default=20)
    make.add_argument("--selection-seed", type=int, default=20261015)
    make.add_argument("--source-scope", choices=("eligible", "full"), default="eligible")
    make.add_argument("--wsl-distro", default="Ubuntu")
    execute = commands.add_parser("run", help="Execute or verify completed jobs from the frozen plan")
    execute.add_argument("--plan", required=True, type=Path)
    execute.add_argument("--workers", type=int, default=8)
    execute.add_argument("--limit", type=int, help="Validate only the first few frozen jobs before the full pilot")
    args = parser.parse_args()
    if args.command == "plan":
        result = create_plan(args.historical_root, args.out, args.smoke_proof, count=args.count,
                             selection_seed=args.selection_seed, source_scope=args.source_scope,
                             wsl_distro=args.wsl_distro)
        print(json.dumps({"status": "planned", "seeds": result["seeds"],
                          "jobs": 2 * len(result["seeds"]), "out": result["out"]}))
    else:
        result = run_plan(args.plan, args.workers, args.limit)
        print(json.dumps({"status": result["status"], "completed": result["completed"]}))


if __name__ == "__main__":
    main()
