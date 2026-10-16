#!/usr/bin/env python3
"""Bounded parallel timing only; never launch scientific fitting or a full sweep.

Each worker invokes the existing, pinned-generator time_generator.py helper.
All output must be a fresh child of ignored runs/. No retry or overwrite.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import threading
import time


SCHEMA = "sjaracne-apmi-timing-capacity-v1"
EXPECTED_GENERATOR = "08224b6b20e29628be6d89d22eb7e355f8c6a05623e06f801fae5347a70a7f18"
ENV_CONTROLS = {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1", "LC_ALL": "C"}
PURPOSE = "Timing/capacity only; not scientific calibration; no models or inference."


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def record(path):
    path = Path(path).resolve(strict=True)
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def read_object(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("expected JSON object: " + str(path))
    return value


def runs_root():
    return Path(__file__).resolve().parents[3] / "runs"


def helper_path():
    return Path(__file__).resolve().parents[1] / "time_generator.py"


def child_environment(windows=None):
    environment = os.environ.copy()
    environment.update(ENV_CONTROLS)
    if windows is None:
        windows = os.name == "nt"
    if windows:
        # /u forwards Win32 -> WSL only; existing unrelated mappings are retained.
        # https://learn.microsoft.com/en-us/windows/wsl/filesystems#wslenv-flags
        existing = environment.get("WSLENV", "").split(":")
        retained = [item for item in existing if item and item.split("/", 1)[0] not in ENV_CONTROLS]
        environment["WSLENV"] = ":".join(retained + [key + "/u" for key in ENV_CONTROLS])
    return environment


def verify_pins(request):
    for key in ("generator", "script", "helper", "python"):
        if record(request[key]["path"]) != request[key]:
            raise ValueError(key + " changed after request was frozen")


def helper_job(directory, request):
    path = directory / "helper" / "timing_results.json"
    result = read_object(path)
    if (result.get("status") != "complete" or result.get("draws") != request["draws"] or
            result.get("m") != [request["m"]] or result.get("npar") != 40 or
            result.get("generator", {}).get("sha256") != request["expected_generator_sha256"] or
            result.get("script", {}).get("sha256") != request["helper"]["sha256"]):
        raise ValueError("helper timing result disagrees with frozen request")
    jobs = result.get("jobs")
    if not isinstance(jobs, list) or len(jobs) != 1 or not isinstance(jobs[0], dict):
        raise ValueError("expected exactly one helper timing job")
    job = jobs[0]
    if (job.get("m") != request["m"] or job.get("draws") != request["draws"] or
            job.get("seed") != request["helper_seed"] or job.get("native_exit_code") != 0):
        raise ValueError("helper job identity/seed/native exit mismatch")
    wall = job.get("native_wall_seconds")
    if isinstance(wall, bool) or not isinstance(wall, (int, float)) or not math.isfinite(wall) or wall <= 0:
        raise ValueError("invalid native timing")
    artifacts = job.get("artifacts")
    if not isinstance(artifacts, dict) or not {"timing.f64", "timing.f64.meta", "time.tsv", "stdout.log", "stderr.log"}.issubset(artifacts):
        raise ValueError("helper result is missing timing evidence")
    boundary = (directory / "helper").resolve()
    for item in artifacts.values():
        if not isinstance(item, dict):
            raise ValueError("invalid helper artifact record")
        artifact = Path(item["path"]).resolve(strict=True)
        if not artifact.is_relative_to(boundary) or record(artifact) != item:
            raise ValueError("helper artifact path/hash/size mismatch")
    if artifacts["timing.f64"]["bytes"] != 8 * request["draws"]:
        raise ValueError("helper raw draw count mismatch")
    return job, record(path)["sha256"]


def worker(request, specification, environment, start_event):
    directory = Path(specification["directory"])
    directory.mkdir(exist_ok=False)
    write_new(directory / "request.json", specification)
    start_event.wait()
    started_utc, started = utc_now(), time.monotonic()
    returncode, error, job, result_hash = None, None, None, None
    try:
        verify_pins(request)
        with (directory / "stdout.log").open("xb") as stdout, (directory / "stderr.log").open("xb") as stderr:
            process = subprocess.run(specification["argv"], stdout=stdout, stderr=stderr,
                                     cwd=request["cwd"], env=environment, check=False,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        returncode = process.returncode
        if returncode != 0:
            raise ValueError("timing helper exited with return code " + str(returncode))
        job, result_hash = helper_job(directory, request)
        verify_pins(request)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as failure:
        error = str(failure)
    result = {"format": SCHEMA, "purpose": PURPOSE, "worker": specification["worker"],
              "started_utc": started_utc, "finished_utc": utc_now(),
              "elapsed_seconds": time.monotonic() - started, "returncode": returncode,
              "status": "complete" if error is None else "failed", "error": error,
              "helper_timing_results_sha256": result_hash, "job": job,
              "artifacts_sha256": {}, "worker_result_persisted": True}
    try:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                result["artifacts_sha256"][path.relative_to(directory).as_posix()] = record(path)["sha256"]
    except (OSError, ValueError, KeyError, TypeError) as failure:
        result["status"] = "failed"
        result["error"] = (result["error"] + "; " if result["error"] else "") + "Evidence hashing failed: " + str(failure)
    try:
        write_new(directory / "result.json", result)
    except (OSError, ValueError, TypeError) as failure:
        # Parent capacity_results.json still retains the known process code/job.
        result["status"] = "failed"
        result["worker_result_persisted"] = False
        result["error"] = (result["error"] + "; " if result["error"] else "") + "Worker result persistence failed: " + str(failure)
    return result


def run_capacity(generator, out, workers=8, draws=100_000, m=10_000, distro="Ubuntu"):
    for value, low, high, name in ((workers, 1, 12, "workers"), (draws, 1, 200_000, "draws"), (m, 2, 10_000, "m")):
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise ValueError("%s must be an integer in [%s,%s]" % (name, low, high))
    generator, out = Path(generator).resolve(strict=True), Path(out).resolve()
    boundary = runs_root().resolve()
    if out == boundary or not out.is_relative_to(boundary) or out.exists():
        raise ValueError("output must be a fresh child of ignored runs/")
    generator_record = record(generator)
    if generator_record["sha256"] != EXPECTED_GENERATOR:
        raise ValueError("unexpected generator binary SHA256")
    helper, script = record(helper_path()), record(__file__)
    environment = child_environment()
    specifications = []
    for number in range(1, workers + 1):
        directory = out / ("worker_%03d" % number)
        argv = [sys.executable, helper["path"], "--generator", str(generator), "--out", str(directory / "helper"),
                "--draws", str(draws), "--m", str(m), "--distro", distro]
        specifications.append({"worker": number, "directory": str(directory), "argv": argv})
    request = {"format": SCHEMA, "purpose": PURPOSE, "created_utc": utc_now(),
               "script_argv": list(sys.argv),
               "workers": workers, "draws": draws, "m": m, "npar": 40,
               "total_requested_timing_draws": workers * draws, "out": str(out),
               "generator": generator_record, "expected_generator_sha256": EXPECTED_GENERATOR,
               "script": script, "helper": helper, "python": record(sys.executable),
               "python_version": sys.version, "cwd": str(Path(__file__).resolve().parents[3]),
               "environment_controls": ENV_CONTROLS,
               "wslenv": environment.get("WSLENV") if os.name == "nt" else None,
               "helper_seed": 20261015 + 2_000_000 + m,
               "seed_warning": "The unchanged helper repeats this timing-only seed across workers. These are contention replicates, not independent scientific streams, and must never be reused for calibration/confirmation.",
               "worker_requests": specifications, "retry_policy": "none; fresh output required for any new batch"}
    out.mkdir(parents=True, exist_ok=False)
    write_new(out / "capacity_request.json", request)
    request_hash = record(out / "capacity_request.json")["sha256"]
    with (out / "capacity_request.sha256").open("x", encoding="ascii") as handle:
        handle.write(request_hash + "\n")
    started_utc, started = utc_now(), time.monotonic()
    start_event = threading.Event()
    records = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(worker, request, specification, environment, start_event): specification for specification in specifications}
        start_event.set()
        for future in as_completed(futures):
            try:
                records.append(future.result())
            except (OSError, ValueError, KeyError, TypeError, RuntimeError) as failure:
                # Retain every worker identity even if preparing its directory failed.
                records.append({"worker": futures[future]["worker"], "returncode": None,
                                "status": "failed", "error": "Worker orchestration failed: " + str(failure), "job": None})
    wall = time.monotonic() - started
    request_unchanged = record(out / "capacity_request.json")["sha256"] == request_hash
    complete = all(r["status"] == "complete" for r in records) and request_unchanged
    native = [r["job"]["native_wall_seconds"] for r in records if r["status"] == "complete"]
    summary = {"format": SCHEMA, "purpose": PURPOSE, "status": "complete" if complete else "failed",
               "capacity_request_sha256": request_hash, "request_unchanged": request_unchanged,
               "batch_started_utc": started_utc, "batch_finished_utc": utc_now(), "batch_wall_seconds": wall,
               "wall_definition": "Parent elapsed including helper/Python/WSL startup, generation and evidence checks; concurrent worker times must not be summed as wall time.",
               "workers": workers, "draws_per_worker": draws, "m": m,
               "worker_returncodes": {str(r["worker"]): r["returncode"] for r in sorted(records, key=lambda r: r["worker"])},
               "successful_workers": sum(r["status"] == "complete" for r in records),
               "aggregate_draws_per_batch_wall_second": workers * draws / wall if complete else None,
               "native_wall_seconds_min": min(native) if native else None,
               "native_wall_seconds_median": statistics.median(native) if native else None,
               "native_wall_seconds_max": max(native) if native else None,
               "results": sorted(records, key=lambda r: r["worker"])}
    write_new(out / "capacity_results.json", summary)
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generator", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--draws", type=int, default=100_000)
    parser.add_argument("--m", type=int, default=10_000)
    parser.add_argument("--distro", default="Ubuntu")
    args = parser.parse_args(argv)
    try:
        result = run_capacity(args.generator, args.out, args.workers, args.draws, args.m, args.distro)
    except (OSError, ValueError, KeyError, TypeError) as error:
        print("Timing-only capacity batch failed: " + str(error), file=sys.stderr)
        return 1
    print(json.dumps({"status": result["status"], "batch_wall_seconds": result["batch_wall_seconds"],
                      "worker_returncodes": result["worker_returncodes"]}, sort_keys=True))
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
