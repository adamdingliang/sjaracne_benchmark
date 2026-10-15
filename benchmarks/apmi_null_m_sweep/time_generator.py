"""Time the pinned AP-MI null generator; never fit models or change defaults."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import time

import numpy as np

EXPECTED_GENERATOR = "08224b6b20e29628be6d89d22eb7e355f8c6a05623e06f801fae5347a70a7f18"


def record(path):
    path = Path(path).resolve(strict=True)
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": value.hexdigest()}


def wsl_path(path):
    path = Path(path).resolve()
    if os.name != "nt":
        return str(path)
    if len(path.drive) != 2 or path.drive[1] != ":":
        raise ValueError("Drive-letter path required")
    return "/mnt/" + path.drive[0].lower() + path.as_posix()[2:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generator", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--draws", type=int, default=200_000)
    parser.add_argument("--m", type=int, nargs="+", default=[30, 300, 1000])
    parser.add_argument("--distro", default="Ubuntu")
    args = parser.parse_args()
    if args.draws <= 0 or len(set(args.m)) != len(args.m) or any(m < 2 for m in args.m):
        parser.error("Positive draws and unique m>=2 required")
    generator = record(args.generator)
    if generator["sha256"] != EXPECTED_GENERATOR:
        raise ValueError("Unexpected generator binary")
    out = args.out.resolve()
    boundary = Path(__file__).resolve().parents[2] / "runs"
    if out == boundary or not out.is_relative_to(boundary) or out.exists():
        raise ValueError("Timing output must be a fresh child of ignored runs/")
    out.mkdir(parents=True)
    plan = {"status": "running", "purpose": "timing only, not scientific calibration",
            "generator": generator, "script": record(__file__), "draws": args.draws,
            "m": args.m, "npar": 40, "jobs": []}
    (out / "timing_plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    for m in args.m:
        directory = out / f"m{m:05d}"
        directory.mkdir()
        raw = directory / "timing.f64"
        seed = 20261015 + 2_000_000 + m
        native = [wsl_path(args.generator), "--m", str(m), "--draws", str(args.draws),
                  "--npar", "40", "--seed", str(seed), "--format", "binary", "--output", wsl_path(raw)]
        command = ["/usr/bin/time", "-f", "%e\t%U\t%S\t%M", "-o", wsl_path(directory / "time.tsv"), *native]
        if os.name == "nt":
            command = ["wsl.exe", "-d", args.distro, "--", *command]
        print(f"START timing m={m} draws={args.draws}", flush=True)
        started = time.monotonic()
        with (directory / "stdout.log").open("xb") as stdout, (directory / "stderr.log").open("xb") as stderr:
            process = subprocess.run(command, stdout=stdout, stderr=stderr, check=False,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if process.returncode or (directory / "stderr.log").stat().st_size:
            raise RuntimeError(f"Native timing failed; inspect {directory}")
        metadata = dict(line.split("=", 1) for line in Path(str(raw) + ".meta").read_text().splitlines())
        expected = {"kernel_schema": "sjaracne-apmi-v1", "m": str(m), "draws": str(args.draws),
                    "npar_limit": "40", "seed": str(seed), "dtype": "float64", "byte_order": "little"}
        if any(metadata.get(key) != value for key, value in expected.items()) or raw.stat().st_size != 8 * args.draws:
            raise ValueError("Unexpected timing binary metadata/size")
        values = np.fromfile(raw, dtype="<f8")
        if not np.isfinite(values).all() or np.any(values < -1e-14) or np.any(values > math.log(m) + 1e-14):
            raise ValueError("Invalid native null MI values")
        elapsed, user, system, rss = (directory / "time.tsv").read_text().strip().split("\t")
        row = {"m": m, "draws": args.draws, "seed": seed, "native_exit_code": 0,
               "native_wall_seconds": float(elapsed), "user_seconds": float(user),
               "system_seconds": float(system), "peak_rss_kib": int(rss),
               "total_wall_seconds": time.monotonic() - started, "command": command,
               "artifacts": {path.name: record(path) for path in directory.iterdir() if path.is_file()}}
        plan["jobs"].append(row)
        (directory / "job.json").write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        print(f"DONE timing m={m}: native={elapsed}s; rate={args.draws / float(elapsed):.1f} draws/s", flush=True)
    plan["status"] = "complete"
    (out / "timing_results.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "complete", "out": str(out)}), flush=True)


if __name__ == "__main__":
    main()
