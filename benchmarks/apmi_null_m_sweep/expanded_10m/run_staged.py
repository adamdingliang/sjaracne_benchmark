#!/usr/bin/env python3
"""Frozen, exact-m staged orchestration of the engine's unmodified calibrator.

The runner itself has no NumPy/SciPy dependency. On Windows generation runs in
WSL; the pinned Windows Python fits only strictly checked freshly generated raw
streams through the unmodified calibrator's provenance-checked --reuse-raw path.
Planning does not launch simulations. Scientific rejection is a completed result;
process/model-fit failures are retained separately and are never retried silently.
"""
from __future__ import annotations

import argparse
from array import array
from concurrent.futures import ThreadPoolExecutor, as_completed
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
import time
import uuid


SCHEMA = "sjaracne-staged-apmi-calibration-10m-v1"
EXPECTED_GENERATOR_SHA256 = "08224b6b20e29628be6d89d22eb7e355f8c6a05623e06f801fae5347a70a7f18"
STAGES = {"anchors": [30, 50, 80, 90, 100, 150, 300, 1000],
          "expanded": [200, 250, 400, 500, 600, 700, 800, 900],
          "dream": [644, 516, 725]}
ALL_M = STAGES["anchors"] + STAGES["expanded"] + STAGES["dream"]
CONFIG = {"npar": 40, "fit_draws": 10_000_000,
          "validation_draws": 10_000_000, "fit_seed": 20261017,
          "validation_seed": 20261018, "tail_quantile": 0.995,
          "min_tail_count": 20_000, "p_min": 5e-4, "p_max": 1e-3,
          "default_p": 5e-4, "validation_p": [1e-3, 5e-4],
          "stability_relative_tolerance": 0.10, "min_stability_fits": 3,
          "validation_family_confidence": 0.99,
          "validation_family_comparisons": 10}
ENV_CONTROLS = {"OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1", "NUMEXPR_NUM_THREADS": "1", "LC_ALL": "C"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_expected_generator(path):
    actual = sha256(path)
    if actual != EXPECTED_GENERATOR_SHA256:
        raise ValueError("generator does not match the fixed expected SHA256")
    return actual


def json_write_new(path, value):
    """Exclusive creation: existing evidence is never overwritten."""
    with Path(path).open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, allow_nan=False)
        handle.write("\n")


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def native_path(path, distro):
    if not distro:
        return str(Path(path).resolve())
    # Explicit drive mapping avoids shell interpolation and wslpath subprocesses.
    windows = PureWindowsPath(str(path))
    if not windows.is_absolute() or not re.fullmatch(r"[A-Za-z]:", windows.drive):
        raise ValueError("WSL paths must be absolute Windows drive paths: " + str(path))
    return "/mnt/" + windows.drive[0].lower() + "/" + "/".join(windows.parts[1:])


def wrap_wsl(command, distro):
    return (["wsl.exe", "--distribution", distro, "--exec"] + command
            if distro else command)


def git_output(root, *arguments):
    safe_root = str(Path(root).resolve()).replace("\\", "/")
    return subprocess.check_output(["git", "-c", "safe.directory=" + safe_root, "-C", str(root), *arguments], text=True).strip()


def source_snapshot(root):
    paths = git_output(root, "ls-files", "SJARACNe", "tools").splitlines()
    selected = [p for p in paths if Path(p).suffix.lower() in
                {".py", ".cpp", ".cc", ".c", ".h", ".hpp"}
                or Path(p).name in {"Makefile", "CMakeLists.txt"}]
    if not selected:
        raise ValueError("no tracked engine source files found")
    return {p: sha256(root / p) for p in sorted(selected)}


