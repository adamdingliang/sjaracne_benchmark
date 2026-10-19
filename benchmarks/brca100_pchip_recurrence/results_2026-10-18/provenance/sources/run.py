#!/usr/bin/env python3
"""Verify and reaggregate frozen PCHIP BRCA100 adjacencies; never run inference.

Linux/WSL only for execution. Preparation exports raw Git blobs into a NEW work
root and creates adjacency-only symlink directories. Consensus uses the tested
f512ef3 Python environment and unmodified production code. Failed jobs are not
implicitly resumed or overwritten: investigate them and choose a new work root.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time


HERE = Path(__file__).resolve().parent
ENGINE_COMMIT = "f512ef3a29c661e7cdd7b3b2c4027285d8d19fa3"
INFERENCE_COMMIT = "86f8729087b3a6d22bdce128649b4e49d725fb9e"
RAW_ROOT = Path("/home/adam/sjaracne-benchmarks/brca100-pchip-refresh-20261017-full100")
WORK_ROOT = Path("/home/adam/sjaracne-benchmarks/brca100-pchip-recurrence-20261018")
TESTED_ROOT = Path("/home/adam/sjaracne-regression/pr3-f512ef3-20261018-r2")
REGRESSION_EVIDENCE = Path("/mnt/d/GitHub/_validation/sjaracne_pr3_refresh_20261018_r2")
FROZEN_RESULTS = HERE.parent / "brca100_pchip_refresh/results_2026-10-17"
SEEDS = tuple(range(1, 101))
DRIVERS = {"tf": "BRCA100_TF.txt", "sig": "BRCA100_SIG.txt"}
MODES = ("k6", "legacy_pc")
INPUTS = {
    "BRCA100.exp": {"bytes": 49824227, "sha256": "ad8a334f5f8cdf46a1000d3ee259b35258a18b3da2e314bb3a0cf7a421d98bc8"},
    "BRCA100_TF.txt": {"bytes": 33904, "sha256": "9b1219a489b99432175e4c4ad46add7b06f25aae388ee8dd3261fa91e4c43ffd"},
    "BRCA100_SIG.txt": {"bytes": 138840, "sha256": "16ca27df655f16684f880a4ad719c4e2ae3f8dc0d7e6b9eccdd24cd97c40797c"},
}
FROZEN_PINS = {
    "provenance/design.json": "053afb20a3edcb54c72a563df2194566dd5d559b6934c63eed8b5a5b1f58270c",
    "provenance/run_manifest.json": "7ca556d88bc7d75924c870fdaecef6abe8775f20dfbf1bd18025eb3c0ffb2d2b",
    "provenance/tf/consensus_manifest.json": "82480fcdc50b5c746e419c9dbf667efe39b0cf0cdd4e1c1082c3b5e970bff406",
    "provenance/sig/consensus_manifest.json": "6a959ee63a7e87d2ba18467bd40617eddaf8430cf3cedc366adc5857498f8e25",
}
SOURCE_FILES = (
    "SJARACNe/__init__.py", "SJARACNe/apmi_cutoff.py",
    "SJARACNe/bin/__init__.py", "SJARACNe/bin/ch_line_ending.py",
    "SJARACNe/bin/create_consensus_network.py",
)
OUTPUT_FILES = ("consensus_network_3col_.txt", "consensus_network_ncol_.txt",
                "bootstrap_info_.txt", "parameter_info_.txt")
PER_JOB_BUDGET_KIB = 5 * 1024 * 1024


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path):
    path = Path(path)
    return {"bytes": path.stat().st_size, "sha256": sha256(path)}


def load_json(path):
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("Expected JSON object: " + str(path))
    return value


def atomic_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    temporary.replace(path)


def require_file(path, expected):
    path = Path(path)
    actual = file_record(path)
    if actual != {key: expected[key] for key in ("bytes", "sha256")}:
        raise RuntimeError("Frozen file mismatch: " + str(path))
    return actual


def git_blob(repo, relative):
    command = ["git", "-c", "safe.directory=" + str(repo), "-C", str(repo),
               "cat-file", "blob", ENGINE_COMMIT + ":" + relative]
    return subprocess.run(command, check=True, stdout=subprocess.PIPE).stdout


def export_blob(repo, relative, destination, expected=None):
    payload = git_blob(repo, relative)
    digest = hashlib.sha256(payload).hexdigest()
    if expected is not None and digest != expected:
        raise RuntimeError("Raw Git blob SHA256 mismatch: " + relative)
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("xb") as handle:
        handle.write(payload)
    return {"bytes": len(payload), "sha256": digest}


def run_rows(manifest, seeds=SEEDS):
    expected = {(driver, seed) for driver in DRIVERS for seed in seeds}
    rows = {}
    for row in manifest["rows"]:
        key = (row["driver"], row["seed"])
        if key not in expected or key in rows:
            raise RuntimeError("Unexpected/duplicate seed manifest row: " + repr(key))
        rows[key] = row
    if (not manifest.get("complete") or set(rows) != expected
            or manifest.get("completed_seed_jobs") != len(expected)):
        raise RuntimeError("Incomplete frozen seed schedule")
    return rows


def exact_adjacency_files(directory, seeds=SEEDS):
    directory = Path(directory)
    names = ["TF_run_%03d.adj" % seed for seed in seeds]
    if sorted(path.name for path in directory.iterdir()) != sorted(names):
        raise RuntimeError("Expected adjacency-only exact seed directory: " + str(directory))
    paths = [directory / name for name in names]
    if any(not path.is_file() or path.is_symlink() for path in paths):
        raise RuntimeError("Raw adjacency inputs must be regular, non-symlink files")
    return paths


def option(command, name):
    if command.count(name) != 1 or command.index(name) + 1 >= len(command):
        raise RuntimeError("Missing/duplicate frozen command option: " + name)
    return command[command.index(name) + 1]


def verify_seed(path, metadata_path, frozen_metadata, row, driver, seed, design):
    if sha256(frozen_metadata) != row["metadata_sha256"]:
        raise RuntimeError("Frozen seed metadata hash mismatch: " + str(frozen_metadata))
    if sha256(metadata_path) != row["metadata_sha256"]:
        raise RuntimeError("Raw seed metadata differs from frozen record: " + str(metadata_path))
    metadata = load_json(frozen_metadata)
    expected = metadata["adjacency"]
    if (metadata.get("driver") != driver or metadata.get("seed") != seed
            or expected["full_sha256"] != row["sha256"] or expected["edges"] != row["edges"]
            or Path(metadata["final_output"]).resolve() != path.resolve()):
        raise RuntimeError("Seed metadata identity mismatch: " + str(path))
    command = metadata["command"]
    raw_root = path.parents[3]
    wanted = {"-S": str(seed), "-M": "pchip", "-u": "80%", "-N": "40", "-e": "0",
              "-p": design["arms"][driver]["p_token"],
              "-i": str(raw_root / "inputs/BRCA100.exp"),
              "-s": str(raw_root / "inputs" / DRIVERS[driver]),
              "-l": str(raw_root / "inputs" / DRIVERS[driver]),
              "-o": str(path) + ".partial"}
    if any(option(command, flag) != value for flag, value in wanted.items()):
        raise RuntimeError("Frozen seed command contract mismatch: " + str(path))
    full, data = hashlib.sha256(), hashlib.sha256()
    headers, edges, source_rows, byte_count = [], 0, 0, 0
    with path.open("rb") as handle:
        for line in handle:
            full.update(line)
            byte_count += len(line)
            if line.startswith(b">"):
                headers.append(line.decode("utf-8").rstrip("\r\n"))
            else:
                data.update(line)
                tokens = line.rstrip(b"\r\n").split(b"\t")
                if len(tokens) < 3 or len(tokens) % 2 == 0:
                    raise RuntimeError("Malformed frozen adjacency row: " + str(path))
                edges += (len(tokens) - 1) // 2
                source_rows += 1
    actual = {"bytes": byte_count, "full_sha256": full.hexdigest(),
              "data_sha256": data.hexdigest(), "edges": edges,
              "header_lines": len(headers), "source_rows": source_rows}
    if any(expected[key] != value for key, value in actual.items()):
        raise RuntimeError("Adjacency bytes/data/counts differ from frozen metadata: " + str(path))
    required = [">  MI threshold method experimental PCHIP empirical cutoff",
                ">  AP-MI actual m 80", ">  AP-MI Npar 40", ">  DPI tolerance   0",
                ">  Sampling method fixed-size without replacement", ">  Sampling request 80%",
                ">  Eligible observations 100", ">  Sampled observations 80",
                ">  AP-MI PCHIP data SHA256 " + design["pchip_data_sha256"],
                ">  AP-MI PCHIP primary SHA256 " + design["pchip_primary_sha256"]]
    if any(header not in headers for header in required):
        raise RuntimeError("Frozen PCHIP/native header mismatch: " + str(path))
    observed_cutoffs = {}
    for key, wanted_value in (("MI requested p binary64", float(wanted["-p"])),
                              ("MI threshold binary64", design["arms"][driver]["mi_cutoff"])):
        prefix = ">  " + key + " "
        values = [float(header[len(prefix):]) for header in headers if header.startswith(prefix)]
        if (len(values) != 1 or not math.isfinite(values[0])
                or (values[0] != wanted_value if key == "MI requested p binary64"
                    else not math.isclose(values[0], wanted_value, rel_tol=2e-14, abs_tol=1e-15))):
            raise RuntimeError("Wrong probability/cutoff header: " + str(path))
        observed_cutoffs[key] = values[0]
    return {"driver": driver, "seed": seed, "path": str(path),
            "metadata_path": str(metadata_path), "metadata_sha256": row["metadata_sha256"],
            "native_cutoff": observed_cutoffs["MI threshold binary64"],
            "native_cutoff_hex": observed_cutoffs["MI threshold binary64"].hex(), **actual}


def verify_frozen(raw, frozen):
    provenance = {}
    for relative, expected in FROZEN_PINS.items():
        path = frozen / relative
        if sha256(path) != expected:
            raise RuntimeError("Pinned provenance changed: " + str(path))
        provenance[relative] = file_record(path)
    design = load_json(frozen / "provenance/design.json")
    if (design["engine_commit"] != INFERENCE_COMMIT or design["m"] != 80
            or design["npar"] != 40 or design["dpi_epsilon"] != 0
            or design["seeds"] != list(SEEDS)):
        raise RuntimeError("Unexpected frozen inference design")
    require_file(raw / "design.json", provenance["provenance/design.json"])
    require_file(raw / "run_manifest.json", provenance["provenance/run_manifest.json"])
    manifest = load_json(frozen / "provenance/run_manifest.json")
    if manifest["design_sha256"] != FROZEN_PINS["provenance/design.json"]:
        raise RuntimeError("Frozen run/design link differs")
    rows = run_rows(manifest)
    inputs = {}
    for name, expected in INPUTS.items():
        if design["inputs"][name] != expected:
            raise RuntimeError("Frozen input contract differs: " + name)
        inputs[name] = {"path": str(raw / "inputs" / name),
                        **require_file(raw / "inputs" / name, expected)}
    verified = []
    baselines = {}
    for driver in DRIVERS:
        paths = exact_adjacency_files(raw / "arms" / driver / "adj")
        for seed, path in zip(SEEDS, paths):
            name = "TF_run_%03d.json" % seed
            verified.append(verify_seed(path, raw / "arms" / driver / "seed_metadata" / name,
                frozen / "provenance/native" / driver / "seed_metadata" / name,
                rows[(driver, seed)], driver, seed, design))
        if len({row["native_cutoff_hex"] for row in verified if row["driver"] == driver}) != 1:
            raise RuntimeError("Native cutoff changed between seeds in one arm")
        baseline = load_json(frozen / "provenance" / driver / "consensus_manifest.json")
        if baseline["driver"] != driver or baseline["consensus_p"] != 1e-5:
            raise RuntimeError("Unexpected frozen consensus selection")
        baseline_root = raw / "arms" / driver / "consensus"
        files = {name: require_file(baseline_root / name, baseline["inventory"][name])
                 for name in OUTPUT_FILES}
        baselines[driver] = {"path": str(baseline_root), "inventory": files,
                             "ncol": baseline["ncol"]}
    return {"schema": "brca100-pchip-recurrence-verification-v1", "passed": True,
            "raw_root": str(raw), "frozen_results": str(frozen),
            "provenance_inventory": provenance, "inputs": inputs,
            "adjacency_files_verified": len(verified), "rows": verified,
            "baselines": baselines, "inference_design": design}


def bounded_environment(python, source, work):
    allowed = {"PATH", "LANG", "LC_ALL", "TZ", "USER", "LOGNAME"}
    env = {key: value for key, value in os.environ.items() if key in allowed}
    env.update({"PATH": str(python.parent) + ":" + env.get("PATH", "/usr/bin:/bin"),
                "PYTHONPATH": str(source), "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1", "TMPDIR": str(work / "tmp")})
    for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
        env[key] = "1"
    return env


def stage_engine(repo, tested, evidence, python, work):
    regression = load_json(evidence / "manifest.json")
    tracked = load_json(evidence / "tracked_source_sha256.json")
    if (regression.get("commit") != ENGINE_COMMIT or not regression.get("complete")
            or not regression.get("passed") or Path(regression["source_root"]).resolve() != tested.resolve()
            or Path(regression["installed_test_environment"]["executable"]).absolute() != python.absolute()):
        raise RuntimeError("Expected exact successful f512ef3 regression environment")
    source = work / "engine_source"
    inventory = {}
    for relative in SOURCE_FILES:
        if sha256(tested / relative) != tracked[relative]:
            raise RuntimeError("Tested source changed: " + relative)
        inventory[relative] = export_blob(repo, relative, source / relative, tracked[relative])
    for name, expected in INPUTS.items():
        exported = export_blob(repo, "tests/inputs/" + name, work / "inputs" / name, expected["sha256"])
        if exported != expected:
            raise RuntimeError("Exported input byte count differs: " + name)
    env = bounded_environment(python, source, work)
    code = (
        "import importlib,json,sys,hashlib;from pathlib import Path;import importlib.metadata as m;"
        "import SJARACNe;mod=importlib.import_module('SJARACNe.bin.create_consensus_network');"
        "root=Path(sys.argv[1]).resolve();assert Path(SJARACNe.__file__).resolve()==root/'SJARACNe/__init__.py';"
        "assert Path(mod.__file__).resolve()==root/'SJARACNe/bin/create_consensus_network.py';"
        "print(json.dumps({'python':sys.version,'executable':sys.executable,'package':SJARACNe.__file__,"
        "'consensus_module':mod.__file__,'versions':{x:m.version(x) for x in ['numpy','scipy','pandas']}}))"
    )
    command = [str(python), "-c", code, str(source)]
    result = subprocess.run(command, cwd=source, env=env, check=True,
                            capture_output=True, text=True)
    identity = json.loads(result.stdout)
    expected_versions = regression["installed_test_environment"]["versions"]
    if any(identity["versions"][key] != expected_versions[key] for key in identity["versions"]):
        raise RuntimeError("Tested numerical dependency versions changed")
    return {"commit": ENGINE_COMMIT, "source": str(source), "python": str(python),
            "source_inventory": inventory, "identity_command": command, "identity": identity,
            "regression_evidence": str(evidence), "regression_manifest_sha256": sha256(evidence / "manifest.json")}


def create_adjacency_links(work, verification):
    for driver in DRIVERS:
        directory = work / "adjacency" / driver
        directory.mkdir(parents=True)
        for row in verification["rows"]:
            if row["driver"] == driver:
                target = Path(row["path"])
                (directory / target.name).symlink_to(target)
        expected = {"TF_run_%03d.adj" % seed for seed in SEEDS}
        if {path.name for path in directory.iterdir()} != expected:
            raise RuntimeError("Adjacency staging did not preserve all seeds")


def consensus_command(python, work, driver, mode):
    if driver not in DRIVERS or mode not in MODES:
        raise ValueError("Unknown consensus configuration")
    selection = ["-k", "6"] if mode == "k6" else ["-p", "0.00001"]
    return [str(python), "-m", "SJARACNe.bin.create_consensus_network",
            "-a", str(work / "adjacency" / driver), *selection,
            "-e", str(work / "inputs/BRCA100.exp"),
            "-o", str(work / "arms" / driver / mode)]


def normalized_parameters(path):
    lines = Path(path).read_bytes().splitlines(keepends=True)
    if sum(line.startswith(b">  Output network: ") for line in lines) != 1:
        raise RuntimeError("Expected exactly one output-path provenance line")
    return b"".join(b">  Output network: <OUTPUT>\n" if line.startswith(b">  Output network: ")
                    else line for line in lines)


def validate_consensus_metadata(root, mode):
    info = (root / "bootstrap_info_.txt").read_text(encoding="utf-8")
    parameters = (root / "parameter_info_.txt").read_text(encoding="utf-8")
    if ">  Bootstrap No: 100\n" not in parameters:
        raise RuntimeError("Consensus B is not 100")
    if mode == "k6":
        metadata = dict(line.split(": ", 1) for line in info.splitlines())
        required = {"Consensus selection": "minimum recurrence", "Bootstrap networks": "100",
                    "Minimum recurrence": "6", "Minimum recurrence fraction": "0.06"}
        if (any(metadata.get(key) != value for key, value in required.items())
                or set(metadata) != set(required) | {"Total edge tested"}
                or ">  Minimum recurrence 6 of 100\n" not in parameters
                or ">  Minimum recurrence fraction 0.06\n" not in parameters):
            raise RuntimeError("Incorrect K6/B100 recurrence metadata")
    elif "Minimum recurrence" in info + parameters or "mu: " not in info or "sigma: " not in info:
        raise RuntimeError("Legacy consensus did not remain on the probability path")


def compare_legacy(root, baseline):
    original = Path(baseline["path"])
    for name in OUTPUT_FILES[:-1]:
        require_file(root / name, baseline["inventory"][name])
    if normalized_parameters(root / "parameter_info_.txt") != normalized_parameters(original / "parameter_info_.txt"):
        raise RuntimeError("Legacy parameter provenance changed beyond output path")
    return {"passed": True, "baseline": str(original),
            "exact_files": list(OUTPUT_FILES[:-1]), "parameter_info": "exact_except_output_path"}


def parse_time(path):
    values = dict(line.split("=", 1) for line in Path(path).read_text().splitlines())
    return {key: int(value) if key == "max_rss_kib" else float(value)
            for key, value in values.items()}


def run_consensus(work, design, verification, driver, mode):
    output = work / "arms" / driver / mode
    if output.exists():
        raise RuntimeError("Refusing existing consensus output: " + str(output))
    logs = work / "arms" / driver / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    command = consensus_command(Path(design["engine"]["python"]), work, driver, mode)
    time_path = logs / (mode + ".time.txt")
    actual = ["/usr/bin/time", "-f", "elapsed_s=%e\nuser_s=%U\nsystem_s=%S\nmax_rss_kib=%M",
              "-o", str(time_path), *command]
    print(now(), "START", driver, mode, flush=True)
    with (logs / (mode + ".stdout.log")).open("xb") as stdout:
        with (logs / (mode + ".stderr.log")).open("xb") as stderr:
            result = subprocess.run(actual, cwd=design["engine"]["source"],
                env=bounded_environment(Path(design["engine"]["python"]),
                    Path(design["engine"]["source"]), work), stdout=stdout, stderr=stderr)
    if result.returncode:
        raise RuntimeError("Consensus failed: %s/%s rc=%s" % (driver, mode, result.returncode))
    validate_consensus_metadata(output, mode)
    legacy = compare_legacy(output, verification["baselines"][driver]) if mode == "legacy_pc" else None
    record = {"schema": "brca100-pchip-recurrence-consensus-v1", "driver": driver, "mode": mode,
              "engine_commit": ENGINE_COMMIT, "inference_engine_commit": INFERENCE_COMMIT,
              "command": command, "executed_command": actual, "finished_at_utc": now(),
              "B": 100, "K": 6 if mode == "k6" else None,
              "K_over_B": 0.06 if mode == "k6" else None,
              "p_value_consensus": 1e-5 if mode == "legacy_pc" else None,
              "gnu_time": parse_time(time_path), "legacy_comparison": legacy,
              "inventory": {name: file_record(output / name) for name in OUTPUT_FILES},
              "log_inventory": {path.name: file_record(path) for path in sorted(logs.glob(mode + ".*"))}}
    atomic_json(output / "consensus_manifest.json", record)
    print(now(), "COMPLETE", driver, mode, json.dumps(record["gnu_time"]), flush=True)
    return record


def available_memory_kib():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1])
    raise RuntimeError("MemAvailable is unavailable")


def validate_prepared(work, raw, frozen):
    design = load_json(work / "design.json")
    old_verification = load_json(work / "verification.json")
    if (design["engine_commit"] != ENGINE_COMMIT or design["raw_root"] != str(raw)
            or design["runner_sha256"] != sha256(__file__)):
        raise RuntimeError("Prepared work/controller identity differs")
    verification = verify_frozen(raw, frozen)  # all 200 hashes before any process
    if verification != old_verification:
        raise RuntimeError("Prepared inputs/provenance changed")
    for relative, expected in design["engine"]["source_inventory"].items():
        require_file(work / "engine_source" / relative, expected)
    for name, expected in INPUTS.items():
        require_file(work / "inputs" / name, expected)
    for driver in DRIVERS:
        staging = work / "adjacency" / driver
        if {path.name for path in staging.iterdir()} != {"TF_run_%03d.adj" % seed for seed in SEEDS}:
            raise RuntimeError("Prepared adjacency staging changed")
        for row in verification["rows"]:
            if row["driver"] == driver:
                link = staging / Path(row["path"]).name
                if not link.is_symlink() or link.resolve() != Path(row["path"]).resolve():
                    raise RuntimeError("Prepared adjacency link changed")
    return design, verification


def prepare(args, work, raw, frozen):
    if work.exists():
        raise RuntimeError("Preparation requires a NEW work root: " + str(work))
    verification = verify_frozen(raw, frozen)  # no output writes before all200 verify
    work.mkdir(parents=True)
    (work / "tmp").mkdir()
    engine = stage_engine(args.engine_repo.resolve(), args.tested_source.resolve(),
                          args.regression_evidence.resolve(), args.python.absolute(), work)
    create_adjacency_links(work, verification)
    design = {"schema": "brca100-pchip-recurrence-design-v1", "engine_commit": ENGINE_COMMIT,
              "inference_engine_commit": INFERENCE_COMMIT, "raw_root": str(raw),
              "frozen_results": str(frozen), "engine": engine, "runner_sha256": sha256(__file__),
              "inputs": INPUTS, "B": 100, "K": 6, "K_over_B": 0.06,
              "legacy_p_value_consensus": 1e-5, "drivers": DRIVERS, "modes": list(MODES),
              "seeds": list(SEEDS), "m": 80, "npar": 40, "dpi_epsilon": 0,
              "sampling": "fixed-size without replacement", "sampling_request": "80%",
              "inference_rerun": False, "created_at_utc": now()}
    atomic_json(work / "verification.json", verification)
    atomic_json(work / "design.json", design)
    atomic_json(work / "run_manifest.json", {"schema": "brca100-pchip-recurrence-run-v1",
                "complete": False, "passed": False, "status": "prepared", "engine_commit": ENGINE_COMMIT,
                "design_sha256": sha256(work / "design.json"), "rows": []})
    return design, verification


def execute(work, design, verification, workers):
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 4:
        raise ValueError("Consensus workers must be within1..4")
    initial = load_json(work / "run_manifest.json")
    if initial.get("status") != "prepared" or initial.get("rows"):
        raise RuntimeError("Run is not a fresh prepared plan; implicit resume is forbidden")
    for driver in DRIVERS:
        for mode in MODES:
            if (work / "arms" / driver / mode).exists():
                raise RuntimeError("Refusing an existing consensus output directory")
            if list((work / "arms" / driver / "logs").glob(mode + ".*")):
                raise RuntimeError("Refusing existing consensus logs; implicit resume is forbidden")
    memory = available_memory_kib()
    if memory < workers * PER_JOB_BUDGET_KIB:
        raise RuntimeError("Insufficient available memory for requested consensus concurrency")
    record = {**initial, "status": "running", "started_at_utc": now(), "workers": workers,
              "numeric_threads_per_job": 1, "mem_available_kib_before_jobs": memory,
              "per_job_budget_kib": PER_JOB_BUDGET_KIB,
              "verification_sha256": sha256(work / "verification.json")}
    atomic_json(work / "run_manifest.json", record)
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(run_consensus, work, design, verification, driver, mode)
                       for driver in DRIVERS for mode in MODES]
            for future in as_completed(futures):
                result = future.result()
                path = work / "arms" / result["driver"] / result["mode"] / "consensus_manifest.json"
                record["rows"].append({"driver": result["driver"], "mode": result["mode"],
                    "path": str(path), "sha256": sha256(path), "inventory": result["inventory"]})
                atomic_json(work / "run_manifest.json", record)
        # Detect source/raw/provenance changes during aggregation, not just before it.
        final_design, final_verification = validate_prepared(work,
            Path(design["raw_root"]), Path(design["frozen_results"]))
        if final_design != design or final_verification != verification:
            raise RuntimeError("Run input identities changed")
        record.update({"complete": True, "passed": True, "status": "complete", "finished_at_utc": now()})
    except BaseException as error:
        record.update({"complete": False, "passed": False, "status": "failed", "error": repr(error), "finished_at_utc": now()})
        raise
    finally:
        atomic_json(work / "run_manifest.json", record)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine-repo", type=Path, required=True)
    parser.add_argument("--tested-source", type=Path, default=TESTED_ROOT / "source")
    parser.add_argument("--python", type=Path, default=TESTED_ROOT / "venv/bin/python")
    parser.add_argument("--regression-evidence", type=Path, default=REGRESSION_EVIDENCE)
    parser.add_argument("--raw-root", type=Path, default=RAW_ROOT)
    parser.add_argument("--frozen-results", type=Path, default=FROZEN_RESULTS)
    parser.add_argument("--work-root", type=Path, default=WORK_ROOT)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--phase", choices=("prepare", "consensus", "all"), default="all")
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        parser.error("workers must be within1..4")
    if sys.platform != "linux":
        parser.error("Execution requires Linux/WSL")
    work, raw, frozen = args.work_root.resolve(), args.raw_root.resolve(), args.frozen_results.resolve()
    safe_parent = Path("/home/adam/sjaracne-benchmarks").resolve()
    protected = (raw, frozen, args.engine_repo.resolve(), args.tested_source.resolve(), args.python.parent.resolve())
    if work == safe_parent or not work.is_relative_to(safe_parent) or any(work.is_relative_to(path) for path in protected):
        parser.error("Choose a NEW isolated directory under /home/adam/sjaracne-benchmarks")
    if args.phase in ("prepare", "all"):
        design, verification = prepare(args, work, raw, frozen)
    else:
        design, verification = validate_prepared(work, raw, frozen)
    if args.phase in ("consensus", "all"):
        import fcntl
        with (work / ".consensus.lock").open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            execute(work, design, verification, args.workers)
    print(now(), "FINISHED", args.phase, str(work), flush=True)


if __name__ == "__main__":
    main()
