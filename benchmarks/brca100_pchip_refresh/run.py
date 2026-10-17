#!/usr/bin/env python3
"""Matched BRCA100 PCHIP refresh: frozen engine, 100 TF + 100 SIG runs.

Run under Linux/WSL. Native calls reproduce the full inference -> DPI -> stock
consensus workflow without adding CWL scheduling overhead. Historical outputs
are read-only comparators, never accepted as current PCHIP results.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
import warnings

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "brca100_netbid_qc"))
import run_workflows as core

ENGINE_COMMIT = "86f8729087b3a6d22bdce128649b4e49d725fb9e"
DATA_SHA256 = "5ae44f3ec251282b242e1e25e5695fe8c6d80a0e7a3f156170dbb72c29e09f59"
PRIMARY_SHA256 = "8b4104be3f3ffe0a476a4dd7c8f7f6d95f00f1a51fa467c7194edf3806d427f5"
OLD_ROOT = Path("/home/adam/sjaracne-benchmarks/brca100-pr67-threshold-sweep-20260818")
DRIVERS = {"tf": ("BRCA100_TF.txt", "0.001", "p1e-03"),
           "sig": ("BRCA100_SIG.txt", "0.0005", "p5e-04")}
SEEDS = list(range(1, 101))
STAGE_KEY = "pchip_86f8729"


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def inventory(root: Path, files: list[Path]) -> dict[str, dict]:
    return {str(p.relative_to(root)): {"sha256": core.sha256_file(p),
                                      "bytes": p.stat().st_size}
            for p in sorted(files)}


def verify_inventory(root: Path, expected: dict) -> None:
    for relative, record in expected.items():
        path = root / relative
        if (not path.is_file() or path.stat().st_size != record["bytes"]
                or core.sha256_file(path) != record["sha256"]):
            raise RuntimeError(f"Frozen artifact changed: {path}")


def immutable_json(path: Path, value: dict) -> None:
    if path.exists():
        if core.load_json(path) != value:
            raise RuntimeError(f"Existing immutable manifest disagrees: {path}")
    else:
        core.atomic_json(path, value)


def timed(command: list[str], logs: Path, stem: str, *, cwd: Path,
          env: dict | None = None) -> dict:
    logs.mkdir(parents=True, exist_ok=True)
    time_path = logs / f"{stem}.time.txt"
    actual = ["/usr/bin/time", "-f",
              "elapsed_s=%e\nuser_s=%U\nsystem_s=%S\nmax_rss_kib=%M",
              "-o", str(time_path), *command]
    core.checked_run(actual, cwd=cwd, env=env,
                     stdout_path=logs / f"{stem}.stdout.log",
                     stderr_path=logs / f"{stem}.stderr.log")
    return core.parse_gnu_time(time_path)


def build_engine(engine_repo: Path, work: Path) -> dict:
    root = work / "builds" / STAGE_KEY
    marker = root / "build_manifest.json"
    source = root / "source"
    if marker.exists():
        record = core.load_json(marker)
        if record["commit"] != ENGINE_COMMIT:
            raise RuntimeError("Build commit mismatch")
        verify_inventory(root, record["inventory"])
        return record
    # Fail closed on incomplete builds; never remove a user's existing tree.
    if root.exists():
        raise RuntimeError(f"Incomplete build needs inspection: {root}")
    root.mkdir(parents=True)
    archive_path = root / "source.tar"
    core.checked_run(core.git_command(engine_repo, "archive", "--format=tar",
                                      "-o", str(archive_path), ENGINE_COMMIT))
    archive_sha = core.sha256_file(archive_path)
    source.mkdir()
    with tarfile.open(archive_path, "r") as archive:
        archive.extractall(source, filter="data")
    # This list is captured before the build so it excludes generated objects.
    tracked = [p for p in source.rglob("*") if p.is_file()
               and p.relative_to(source).as_posix() != "SJARACNe/bin/sjaracne.exe"]
    frozen = inventory(root, tracked)
    data = source / "SJARACNe/config/apmi_pchip.json"
    if core.sha256_file(data) != DATA_SHA256:
        raise RuntimeError("Unexpected frozen PCHIP data SHA256")
    command = ["make", "-C", str(source / "SJARACNe"), "-j12", "bin/sjaracne.exe"]
    core.checked_run(command, stdout_path=root / "build.stdout.log",
                     stderr_path=root / "build.stderr.log")
    binary = source / "SJARACNe/bin/sjaracne.exe"
    if not binary.is_file():
        raise RuntimeError("Native build produced no executable")
    binary.chmod(0o755)
    # Archived source remains immutable, including its stock consensus code.
    verify_inventory(root, frozen)
    frozen.update(inventory(root, [binary, archive_path]))
    record = {"schema": "brca100-pchip-build-v1", "commit": ENGINE_COMMIT,
              "built_at_utc": now(), "binary": str(binary), "source": str(source),
              "config": str(source / "SJARACNe/config"),
              "binary_sha256": core.sha256_file(binary), "archive_sha256": archive_sha,
              "compiler": subprocess.run(["g++", "--version"], check=True,
                   text=True, capture_output=True).stdout.splitlines()[0],
              "command": command, "inventory": frozen}
    core.atomic_json(marker, record)
    return record


def cutoff_values(build: dict) -> dict[str, float]:
    path = Path(build["source"]) / "SJARACNe/apmi_cutoff.py"
    spec = importlib.util.spec_from_file_location("brca_frozen_pchip", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return {key: module.get_mi_cutoff(80, float(v[1])) for key, v in DRIVERS.items()}


def stage_inputs(engine: Path, work: Path) -> dict:
    """Export immutable LF blobs, rejecting rather than replacing changed inputs."""
    target = work / "inputs"
    target.mkdir(parents=True, exist_ok=True)
    for name, expected in core.EXPECTED_LF_SHA256.items():
        path = target / name
        if path.exists():
            if core.sha256_file(path) != expected:
                raise RuntimeError(f"Existing input differs: {path}")
            continue
        payload = subprocess.run(core.git_command(engine, "show",
            f"{ENGINE_COMMIT}:tests/inputs/{name}"), check=True, capture_output=True).stdout
        if hashlib.sha256(payload).hexdigest() != expected:
            raise RuntimeError(f"Pinned input blob differs: {name}")
        temporary = path.with_suffix(path.suffix + ".partial")
        if temporary.exists():
            raise RuntimeError(f"Incomplete input staging: {temporary}")
        temporary.write_bytes(payload)
        os.replace(temporary, path)
    return inventory(target, [target / name for name in core.EXPECTED_LF_SHA256])


def prepare(engine: Path, work: Path, old_root: Path) -> tuple[dict, dict]:
    work.mkdir(parents=True, exist_ok=True)
    # Refuse an historical work-root accidentally supplied on the CLI.
    if (work / "sweep_design.json").exists() or work == old_root:
        raise ValueError("Use a fresh PCHIP work root, never the historical sweep root")
    inputs = stage_inputs(engine, work)
    build = build_engine(engine, work)
    cutoffs = cutoff_values(build)
    code_files = [HERE / "run.py", HERE.parent / "brca100_netbid_qc/run_workflows.py"]
    design = {"schema": "brca100-pchip-refresh-v1", "engine_commit": ENGINE_COMMIT,
              "pchip_data_sha256": DATA_SHA256, "pchip_primary_sha256": PRIMARY_SHA256,
              "inputs": inputs, "input_expression_nodes": 28278, "input_samples": 100,
              "sampling": "fixed-size without replacement", "sampling_request": "80%",
              "m": 80, "npar": 40, "dpi_epsilon": 0, "consensus_p": 1e-5,
              "seeds": SEEDS, "seeds_sha256": core.json_fingerprint(SEEDS),
              "binary_sha256": build["binary_sha256"],
              "runner_source_sha256": {str(p.relative_to(HERE.parent)): core.sha256_file(p)
                                        for p in code_files},
              "arms": {key: {"driver_file": value[0], "p_token": value[1],
                       "mi_cutoff": cutoffs[key],
                       "historical_arm": str(old_root / "results" / value[2] / key)}
                       for key, value in DRIVERS.items()},
              "comparability": "Matched input blobs, native seed schedule, m/Npar/DPI and consensus probability. AP-MI kernel and stock consensus source match the historical engine; cutoff selection and output metadata change. Compiler/runtime differences remain a qualification."}
    immutable_json(work / "design.json", design)
    return design, build


def seed_command(build: dict, work: Path, driver: str, seed: int, output: Path) -> list[str]:
    filename, p, _ = DRIVERS[driver]
    return [build["binary"], "-i", str(work / "inputs/BRCA100.exp"),
            "-l", str(work / "inputs" / filename),
            "-s", str(work / "inputs" / filename), "-p", p, "-e", "0",
            "-a", "adaptive_partitioning", "-H", build["config"].rstrip("/") + "/",
            "-N", "40", "-S", str(seed), "-o", str(output), "-u", "80%", "-M", "pchip"]


def required_headers(driver: str) -> tuple[str, ...]:
    return (">  MI threshold method experimental PCHIP empirical cutoff",
            ">  AP-MI actual m 80", ">  AP-MI Npar 40",
            f">  AP-MI PCHIP data SHA256 {DATA_SHA256}",
            f">  AP-MI PCHIP primary SHA256 {PRIMARY_SHA256}",
            ">  AP-MI outside principal p range no", ">  AP-MI extreme-tail p no",
            ">  AP-MI off-grid m yes", ">  DPI tolerance   0",
            ">  Sampling method fixed-size without replacement", ">  Sampling request 80%",
            ">  Eligible observations 100", ">  Sampled observations 80")


def validate_seed(path: Path, driver: str, design: dict, ids: set, hubs: set) -> dict:
    stage = core.Stage(STAGE_KEY, ENGINE_COMMIT, ("-u", "80%"), required_headers(driver))
    stats = core.validate_adjacency(path, stage=stage, driver_ids=hubs, expression_ids=ids)
    headers = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.startswith(">"):
                break
            for name in ("MI requested p binary64", "MI threshold binary64"):
                prefix = ">  " + name + " "
                if line.startswith(prefix):
                    headers[name] = float(line[len(prefix):])
    wanted = design["arms"][driver]
    if headers.get("MI requested p binary64") != float(wanted["p_token"]):
        raise RuntimeError(f"Wrong PCHIP p header: {path}")
    if not math.isclose(headers.get("MI threshold binary64", math.nan),
                        wanted["mi_cutoff"], rel_tol=2e-14, abs_tol=1e-15):
        raise RuntimeError(f"Wrong PCHIP cutoff header: {path}")
    return stats


def seed_job(build: dict, work: Path, design: dict, driver: str, seed: int,
             ids: set, hubs: set) -> dict:
    arm = work / "arms" / driver
    for folder in ("adj", "logs", "seed_metadata"):
        (arm / folder).mkdir(parents=True, exist_ok=True)
    stem = f"TF_run_{seed:03d}"
    output = arm / "adj" / f"{stem}.adj"
    temporary = output.with_suffix(".adj.partial")
    marker = arm / "seed_metadata" / f"{stem}.json"
    command = seed_command(build, work, driver, seed, temporary)
    fingerprint = core.json_fingerprint({"design_sha256": core.sha256_file(work / "design.json"),
                                        "executed_command": command, "final_output": str(output)})
    pending = marker.with_suffix(".pending.json")
    if marker.exists():
        record = core.load_json(marker)
        if record["fingerprint"] != fingerprint:
            raise RuntimeError(f"Stale seed manifest: {marker}")
        actual = validate_seed(output, driver, design, ids, hubs)
        verify_inventory(arm, record["log_inventory"])
        if record["adjacency"] != actual:
            raise RuntimeError(f"Changed seed output: {output}")
        return record
    if pending.exists():
        record = core.load_json(pending)
        candidate = output if output.exists() else temporary
        if record["fingerprint"] != fingerprint or not candidate.is_file():
            raise RuntimeError(f"Inconsistent pending seed: {pending}")
        stats = validate_seed(candidate, driver, design, ids, hubs)
        verify_inventory(arm, record["log_inventory"])
        if stats != record["adjacency"] or (output.exists() and temporary.exists()):
            raise RuntimeError(f"Pending seed changed: {candidate}")
        if candidate == temporary:
            os.replace(temporary, output)
        core.atomic_json(marker, record)
        pending.unlink()
        return record
    if output.exists() or temporary.exists():
        raise RuntimeError(f"Unverified incomplete seed; inspect explicitly: {output}")
    began = now()
    timings = timed(command, arm / "logs", stem,
                    cwd=Path(build["source"]), env=bounded_environment())
    stats = validate_seed(temporary, driver, design, ids, hubs)
    record = {"schema": "brca100-pchip-seed-v1", "driver": driver, "seed": seed,
              "fingerprint": fingerprint, "command": command, "final_output": str(output),
              "started_at_utc": began,
              "finished_at_utc": now(), "gnu_time": timings, "adjacency": stats,
              "log_inventory": inventory(arm, list((arm / "logs").glob(f"{stem}.*")))}
    # Do not reuse partial data after crashes without validation of a pending record.
    core.atomic_json(pending, record)
    os.replace(temporary, output)
    core.atomic_json(marker, record)
    pending.unlink()
    return record


def bounded_environment() -> dict:
    env = os.environ.copy()
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                 "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        env[name] = "1"
    return env


def aggregate(work: Path, design: dict) -> dict:
    rows = []
    for driver in DRIVERS:
        for seed in SEEDS:
            path = work / "arms" / driver / "seed_metadata" / f"TF_run_{seed:03d}.json"
            if path.exists():
                record = core.load_json(path)
                rows.append({"driver": driver, "seed": seed, "metadata_sha256": core.sha256_file(path),
                             "edges": record["adjacency"]["edges"],
                             "sha256": record["adjacency"]["full_sha256"]})
    result = {"schema": "brca100-pchip-run-v1", "design_sha256": core.sha256_file(work / "design.json"),
              "complete": len(rows) == 200, "completed_seed_jobs": len(rows), "rows": rows}
    core.atomic_json(work / "run_manifest.json", result)
    return result


def consensus(work: Path, build: dict, design: dict, driver: str, ids: set, hubs: set) -> dict:
    arm = work / "arms" / driver
    adjacency = arm / "adj"
    expected = [adjacency / f"TF_run_{seed:03d}.adj" for seed in SEEDS]
    if sorted(adjacency.iterdir()) != expected:
        raise RuntimeError(f"Consensus requires exactly all 100 adjacency files: {adjacency}")
    for seed in SEEDS:
        seed_job(build, work, design, driver, seed, ids, hubs)  # strict hash-validated reuse
    source = Path(build["source"])
    script = source / "SJARACNe/bin/create_consensus_network.py"
    root = arm / "consensus"
    partial = arm / "consensus.partial"
    marker = arm / "consensus_manifest.json"
    pending = marker.with_suffix(".pending.json")
    command = [sys.executable, "-m", "SJARACNe.bin.create_consensus_network",
               "-a", str(adjacency), "-p", "0.00001", "-e",
               str(work / "inputs/BRCA100.exp"), "-o", str(partial)]
    fingerprint = core.json_fingerprint({"command": command, "script_sha256": core.sha256_file(script),
        "design_sha256": core.sha256_file(work / "design.json"),
        "adjacency_sha256": [core.sha256_file(p) for p in expected]})
    if marker.exists():
        record = core.load_json(marker)
        if record["fingerprint"] != fingerprint:
            raise RuntimeError("Consensus manifest differs")
        verify_inventory(root, record["inventory"])
        verify_inventory(arm, record["log_inventory"])
        return record
    if pending.exists():
        record = core.load_json(pending)
        candidate = root if root.exists() else partial
        if record["fingerprint"] != fingerprint or not candidate.is_dir():
            raise RuntimeError(f"Inconsistent pending consensus: {pending}")
        verify_inventory(candidate, record["inventory"])
        verify_inventory(arm, record["log_inventory"])
        if root.exists() and partial.exists():
            raise RuntimeError("Both final and partial consensus exist")
        if candidate == partial:
            os.replace(partial, root)
        core.atomic_json(marker, record)
        pending.unlink()
        return record
    if root.exists() or partial.exists():
        raise RuntimeError(f"Unverified partial consensus; inspect: {arm}")
    env = bounded_environment()
    env["PYTHONPATH"] = str(source)
    timings = timed(command, arm / "logs", "consensus", cwd=source, env=env)
    ncol = partial / "consensus_network_ncol_.txt"
    stats = core.validate_consensus_ncol(ncol, driver_ids=hubs, expression_ids=ids)
    if ">  Bootstrap No: 100" not in (partial / "parameter_info_.txt").read_text():
        raise RuntimeError("Consensus did not record all 100 seeds")
    shutil.copy2(ncol, partial / "final_consensus_network.txt")
    record = {"schema": "brca100-pchip-consensus-v1", "fingerprint": fingerprint,
              "driver": driver, "command": command, "finished_at_utc": now(),
              "consensus_p": 1e-5, "ncol": stats, "gnu_time": timings,
              "inventory": inventory(partial, [p for p in partial.iterdir() if p.is_file()]),
              "log_inventory": inventory(arm, list((arm / "logs").glob("consensus.*")))}
    core.atomic_json(pending, record)
    os.replace(partial, root)
    core.atomic_json(marker, record)
    pending.unlink()
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-repo", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--historical-root", type=Path, default=OLD_ROOT)
    parser.add_argument("--phase", choices=("prepare", "infer", "consensus", "all"), default="all")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--drivers", choices=("all", "tf", "sig"), default="all")
    parser.add_argument("--seed-start", type=int, default=1)
    parser.add_argument("--seed-end", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.workers <= 12 or not 1 <= args.seed_start <= args.seed_end <= 100:
        parser.error("workers must be 1..12 and seeds must be within 1..100")
    engine, work, old = args.engine_repo.resolve(), args.work_root.resolve(), args.historical_root.resolve()
    # Keep this descriptor alive throughout main; concurrent invocations fail
    # before they can race against the same immutable outputs.
    import fcntl
    work.mkdir(parents=True, exist_ok=True)
    work_lock = (work / ".run.lock").open("a")
    try:
        fcntl.flock(work_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        raise RuntimeError(f"Another controller owns {work}") from error
    design, build = prepare(engine, work, old)
    drivers = list(DRIVERS) if args.drivers == "all" else [args.drivers]
    ids = core.parse_expression_ids(work / "inputs/BRCA100.exp")
    hubs = {key: core.parse_driver_ids(work / "inputs" / DRIVERS[key][0]) for key in drivers}
    if len(ids) != 28278 or any(len(hubs[key]) != (2608 if key == "tf" else 10680) for key in drivers):
        raise RuntimeError("Unexpected input gene counts")
    invocation = {"started_at_utc": now(), "arguments": vars(args) | {}, "status": "running"}
    invocation["arguments"] = {key: str(value) if isinstance(value, Path) else value
                               for key, value in invocation["arguments"].items()}
    history = work / "invocations"
    history.mkdir(exist_ok=True)
    invocation_path = history / f"{time.time_ns()}.json"
    core.atomic_json(invocation_path, invocation)
    try:
        if args.phase in ("infer", "all"):
            jobs = [(key, seed) for key in drivers for seed in range(args.seed_start, args.seed_end + 1)]
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = {pool.submit(seed_job, build, work, design, key, seed, ids, hubs[key]): (key, seed)
                           for key, seed in jobs}
                for count, future in enumerate(as_completed(futures), 1):
                    result = future.result()
                    print(f"{count}/{len(jobs)} {result['driver']} seed={result['seed']:03d} edges={result['adjacency']['edges']}", flush=True)
            aggregate(work, design)
        if args.phase in ("consensus", "all"):
            for key in drivers:  # serialized: stock consensus retains the full union
                record = consensus(work, build, design, key, ids, hubs[key])
                print(f"Consensus {key}: {record['ncol']['edges']} edges", flush=True)
        invocation["status"] = "complete"
    except BaseException as error:
        invocation["status"] = "failed"
        invocation["error"] = repr(error)
        raise
    finally:
        invocation["finished_at_utc"] = now()
        core.atomic_json(invocation_path, invocation)


if __name__ == "__main__":
    main()
