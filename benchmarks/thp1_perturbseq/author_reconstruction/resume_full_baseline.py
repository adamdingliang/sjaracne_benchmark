#!/usr/bin/env python3
"""Recover an interrupted Windows/WSL legacy coordinator without changing its protocol.

The original driver and attempt logs remain untouched. Completed artifacts and
the original stage sources are verified before the stale runner lock is moved
into a fresh recovery directory. Only run_legacy.py --resume retries native jobs.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import ctypes
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import run_legacy


def process_alive(pid):
    """Windows process existence; access denied is not evidence of absence."""
    if os.name != "nt":
        raise RuntimeError("This recovery helper is for a Windows/WSL coordinator")
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_int, ctypes.c_uint32]
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if handle:
        kernel.CloseHandle(handle)
        return True
    error = ctypes.get_last_error()
    if error != 87:  # ERROR_INVALID_PARAMETER: PID does not exist.
        raise OSError(error, "Could not establish that the old process is absent")
    return False


def require_no_native_workers(distro):
    check = subprocess.run(
        ["wsl.exe", "--distribution", distro, "--exec", "pgrep", "-x", "sjaracne.exe"],
        capture_output=True, text=True, check=False,
    )
    if check.returncode != 1 or check.stdout.strip():
        raise RuntimeError("WSL worker-absence check failed or native workers remain: "
                           + check.stdout + check.stderr)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def freeze_recovery(root, here):
    old_path = root / "driver" / "status.json"
    old = read_json(old_path)
    if old.get("status") != "native_100_and_consensus":
        raise ValueError("Expected an interrupted original native stage, not another driver state")
    for key in ("pid", "child_pid"):
        if old.get(key) is None or process_alive(old[key]):
            raise RuntimeError("Original driver/child may still be running: " + key)
    frozen_records = {old_path: run_legacy.digest(old_path)}
    for path, expected in (
        (root / "prepared" / "prepare_manifest.json", old["prepare_manifest_sha256"]),
        (root / "independent_audit.json", old["audit_sha256"]),
        (here / "run_full_baseline.py", old["driver_sha256"]),
        *((here / name, expected) for name, expected in old["stage_code_sha256"].items()),
    ):
        if run_legacy.digest(path) != expected:
            raise ValueError("Original frozen stage/provenance changed: " + str(path))
        frozen_records[path] = expected
    prep = read_json(root / "prepared" / "prepare_manifest.json")
    audit = read_json(root / "independent_audit.json")
    if prep.get("status") != "complete" or audit.get("status") != "pass":
        raise ValueError("Completed preparation and PASS audit required")
    if audit["prepare_manifest_sha256"] != old["prepare_manifest_sha256"]:
        raise ValueError("Audit/preparation binding differs")
    command = old["command"]
    if (command[:3] != [sys.executable, str(here / "run_legacy.py"), "run"]
            or "--resume" in command):
        raise ValueError("Original native command is not the expected interpreter/stage")
    args = run_legacy.parser().parse_args(command[2:])
    if args.out.resolve() != root / "legacy" or args.workers != 8 or old["workers"] != 8:
        raise ValueError("Expected the original eight-worker legacy output")
    run = read_json(root / "legacy" / "run_manifest.json")
    frozen, _, _ = run_legacy.make_frozen(args)
    if run["frozen"] != frozen:
        raise ValueError("Reconstructed command differs from the frozen native manifest")
    run_legacy.verify_frozen(frozen)
    for records in (run["bootstraps"], run["consensus"]):
        for record in records.values():
            if record.get("status") == "complete":
                run_legacy.verify_completed(record)
    completed = sorted(int(seed) for seed, record in run["bootstraps"].items()
                       if record.get("status") == "complete")
    actual = {p.name for p in (root / "legacy" / "adj").iterdir()}
    expected = {f"bootstrap_{seed:03d}.adj" for seed in completed}
    if actual != expected:
        raise ValueError("Adjacency directory contains missing or uncheckpointed outputs")
    if (root / "comparison").exists():
        raise FileExistsError("Existing comparison will not be adopted or overwritten")
    require_no_native_workers(args.wsl_distro)
    return old, run, completed, frozen_records


def preserve_stale_lock(root, recovery, old):
    lock = root / "legacy" / ".runner.lock"
    if not lock.exists():
        return None
    lock_record = read_json(lock)
    if lock_record.get("pid") != old["child_pid"] or process_alive(lock_record["pid"]):
        raise RuntimeError("Runner lock does not belong to the absent original child")
    record = run_legacy.record_file(lock)
    destination = recovery / "interrupted_runner.lock"
    lock.rename(destination)  # Recoverable move, never unlink/delete the evidence.
    record["preserved_path"] = str(destination)
    return record


@contextmanager
def recovery_lock(root):
    lock = root / ".baseline_recovery.lock"
    with lock.open("x", encoding="utf-8") as stream:
        json.dump({"pid": os.getpid(), "created": time.time()}, stream)
    try:
        yield
    finally:
        lock.unlink()


def recover(root, assets, recovery):
    here = Path(__file__).resolve().parent
    old, run, completed, bindings = freeze_recovery(root, here)
    if Path(run["frozen"]["component_manifest"]["path"]).resolve() != assets / "sources" / "SJARACNe-v0.2.1" / "build_record.json":
        raise ValueError("Assets root differs from the original frozen native source")
    for name in ("r44", "paper_r_library", "micromamba"):
        if not (assets / "toolchain" / name).exists():
            raise FileNotFoundError(assets / "toolchain" / name)
    import complete_baseline
    score_command = [
        sys.executable, str(here / "complete_baseline.py"),
        "--run-manifest", str(root / "legacy" / "run_manifest.json"),
        "--prepared-dir", str(root / "prepared"),
        "--publication-dir", str(root / "publication"),
        "--audit-file", str(root / "independent_audit.json"),
        "--out", str(root / "comparison"),
        "--wsl-r-env", run_legacy.wsl_path(assets / "toolchain" / "r44"),
        "--wsl-r-library", run_legacy.wsl_path(assets / "toolchain" / "paper_r_library"),
    ]
    score_args = complete_baseline.parser().parse_args(score_command[2:])
    score_context, _, _ = complete_baseline.freeze_context(score_args)
    bindings.update({Path(record["path"]): record["sha256"]
                     for record in score_context["inputs"].values()})
    recovery.mkdir(exist_ok=False)
    for name, source in (("original_driver_status.json", root / "driver" / "status.json"),
                         ("interrupted_run_manifest.json", root / "legacy" / "run_manifest.json")):
        with source.open("rb") as src, (recovery / name).open("xb") as dst:
            shutil.copyfileobj(src, dst)
    status_path = recovery / "status.json"
    state = {
        "status": "verified_checkpoint", "pid": os.getpid(), "created": time.time(),
        "scope": old["scope"], "workers": 8,
        "recovery_script_sha256": run_legacy.digest(Path(__file__)),
        "original_bindings": {str(path): sha for path, sha in bindings.items()},
        "completed_at_resume": completed,
        "pending_at_resume": [seed for seed in run["frozen"]["parameters"]["seeds"]
                              if seed not in completed],
    }

    def checkpoint(**updates):
        state.update(updates, updated=time.time())
        run_legacy.json_write(status_path, state, replace=status_path.exists())
        print(json.dumps({"status": state["status"], "time": state["updated"]}), flush=True)

    def unchanged():
        for path, expected in bindings.items():
            if run_legacy.digest(path) != expected:
                raise ValueError("Original frozen provenance/stage changed: " + str(path))
        run_legacy.verify_frozen(run["frozen"])

    def stage(name, command):
        unchanged()
        log_path = recovery / (name + ".log")
        with log_path.open("x", encoding="utf-8") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            checkpoint(status=name, child_pid=process.pid, command=command, log=str(log_path))
            returncode = process.wait()
            checkpoint(child_pid=None, returncode=returncode)
        unchanged()
        if returncode != 0:
            raise RuntimeError(f"{name} failed (exit {returncode}); outputs retained at {log_path}")

    try:
        checkpoint()
        unchanged()
        checkpoint(stale_lock=preserve_stale_lock(root, recovery, old))
        stage("native_resume_and_consensus", [*old["command"], "--resume"])
        stage("score_and_compare", score_command)
        completion = read_json(root / "comparison" / "status.json")
        if completion.get("status") != "complete" or set(completion.get("outputs", {})) != {"REPORT.md", "summary.json"}:
            raise RuntimeError("Comparison did not publish both completed report artifacts")
        for name, record in completion["outputs"].items():
            if Path(record["path"]).resolve() != root / "comparison" / name:
                raise ValueError("Comparison output binding mismatch: " + name)
            if record["sha256"] != run_legacy.digest(root / "comparison" / name):
                raise ValueError("Comparison output hash mismatch: " + name)
        checkpoint(status="complete", child_pid=None, report=str(root / "comparison" / "REPORT.md"))
    except BaseException as error:
        checkpoint(status="failed", error=str(error),
                   child_may_still_be_running=state.get("child_pid") is not None)
        raise
    return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-root", type=Path, required=True)
    parser.add_argument("--assets-root", type=Path, required=True)
    parser.add_argument("--recovery-name", required=True, help="Fresh direct-child directory name for recovery logs")
    parser.add_argument("--verify-only", action="store_true", help="Check the native checkpoint without creating outputs or starting children")
    args = parser.parse_args()
    root = args.result_root.resolve(strict=True)
    assets = args.assets_root.resolve(strict=True)
    if Path(args.recovery_name).name != args.recovery_name or args.recovery_name in (".", ".."):
        raise ValueError("Recovery name must be one directory component")
    if args.verify_only:
        _, run, completed, _ = freeze_recovery(root, Path(__file__).resolve().parent)
        print(json.dumps({"status": "verified", "completed": completed,
                          "pending": [seed for seed in run["frozen"]["parameters"]["seeds"] if seed not in completed]}))
        return
    with recovery_lock(root):
        recover(root, assets, root / args.recovery_name)


if __name__ == "__main__":
    main()
