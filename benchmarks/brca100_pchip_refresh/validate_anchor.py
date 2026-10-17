#!/usr/bin/env python3
"""Compare one fixed-threshold TF seed with its immutable historical output.

This is an implementation/compiler/runtime anchor, not PCHIP calibration or
another threshold sweep. It does not write into either inference adjacency
directory, and it never substitutes this explicit-threshold run for a PCHIP run.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("brca_pchip_anchor_run", HERE / "run.py")
run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run)
core = run.core

OLD_COMMIT = "7633ebb4a0d966dbda15a4e32d0efa492fb71aeb"
OLD_DESIGN_SHA256 = "2eca0f9ef388fdf48632f8292c226bac59e0e325d9641574b314689651c6a8e5"
POINT = "p1e-03"
SEED = 1


def historical_cutoff(design: dict) -> float:
    """Take the full binary64 cutoff from the archived design, never its header."""
    if design.get("commit") != OLD_COMMIT:
        raise RuntimeError("Historical inference commit differs")
    fixed = design["fixed_parameters"]
    for key, value in (("m", 80), ("npar", 40), ("dpi_epsilon", 0)):
        if fixed.get(key) != value:
            raise RuntimeError(f"Historical {key} differs")
    if fixed.get("seeds") != list(range(1, 101)):
        raise RuntimeError("Historical seed schedule differs")
    matches = [point for point in design["all_points"] if point.get("key") == POINT]
    if len(matches) != 1 or matches[0].get("p_value") != 0.001:
        raise RuntimeError("Historical TF probability point missing or ambiguous")
    cutoff = matches[0]["mi_cutoff"]
    if not isinstance(cutoff, (float, int)) or not math.isfinite(cutoff) or cutoff <= 0:
        raise RuntimeError("Invalid historical MI cutoff")
    return float(cutoff)


def anchor_command(build: dict, work: Path, output: Path, cutoff: float) -> list[str]:
    return [build["binary"], "-i", str(work / "inputs/BRCA100.exp"),
            "-l", str(work / "inputs/BRCA100_TF.txt"),
            "-s", str(work / "inputs/BRCA100_TF.txt"), "-t", repr(cutoff),
            "-e", "0", "-a", "adaptive_partitioning", "-H",
            build["config"].rstrip("/") + "/", "-N", "40", "-S", str(SEED),
            "-o", str(output), "-u", "80%"]


def validate_anchor(engine_work: Path, old_root: Path) -> dict:
    work, old = engine_work.resolve(), old_root.resolve()
    if work == old:
        raise RuntimeError("Current and historical roots must be distinct")
    design_path = work / "design.json"
    design = core.load_json(design_path)
    if design["engine_commit"] != run.ENGINE_COMMIT:
        raise RuntimeError("Current design does not use the frozen PCHIP source")
    build_root = work / "builds" / run.STAGE_KEY
    build_path = build_root / "build_manifest.json"
    build = core.load_json(build_path)
    if build["commit"] != run.ENGINE_COMMIT:
        raise RuntimeError("Current build commit differs")
    run.verify_inventory(build_root, build["inventory"])
    if core.sha256_file(Path(build["binary"])) != build["binary_sha256"]:
        raise RuntimeError("Current executable changed")
    run.verify_inventory(work / "inputs", design["inputs"])

    old_design_path = old / "sweep_design.json"
    if core.sha256_file(old_design_path) != OLD_DESIGN_SHA256:
        raise RuntimeError("Historical 13-point design hash differs")
    old_design = core.load_json(old_design_path)
    cutoff = historical_cutoff(old_design)
    for filename in ("BRCA100.exp", "BRCA100_TF.txt"):
        wanted = core.EXPECTED_LF_SHA256[filename]
        if (design["inputs"][filename]["sha256"] != wanted
                or old_design["inputs"][filename]["sha256"] != wanted):
            raise RuntimeError(f"Current/historical input hash mismatch: {filename}")

    old_arm = old / "results" / POINT / "tf"
    old_adjacency = old_arm / "adjacency/TF_run_001.adj"
    old_metadata = old_arm / "seed_metadata/TF_run_001.json"
    old_record = core.load_json(old_metadata)
    if (old_record.get("commit") != OLD_COMMIT or old_record.get("seed") != SEED
            or old_record.get("driver") != "tf"
            or old_record["point"]["mi_cutoff"] != cutoff):
        raise RuntimeError("Historical seed manifest differs")

    ids = core.parse_expression_ids(work / "inputs/BRCA100.exp")
    hubs = core.parse_driver_ids(work / "inputs/BRCA100_TF.txt")
    headers = (">  DPI tolerance   0", ">  Sampling method fixed-size without replacement",
               ">  Sampling request 80%", ">  Eligible observations 100",
               ">  Sampled observations 80", ">  MI threshold    " + format(cutoff, ".6g"))
    stage = core.Stage("explicit-threshold-tf-seed001", run.ENGINE_COMMIT,
                       ("-u", "80%"), headers)
    old_stats = core.validate_adjacency(old_adjacency, stage=stage,
                                         driver_ids=hubs, expression_ids=ids)
    if old_stats != old_record["adjacency"]:
        raise RuntimeError("Historical adjacency changed against its seed manifest")

    validation = work / "validation" / "explicit_threshold_tf_seed001"
    marker = validation / "anchor_result.json"
    output = validation / "explicit_threshold_tf_seed001.adj"
    command = anchor_command(build, work, output, cutoff)
    pin_paths = {"current_design": design_path, "current_build": build_path,
                 "historical_design": old_design_path, "historical_seed": old_metadata,
                 "anchor_script": Path(__file__).resolve(), "runner_script": HERE / "run.py",
                 "helper_script": HERE.parent / "brca100_netbid_qc/run_workflows.py"}
    fingerprint = core.json_fingerprint({"command": command,
        "pins": {key: core.sha256_file(path) for key, path in pin_paths.items()},
        "old_adjacency_sha256": old_stats["full_sha256"]})
    if marker.exists():
        record = core.load_json(marker)
        if record["fingerprint"] != fingerprint:
            raise RuntimeError("Existing anchor has different provenance")
        run.verify_inventory(validation, record["inventory"])
        return record
    # A partial attempt is evidence to inspect, never silently overwritten.
    validation.mkdir(parents=True, exist_ok=False)
    began = run.now()
    timings = run.timed(command, validation / "logs", "explicit_threshold_tf_seed001",
                        cwd=Path(build["source"]), env=run.bounded_environment())
    current_stats = core.validate_adjacency(output, stage=stage,
                                             driver_ids=hubs, expression_ids=ids)
    match = current_stats["data_sha256"] == old_stats["data_sha256"]
    record = {"schema": "brca100-pchip-explicit-threshold-anchor-v1",
              "fingerprint": fingerprint, "status": "match" if match else "differ",
              "driver": "tf", "seed": SEED, "m": 80, "npar": 40, "dpi_epsilon": 0,
              "mi_cutoff": cutoff, "mi_cutoff_hex": cutoff.hex(),
              "threshold_mode": "explicit -t; no probability conversion or PCHIP model used",
              "historical_commit": OLD_COMMIT, "current_commit": run.ENGINE_COMMIT,
              "current_binary_sha256": build["binary_sha256"],
              "historical_binary_sha256": old_record["binary_sha256"],
              "current_compiler": build["compiler"], "command": command,
              "pins": {key: {"path": str(path), "sha256": core.sha256_file(path)}
                       for key, path in pin_paths.items()},
              "input_hashes": {name: design["inputs"][name]["sha256"]
                               for name in ("BRCA100.exp", "BRCA100_TF.txt")},
              "old_adjacency": {"path": str(old_adjacency), **old_stats},
              "new_adjacency": {"path": str(output), **current_stats},
              "started_at_utc": began, "finished_at_utc": run.now(), "gnu_time": timings,
              "interpretation": "One seed at an identical explicit threshold tests serialized post-DPI data equivalence in these builds. A match does not prove equivalence for every seed, threshold, dataset or environment; this run is not PCHIP calibration or a PCHIP output.",
              "inventory": run.inventory(validation,
                  [p for p in validation.rglob("*") if p.is_file()])}
    core.atomic_json(marker, record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--historical-root", type=Path, default=run.OLD_ROOT)
    args = parser.parse_args()
    record = validate_anchor(args.work_root, args.historical_root)
    print(json.dumps({"status": record["status"], "mi_cutoff": record["mi_cutoff"],
                      "old_data_sha256": record["old_adjacency"]["data_sha256"],
                      "new_data_sha256": record["new_adjacency"]["data_sha256"]}, indent=2))
    if record["status"] != "match":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
