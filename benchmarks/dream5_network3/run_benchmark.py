#!/usr/bin/env python3
"""Frozen, resumable Network3 sampling/DPI benchmark using the Net1 PR70 binary.

Planning launches nothing. Run --smoke first (10 native jobs), then run without
--smoke to verify those outputs and execute the other 50 direct-inference jobs.
No adjacency replay, consensus, engine edits or parameter optimization is used.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import copy
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import threading
import time
import uuid


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
ENGINE_COMMIT = "8c5f26c4fb5e05c7b280bcaa7d5a6461125a6aa3"
BINARY_SHA256 = "8264118ea83b8c37b16000ce0c36087e3fe03a28cb1687eba5329370abb8c33e"
EXPRESSION_SHA256 = "a8ea101efa68ae9f047ad5ae4d625e5ddb3b8d03eb6757407c332c46397409f9"
HUBS_SHA256 = "69dff62d76c1cf5cb45ecfa4301734b8c4885bd8cdbc0d1d1a824fab7ab8cd5b"
CONFIG_SHA256 = {
    "config_threshold.txt": "bc37e881c828d3098def89e1f5e465367e8ea900fef2fbb723fbb054aeb086cc",
    "config_kernel.txt": "4a7d155ac4a1fc5ed835af5b64b58323c3fe2a3ed76084d129b4f362199f0041",
}
SOURCE_SHA256 = {
    "input data/net3_expression_data.tsv": "b49b67d278b27d988c68652df76d0dc9c5e316abb774e6eac30b35b2712f9e2c",
    "input data/net3_transcription_factors.tsv": HUBS_SHA256,
    "gold standard/DREAM5_NetworkInference_GoldStandard_Network3.tsv": "657c9d413e24279466df6ed3219c12c42b59068b0d4d92b28ed4f1e078ba78d3",
    "input data/net3_chip_features.tsv": "65801c68bda99d36236865b7f17af94a5159df97a5833906131bb224868dc765",
    "anonymization/net3_gene_ids.tsv": "a3fa4f3690c26774492591a3fcd303b21678df333e908c10e27cd6a53a73dcd9",
}
DATASET = {"genes": 4511, "profiles": 805, "TFs": 334, "labelled_pairs": 152280,
           "positive_pairs": 2066, "negative_pairs": 150214, "scored_sources": 141,
           "scored_targets": 1081, "full_TF_nonself_pairs": 1506340, "unlabelled_pairs": 1354060}
ARMS = ("legacy", "u64", "u80", "u90")
SEEDS = (1, 2, 3)
STAGES = ("raw", "nominal_pre", "nominal_post", "fixed_pre", "fixed_post")
FIXED_MI = 0.03759353615996272
SAMPLING = {
    "legacy": {"flag": "-r", "value": "1", "draws": 805, "population": 805,
               "method": "legacy bootstrap with replacement"},
    **{f"u{fraction}": {"flag": "-u", "value": f"{fraction}%", "draws": draws,
                        "population": 805, "method": "fixed-size without replacement"}
       for fraction, draws in ((64, 516), (80, 644), (90, 725))},
}
PARAMETERS = {"npar": 40, "nominal_p": 1e-7, "fixed_mi": FIXED_MI,
              "nominal_cutoffs": {"legacy": 0.03072977561120847, "u64": 0.045710708833873417,
                                   "u80": FIXED_MI, "u90": 0.033795801418232164},
              "measurement_noise": 0, "filter_mean": 0, "filter_cv": 0, "consensus": "none"}
PRIMARY = {"contrast": ["legacy", "u80"], "stage": "nominal_post", "endpoint": "average_precision"}
ARTIFACTS = ("raw.adj", "stdout.log", "stderr.log", "time.tsv", "validation.json")
CODE_NAMES = ("run_benchmark.py", "metrics.py", "prepare.py")
_METRICS_IMPORT_LOCK = threading.Lock()


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def record(path, expected=None):
    path = Path(path).resolve(strict=True)
    value = {"path": str(path), "sha256": digest(path), "bytes": path.stat().st_size}
    if expected is not None and value["sha256"] != expected:
        raise ValueError(f"Pinned file hash mismatch: {path}")
    return value


def verify_record(value):
    path = Path(value["path"]).resolve(strict=True)
    if path.stat().st_size != value["bytes"] or digest(path) != value["sha256"]:
        raise ValueError(f"Frozen artifact changed: {path}")
    return path


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"),
                      parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)))


def write_json(path, value, *, replace=False, attempts=100):
    """Atomic same-directory writes, with bounded Windows-reader retries."""
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, allow_nan=False)
            stream.write("\n")
        if not replace:
            os.link(temporary, path)  # Fails instead of overwriting an existing artifact.
            return
        for attempt in range(attempts):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt + 1 == attempts:
                    raise
                time.sleep(.1)
    finally:
        if temporary.exists():
            temporary.unlink()


def metrics_module():
    # A unique module name avoids clashes with other benchmark metrics.py files.
    name = "sjaracne_dream5_network3_metrics"
    with _METRICS_IMPORT_LOCK:
        if name not in sys.modules:
            spec = importlib.util.spec_from_file_location(name, HERE / "metrics.py")
            if spec is None or spec.loader is None:
                raise ImportError("Network3 metrics.py is unavailable")
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            try:
                spec.loader.exec_module(module)
            except Exception:
                del sys.modules[name]
                raise
        return sys.modules[name]


def wsl_path(path):
    path = Path(path).resolve()
    if os.name != "nt":
        return str(path)
    if not re.fullmatch(r"[A-Za-z]:", path.drive):
        raise ValueError("WSL native inputs require drive-letter paths")
    return "/mnt/" + path.drive[0].lower() + path.as_posix()[2:]


def fresh_output(path):
    path = Path(path).resolve()
    boundary = (REPO / "runs").resolve()
    if path == boundary or not path.is_relative_to(boundary):
        raise ValueError("Output must be a new child directory under the repository runs/")
    if path.exists():
        raise FileExistsError("Output exists; resume its frozen plan instead")
    return path


def create_plan(prepared_root, binary, config, out, *, distro="Ubuntu"):
    prepared_root, binary, config = (Path(value).resolve(strict=True) for value in (prepared_root, binary, config))
    out = fresh_output(out)
    if not distro or any(character in distro for character in "\r\n"):
        raise ValueError("Invalid WSL distribution name")
    preparation = read_json(prepared_root / "provenance.json")
    if (preparation.get("schema"), preparation.get("status"), preparation.get("counts")) != (1, "prepared", DATASET):
        raise ValueError("Prepared input does not match the frozen Network3 dataset")
    inputs = {"expression": record(prepared_root / "dream5_net3.exp", EXPRESSION_SHA256),
              "hubs": record(prepared_root / "all334_tfs.txt", HUBS_SHA256),
              "preparation": record(prepared_root / "provenance.json")}
    for key, name in (("expression", "dream5_net3.exp"), ("hubs", "all334_tfs.txt")):
        expected = preparation["outputs"][name]
        if any(inputs[key][field] != expected[field] for field in ("sha256", "bytes")):
            raise ValueError("Prepared output differs from preparation provenance")
    if set(preparation["source_files"]) != set(SOURCE_SHA256):
        raise ValueError("Unexpected Network3 source-file population")
    sources = {}
    for name, expected in SOURCE_SHA256.items():
        source = preparation["source_files"][name]
        if source["sha256"] != expected:
            raise ValueError("Source provenance uses a different DREAM5 file")
        verify_record(source)
        sources[name] = source
    component = {"source_commit": ENGINE_COMMIT, "binary": record(binary, BINARY_SHA256),
                 "config_dir": str(config),
                 "config": {name: record(config / name, expected) for name, expected in CONFIG_SHA256.items()}}
    code = {name: record(HERE / name) for name in CODE_NAMES}
    plan = {"schema": 1, "dataset_name": "DREAM5 Network3 E. coli",
            "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "dataset": dict(DATASET), "inputs": inputs, "source_files": sources,
            "component": component, "code": code,
            "approved_protocol": record(HERE / "PLAN_2026-10-15.md"),
            "out": str(out), "arms": list(ARMS),
            "seeds": list(SEEDS), "stages": list(STAGES), "sampling": copy.deepcopy(SAMPLING),
            "parameters": copy.deepcopy(PARAMETERS), "primary": copy.deepcopy(PRIMARY),
            "execution": {"distro": distro, "python": sys.version, "platform": platform.platform()},
            "design": "Same pinned Net1 PR70 binary for legacy and all without-replacement arms; all334 TFs, all4511 genes; direct native inference for every stage",
            "reference_policy": "Only 152280 explicitly labelled directed nonself pairs; all other pairs are unlabelled, not negatives",
            "smoke": {"seed": 1, "arms": ["legacy", "u80"], "stages": list(STAGES), "jobs": 10},
            "limitations": ["Three computational seed IDs are not independent biological datasets.",
                            "Protocols differ in draw count, selected observations and tie-noise RNG consumption.",
                            "Nominal affine p-to-MI thresholds differ with sample count; common numeric MI is a separately fixed control.",
                            "Biological reference is incomplete; zero labels are operational negatives.",
                            "No PR71 calibration, consensus or downstream activity assessment."]}
    out.mkdir(parents=True)
    write_json(out / "plan.json", plan)
    return plan


def verify_plan(path):
    path = Path(path).resolve(strict=True)
    plan = read_json(path)
    if (plan.get("schema") != 1 or plan.get("arms") != list(ARMS)
            or plan.get("seeds") != list(SEEDS) or plan.get("stages") != list(STAGES)
            or plan.get("dataset") != DATASET or plan.get("sampling") != SAMPLING
            or plan.get("parameters") != PARAMETERS or plan.get("primary") != PRIMARY):
        raise ValueError("Frozen Network3 protocol changed")
    if path.name != "plan.json" or Path(plan["out"]).resolve() != path.parent:
        raise ValueError("Plan cannot be relocated")
    if plan.get("smoke") != {"seed": 1, "arms": ["legacy", "u80"], "stages": list(STAGES), "jobs": 10}:
        raise ValueError("Engineering smoke population changed")
    if set(plan["inputs"]) != {"expression", "hubs", "preparation"} or set(plan["code"]) != set(CODE_NAMES):
        raise ValueError("Frozen runtime inputs/code population changed")
    if plan["inputs"]["expression"]["sha256"] != EXPRESSION_SHA256 or plan["inputs"]["hubs"]["sha256"] != HUBS_SHA256:
        raise ValueError("Frozen expression or full TF list changed")
    if set(plan["source_files"]) != set(SOURCE_SHA256):
        raise ValueError("Frozen source population changed")
    for name, value in plan["source_files"].items():
        if value["sha256"] != SOURCE_SHA256[name]:
            raise ValueError("Frozen source digest changed")
    component = plan["component"]
    if component["source_commit"] != ENGINE_COMMIT or component["binary"]["sha256"] != BINARY_SHA256:
        raise ValueError("Frozen native executable changed")
    if set(component["config"]) != set(CONFIG_SHA256):
        raise ValueError("Frozen native configuration population changed")
    for name, value in component["config"].items():
        if value["sha256"] != CONFIG_SHA256[name] or Path(value["path"]).resolve() != (Path(component["config_dir"]) / name).resolve():
            raise ValueError("Frozen config path or digest changed")
    for name, value in plan["code"].items():
        if Path(value["path"]).resolve() != (HERE / name).resolve():
            raise ValueError("Frozen code path differs from the executing implementation")
    if Path(plan["approved_protocol"]["path"]).resolve() != (HERE / "PLAN_2026-10-15.md").resolve():
        raise ValueError("Approved protocol points to a different document")
    for value in [*plan["inputs"].values(), *plan["source_files"].values(), *plan["code"].values(),
                  component["binary"], *component["config"].values(), plan["approved_protocol"]]:
        verify_record(value)
    return plan


def job_directory(plan, arm, seed, stage):
    if arm not in ARMS or seed not in SEEDS or stage not in STAGES:
        raise ValueError("Job is outside the frozen comparison")
    return Path(plan["out"]) / "jobs" / arm / f"seed_{seed:03d}" / stage


def native_command(plan, arm, seed, stage):
    directory = job_directory(plan, arm, seed, stage)
    command = [wsl_path(plan["component"]["binary"]["path"]),
               "-i", wsl_path(plan["inputs"]["expression"]["path"]),
               "-l", wsl_path(plan["inputs"]["hubs"]["path"]),
               "-s", wsl_path(plan["inputs"]["hubs"]["path"]),
               "-H", wsl_path(plan["component"]["config_dir"]),
               "-a", "adaptive_partitioning", "-N", "40", "-S", str(seed),
               "-n", "0", "-f", "0", "0"]
    if stage == "raw":
        command += ["-p", "1", "-t", "0", "-e", "1"]
    elif stage.startswith("nominal_"):
        command += ["-p", "1e-7", "-e", "1" if stage.endswith("pre") else "0"]
    else:
        command += ["-p", "1", "-t", format(FIXED_MI, ".17g"),
                    "-e", "1" if stage.endswith("pre") else "0"]
    sampler = plan["sampling"][arm]
    command += [sampler["flag"], sampler["value"], "-o", wsl_path(directory / "raw.adj")]
    command = ["/usr/bin/time", "-f", "%e\t%M", "-o", wsl_path(directory / "time.tsv"), *command]
    if os.name == "nt":
        command = ["wsl.exe", "-d", plan["execution"]["distro"], "--", *command]
    return command


def checked_job(plan, arm, seed, stage):
    directory = job_directory(plan, arm, seed, stage)
    path = directory / "job.json"
    value = read_json(path)
    if value.get("status") != "complete" or (value.get("arm"), value.get("seed"), value.get("stage")) != (arm, seed, stage):
        raise ValueError("Completed job identity differs from the frozen job")
    if value.get("plan_sha256") != digest(Path(plan["out"]) / "plan.json") or value.get("command") != native_command(plan, arm, seed, stage):
        raise ValueError("Completed native command/plan attribution changed")
    if value.get("native_exit_code") != 0 or set(value.get("artifacts", {})) != set(ARTIFACTS):
        raise ValueError("Completed job lacks successful execution and exact artifacts")
    for name, artifact in value["artifacts"].items():
        if Path(artifact["path"]).resolve() != (directory / name).resolve():
            raise ValueError("Completed artifact is outside its named job directory")
        verify_record(artifact)
    if read_json(directory / "validation.json").get("status") != "passed":
        raise ValueError("Completed native output did not pass validation")
    return value


def run_job(plan, arm, seed, stage):
    directory = job_directory(plan, arm, seed, stage)
    if (directory / "job.json").is_file():
        value = checked_job(plan, arm, seed, stage)
        print(f"VERIFIED {arm} seed {seed} {stage}", flush=True)
        return value
    if directory.exists():
        raise FileExistsError(f"Incomplete native directory requires inspection, not overwrite: {directory}")
    directory.mkdir(parents=True)
    command = native_command(plan, arm, seed, stage)
    started = time.monotonic()
    print(f"START {arm} seed {seed} {stage}", flush=True)
    with (directory / "stdout.log").open("xb") as stdout, (directory / "stderr.log").open("xb") as stderr:
        process = subprocess.run(command, stdout=stdout, stderr=stderr, check=False,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if process.returncode != 0:
        raise RuntimeError(f"Native exit {process.returncode}: {directory}")
    if (directory / "stderr.log").stat().st_size:
        raise ValueError(f"Unexpected native stderr; inspect {directory}")
    timing = (directory / "time.tsv").read_text(encoding="utf-8").strip().split("\t")
    if len(timing) != 2:
        raise ValueError("Malformed GNU time output")
    seconds, rss = float(timing[0]), int(timing[1])
    if not math.isfinite(seconds) or seconds < 0 or rss <= 0:
        raise ValueError("Invalid native wall-time or RSS")
    validation = metrics_module().validate_job_output(directory / "raw.adj", directory / "stdout.log",
                                                       plan=plan, arm=arm, stage=stage)
    if validation.get("status") != "passed":
        raise ValueError("Native output validator did not pass")
    write_json(directory / "validation.json", validation)
    value = {"status": "complete", "arm": arm, "seed": seed, "stage": stage,
             "plan_sha256": digest(Path(plan["out"]) / "plan.json"), "command": command,
             "native_exit_code": 0, "native_wall_seconds": seconds, "native_peak_rss_kib": rss,
             "total_wall_seconds": time.monotonic() - started,
             "artifacts": {name: record(directory / name) for name in ARTIFACTS}}
    write_json(directory / "job.json", value)
    print(f"DONE {arm} seed {seed} {stage}: {value['total_wall_seconds']:.1f}s", flush=True)
    return value


def jobs_for(smoke=False):
    return [(arm, seed, stage) for seed in ((1,) if smoke else SEEDS)
            for arm in (("legacy", "u80") if smoke else ARMS) for stage in STAGES]


def verify_smoke(plan):
    gate = read_json(Path(plan["out"]) / "smoke_gate.json")
    if gate.get("status") != "passed" or gate.get("plan_sha256") != digest(Path(plan["out"]) / "plan.json"):
        raise ValueError("Successful matching smoke gate required before the full batch")
    expected = jobs_for(smoke=True)
    records = gate.get("job_records", [])
    if len(records) != 10 or {(row["arm"], row["seed"], row["stage"]) for row in records} != set(expected):
        raise ValueError("Smoke gate does not cover the exact ten engineering jobs")
    groups = gate.get("stage_validations", [])
    if (len(groups) != 2 or {(row["arm"], row["seed"]) for row in groups} != {("legacy", 1), ("u80", 1)}
            or any(row["validation"].get("status") != "passed" for row in groups)):
        raise ValueError("Smoke gate lacks both successful cross-stage comparisons")
    for row in records:
        expected_path = job_directory(plan, row["arm"], row["seed"], row["stage"]) / "job.json"
        if Path(row["record"]["path"]).resolve() != expected_path.resolve():
            raise ValueError("Smoke job attribution differs from the frozen directory")
        verify_record(row["record"])
        checked_job(plan, row["arm"], row["seed"], row["stage"])
    return gate


def validate_groups(plan, *, smoke=False):
    results = []
    for seed in ((1,) if smoke else SEEDS):
        for arm in (("legacy", "u80") if smoke else ARMS):
            paths = {stage: job_directory(plan, arm, seed, stage) for stage in STAGES}
            result = metrics_module().validate_arm_stages(plan, arm, seed, paths)
            if result.get("status") != "passed":
                raise ValueError(f"Stage identity/subset validation failed for {arm} seed {seed}")
            results.append({"arm": arm, "seed": seed, "validation": result})
    return results


def run_plan(path, *, workers=12, smoke=False):
    if not 1 <= workers <= 12:
        raise ValueError("Workers must be between one and the requested maximum of 12")
    plan = verify_plan(path)
    out = Path(plan["out"])
    if not smoke:
        verify_smoke(plan)
    elif (out / "status.json").is_file() and read_json(out / "status.json").get("status") == "complete":
        raise ValueError("Full batch already complete; use the full verification/resume command")
    token, lock = uuid.uuid4().hex, out / ".run.lock"
    with lock.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump({"pid": os.getpid(), "token": token}, stream)
    completed, failures = [], []
    selected = jobs_for(smoke)
    mode = "smoke" if smoke else "full"
    try:
        write_json(out / "status.json", {"status": "running", "mode": mode, "workers": workers,
                                        "completed": 0, "scheduled": len(selected), "total": 60}, replace=True)
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(run_job, plan, *job): job for job in selected}
            for future in as_completed(futures):
                arm, seed, stage = futures[future]
                try:
                    completed.append(future.result())
                except Exception as error:
                    failures.append({"arm": arm, "seed": seed, "stage": stage, "error": str(error)})
                    print(f"FAIL {arm} seed {seed} {stage}: {error}", flush=True)
                write_json(out / "status.json", {"status": "running", "mode": mode, "workers": workers,
                                                "completed": len(completed), "scheduled": len(selected),
                                                "total": 60, "failures": failures}, replace=True)
        if failures:
            raise RuntimeError(f"{len(failures)} native jobs failed; partial artifacts retained")
        groups = validate_groups(plan, smoke=smoke)
        result = {"status": "smoke_complete" if smoke else "complete", "mode": mode,
                  "workers": workers, "completed": len(completed), "scheduled": len(selected), "total": 60,
                  "plan": record(path), "jobs": completed, "failures": [], "stage_validations": groups}
        if smoke:
            gate_path = out / "smoke_gate.json"
            gate = {"schema": 1, "status": "passed", "plan_sha256": digest(path), "stage_validations": groups,
                    "job_records": [{"arm": arm, "seed": seed, "stage": stage,
                                     "record": record(job_directory(plan, arm, seed, stage) / "job.json")}
                                    for arm, seed, stage in selected]}
            if gate_path.exists():
                verify_smoke(plan)
            else:
                write_json(gate_path, gate)
        write_json(out / "status.json", result, replace=True)
        return result
    except Exception as error:
        write_json(out / "status.json", {"status": "failed", "mode": mode, "workers": workers,
                                        "completed": len(completed), "scheduled": len(selected), "total": 60,
                                        "jobs": completed, "failures": failures,
                                        "error": {"type": type(error).__name__, "message": str(error)}}, replace=True)
        raise
    finally:
        if lock.exists() and read_json(lock).get("token") == token:
            lock.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    plan = commands.add_parser("plan", help="Freeze the approved protocol; no inference")
    for name in ("prepared-root", "binary", "config", "out"):
        plan.add_argument("--" + name, type=Path, required=True)
    plan.add_argument("--distro", default="Ubuntu")
    run = commands.add_parser("run", help="Run ten smoke jobs or the gated full 60-job comparison")
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--workers", type=int, default=12)
    run.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    if args.command == "plan":
        value = create_plan(args.prepared_root, args.binary, args.config, args.out, distro=args.distro)
        print(json.dumps({"status": "planned", "out": value["out"], "jobs": 60, "smoke_jobs": 10}))
    else:
        value = run_plan(args.plan, workers=args.workers, smoke=args.smoke)
        print(json.dumps({"status": value["status"], "completed": value["completed"], "total": 60}))


if __name__ == "__main__":
    main()
