#!/usr/bin/env python3
"""Engineering-only validation of unmodified historical raw-MI executables.

This does not score response labels or launch the 20-resample pilot. It checks
that selecting source rows (with the full expression input unchanged) leaves
their serialized MI values and implicit-zero patterns unchanged without DPI.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from pathlib import Path, PureWindowsPath
import re
import subprocess
import sys
import time


BEFORE_SHA256 = "7c358c4553f75f0ccfe5b035e97aebb72473b0e5d9c69c1336c1181ffd084ed5"
AFTER_SHA256 = "664be6122128c6919a82f71aca4c7fa6f21cd095029513969b0e8ff88fb4af86"
EXPRESSION_SHA256 = "d2e27058034efe096ddf7417da566fa2657386a8dee19b2cc27e8b433e34421e"
FULL_HUBS_SHA256 = "1b43bc91288b705ea24dc33ae12f679e72ac926647c9011e81409af3286fa5d1"
CONFIG_SHA256 = {
    "config_threshold.txt": "fb1694b1d4c9d9965a6ab2f3ee036e6387bebd94d2d8624102fd290b5e9f551e",
    "config_kernel.txt": "311b5be2f9939f4de920237de6bb50576cca4a0bb43440caebb98a4b32d2ec2c",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_record(path: Path, expected: str | None = None) -> dict:
    digest = sha256(path)
    if expected is not None and digest != expected:
        raise ValueError(f"Frozen file hash mismatch: {path}")
    return {"path": str(path.resolve()), "sha256": digest, "bytes": path.stat().st_size}


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def expression_info(path: Path) -> dict:
    ids, labels = [], set()
    with path.open(encoding="utf-8", newline="") as stream:
        rows = csv.reader(stream, delimiter="\t")
        header = next(rows)
        observations = len(header) - 2
        if observations < 2:
            raise ValueError("Expression needs at least two observations")
        seen = set()
        for row in rows:
            if len(row) != len(header) or not row[0] or row[0] in seen or row[1] in labels:
                raise ValueError("Invalid expression width or duplicate gene identifier/label")
            if any(not math.isfinite(float(value)) for value in row[2:]):
                raise ValueError("Nonfinite expression value")
            seen.add(row[0])
            labels.add(row[1])
            ids.append(row[0])
    return {"genes": ids, "observations": observations}


def source_scopes(full_hubs: list[str], eligible: set[str]) -> dict[str, list[str]]:
    if len(set(full_hubs)) != len(full_hubs) or not eligible <= set(full_hubs):
        raise ValueError("Eligible genes must be unique members of the full hub list")
    ordered = [hub for hub in full_hubs if hub in eligible]
    if len(ordered) < 3:
        raise ValueError("At least three eligible sources required")
    chosen = [ordered[0], ordered[len(ordered) // 2], ordered[-1]]
    unrelated = [hub for hub in full_hubs if hub not in eligible][:4]
    if len(unrelated) < 4:
        raise ValueError("Four unrelated hubs required")
    selected = set(chosen + unrelated)
    return {
        "subset": chosen,
        "expanded": [hub for hub in full_hubs if hub in selected],
        "reordered": chosen[::-1],
    }


def wsl_path(path: Path) -> str:
    raw = str(path.resolve())
    if re.match(r"^[A-Za-z]:[\\/]", raw):
        windows = PureWindowsPath(raw)
        return "/mnt/" + windows.drive[0].lower() + "/" + "/".join(windows.parts[1:])
    return raw


def native_command(binary: Path, expression: Path, annotation: Path, sources: Path,
                   config: Path, output: Path, seed: int, arm: str) -> list[str]:
    command = [wsl_path(binary), "-i", wsl_path(expression), "-l", wsl_path(annotation),
               "-s", wsl_path(sources), "-H", wsl_path(config), "-a", "adaptive_partitioning",
               "-N", "40", "-S", str(seed), "-p", "1", "-t", "0", "-e", "1", "-n", "0"]
    if arm == "before":
        command += ["-r", "1"]
    elif arm == "after":
        command += ["-u", "80%"]
    else:
        raise ValueError("Unknown sampling arm")
    return command + ["-o", wsl_path(output)]


def parse_adj(path: Path, sources: set[str], genes: set[str]) -> tuple[dict, dict]:
    headers, scores, emitted_sources = {}, {}, set()
    with path.open(encoding="utf-8") as stream:
        for number, line in enumerate(stream, 1):
            if line.startswith(">"):
                match = re.match(r">\s*(MI threshold|MI P-value|DPI tolerance)\s+(.+?)\s*$", line)
                if match:
                    if match[1] in headers:
                        raise ValueError("Duplicate native header")
                    headers[match[1]] = float(match[2])
                continue
            fields = line.rstrip("\r\n").split("\t")
            source = fields[0]
            if source not in sources or source in emitted_sources or len(fields) % 2 != 1:
                raise ValueError(f"Unexpected/duplicate source or malformed adjacency row {number}")
            emitted_sources.add(source)
            for index in range(1, len(fields), 2):
                target, serialized = fields[index:index + 2]
                value = float(serialized)
                key = (source, target)
                if target not in genes or target == source or key in scores:
                    raise ValueError("Unknown, self or duplicate pair")
                if not math.isfinite(value) or value <= 0:
                    raise ValueError("Expected native stored MI to be finite and positive")
                scores[key] = serialized
    if headers != {"MI threshold": 0.0, "MI P-value": 1.0, "DPI tolerance": 1.0}:
        raise ValueError("Native MI/DPI headers disagree with the unfiltered protocol")
    return scores, headers


def audit_log(text: str, *, genes: int, observations: int, arm: str) -> dict:
    draws = observations if arm == "before" else math.ceil(observations * .8)
    marker_counts = re.findall(r"Marker No:\s*(\d+)\s*\((\d+) active\), Array No:\s*(\d+)", text)
    if marker_counts != [(str(genes), str(genes), str(draws))]:
        raise ValueError("Native marker/active/draw counts disagree with the input")
    if "Applying DPI" in text or "MI threshold determined" in text:
        raise ValueError("Unexpected DPI or affine-threshold calculation")
    if "Cannot find probe" in text or "... ignored." in text:
        raise ValueError("Native source/annotation parser ignored a supplied gene")
    if arm == "after":
        pattern = (r"\[SAMPLING\] Fixed-size sampling without replacement: selected (\d+) "
                   r"of (\d+) eligible observations \(request: ([^)]+)\)\.")
        if re.findall(pattern, text) != [(str(draws), str(observations), "80%")]:
            raise ValueError("After arm lacks expected without-replacement sample binding")
    return {"genes": genes, "active_genes": genes, "eligible_observations": observations,
            "draws": draws, "no_dpi": True, "no_affine_threshold": True}


def compare_scores(reference: dict, candidate: dict, selected: list[str], genes: list[str]) -> dict:
    selected_set = set(selected)
    left = {pair: score for pair, score in reference.items() if pair[0] in selected_set}
    right = {pair: score for pair, score in candidate.items() if pair[0] in selected_set}
    if left != right:
        raise ValueError("Source scope changed serialized MI values or implicit-zero pattern")
    digest = hashlib.sha256()
    for (source, target), score in sorted(left.items()):
        digest.update(f"{source}\t{target}\t{score}\n".encode())
    pairs = len(selected) * (len(genes) - 1)
    return {"status": "passed", "sources": selected, "candidate_pairs": pairs,
            "nonzero_pairs": len(left), "implicit_zero_pairs": pairs - len(left),
            "exact_serialized_mi_equality": True, "exact_zero_pattern_equality": True,
            "nonzero_scores_sha256": digest.hexdigest()}


def make_tiny(root: Path) -> tuple[Path, Path, dict]:
    genes = [f"S{index:02d}" for index in range(16)]
    expression, annotation = root / "tiny.exp", root / "tiny_hubs.txt"
    lines = ["\t".join(["isoformId", "geneSymbol"] + [f"MC{i}" for i in range(16)])]
    for index, gene in enumerate(genes):
        values = [0 if index == 15 else ((index + 3) * (cell + 1) % 11) + ((cell // 3 + index) % 3) / 4
                  for cell in range(16)]
        lines.append("\t".join([gene, gene] + [str(value) for value in values]))
    expression.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    annotation.write_text("\n".join(genes[:8]) + "\n", encoding="utf-8", newline="\n")
    return expression, annotation, {"subset": [genes[0], genes[3], genes[7]],
                                    "expanded": genes[:8], "reordered": [genes[7], genes[3], genes[0]]}


def execute_case(args, *, case: str, expression: Path, annotation: Path,
                 scopes: dict, seeds: list[int], proof: dict) -> None:
    info = expression_info(expression)
    genes = info["genes"]
    case_root = args.out / case
    case_root.mkdir()
    hub_paths = {}
    for scope, names in scopes.items():
        hub_paths[scope] = case_root / f"{scope}_sources.txt"
        hub_paths[scope].write_text("\n".join(names) + "\n", encoding="utf-8", newline="\n")
    proof["cases"][case] = {"expression": file_record(expression), "annotation": file_record(annotation),
                              "source_lists": {scope: file_record(path) for scope, path in hub_paths.items()},
                              "observations": info["observations"], "genes": len(genes), "seeds": seeds}
    for arm in ("before", "after"):
        binary, config = getattr(args, f"{arm}_binary"), getattr(args, f"{arm}_config")
        for seed in seeds:
            results = {}
            for scope in ("subset", "expanded", "reordered"):
                stem = f"{arm}_seed{seed:03d}_{scope}"
                output, log, timing = [case_root / (stem + suffix) for suffix in (".adj", ".log", ".time.tsv")]
                command = native_command(binary, expression, annotation, hub_paths[scope], config, output, seed, arm)
                invocation = ["wsl.exe", "-d", args.wsl_distro, "--", "/usr/bin/time", "-f", "%e\t%M\t%x",
                              "-o", wsl_path(timing), "--", *command]
                started = time.monotonic()
                with log.open("w", encoding="utf-8") as stream:
                    completed = subprocess.run(invocation, stdout=stream, stderr=subprocess.STDOUT, check=False)
                run = {"case": case, "arm": arm, "seed": seed, "scope": scope, "command": invocation,
                       "exit_code": completed.returncode, "wall_seconds": time.monotonic() - started,
                       "log": file_record(log), "timing": file_record(timing) if timing.exists() else None}
                proof["runs"].append(run)
                if completed.returncode != 0:
                    raise RuntimeError(f"Native smoke failed: {stem}; inspect {log}")
                time_fields = timing.read_text().strip().splitlines()[-1].split("\t")
                if len(time_fields) != 3 or int(time_fields[2]) != 0:
                    raise ValueError("Native timing record is malformed")
                run.update({"native_seconds": float(time_fields[0]), "max_rss_kib": int(time_fields[1]),
                            "output": file_record(output)})
                run["audit"] = audit_log(log.read_text(encoding="utf-8", errors="replace"),
                                         genes=len(genes), observations=info["observations"], arm=arm)
                scores, headers = parse_adj(output, set(scopes[scope]), set(genes))
                run["headers"] = headers
                run["nonzero_pairs"] = len(scores)
                results[scope] = scores
            for scope in ("expanded", "reordered"):
                comparison = compare_scores(results["subset"], results[scope], scopes["subset"], genes)
                comparison.update({"case": case, "arm": arm, "seed": seed, "compared_scope": scope})
                proof["comparisons"].append(comparison)
            write_json(args.out / "proof.json", proof)


def run(args) -> dict:
    args.out.mkdir(parents=True, exist_ok=False)
    proof = {"schema_version": 1, "status": "running", "purpose": "engineering-only source-row equivalence",
             "response_reference_scored": False, "pilot_launched": False, "cases": {}, "runs": [],
             "comparisons": [], "parameters": {"mi_p": 1, "mi_threshold": 0, "dpi_epsilon": 1,
                                                "npar": 40, "noise_correction": 0},
             "serialization": "unchanged native default six significant digits; exact text equality"}
    started = time.monotonic()
    try:
        proof["binaries"] = {"before": file_record(args.before_binary, BEFORE_SHA256),
                              "after": file_record(args.after_binary, AFTER_SHA256)}
        proof["configs"] = {arm: {name: file_record(getattr(args, f"{arm}_config") / name, digest)
                                   for name, digest in CONFIG_SHA256.items()} for arm in ("before", "after")}
        expression, hubs = args.prepared / "expression.exp", args.prepared / "hubs.txt"
        proof["frozen_inputs"] = {"expression": file_record(expression, EXPRESSION_SHA256),
                                  "hubs": file_record(hubs, FULL_HUBS_SHA256),
                                  "eligible_sources": file_record(args.prepared / "reference_eligible_sources.tsv")}
        with (args.prepared / "reference_eligible_sources.tsv").open(encoding="utf-8", newline="") as stream:
            eligible = [row["source"] for row in csv.DictReader(stream, delimiter="\t")]
        full_hubs = hubs.read_text(encoding="utf-8").splitlines()
        if len(eligible) != 272 or len(set(eligible)) != 272 or len(full_hubs) != 6951:
            raise ValueError("Frozen THP-1 eligible/full hub counts disagree")
        actual_scopes = source_scopes(full_hubs, set(eligible))
        tiny_root = args.out / "tiny_inputs"
        tiny_root.mkdir()
        tiny_expression, tiny_annotation, tiny_scopes = make_tiny(tiny_root)
        execute_case(args, case="tiny", expression=tiny_expression, annotation=tiny_annotation,
                     scopes=tiny_scopes, seeds=[2, 17, 61], proof=proof)
        execute_case(args, case="actual_full_expression", expression=expression, annotation=hubs,
                     scopes=actual_scopes, seeds=[2], proof=proof)
        actual = proof["cases"]["actual_full_expression"]
        if actual["genes"] != 17971 or actual["observations"] != 121:
            raise ValueError("Frozen full expression dimensions disagree")
        proof["status"] = "passed"
    except Exception as error:
        proof["status"] = "failed"
        proof["error"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        proof["wall_seconds"] = time.monotonic() - started
        write_json(args.out / "proof.json", proof)
    return proof


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    for name in ("out", "prepared", "before-binary", "after-binary", "before-config", "after-config"):
        result.add_argument("--" + name, required=True, type=Path)
    result.add_argument("--wsl-distro", default="Ubuntu")
    return result


if __name__ == "__main__":
    try:
        args = parser().parse_args()
        result = run(args)
        print(json.dumps({"status": result["status"], "proof": str(args.out / "proof.json"),
                          "runs": len(result["runs"]), "comparisons": len(result["comparisons"]),
                          "wall_seconds": result["wall_seconds"]}, indent=2))
    except Exception as error:
        print(f"Smoke failed: {error}", file=sys.stderr)
        sys.exit(1)
