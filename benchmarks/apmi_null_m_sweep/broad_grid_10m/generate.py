#!/usr/bin/env python3
"""Generation-only, checkpointed broad-grid null sweep; no fits or summaries.

plan freezes 400 fresh streams. run owns and waits for every native child;
stop requests no-new-launches, finishing existing streams. Resume rechecks all
completed bytes and rejects interrupted/failed attempts (no automatic retry).
"""
from __future__ import annotations

import argparse
from array import array
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys
import threading
import time
import uuid

SCHEMA = "sjaracne-broad-grid-generation-v1"
EXPECTED_GENERATOR = "08224b6b20e29628be6d89d22eb7e355f8c6a05623e06f801fae5347a70a7f18"
EXPECTED_ENGINE = "7633ebb4a0d966dbda15a4e32d0efa492fb71aeb"
GRID = list(range(50, 10001, 50))
CONFIG = {"draws_per_stream": 10_000_000, "npar": 40, "fit_seed": 20261019,
          "validation_seed": 20261020, "max_workers": 12}
ENV = {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
       "NUMEXPR_NUM_THREADS": "1", "LC_ALL": "C"}
PURPOSE = "Sealed raw generation and integrity only; no statistics, fitting or validation opening."


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def record(path):
    path = Path(path).resolve(strict=True)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}


def read_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("JSON object required: " + str(path))
    return value


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())


def atomic_status(path, value):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    write_new(temporary, value)
    os.replace(temporary, path)


def repo_root():
    return Path(__file__).resolve().parents[3]


def git_output(root, *args):
    return subprocess.check_output(["git", "-c", "safe.directory=" + str(root).replace("\\", "/"),
                                    "-C", str(root), *args], text=True).strip()


def source_snapshot(root):
    paths = git_output(root, "ls-files", "SJARACNe", "tools").splitlines()
    selected = [p for p in paths if Path(p).suffix.lower() in {".py", ".cpp", ".cc", ".c", ".h", ".hpp"}
                or Path(p).name in {"Makefile", "CMakeLists.txt"}]
    if not selected:
        raise ValueError("no tracked engine sources")
    return {p: sha256(root / p) for p in sorted(selected)}


def native_path(path, distro):
    if not distro:
        return str(Path(path).resolve())
    windows = PureWindowsPath(str(path))
    if not windows.is_absolute() or not re.fullmatch(r"[A-Za-z]:", windows.drive):
        raise ValueError("absolute Windows drive path required for WSL: " + str(path))
    return "/mnt/" + windows.drive[0].lower() + "/" + "/".join(windows.parts[1:])


def task_list():
    tasks = []
    for m in reversed(GRID):
        group = "final_interpolation_test" if m % 500 == 350 else "development" if m % 500 == 450 else "training"
        for stream in ("fit", "validation"):
            seed = CONFIG[stream + "_seed"] + m + (1_000_000_000 if stream == "validation" else 0)
            tasks.append({"id": "m%05d_%s" % (m, stream), "m": m, "stream": stream,
                          "seed": seed, "draws": CONFIG["draws_per_stream"], "m_group": group})
    return tasks


def prior_plan_paths():
    base = Path(__file__).resolve().parents[1]
    return [base / "results_2026-10-15" / "plan.json",
            base / "expanded_10m" / "results_2026-10-15" / "plan.json"]


def verify_seeds(tasks, old_plans):
    seeds = [task["seed"] for task in tasks]
    historical = set()
    for old in old_plans:
        for m in old["m"]:
            historical.add(old["config"]["fit_seed"] + m)
            historical.add(old["config"]["validation_seed"] + 1_000_000_000 + m)
    if len(set(seeds)) != len(seeds) or set(seeds) & historical:
        raise ValueError("new stream seeds repeat or overlap historical scientific streams")
    return {"new_unique_seeds": len(seeds), "historical_unique_seeds": len(historical), "overlap": 0}


def command_for(plan, task, directory):
    distro = plan["execution"]["distro"]
    native = ["/usr/bin/env"] + [key + "=" + value for key, value in ENV.items()]
    native += ["/usr/bin/time", "-f", "%e\t%U\t%S\t%M", "-o", native_path(directory / "time.tsv", distro),
               plan["generator_native"], "--m", str(task["m"]), "--draws", str(task["draws"]),
               "--npar", "40", "--seed", str(task["seed"]), "--format", "binary", "--output",
               native_path(directory / "null.f64", distro)]
    return ["wsl.exe", "--distribution", distro, "--exec", *native] if distro else native


