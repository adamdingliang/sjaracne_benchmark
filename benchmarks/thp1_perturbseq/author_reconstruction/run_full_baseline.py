#!/usr/bin/env python3
"""Complete the author-style legacy baseline after its real one-run smoke test.

This coordinator can run in the background. It never changes prepared inputs,
uses the unmodified release binary/script via run_legacy.py, and delegates
scoring to complete_baseline.py only after all 100 jobs and both consensuses
have passed integrity checks. No subsequent PR70 comparison is launched.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import run_legacy


def sha256(path):
    return run_legacy.digest(Path(path))


def wait_for_smoke(path, prepared, *, interval=30):
    """Wait for a single completed native job, not an unverified .adj file."""
    while True:
        state = json.loads(path.read_text(encoding="utf-8"))
        if state.get("status") in ("failed", "error"):
            raise RuntimeError("Native smoke failed; full run will not start")
        frozen = state["frozen"]
        if frozen["parameters"]["bootstrap_count"] != 1:
            raise ValueError("Expected the separate one-bootstrap smoke manifest")
        expected = {"seeds": [1], "bootstrap_p": 1e-7, "npar": 40, "dpi_tolerance": 0,
                    "sampling": "legacy -r 1", "algorithm": "adaptive_partitioning",
                    "explicit_mi_override": None}
        if frozen.get("source_commit") != run_legacy.SOURCE_COMMIT or any(
            frozen["parameters"].get(key) != value for key, value in expected.items()
        ):
            raise ValueError("Smoke does not use the frozen legacy baseline protocol")
        for key, filename in (("expression", "expression.exp"), ("hubs", "hubs.txt")):
            if frozen["inputs"][key]["sha256"] != sha256(prepared / filename):
                raise ValueError("Smoke and full baseline inputs differ")
        record = state["bootstraps"].get("1")
        if record is not None:
            if set(state["bootstraps"]) != {"1"} or record.get("seed") != 1:
                raise ValueError("Expected exactly the seed-one smoke record")
            if set(record.get("artifacts", {})) != {"adjacency", "log"}:
                raise ValueError("Smoke must bind both its adjacency and native log")
            if record.get("status") != "complete":
                raise RuntimeError("Native smoke failed; full run will not start")
            run_legacy.verify_completed(record)
            run_legacy.verify_frozen(frozen)
            return state
        time.sleep(interval)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--result-root", type=Path, required=True)
    parser.add_argument("--assets-root", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()
    root = args.result_root.resolve(strict=True)
    assets = args.assets_root.resolve(strict=True)
    prepared = root / "prepared"
    prep_file = prepared / "prepare_manifest.json"
    audit_file = root / "independent_audit.json"
    prep = json.loads(prep_file.read_text(encoding="utf-8"))
    audit = json.loads(audit_file.read_text(encoding="utf-8"))
    if prep.get("status") != "complete" or audit.get("status") != "pass":
        raise ValueError("Completed preparation and passing independent audit required")
    if audit["prepare_manifest_sha256"] != sha256(prep_file):
        raise ValueError("Audit does not bind the completed preparation")
    if args.workers < 1:
        raise ValueError("Workers must be positive")
    here = Path(__file__).resolve().parent
    for name in ("run_legacy.py", "complete_baseline.py", "score_author.R"):
        if not (here / name).is_file():
            raise FileNotFoundError(here / name)
    driver_dir = root / "driver"
    driver_dir.mkdir(exist_ok=False)
    status_path = driver_dir / "status.json"
    state = {
        "status": "waiting_for_smoke", "pid": os.getpid(), "created": time.time(),
        "scope": "author-style legacy reconstruction; no PR70/PR71/K; exact author inputs unavailable",
        "prepare_manifest_sha256": sha256(prep_file), "audit_sha256": sha256(audit_file),
        "driver_sha256": sha256(__file__), "workers": args.workers,
        "stage_code_sha256": {name: sha256(here / name) for name in
                              ("run_legacy.py", "complete_baseline.py", "score_author.R")},
    }
    def checkpoint(**updates):
        state.update(updates, updated=time.time())
        run_legacy.json_write(status_path, state, replace=status_path.exists())
        print(json.dumps({"status": state["status"], "time": state["updated"]}), flush=True)

    def unchanged():
        if sha256(prep_file) != state["prepare_manifest_sha256"] or sha256(audit_file) != state["audit_sha256"]:
            raise ValueError("Prepared provenance/audit changed during background coordination")
        for name, expected in state["stage_code_sha256"].items():
            if sha256(here / name) != expected:
                raise ValueError("Frozen stage source changed: " + name)

    def run_stage(name, command):
        unchanged()
        log_path = driver_dir / (name + ".log")
        with log_path.open("x", encoding="utf-8") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            checkpoint(status=name, child_pid=process.pid, command=command, log=str(log_path))
            returncode = process.wait()
            checkpoint(child_pid=None, returncode=returncode)
        unchanged()
        if returncode != 0:
            raise RuntimeError(f"{name} failed (exit {returncode}); inspect {log_path}; outputs retained")

    try:
        checkpoint()
        smoke = wait_for_smoke(root / "legacy_smoke" / "run_manifest.json", prepared)
        checkpoint(status="smoke_passed", smoke_manifest_sha256=sha256(root / "legacy_smoke" / "run_manifest.json"),
                   smoke_duration_seconds=smoke["bootstraps"]["1"]["finished"]-smoke["bootstraps"]["1"]["started"])
        native = assets / "sources" / "SJARACNe-v0.2.1"
        command = [sys.executable, str(here / "run_legacy.py"), "run",
                   "--expression", str(prepared / "expression.exp"), "--hubs", str(prepared / "hubs.txt"),
                   "--prepare-manifest", str(prep_file),
                   "--binary", str(native / "SJARACNe" / "bin" / "sjaracne.exe"),
                   "--config", str(native / "SJARACNe" / "config"),
                   "--consensus-script", str(native / "SJARACNe" / "bin" / "create_consensus_network.py"),
                   "--component-manifest", str(native / "build_record.json"),
                   "--out", str(root / "legacy"), "--bootstrap-count", "100", "--workers", str(args.workers)]
        run_stage("native_100_and_consensus", command)
        command = [sys.executable, str(here / "complete_baseline.py"),
                   "--run-manifest", str(root / "legacy" / "run_manifest.json"),
                   "--prepared-dir", str(prepared), "--publication-dir", str(root / "publication"),
                   "--audit-file", str(audit_file), "--out", str(root / "comparison"),
                   "--wsl-r-env", run_legacy.wsl_path(assets / "toolchain" / "r44"),
                   "--wsl-r-library", run_legacy.wsl_path(assets / "toolchain" / "paper_r_library")]
        run_stage("score_and_compare", command)
        completion = json.loads((root / "comparison" / "status.json").read_text(encoding="utf-8"))
        if completion.get("status") != "complete":
            raise RuntimeError("Comparison did not publish a complete status")
        if set(completion.get("outputs", {})) != {"REPORT.md", "summary.json"}:
            raise RuntimeError("Comparison output manifest is incomplete")
        for name, record in completion["outputs"].items():
            target = root / "comparison" / name
            if Path(record["path"]).resolve() != target.resolve() or record["sha256"] != sha256(target):
                raise RuntimeError("Comparison output failed integrity check: " + name)
        checkpoint(status="complete", report=str(root / "comparison" / "REPORT.md"), child_pid=None)
    except BaseException as error:
        checkpoint(status="failed", error=str(error), child_may_still_be_running=state.get("child_pid") is not None)
        raise


if __name__ == "__main__":
    main()