def make_plan(args):
    root = args.engine_root.resolve(strict=True)
    generator = args.generator.resolve(strict=True)
    generator_hash = verify_expected_generator(generator)
    calibrator = root / "SJARACNe" / "calibrate_apmi_null.py"
    commit = git_output(root, "rev-parse", "HEAD")
    if args.engine_commit and args.engine_commit != commit:
        raise ValueError("engine commit does not match --engine-commit")
    out = args.out.resolve()
    if out.exists():
        raise ValueError("output must be a fresh nonexistent directory: " + str(out))
    python_path = Path(args.python).resolve(strict=True)
    # Fail before creating output for unmappable paths or missing source files.
    for path in (root, generator, calibrator, out):
        native_path(path, args.distro)
    plan = {"format": SCHEMA, "created_utc": utc_now(),
            "output_dir": str(out), "stages": STAGES, "m": ALL_M,
            "config": CONFIG, "engine_root": str(root), "engine_commit": commit,
            "engine_source_sha256": source_snapshot(root),
            "generator": str(generator), "generator_sha256": generator_hash,
            "calibrator": str(calibrator), "calibrator_sha256": sha256(calibrator),
            "runner": str(Path(__file__).resolve()), "runner_sha256": sha256(__file__),
            "runner_tests": str(Path(__file__).with_name("test_run_staged.py").resolve()),
            "runner_tests_sha256": sha256(Path(__file__).with_name("test_run_staged.py")),
            "execution": {"distro": args.distro, "python": str(python_path),
                          "python_sha256": sha256(python_path), "environment_controls": ENV_CONTROLS,
                          "time_program": "/usr/bin/time", "max_workers": 12},
            "seed_derivation": {"fit": "fit_seed + m",
                                "validation": "validation_seed + 1000000000 + m"},
            "stability_quantiles": [0.9925, 0.995, 0.9975],
            "legacy_label_warning": "Engine CSV cutoff_p1e-7 and report prose are legacy labels; actual configured default_p is 0.0005.",
            "protocol": None}
    if args.protocol:
        protocol = args.protocol.resolve(strict=True)
        plan["protocol"] = {"path": str(protocol), "sha256": sha256(protocol)}
    probe = subprocess.run(environment_command(plan), text=True, capture_output=True, check=False)
    if probe.returncode:
        raise ValueError("calibration Python/NumPy/SciPy probe failed: " + probe.stderr)
    plan["environment"] = json.loads(probe.stdout)
    out.mkdir(parents=True, exist_ok=False)
    (out / "jobs").mkdir()
    (out / "invocations").mkdir()
    json_write_new(out / "plan.json", plan)
    with (out / "plan.sha256").open("x", encoding="ascii") as handle:
        handle.write(sha256(out / "plan.json") + "\n")
    print(out / "plan.json", flush=True)
    return 0


def verify_plan(path):
    path = Path(path).resolve(strict=True)
    expected = path.with_suffix(".sha256").read_text(encoding="ascii").strip()
    if sha256(path) != expected:
        raise ValueError("frozen plan hash mismatch")
    plan = read_json(path)
    if plan.get("format") != SCHEMA or plan["config"] != CONFIG:
        raise ValueError("unknown or modified calibration protocol")
    if plan.get("generator_sha256") != EXPECTED_GENERATOR_SHA256:
        raise ValueError("plan generator is not the fixed expected SHA256")
    if plan["stages"] != STAGES or plan["m"] != ALL_M:
        raise ValueError("modified predeclared m grid")
    if Path(plan["output_dir"]).resolve() != path.parent:
        raise ValueError("plan moved from its frozen output directory")
    root = Path(plan["engine_root"])
    if git_output(root, "rev-parse", "HEAD") != plan["engine_commit"]:
        raise ValueError("engine HEAD changed since planning")
    if source_snapshot(root) != plan["engine_source_sha256"]:
        raise ValueError("engine source changed since planning")
    for name in ("generator", "calibrator", "runner", "runner_tests"):
        if sha256(plan[name]) != plan[name + "_sha256"]:
            raise ValueError(name + " changed since planning")
    if plan["protocol"] and sha256(plan["protocol"]["path"]) != plan["protocol"]["sha256"]:
        raise ValueError("protocol document changed since planning")
    if sha256(plan["execution"]["python"]) != plan["execution"]["python_sha256"]:
        raise ValueError("calibration Python executable changed since planning")
    return plan