def make_plan(args):
    root, generator = args.engine_root.resolve(strict=True), args.generator.resolve(strict=True)
    out = args.out.resolve()
    boundary = (repo_root() / "runs").resolve()
    if out.exists() or out == boundary or not out.is_relative_to(boundary):
        raise ValueError("output must be a fresh child of ignored runs/")
    if sha256(generator) != EXPECTED_GENERATOR:
        raise ValueError("unexpected generator SHA256")
    commit = git_output(root, "rev-parse", "HEAD")
    if commit != EXPECTED_ENGINE:
        raise ValueError("engine must remain at pinned commit " + EXPECTED_ENGINE)
    old_paths = prior_plan_paths()
    old_plans = [read_json(path) for path in old_paths]
    sources = source_snapshot(root)
    if sources != old_plans[-1]["engine_source_sha256"]:
        raise ValueError("engine source differs from previously pinned scientific generator source")
    tasks = task_list()
    seed_check = verify_seeds(tasks, old_plans)
    python = args.python.resolve(strict=True)
    probe = subprocess.run([str(python), "-c", "import json,platform,sys; print(json.dumps({'python':sys.version,'platform':platform.platform()}))"],
                           text=True, capture_output=True, check=False)
    if probe.returncode:
        raise ValueError("Python probe failed: " + probe.stderr)
    plan = {"format": SCHEMA, "purpose": PURPOSE, "created_utc": utc_now(), "output_dir": str(out),
            "config": CONFIG, "grid": GRID, "tasks": tasks, "expected_raw_bytes": 32_000_000_000,
            "engine_root": str(root), "engine_commit": commit, "engine_source_sha256": sources,
            "generator_native": native_path(generator, args.distro),
            "pins": {"generator": record(generator), "python": record(python), "runner": record(__file__),
                     "runner_tests": record(Path(__file__).with_name("test_generate.py")),
                     "protocol": record(args.protocol), "analysis_spec": record(args.analysis_spec),
                     **{"prior_plan_%d" % i: record(path) for i, path in enumerate(old_paths)}},
            "seed_check": seed_check, "execution": {"distro": args.distro, "environment": ENV,
                                                       "max_workers": 12, "python_environment": json.loads(probe.stdout)},
            "retry_policy": "none; failed or incomplete stream directories block resume",
            "sealing": "Final validation and final-test fit distributions are integrity-checked only, never statistically summarized."}
    launcher = Path(__file__).with_name("start_generation.ps1")
    if launcher.exists():
        plan["pins"]["launcher"] = record(launcher)
    # All paths/commands must be valid before output creation.
    for task in tasks:
        task["command"] = command_for(plan, task, out / "streams" / task["id"])
    out.mkdir(parents=True, exist_ok=False)
    (out / "streams").mkdir()
    (out / "invocations").mkdir()
    write_new(out / "plan.json", plan)
    with (out / "plan.sha256").open("x", encoding="ascii") as handle:
        handle.write(sha256(out / "plan.json") + "\n")
    return out / "plan.json"


def load_plan(path, verify_pins=True):
    path = Path(path).resolve(strict=True)
    digest = sha256(path)
    if path.with_suffix(".sha256").read_text(encoding="ascii").strip() != digest:
        raise ValueError("frozen plan hash mismatch")
    plan = read_json(path)
    if plan.get("format") != SCHEMA or plan.get("config") != CONFIG or plan.get("grid") != GRID:
        raise ValueError("unexpected generation protocol")
    if Path(plan["output_dir"]).resolve() != path.parent:
        raise ValueError("plan moved from frozen output directory")
    expected = task_list()
    if len(plan["tasks"]) != len(expected):
        raise ValueError("expected exactly 400 streams")
    for actual, task in zip(plan["tasks"], expected):
        if {key: actual.get(key) for key in task} != task:
            raise ValueError("modified stream identity")
        if actual.get("command") != command_for(plan, task, path.parent / "streams" / task["id"]):
            raise ValueError("modified stream command")
    if plan["pins"]["generator"]["sha256"] != EXPECTED_GENERATOR or plan["engine_commit"] != EXPECTED_ENGINE:
        raise ValueError("unexpected generator/engine pin")
    if verify_pins:
        for name, pin in plan["pins"].items():
            if record(pin["path"]) != pin:
                raise ValueError(name + " changed since planning")
        root = Path(plan["engine_root"])
        if git_output(root, "rev-parse", "HEAD") != EXPECTED_ENGINE or source_snapshot(root) != plan["engine_source_sha256"]:
            raise ValueError("engine HEAD or source changed since planning")
    return plan, digest


