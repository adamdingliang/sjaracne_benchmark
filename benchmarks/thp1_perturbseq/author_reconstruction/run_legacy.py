#!/usr/bin/env python3
"""Frozen, resumable paper-era SJARACNe bootstrap/consensus reconstruction.

This is NOT the missing author THP-1 artifact: version 0.2.1 is a documented
paper-era proxy. It executes its original consensus script, including its
normal approximation and four-decimal MI output. No PR71 or recurrence rule.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid


SOURCE_COMMIT = "2922ec9a57d3da4e88b849b840643f543f49807c"
PLATFORM = os.name
CONFIG_FILES = ("config_threshold.txt", "config_kernel.txt")
CONSENSUS_FILES = ("consensus_network_3col_.txt", "consensus_network_ncol_.txt",
                   "bootstrap_info_.txt", "parameter_info_.txt")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def json_write(path: Path, data, *, replace=False) -> None:
    """Exclusive first write; only our locked checkpoint may be replaced."""
    temporary = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    with temporary.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    if replace:
        os.replace(temporary, path)
    else:
        publish_file(temporary, path)


def publish_file(temporary: Path, target: Path) -> None:
    # Unlike rename on POSIX, link cannot replace an existing output.
    os.link(temporary, target)
    temporary.unlink()


def record_file(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": digest(path),
            "bytes": path.stat().st_size}


def wsl_path(path: Path) -> str:
    absolute = path.resolve()
    if PLATFORM != "nt":
        return str(absolute)
    if not re.fullmatch(r"[A-Za-z]:", absolute.drive):
        raise ValueError("WSL execution requires a drive-letter path, not UNC")
    return "/mnt/" + absolute.drive[0].lower() + absolute.as_posix()[2:]


def expression_info(path: Path) -> dict:
    """Validate identifiers/dimensions/values without modifying expression."""
    ids = set()
    with path.open(encoding="utf-8") as stream:
        header = stream.readline().rstrip("\r\n").split("\t")
        # The legacy native reader and original consensus use the first two
        # columns positionally; their labels vary across historical examples.
        if len(header) < 4 or not all(header[:2]):
            raise ValueError("Expected identifier, symbol, >=2 observation columns")
        if len(set(header[2:])) != len(header[2:]):
            raise ValueError("Duplicate observation identifiers")
        for rowno, line in enumerate(stream, 2):
            fields = line.rstrip("\r\n").split("\t")
            if len(fields) != len(header) or not fields[0] or not fields[1]:
                raise ValueError(f"Malformed expression row {rowno}")
            if fields[0] in ids or "----" in fields[0]:
                raise ValueError(f"Duplicate/unsafe expression identifier: {fields[0]}")
            ids.add(fields[0])
            if any(not math.isfinite(float(value)) for value in fields[2:]):
                raise ValueError(f"Nonfinite expression row {rowno}")
    if len(ids) < 2:
        raise ValueError("At least two genes required")
    return {"observations": len(header) - 2, "genes": len(ids), "ids": ids}


def hub_info(path: Path, genes: set) -> set:
    rows = path.read_text(encoding="utf-8").splitlines()
    if not rows or any(not row or row != row.strip() or "\t" in row for row in rows):
        raise ValueError("Hub file must contain one nonempty identifier per line")
    if len(set(rows)) != len(rows) or not set(rows) <= genes:
        raise ValueError("Duplicate hubs or hubs absent from expression")
    return set(rows)


def affine_cutoff(config: Path, observations: int, p: float) -> float:
    rows = [row for row in (config / CONFIG_FILES[0]).read_text().splitlines()
            if row.strip() and not row.startswith(">")]
    if len(rows) != 1:
        raise ValueError("Expected exactly one legacy affine coefficient row")
    alpha, beta, gamma = map(float, rows[0].split())
    cutoff = (alpha - math.log(p)) / (-beta - gamma * observations)
    if not math.isfinite(cutoff) or cutoff <= 0:
        raise ValueError("Invalid affine threshold")
    return cutoff


def make_frozen(args) -> tuple[dict, set, set]:
    if args.bootstrap_count < 1 or args.npar < 1 or args.workers < 1:
        raise ValueError("Bootstrap count, partition limit and workers must be positive")
    probabilities = [args.bootstrap_p, *args.consensus_p]
    if any(not math.isfinite(p) or not 0 < p < 1 for p in probabilities):
        raise ValueError("All p cutoffs must be finite and strictly between 0 and 1")
    if len(set(args.consensus_p)) != len(args.consensus_p):
        raise ValueError("Duplicate consensus p cutoff")
    components = json.loads(args.component_manifest.read_text(encoding="utf-8"))
    if components.get("source_commit") != SOURCE_COMMIT:
        raise ValueError("This reconstructed baseline requires the pinned version 0.2.1 commit")
    paths = {"binary": args.binary, "consensus_script": args.consensus_script,
             **{name: args.config / name for name in CONFIG_FILES}}
    for name, path in paths.items():
        expected = (components.get("config_sha256", {}).get(name) if name in CONFIG_FILES
                    else components.get(name + "_sha256"))
        if expected != digest(path):
            raise ValueError(f"Component hash mismatch: {name}")
    exp = expression_info(args.expression)
    hubs = hub_info(args.hubs, exp["ids"])
    inputs = {"expression": record_file(args.expression), "hubs": record_file(args.hubs)}
    preparation_binding = None
    if args.prepare_manifest is not None:
        inputs["prepare_manifest"] = record_file(args.prepare_manifest)
        prepared = json.loads(args.prepare_manifest.read_text(encoding="utf-8"))
        status = prepared.get("status")
        if status == "complete":
            prepared_files = prepared.get("outputs", {})
        elif status == "inference_inputs_ready":
            prepared_files = prepared.get("files", {})
        else:
            raise ValueError("Preparation manifest must be complete or inference_inputs_ready")
        for output_name, input_name in (("expression.exp", "expression"), ("hubs.txt", "hubs")):
            recorded = prepared_files.get(output_name, {})
            if recorded.get("sha256") != inputs[input_name]["sha256"]:
                raise ValueError(f"Input not bound to prepared artifact: {output_name}")
        preparation_binding = {"status": status,
                               "manifest": inputs["prepare_manifest"],
                               "expression": inputs["expression"], "hubs": inputs["hubs"]}
    frozen = {
        "schema": 1,
        "label": "author-style reconstructed paper-era baseline; exact THP1 author commit unknown",
        "source_commit": SOURCE_COMMIT,
        "component_manifest": record_file(args.component_manifest),
        "components": {name: record_file(path) for name, path in paths.items()},
        "build_record": components,
        "inputs": inputs,
        "preparation_binding": preparation_binding,
        "out": str(args.out.resolve()),
        "observations": exp["observations"], "genes": exp["genes"], "hubs": len(hubs),
        "parameters": {"bootstrap_count": args.bootstrap_count,
                       "seeds": list(range(1, args.bootstrap_count + 1)),
                       "bootstrap_p": args.bootstrap_p, "consensus_p": args.consensus_p,
                       "npar": args.npar, "dpi_tolerance": 0, "sampling": "legacy -r 1",
                       "algorithm": "adaptive_partitioning",
                       "explicit_mi_override": None,
                       "affine_mi_cutoff": affine_cutoff(args.config, exp["observations"], args.bootstrap_p)},
        "execution": {"platform": PLATFORM, "wsl_distro": args.wsl_distro,
                      "consensus_python": args.python, "consensus_wsl": args.consensus_wsl},
        "cutoff_provenance": {
            "bootstrap_p": "inferred from paper-era wrapper default; actual THP1 invocation unavailable",
            "consensus_primary": "0.01 stated in scMINER methods",
            "consensus_secondary": "0.001 author analysis folder label, not a tuned optimum",
            "version": "paper-era proxy inferred from public example; not exact THP1 commit"},
    }
    return frozen, exp["ids"], hubs


def verify_frozen(frozen: dict) -> None:
    records = [frozen["component_manifest"], *frozen["components"].values(),
               *frozen["inputs"].values()]
    for record in records:
        if digest(Path(record["path"])) != record["sha256"]:
            raise ValueError(f"Frozen input/component changed: {record['path']}")


def native_command(args, seed: int, output: Path) -> list[str]:
    path = wsl_path if PLATFORM == "nt" else lambda value: str(value.resolve())
    command = [path(args.binary), "-i", path(args.expression), "-l", path(args.hubs),
               "-s", path(args.hubs), "-H", path(args.config),
               "-a", "adaptive_partitioning", "-N", str(args.npar), "-S", str(seed),
               "-p", format(args.bootstrap_p, ".17g"), "-e", "0", "-r", "1",
               "-o", path(output)]
    if PLATFORM == "nt":
        command = ["wsl.exe", "-d", args.wsl_distro, "--", *command]
    return command


def consensus_command(args, p: float, output: Path) -> list[str]:
    path = wsl_path if args.consensus_wsl and PLATFORM == "nt" else lambda value: str(value.resolve())
    command = [args.python, path(args.consensus_script), "-a", path(args.out / "adj"),
               "-p", format(p, ".17g"), "-e", path(args.expression),
               "-o", path(output), "-s", path(args.hubs)]
    if args.consensus_wsl and PLATFORM == "nt":
        command = ["wsl.exe", "-d", args.wsl_distro, "--", *command]
    return command


def consensus_name(p: float) -> str:
    return "consensus_pc" + format(p, ".12e").replace(".000000000000", "")


def plan(args, frozen: dict) -> dict:
    return {"frozen": frozen,
            "bootstrap_commands": [native_command(args, seed, args.out / "adj" / f"bootstrap_{seed:03d}.adj")
                                   for seed in frozen["parameters"]["seeds"]],
            "consensus_commands": [consensus_command(args, p, args.out / consensus_name(p))
                                   for p in args.consensus_p],
            "note": "Plan does not run inference. Actual jobs use exclusive attempt paths before publishing."}


@contextmanager
def run_lock(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    lock = out / ".runner.lock"
    with lock.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps({"pid": os.getpid(), "started": time.time()}))
    try:
        yield
    finally:
        lock.unlink()


def next_attempt(out: Path, name: str) -> Path:
    parent = out / "attempts"
    parent.mkdir(exist_ok=True)
    index = 1
    while True:
        path = parent / f"{name}_{index:03d}"
        try:
            path.mkdir()
            return path
        except FileExistsError:
            index += 1


def validate_adjacency(path: Path, genes: set, hubs: set, frozen: dict, log: Path) -> dict:
    header = {}
    sources = set()
    edges = 0
    with path.open(encoding="utf-8") as stream:
        for rowno, line in enumerate(stream, 1):
            if line.startswith(">"):
                text = line[1:].strip()
                for key in ("MI threshold", "MI P-value", "DPI tolerance"):
                    if text.startswith(key):
                        header[key] = float(text[len(key):].strip())
                continue
            fields = line.rstrip("\r\n").split("\t")
            if not fields[0] or fields[0] not in hubs or fields[0] in sources or len(fields) % 2 != 1:
                raise ValueError(f"Invalid adjacency source/width at row {rowno}")
            sources.add(fields[0])
            targets = set()
            for index in range(1, len(fields), 2):
                target, value = fields[index], float(fields[index + 1])
                if target not in genes or target == fields[0] or target in targets:
                    raise ValueError(f"Invalid/duplicate adjacency target at row {rowno}")
                if not math.isfinite(value) or value < 0:
                    raise ValueError("Invalid adjacency MI")
                targets.add(target)
                edges += 1
    params = frozen["parameters"]
    for key, expected in (("MI threshold", params["affine_mi_cutoff"]),
                          ("MI P-value", params["bootstrap_p"]), ("DPI tolerance", 0)):
        if key not in header or not math.isclose(header[key], expected, rel_tol=1e-5, abs_tol=1e-12):
            raise ValueError(f"Native {key} disagrees with frozen parameters")
    counts = re.findall(r"Array No:\s*(\d+)", log.read_text(encoding="utf-8", errors="replace"))
    if not counts or any(int(count) != frozen["observations"] for count in counts):
        raise ValueError("Native observation/draw count disagrees with frozen expression")
    return {"edges": edges, "source_rows": len(sources), "header": header,
            "draws": frozen["observations"]}


def verify_completed(record: dict) -> None:
    if record.get("status") != "complete":
        raise ValueError("Job is not complete")
    for artifact in record["artifacts"].values():
        if digest(Path(artifact["path"])) != artifact["sha256"]:
            raise ValueError(f"Completed output changed: {artifact['path']}")


def bootstrap_job(args, frozen, genes, hubs, seed):
    final = args.out / "adj" / f"bootstrap_{seed:03d}.adj"
    attempt = next_attempt(args.out, f"bootstrap_{seed:03d}")
    temporary = attempt / final.name
    log = attempt / "native.log"
    command = native_command(args, seed, temporary)
    record = {"seed": seed, "status": "failed", "command": command,
              "attempt": str(attempt), "started": time.time()}
    try:
        if final.exists():
            raise FileExistsError(f"Uncheckpointed output will not be overwritten: {final}")
        verify_frozen(frozen)
        with log.open("x", encoding="utf-8") as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
        record["returncode"] = result.returncode
        if result.returncode != 0:
            raise RuntimeError(f"Native bootstrap {seed} failed; inspect {log}")
        record["validation"] = validate_adjacency(temporary, genes, hubs, frozen, log)
        verify_frozen(frozen)
        publish_file(temporary, final)
        record.update(status="complete", artifacts={"adjacency": record_file(final), "log": record_file(log)})
    except Exception as exc:
        record["error"] = str(exc)
    record["finished"] = time.time()
    return record


def verify_bootstraps(args, state) -> None:
    expected = {f"bootstrap_{seed:03d}.adj" for seed in state["frozen"]["parameters"]["seeds"]}
    actual = {path.name for path in (args.out / "adj").iterdir()}
    if actual != expected:
        raise ValueError("Consensus directory is not the exact completed bootstrap set")
    for seed in state["frozen"]["parameters"]["seeds"]:
        verify_completed(state["bootstraps"].get(str(seed), {}))


def validate_consensus(output: Path, genes: set, hubs: set) -> dict:
    """Stream-check original 3col/enhanced output agreement, preserving order."""
    three = output / CONSENSUS_FILES[0]
    enhanced = output / CONSENSUS_FILES[1]
    count = 0
    previous = None
    with three.open(encoding="utf-8") as left, enhanced.open(encoding="utf-8") as right:
        lreader, rreader = csv.reader(left, delimiter="\t"), csv.reader(right, delimiter="\t")
        if next(lreader, None) != ["source", "target", "MI"]:
            raise ValueError("Invalid original consensus header")
        rheader = next(rreader, [])
        if rheader[:5] != ["source", "target", "source.symbol", "target.symbol", "MI"]:
            raise ValueError("Invalid original enhanced consensus header")
        for row in lreader:
            other = next(rreader, None)
            if len(row) != 3 or other is None or len(other) != len(rheader):
                raise ValueError("Malformed or unequal consensus rows")
            source, target, value = row
            key = source + "----" + target
            # The pinned original script sorts by this key. Detect duplicates
            # without a millions-of-pairs in-memory set.
            if previous is not None and key <= previous:
                raise ValueError("Consensus order/duplicate mismatch with original script")
            previous = key
            mi = float(value)
            if source not in hubs or target not in genes or source == target or not math.isfinite(mi) or mi < 0:
                raise ValueError("Invalid consensus edge")
            if other[:2] != row[:2] or float(other[4]) != mi:
                raise ValueError("Enhanced consensus does not match 3col output")
            count += 1
        if next(rreader, None) is not None:
            raise ValueError("Extra enhanced consensus row")
    for name in CONSENSUS_FILES:
        if not (output / name).is_file():
            raise FileNotFoundError(output / name)
    return {"edges": count, "edge_order": "original consensus script order; adapter does not sort"}


def consensus_job(args, state, genes, hubs, p):
    name = consensus_name(p)
    final = args.out / name
    if final.exists():
        raise FileExistsError(f"Uncheckpointed consensus will not be overwritten: {final}")
    attempt = next_attempt(args.out, name)
    output = attempt / "output"
    log = attempt / "consensus.log"
    command = consensus_command(args, p, output)
    record = {"p": p, "status": "failed", "command": command,
              "attempt": str(attempt), "started": time.time()}
    try:
        verify_frozen(state["frozen"])
        verify_bootstraps(args, state)
        # The original script intentionally remains unmodified and uses
        # os.listdir rather than sorted filenames. Record the directory order
        # visible to the host; same directory is used for both consensus cuts.
        record["adjacency_directory_order_host"] = os.listdir(args.out / "adj")
        with log.open("x", encoding="utf-8") as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT, check=False)
        record["returncode"] = result.returncode
        if result.returncode != 0:
            raise RuntimeError(f"Original consensus failed; inspect {log}")
        record["validation"] = validate_consensus(output, genes, hubs)
        bootstrap_counts = re.findall(r"Bootstrap No:\s*(\d+)",
                                     (output / "parameter_info_.txt").read_text(encoding="utf-8"))
        if bootstrap_counts != [str(state["frozen"]["parameters"]["bootstrap_count"])]:
            raise ValueError("Original consensus bootstrap count disagrees with frozen run")
        verify_frozen(state["frozen"])
        verify_bootstraps(args, state)
        final.mkdir()  # Exclusive; an existing directory is never adopted.
        for source in output.iterdir():
            if not source.is_file():
                raise ValueError("Unexpected nested original consensus output")
            with source.open("rb") as src, (final / source.name).open("xb") as dst:
                shutil.copyfileobj(src, dst)
        # Exact copy retains the original MI strings and edge order for the R scorer.
        with (final / CONSENSUS_FILES[0]).open("rb") as src, (final / "edges.tsv").open("xb") as dst:
            shutil.copyfileobj(src, dst)
        record.update(status="complete", artifacts={path.name: record_file(path) for path in final.iterdir()})
        record["artifacts"]["log"] = record_file(log)
    except Exception as exc:
        record["error"] = str(exc)
    record["finished"] = time.time()
    return record


def execute(args) -> dict:
    args.out = args.out.resolve()
    frozen, genes, hubs = make_frozen(args)
    if args.action == "plan":
        return plan(args, frozen)
    path = args.out / "run_manifest.json"
    with run_lock(args.out):
        if path.exists():
            if not args.resume:
                raise FileExistsError("Run exists; use --resume only for unchanged frozen inputs/settings")
            state = json.loads(path.read_text(encoding="utf-8"))
            if state.get("frozen") != frozen:
                raise ValueError("Resume configuration/input/component differs from frozen run")
            for collection in (state["bootstraps"], state["consensus"]):
                for record in collection.values():
                    if record.get("status") == "complete":
                        verify_completed(record)
        else:
            if args.resume:
                raise FileNotFoundError("--resume requires an existing run_manifest.json")
            state = {"frozen": frozen, "bootstraps": {}, "consensus": {},
                     "created": time.time(), "status": "incomplete"}
            json_write(path, state)
        (args.out / "adj").mkdir(exist_ok=True)
        if args.action in ("bootstrap", "run"):
            pending = [seed for seed in frozen["parameters"]["seeds"]
                       if state["bootstraps"].get(str(seed), {}).get("status") != "complete"]
            for seed in pending:
                target = args.out / "adj" / f"bootstrap_{seed:03d}.adj"
                if target.exists():
                    raise FileExistsError(f"Uncheckpointed output will not be overwritten: {target}")
            # Queue only bounded worker jobs. Each result is checkpointed by
            # the single coordinator; completed futures are never lost on error.
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                futures = [pool.submit(bootstrap_job, args, frozen, genes, hubs, seed) for seed in pending]
                for future in as_completed(futures):
                    record = future.result()
                    state["bootstraps"][str(record["seed"])] = record
                    json_write(path, state, replace=True)
                    print(f"bootstrap {record['seed']}: {record['status']}", file=sys.stderr, flush=True)
            if any(state["bootstraps"].get(str(seed), {}).get("status") != "complete"
                   for seed in frozen["parameters"]["seeds"]):
                raise RuntimeError("One or more bootstraps failed; attempt outputs retained, inspect manifest/logs")
        if args.action in ("consensus", "run"):
            verify_bootstraps(args, state)
            for p in args.consensus_p:
                name = consensus_name(p)
                if state["consensus"].get(name, {}).get("status") == "complete":
                    continue
                record = consensus_job(args, state, genes, hubs, p)
                state["consensus"][name] = record
                json_write(path, state, replace=True)
                if record["status"] != "complete":
                    raise RuntimeError(record["error"])
        verify_frozen(frozen)
        state["status"] = ("complete" if len(state["consensus"]) == len(args.consensus_p)
                           and all(row["status"] == "complete" for row in state["consensus"].values())
                           else "bootstraps_complete")
        state["updated"] = time.time()
        json_write(path, state, replace=True)
        return state


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("action", choices=("plan", "bootstrap", "consensus", "run"))
    for name in ("expression", "hubs", "out", "binary", "config", "consensus-script", "component-manifest"):
        result.add_argument("--" + name, type=Path, required=True)
    result.add_argument("--prepare-manifest", type=Path)
    result.add_argument("--bootstrap-count", type=int, default=100)
    result.add_argument("--bootstrap-p", type=float, default=1e-7)
    result.add_argument("--consensus-p", type=float, nargs="+", default=[0.01, 0.001])
    result.add_argument("--npar", type=int, default=40)
    result.add_argument("--workers", type=int, default=2)
    result.add_argument("--python", default=sys.executable, help="Interpreter for the ORIGINAL consensus script")
    result.add_argument("--consensus-wsl", action="store_true", help="Run consensus interpreter in WSL too")
    result.add_argument("--wsl-distro", default="Ubuntu")
    result.add_argument("--resume", action="store_true")
    return result


if __name__ == "__main__":
    arguments = parser().parse_args()
    result = execute(arguments)
    if arguments.action == "plan":
        print(json.dumps(result, indent=2, allow_nan=False))
    else:
        print(json.dumps({"status": result["status"], "manifest": str(arguments.out / "run_manifest.json")}))