@contextmanager
def output_lock(out):
    """OS lock releases on crashes; the small lock file is not a PID assertion."""
    with (out / ".runner.lock").open("a+b") as handle:
        if handle.tell() == 0:
            handle.write(b"0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise ValueError("another runner holds this output directory") from error
        else:
            import fcntl
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise ValueError("another runner holds this output directory") from error
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def calibration_command(plan, m, attempt):
    execution = plan["execution"]
    command = [execution["python"], str(plan["calibrator"]),
               "--generator", str(plan["generator"]),
               "--output-dir", str(attempt / "calibration"),
               "--m", str(m)]
    for key, value in plan["config"].items():
        command.append("--" + key.replace("_", "-"))
        command.extend(str(item) for item in (value if isinstance(value, list) else [value]))
    # These raw files were just provisioned by this attempt, not historical reuse.
    command.extend(["--reuse-raw", "--allow-rejected-calibration"])
    return command


def stream_path(plan, m, attempt, role):
    return attempt / "calibration" / "raw" / ("m%05d_npar%03d_%s.f64" % (m, plan["config"]["npar"], role))


def generation_command(plan, m, attempt, role):
    execution = plan["execution"]
    config = plan["config"]
    distro = execution["distro"]
    seed = config[role + "_seed"] + m + (1_000_000_000 if role == "validation" else 0)
    command = ["/usr/bin/env"] + [key + "=" + value for key, value in ENV_CONTROLS.items()]
    command += [execution["time_program"], "-v", "-o", native_path(attempt / (role + "_time.txt"), distro),
                native_path(plan["generator"], distro), "--m", str(m), "--draws", str(config[role + "_draws"]),
                "--npar", str(config["npar"]), "--seed", str(seed), "--format", "binary",
                "--output", native_path(stream_path(plan, m, attempt, role), distro)]
    return wrap_wsl(command, distro)


def check_raw(plan, m, attempt, role, require_provenance=True):
    """Strict metadata, hash, support and length preflight before ELF reuse path."""
    config = plan["config"]
    path = stream_path(plan, m, attempt, role)
    metadata = {}
    for raw in Path(str(path) + ".meta").read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith("#"):
            continue
        key, value = raw.split("=", 1)
        if not key or key in metadata:
            raise ValueError("duplicate/empty raw metadata key")
        metadata[key] = value
    expected = {"format": "sjaracne-apmi-null-binary-v1", "kernel_schema": "sjaracne-apmi-v1",
                "estimator": "sjaracne-adaptive-partitioning", "rng": "mt19937-rejection-fisher-yates-v1",
                "m": str(m), "draws": str(config[role + "_draws"]), "npar_limit": str(config["npar"]),
                "seed": str(config[role + "_seed"] + m + (1_000_000_000 if role == "validation" else 0)),
                "dtype": "float64", "byte_order": "little", "record_bytes": "8"}
    if any(metadata.get(key) != value for key, value in expected.items()):
        raise ValueError("raw metadata mismatch: " + str(path))
    if path.stat().st_size != config[role + "_draws"] * 8:
        raise ValueError("raw binary length mismatch: " + str(path))
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            values = array("d")
            values.frombytes(block)
            if sys.byteorder != "little":
                values.byteswap()
            tolerance = 64 * sys.float_info.epsilon
            if any(not math.isfinite(value) for value in values) or min(values) < -tolerance or max(values) > math.log(m) + tolerance:
                raise ValueError("raw AP-MI is nonfinite/outside support: " + str(path))
    if sha256(plan["generator"]) != plan["generator_sha256"]:
        raise ValueError("generator changed during native generation")
    provenance_path = Path(str(path) + ".provenance.json")
    provenance = {"format": "sjaracne-apmi-null-raw-provenance-v1", "generator_sha256": plan["generator_sha256"]}
    if require_provenance and read_json(provenance_path) != provenance:
        raise ValueError("raw provenance mismatch")
    return {"path": str(path), "sha256": sha256(path), "metadata": metadata, "seed": int(expected["seed"])}


def peak_working_set(process):
    """Read Windows' process lifetime high-water working set without psutil."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize",
            "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
            "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
    counters = Counters()
    counters.cb = ctypes.sizeof(counters)
    function = ctypes.windll.psapi.GetProcessMemoryInfo
    function.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD]
    function.restype = wintypes.BOOL
    return int(counters.PeakWorkingSetSize) if function(int(process._handle), ctypes.byref(counters), counters.cb) else None


def parse_time(path):
    if not path.is_file():
        return {"maximum_resident_set_kbytes": None, "time_log_present": False}
    content = path.read_text(encoding="utf-8", errors="replace")
    match = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", content)
    return {"maximum_resident_set_kbytes": int(match.group(1)) if match else None,
            "time_log_present": True,
            "rss_definition": "GNU time maximum resident set size; not aggregate concurrent-worker RSS"}


def artifact_hashes(attempt):
    return {str(path.relative_to(attempt)).replace("\\", "/"): sha256(path)
            for path in sorted(attempt.rglob("*"))
            if path.is_file() and path.name != "result.json"}


def verify_result(attempt):
    record = read_json(attempt / "result.json")
    if artifact_hashes(attempt) != record["artifacts_sha256"]:
        raise ValueError("completed attempt artifacts changed: " + str(attempt))
    return record


def inspect_calibration(plan, m, attempt, returncode):
    """Do not infer acceptance from exit status, a model file, or a partial report."""
    report_path = attempt / "calibration" / "calibration_report.json"
    models = list((attempt / "calibration").glob("*.model"))
    if returncode != 0:
        if models:
            raise ValueError("failed process left a model; it is not accepted evidence")
        return {"status": "failed", "accepted": False,
                "failure_kind": "computational-or-model-fit-failure"}
    report = read_json(report_path)
    results = report.get("results", [])
    if len(results) != 1 or results[0].get("m") != m:
        raise ValueError("report must contain exactly the requested m")
    result = results[0]
    model = result["model"]
    config = plan["config"]
    required = {"m": m, "npar_limit": config["npar"],
                "fit_draws": config["fit_draws"], "validation_draws": config["validation_draws"],
                "fit_seed": config["fit_seed"] + m,
                "validation_seed": config["validation_seed"] + 1_000_000_000 + m,
                "generator_sha256": plan["generator_sha256"],
                "calibrator_sha256": plan["calibrator_sha256"],
                "default_p": config["default_p"], "supported_p_min": config["p_min"],
                "validation_family_confidence": config["validation_family_confidence"]}
    for key, value in required.items():
        if model.get(key) != value:
            raise ValueError("calibration report mismatch for " + key)
    for role in ("fit", "validation"):
        if model.get(role + "_values_sha256") != sha256(stream_path(plan, m, attempt, role)):
            raise ValueError("calibration report raw hash mismatch for " + role)
    if result.get("validation_family_comparisons") != 10:
        raise ValueError("validation family must retain ten comparisons")
    accepted = result.get("accepted") is True
    if len(models) != int(accepted):
        raise ValueError("model artifact count does not agree with acceptance")
    if accepted and (not result.get("stability_pass") or not result.get("validation_pass")
                     or model.get("calibration_status") != "accepted"):
        raise ValueError("inconsistent accepted calibration gates")
    if accepted:
        if result["primary_fit"]["threshold_quantile"] != config["tail_quantile"] or result["primary_fit"]["tail_count"] < config["min_tail_count"]:
            raise ValueError("primary fit did not retain fixed threshold/tail count")
        if sorted(row["threshold_quantile"] for row in result["stability_fits"]) != [0.9925, 0.995, 0.9975]:
            raise ValueError("accepted model did not retain all stability fits")
        if sorted(row["nominal_p"] for row in result["validation"]) != sorted(config["validation_p"]):
            raise ValueError("accepted model did not validate both declared probabilities")
    return {"status": "accepted" if accepted else "rejected", "accepted": accepted,
            "default_p": model["default_p"], "cutoff_at_default_p_5e_4": model["default_p_cutoff"],
            "stability_pass": result["stability_pass"],
            "validation_pass": result["validation_pass"],
            "relative_stability_range": result["relative_stability_range"],
            "model_path": str(models[0]) if accepted else None,
            "legacy_report": str(report_path)}


def run_one(plan, m, invocation):
    job = Path(plan["output_dir"]) / "jobs" / ("m%05d" % m)
    job.mkdir(exist_ok=True)
    attempts = sorted(job.glob("attempt_*"))
    attempt = job / ("attempt_%04d" % (len(attempts) + 1))
    attempt.mkdir(exist_ok=False)
    command = calibration_command(plan, m, attempt)
    request = {"format": SCHEMA, "m": m, "invocation": str(invocation),
               "started_utc": utc_now(), "argv": command,
               "cwd": str(Path(plan["engine_root"])),
               "generator_sha256": plan["generator_sha256"],
               "calibrator_sha256": plan["calibrator_sha256"],
               "fit_seed": CONFIG["fit_seed"] + m,
               "validation_seed": CONFIG["validation_seed"] + 1_000_000_000 + m}
    json_write_new(attempt / "request.json", request)
    start = time.monotonic()
    returncode = None
    failure = None
    raw_records = {}
    calibration_rss = None
    try:
        # Verify pins immediately before each launch, not only at invocation start.
        for name in ("generator", "calibrator", "runner", "runner_tests"):
            if sha256(plan[name]) != plan[name + "_sha256"]:
                raise ValueError(name + " changed before job launch")
        environment = os.environ.copy()
        environment.update(ENV_CONTROLS)
        generation = {role: generation_command(plan, m, attempt, role) for role in ("fit", "validation")}
        json_write_new(attempt / "launch.json", {"calibration_argv": command,
                       "generation_argv": generation, "environment_controls": ENV_CONTROLS})
        stream_path(plan, m, attempt, "fit").parent.mkdir(parents=True, exist_ok=False)
        for role in ("fit", "validation"):
            stream_start = time.monotonic()
            with (attempt / (role + "_stdout.log")).open("xb") as stdout, (attempt / (role + "_stderr.log")).open("xb") as stderr:
                generated = subprocess.run(generation[role], cwd=plan["engine_root"], stdout=stdout,
                                           stderr=stderr, env=environment, check=False)
            if generated.returncode:
                returncode = generated.returncode
                raise ValueError("native %s generator failed (%s)" % (role, generated.returncode))
            raw_records[role] = check_raw(plan, m, attempt, role, require_provenance=False)
            raw_records[role]["generation_elapsed_seconds"] = time.monotonic() - stream_start
            raw_records[role]["resources"] = parse_time(attempt / (role + "_time.txt"))
            json_write_new(Path(str(stream_path(plan, m, attempt, role)) + ".provenance.json"), {
                "format": "sjaracne-apmi-null-raw-provenance-v1", "generator_sha256": plan["generator_sha256"]})
        # All six required files exist and are freshly checked. A hash comparison
        # also catches edits between initial generation and the reuse-only fit.
        for role in ("fit", "validation"):
            verified = check_raw(plan, m, attempt, role)
            if verified["sha256"] != raw_records[role]["sha256"]:
                raise ValueError("fresh raw stream changed before fitting")
        with (attempt / "stdout.log").open("xb") as stdout, (attempt / "stderr.log").open("xb") as stderr:
            process = subprocess.Popen(command, cwd=plan["engine_root"], stdout=stdout,
                                       stderr=stderr, env=environment)
            while process.poll() is None:
                rss = peak_working_set(process)
                if rss is not None:
                    calibration_rss = max(calibration_rss or 0, rss)
                time.sleep(0.1)
            rss = peak_working_set(process)
            if rss is not None:
                calibration_rss = max(calibration_rss or 0, rss)
            returncode = process.wait()
        outcome = inspect_calibration(plan, m, attempt, returncode)
    except (OSError, ValueError, KeyError, TypeError) as error:
        failure = str(error)
        outcome = {"status": "failed", "accepted": False,
                   "failure_kind": "orchestration-or-artifact-validation-failure"}
    quarantined = []
    if outcome["status"] == "failed":
        # Preserve dubious models as diagnostic bytes, never accepted model paths.
        for model_path in (attempt / "calibration").glob("*.model"):
            quarantine = model_path.with_name(model_path.name + ".unverified")
            model_path.rename(quarantine)
            quarantined.append(str(quarantine))
    record = {"format": SCHEMA, "m": m, "attempt": str(attempt),
              "invocation": str(invocation), "started_utc": request["started_utc"],
              "finished_utc": utc_now(), "elapsed_seconds": time.monotonic() - start,
              "returncode": returncode, "error": failure, **outcome,
              "resources": {"calibration_peak_working_set_bytes": calibration_rss,
                            "rss_definition": "Windows calibration process PeakWorkingSetSize; native stream GNU time RSS recorded separately"},
              "raw_streams": raw_records,
              "unverified_model_artifacts": quarantined,
              "artifacts_sha256": artifact_hashes(attempt)}
    json_write_new(attempt / "result.json", record)
    print("m=%s %s %.1fs" % (m, record["status"], record["elapsed_seconds"]), flush=True)
    return record


def environment_command(plan):
    script = ("import sys,json,hashlib,numpy,scipy; "
              "print(json.dumps({'python':sys.version,'executable':sys.executable,"
              "'python_sha256':hashlib.sha256(open(sys.executable,'rb').read()).hexdigest(),"
              "'numpy':numpy.__version__,'scipy':scipy.__version__},sort_keys=True))")
    return [plan["execution"]["python"], "-c", script]


def run_stage(args):
    plan = verify_plan(args.plan)
    if not 1 <= args.workers <= 12:
        raise ValueError("workers must be in [1,12]")
    selected = args.m if args.m else (ALL_M if args.stage == "all" else STAGES[args.stage])
    if len(set(selected)) != len(selected) or not set(selected).issubset(ALL_M):
        raise ValueError("requested m must be unique members of the frozen grid")
    out = Path(plan["output_dir"])
    with output_lock(out):
        pending, reused = [], []
        for m in selected:
            attempts = sorted((out / "jobs" / ("m%05d" % m)).glob("attempt_*"))
            if not attempts:
                pending.append(m)
                continue
            latest = attempts[-1]
            if (latest / "result.json").is_file():
                record = verify_result(latest)
                if record["status"] in {"accepted", "rejected"}:
                    reused.append(record)
                    continue
            if not args.retry_failed:
                raise ValueError("failed/interrupted attempt retained for m=%s; use --retry-failed to create a fresh attempt" % m)
            pending.append(m)
        invocation = out / "invocations" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "_" + uuid.uuid4().hex[:8])
        invocation.mkdir(exist_ok=False)
        command = environment_command(plan)
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        json_write_new(invocation / "environment_probe.json", {"argv": command,
                       "returncode": completed.returncode, "stdout": completed.stdout,
                       "stderr": completed.stderr})
        if completed.returncode:
            raise ValueError("calibration Python/NumPy/SciPy environment probe failed")
        environment = json.loads(completed.stdout)
        frozen_environment = out / "environment.json"
        if environment != plan["environment"]:
            raise ValueError("calibration Python/dependencies differ from frozen plan")
        if frozen_environment.exists():
            if read_json(frozen_environment) != environment:
                raise ValueError("calibration Python/dependency environment changed")
        else:
            json_write_new(frozen_environment, environment)
        json_write_new(invocation / "request.json", {"started_utc": utc_now(),
                       "plan_sha256": sha256(args.plan), "requested_m": selected,
                       "pending_m": pending, "reused_m": [r["m"] for r in reused],
                       "workers": args.workers, "retry_failed": args.retry_failed,
                       "command": sys.argv})
        records = list(reused)
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = [executor.submit(run_one, plan, m, invocation) for m in pending]
            for future in as_completed(futures):
                records.append(future.result())
        summary = {"format": SCHEMA, "finished_utc": utc_now(),
                   "requested_m": selected, "results": sorted(records, key=lambda r: r["m"]),
                   "counts": {status: sum(r["status"] == status for r in records)
                              for status in ("accepted", "rejected", "failed")}}
        json_write_new(invocation / "summary.json", summary)
        print(invocation / "summary.json", flush=True)
        return 1 if summary["counts"]["failed"] else 0


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="action", required=True)
    plan = commands.add_parser("plan", help="freeze a fresh run; launch no simulations")
    plan.add_argument("--engine-root", type=Path, required=True)
    plan.add_argument("--generator", type=Path, required=True)
    plan.add_argument("--engine-commit", help="optional exact expected HEAD")
    plan.add_argument("--out", type=Path, required=True)
    plan.add_argument("--protocol", type=Path)
    plan.add_argument("--python", required=True, help="local Windows Python with NumPy/SciPy; Linux Python on native Linux")
    plan.add_argument("--distro", help="WSL distribution, e.g. Ubuntu; omit on native Linux")
    run = commands.add_parser("run", help="run only a requested predeclared stage/subset")
    run.add_argument("--plan", type=Path, required=True)
    selection = run.add_mutually_exclusive_group(required=True)
    selection.add_argument("--stage", choices=["anchors", "expanded", "dream", "all"])
    selection.add_argument("--m", type=int, nargs="+")
    run.add_argument("--workers", type=int, default=1)
    run.add_argument("--retry-failed", action="store_true", help="retain old failure; start fresh raw streams in a new attempt")
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    try:
        return make_plan(args) if args.action == "plan" else run_stage(args)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print("staged AP-MI calibration failed: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