@contextmanager
def output_lock(out):
    """OS-held lock, automatically released after controller exit/crash."""
    with (Path(out) / ".generation.lock").open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise ValueError("another controller owns this run") from error
        else:
            import fcntl
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise ValueError("another controller owns this run") from error
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def verify_raw(path, task):
    """Bounded-memory integrity check only, without quantiles or tail summaries."""
    if path.stat().st_size != task["draws"] * 8:
        raise ValueError("raw binary length mismatch")
    metadata = {}
    for line in Path(str(path) + ".meta").read_text(encoding="utf-8").splitlines():
        if not line or line.startswith("#"):
            continue
        key, value = line.split("=", 1)
        if not key or key in metadata:
            raise ValueError("duplicate or empty raw metadata key")
        metadata[key] = value
    expected = {"format": "sjaracne-apmi-null-binary-v1", "kernel_schema": "sjaracne-apmi-v1",
                "estimator": "sjaracne-adaptive-partitioning", "rng": "mt19937-rejection-fisher-yates-v1",
                "m": str(task["m"]), "draws": str(task["draws"]), "npar_limit": "40", "seed": str(task["seed"]),
                "dtype": "float64", "byte_order": "little", "record_bytes": "8"}
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError("native raw metadata mismatch")
    tolerance = 64 * sys.float_info.epsilon
    upper = math.log(task["m"]) + tolerance
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            values = array("d")
            values.frombytes(block)
            if sys.byteorder != "little":
                values.byteswap()
            if any(not math.isfinite(value) or value < -tolerance or value > upper for value in values):
                raise ValueError("nonfinite or out-of-support AP-MI")
    return metadata


def artifact_records(directory):
    return {path.name: record(path) for path in sorted(directory.iterdir())
            if path.is_file() and path.name not in {"complete.json", "failure.json"}}


def provenance(plan, plan_hash, task):
    return {"format": "sjaracne-broad-grid-raw-provenance-v1", "plan_sha256": plan_hash,
            "task": task, "generator_sha256": plan["pins"]["generator"]["sha256"],
            "engine_commit": plan["engine_commit"], "purpose": PURPOSE}


def verify_complete(plan, plan_hash, task, directory):
    result = read_json(directory / "complete.json")
    if result.get("status") != "complete" or result.get("returncode") != 0 or result.get("task") != task or result.get("plan_sha256") != plan_hash:
        raise ValueError("completion identity or exit status mismatch: " + task["id"])
    if read_json(directory / "request.json") != provenance(plan, plan_hash, task):
        raise ValueError("request provenance mismatch")
    if read_json(directory / "null.f64.provenance.json") != provenance(plan, plan_hash, task):
        raise ValueError("raw provenance mismatch")
    if artifact_records(directory) != result.get("artifacts"):
        raise ValueError("completed stream artifacts changed: " + task["id"])
    verify_raw(directory / "null.f64", task)
    if (directory / "failure.json").exists():
        raise ValueError("completion conflicts with failure record")
    return result


def validate_workers(workers):
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 12:
        raise ValueError("workers must be an integer in [1,12]")


def run_stream(plan_path, plan, plan_hash, task, registry, registry_lock, abort):
    directory = Path(plan["output_dir"]) / "streams" / task["id"]
    started, started_time = utc_now(), time.monotonic()
    returncode = None
    try:
        load_plan(plan_path)
        if abort.is_set():
            return {"id": task["id"], "status": "not_started"}
        directory.mkdir(exist_ok=False)
        write_new(directory / "request.json", provenance(plan, plan_hash, task))
        environment = os.environ.copy()
        environment.update(ENV)
        with (directory / "stdout.log").open("xb") as stdout, (directory / "stderr.log").open("xb") as stderr:
            child = subprocess.Popen(task["command"], cwd=plan["engine_root"], env=environment,
                                     stdout=stdout, stderr=stderr,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                child_info = {"task": task["id"], "pid": child.pid, "started_utc": utc_now(),
                              "pid_scope": "Windows-owned WSL launcher" if plan["execution"]["distro"] else "native /usr/bin/time",
                              "command": task["command"]}
                write_new(directory / "process.json", child_info)
                with registry_lock:
                    registry[task["id"]] = child_info
                returncode = child.wait()
            finally:
                # A failed checkpoint must never leave an unowned running child.
                if child.poll() is None:
                    child.wait()
                with registry_lock:
                    registry.pop(task["id"], None)
        # Both native log handles are closed before any artifact digest/checkpoint.
        if returncode != 0:
            raise ValueError("native generator exited " + str(returncode))
        if (directory / "stderr.log").stat().st_size:
            raise ValueError("native generator emitted stderr; inspect preserved evidence")
        verify_raw(directory / "null.f64", task)
        native_time = (directory / "time.tsv").read_text(encoding="ascii").strip().split("\t")
        if len(native_time) != 4:
            raise ValueError("invalid native timing log")
        wall, user, system = map(float, native_time[:3])
        rss = int(native_time[3])
        if any(not math.isfinite(x) or x < 0 for x in (wall, user, system)) or rss < 0:
            raise ValueError("invalid native timing values")
        load_plan(plan_path)
        write_new(directory / "null.f64.provenance.json", provenance(plan, plan_hash, task))
        result = {"format": SCHEMA, "status": "complete", "plan_sha256": plan_hash, "task": task,
                  "returncode": returncode, "started_utc": started, "finished_utc": utc_now(),
                  "elapsed_seconds": time.monotonic() - started_time, "native_wall_seconds": wall,
                  "native_user_seconds": user, "native_system_seconds": system, "peak_rss_kib": rss,
                  "artifacts": artifact_records(directory)}
        # Last written: only this file marks a verified stream complete.
        write_new(directory / "complete.json", result)
        return {"id": task["id"], "status": "complete"}
    except Exception as error:
        abort.set()
        failure = {"format": SCHEMA, "status": "failed", "task": task, "plan_sha256": plan_hash,
                   "started_utc": started, "finished_utc": utc_now(), "returncode": returncode,
                   "error": type(error).__name__ + ": " + str(error)}
        if directory.is_dir() and not (directory / "failure.json").exists():
            try:
                write_new(directory / "failure.json", failure)
            except OSError:
                pass
        return {"id": task["id"], "status": "failed", "error": failure["error"]}


def run_generation(plan_path, workers=12, resume=False, only_m=None):
    validate_workers(workers)
    if only_m is not None and (len(only_m) != len(set(only_m)) or any(m not in GRID for m in only_m)):
        raise ValueError("--only-m must contain unique m values from the frozen grid")
    plan, plan_hash = load_plan(plan_path)
    out = Path(plan["output_dir"])
    with output_lock(out):
        known = {task["id"] for task in plan["tasks"]}
        if any(path.name not in known or not path.is_dir() for path in (out / "streams").iterdir()):
            raise ValueError("unexpected stream artifacts")
        existing = list((out / "streams").iterdir())
        if existing and not resume:
            raise ValueError("existing streams require explicit --resume")
        completed = set()
        for task in plan["tasks"]:
            directory = out / "streams" / task["id"]
            if directory.exists():
                if not (directory / "complete.json").is_file():
                    raise ValueError("failed/incomplete stream blocks resume; no automatic retry: " + task["id"])
                verify_complete(plan, plan_hash, task, directory)
                completed.add(task["id"])
        if (out / "STOP.json").exists():
            if not resume:
                raise ValueError("cooperative stop present; explicit --resume required")
            os.rename(out / "STOP.json", out / "invocations" / ("observed_stop_" + uuid.uuid4().hex + ".json"))
        invocation_id = uuid.uuid4().hex
        started = utc_now()
        invocation = {"id": invocation_id, "pid": os.getpid(), "started_utc": started, "plan_sha256": plan_hash,
                      "workers": workers, "resume": resume, "only_m": only_m, "argv": sys.argv,
                      "preverified_completed": sorted(completed)}
        write_new(out / "invocations" / (invocation_id + ".request.json"), invocation)
        pending = [task for task in plan["tasks"] if task["id"] not in completed and (only_m is None or task["m"] in only_m)]
        registry, registry_lock, abort = {}, threading.Lock(), threading.Event()
        failures, fatal = [], None
        futures = {}
        def snapshot(status):
            with registry_lock:
                active = list(registry.values())
            value = {"format": SCHEMA, "purpose": PURPOSE, "status": status, "controller_pid": os.getpid(),
                     "controller_started_utc": started, "heartbeat_utc": utc_now(), "invocation": invocation_id,
                     "plan_sha256": plan_hash, "workers": workers, "scope_streams": 400, "completed": len(completed),
                     "remaining_scope": 400 - len(completed), "pending_selected": len(pending),
                     "active": active, "inflight_tasks": len(futures), "failures": failures, "fatal_error": fatal,
                     "stop_requested": (out / "STOP.json").exists(), "only_m": only_m}
            atomic_status(out / "status.json", value)
            return value
        snapshot("running")
        with ThreadPoolExecutor(max_workers=workers) as executor:
            while pending or futures:
                if (out / "STOP.json").exists():
                    abort.set()
                if not abort.is_set():
                    try:
                        # Hash/source checks at every submission, not merely at startup.
                        load_plan(plan_path)
                    except Exception as error:
                        fatal = type(error).__name__ + ": " + str(error)
                        abort.set()
                while pending and len(futures) < workers and not abort.is_set():
                    task = pending.pop(0)
                    futures[executor.submit(run_stream, plan_path, plan, plan_hash, task, registry, registry_lock, abort)] = task
                if not futures:
                    break
                ready, _ = wait(futures, timeout=10, return_when=FIRST_COMPLETED)
                for future in ready:
                    task = futures.pop(future)
                    try:
                        result = future.result()
                    except Exception as error:
                        abort.set()
                        result = {"id": task["id"], "status": "failed", "error": str(error)}
                    if result["status"] == "complete":
                        completed.add(task["id"])
                    elif result["status"] == "failed":
                        failures.append(result)
                        abort.set()
                snapshot("stopping" if abort.is_set() else "running")
        status = "failed" if failures or fatal else "complete" if len(completed) == 400 else "stopped" if abort.is_set() else "selected_complete"
        final = snapshot(status)
        write_new(out / "invocations" / (invocation_id + ".result.json"), final)
        return final


def status(plan_path):
    plan, plan_hash = load_plan(plan_path, verify_pins=False)
    out = Path(plan["output_dir"])
    checkpoint_count = sum((out / "streams" / task["id"] / "complete.json").is_file() for task in plan["tasks"])
    return {"plan_sha256": plan_hash, "checkpoint_count_unverified": checkpoint_count,
            "status": read_json(out / "status.json") if (out / "status.json").exists() else {"status": "planned"},
            "warning": "Read-only status does not rehash raw streams or assert process liveness; verify PID and heartbeat separately."}


def stop(plan_path):
    plan, plan_hash = load_plan(plan_path, verify_pins=False)
    path = Path(plan["output_dir"]) / "STOP.json"
    if not path.exists():
        write_new(path, {"requested_utc": utc_now(), "plan_sha256": plan_hash,
                         "action": "stop new launches; finish and checkpoint active streams"})
    return {"status": "stop_requested", "path": str(path)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("plan")
    for name in ("engine-root", "generator", "python", "out", "protocol", "analysis-spec"):
        create.add_argument("--" + name, type=Path, required=True)
    create.add_argument("--distro", default="Ubuntu")
    run = sub.add_parser("run")
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--workers", type=int, default=12)
    run.add_argument("--resume", action="store_true")
    run.add_argument("--only-m", type=int, nargs="+")
    for action in ("status", "stop"):
        sub.add_parser(action).add_argument("--plan", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.action == "plan":
            value = {"status": "planned", "plan": str(make_plan(args))}
        elif args.action == "run":
            value = run_generation(args.plan, args.workers, args.resume, args.only_m)
        elif args.action == "status":
            value = status(args.plan)
        else:
            value = stop(args.plan)
        print(json.dumps(value, allow_nan=False), flush=True)
        return 1 if value.get("status") == "failed" else 0
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(type(error).__name__ + ": " + str(error), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
