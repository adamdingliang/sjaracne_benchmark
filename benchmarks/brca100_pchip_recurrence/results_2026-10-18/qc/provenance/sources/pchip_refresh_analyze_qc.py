#!/usr/bin/env python3
"""Run pinned NetBID2 QC on a fresh full BRCA100 PCHIP workflow.

Run under WSL. The engine checkout and its outputs are external inputs; this
script never infers, thresholds, prunes, or reconstructs a network. Historical
sweep networks provide optional matched-setting comparisons of cutoff functions,
not biological validation; compiler/runtime equivalence needs an explicit-cutoff
anchor check.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import statistics
import subprocess
from typing import Any


SCHEMA = "sjaracne-brca100-pchip-netbid-qc-v1"
DRIVERS = {"tf": "BRCA100_TF.txt", "sig": "BRCA100_SIG.txt"}
OLD_POINTS = {"tf": "p1e-03", "sig": "p5e-04"}
ENVIRONMENT = {
    "R": "R version 4.4.3 (2025-02-28)",
    "NetBID2": "2.2.0",
    "NetBID2_remote_sha": "5defa454d600b94f5dd6d1f9f4428f99759a6821",
    "igraph": "2.3.3",
}
R_SOURCE_LF_SHA256 = "f9485b923e278ce7883d359181819cd728402dff11fcd4172b7fd6c0c51149a4"
WRAPPER_LF_SHA256 = "c706c7665fc2e589bf70030bb5dc0fc21935b93922b16fb256a5801752220095"
HEADER = ["source", "target", "source.symbol", "target.symbol", "MI",
          "pearson", "spearman", "slope", "p-value"]
SUMMARY_FIELDS = [
    "candidate_drivers", "active_drivers", "active_driver_fraction", "edges",
    "incident_nodes", "weak_components", "largest_weak_component",
    "largest_weak_component_fraction", "density", "target_size_zero_mean",
    "target_size_zero_median", "target_size_zero_q25", "target_size_zero_q75",
    "target_size_zero_max", "target_size_active_mean", "target_size_active_median",
    "target_size_active_q25", "target_size_active_q75", "target_size_active_max",
    "scale_free_adjusted_r2",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_file(path: Path) -> Path:
    if not path.is_file() or path.is_symlink():
        raise ValueError(f"Missing or non-regular input: {path}")
    return path


def record(path: Path) -> dict[str, Any]:
    require_file(path)
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha256(path)}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(require_file(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".partial")
    with temporary.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, indent=2, sort_keys=True, allow_nan=False)
        handle.write("\n")
    temporary.replace(path)


def inventory(root: Path) -> list[dict[str, Any]]:
    entries = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError(f"Symlink in output inventory: {path}")
        if path.is_file():
            entries.append({**record(path), "path": path.relative_to(root).as_posix()})
    return entries


def read_drivers(path: Path) -> list[str]:
    values = [line.strip() for line in require_file(path).read_text().splitlines()
              if line.strip()]
    if not values or len(values) != len(set(values)):
        raise ValueError(f"Empty or duplicate driver list: {path}")
    return values


def expression_ids(path: Path) -> set[str]:
    with require_file(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle, delimiter="\t")
        header = next(reader)
        if header[:2] != ["isoformId", "geneSymbol"]:
            raise ValueError(f"Unexpected expression header: {path}")
        values = [row[0] for row in reader]
    if not values or len(values) != len(set(values)) or any(not value for value in values):
        raise ValueError(f"Invalid expression accessions: {path}")
    return set(values)


def load_network(path: Path, drivers: list[str], genes: set[str]) -> dict[str, Any]:
    """Validate the native table and independently audit topology, using stdlib."""
    edges: set[tuple[str, str]] = set()
    degree = dict.fromkeys(drivers, 0)
    parent: dict[str, str] = {}
    size: dict[str, int] = {}

    def find(node: str) -> str:
        if node not in parent:
            parent[node], size[node] = node, 1
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    with require_file(path).open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if reader.fieldnames != HEADER:
            raise ValueError(f"Unexpected consensus columns: {path}: {reader.fieldnames}")
        for line_number, row in enumerate(reader, 2):
            source, target = row["source"], row["target"]
            edge = source, target
            if (source not in degree or source not in genes or target not in genes
                    or source == target or edge in edges or None in row):
                raise ValueError(f"Invalid or duplicate consensus edge: {path}:{line_number}")
            mi = float(row["MI"])
            if not math.isfinite(mi) or mi <= 0:
                raise ValueError(f"Invalid consensus MI: {path}:{line_number}")
            edges.add(edge)
            degree[source] += 1
            left, right = find(source), find(target)
            if left != right:
                if size[left] < size[right]:
                    left, right = right, left
                parent[right] = left
                size[left] += size[right]
    if not edges:
        raise ValueError(f"Empty consensus network: {path}")
    components = Counter(find(node) for node in parent)
    active = [value for value in degree.values() if value]
    nodes, largest = len(parent), max(components.values())
    return {"edges": edges, "degree": degree, "metrics": {
        "candidate_drivers": len(degree), "active_drivers": len(active),
        "active_driver_fraction": len(active) / len(degree), "edges": len(edges),
        "incident_nodes": nodes, "weak_components": len(components),
        "largest_weak_component": largest,
        "largest_weak_component_fraction": largest / nodes,
        "density": len(edges) / (nodes * (nodes - 1)),
        "target_size_zero_mean": statistics.mean(degree.values()),
        "target_size_zero_median": statistics.median(degree.values()),
        "target_size_zero_max": max(degree.values()),
        "target_size_active_mean": statistics.mean(active),
        "target_size_active_median": statistics.median(active),
        "target_size_active_max": max(active),
    }}


def read_tsv(path: Path) -> list[dict[str, str]]:
    with require_file(path).open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def read_summary(path: Path) -> dict[str, float]:
    rows = read_tsv(path)
    if len(rows) != len(SUMMARY_FIELDS) or {row["metric"] for row in rows} != set(SUMMARY_FIELDS):
        raise ValueError(f"Unexpected NetBID2 metric schema: {path}")
    values = {row["metric"]: float(row["value"]) for row in rows}
    if any(not math.isfinite(value) for value in values.values()):
        raise ValueError(f"Nonfinite NetBID2 metrics: {path}")
    return values


def check_qc(output: Path, expected: dict[str, Any]) -> dict[str, float]:
    values = read_summary(output / "network_summary.tsv")
    for name, value in expected["metrics"].items():
        if not math.isclose(values[name], value, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError(f"NetBID2/Python topology disagreement for {name}: {output}")
    rows = read_tsv(output / "driver_target_sizes.tsv")
    degrees = {row["driver"]: int(row["target_count"]) for row in rows}
    if len(degrees) != len(rows) or degrees != expected["degree"]:
        raise ValueError(f"NetBID2 zero-filled target-count disagreement: {output}")
    environment = {row["component"]: row["version"]
                   for row in read_tsv(output / "netbid_environment.tsv")}
    if environment != ENVIRONMENT:
        raise ValueError(f"Pinned NetBID2 environment changed: {environment}")
    return values


def check_html(path: Path) -> None:
    text = require_file(path).read_text(encoding="utf-8")
    if "<html" not in text.lower() or "data:image" not in text:
        raise ValueError(f"Missing HTML document or embedded network-QC figures: {path}")
    # Retain generated bytes. Standard R Markdown can dynamically request MathJax
    # online; its absence offline affects mathematical typesetting, not figures.
    for attribute, target in re.findall(r'''\b(src|href)=["']([^"']+)["']''', text):
        if target.startswith(("#", "data:", "http:", "https:", "mailto:", "javascript:")):
            continue
        raise ValueError(f"HTML has a nonportable local {attribute} asset: {target}")


def write_tsv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("x", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def edge_overlap(old: set[tuple[str, str]], new: set[tuple[str, str]]) -> dict[str, Any]:
    common = len(old & new)
    union = len(old) + len(new) - common
    return {"historical_edges": len(old), "pchip_edges": len(new), "common_edges": common,
            "historical_only_edges": len(old) - common, "pchip_only_edges": len(new) - common,
            "jaccard": common / union if union else 1.0,
            "fraction_historical_retained": common / len(old) if old else None,
            "fraction_pchip_shared": common / len(new) if new else None}


def pin_script(path: Path, expected_lf: str) -> dict[str, Any]:
    item = record(path)
    lf_hash = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    if lf_hash != expected_lf:
        raise ValueError(f"Pinned NetBID2 QC method source changed: {path}")
    return {**item, "lf_normalized_sha256": lf_hash}


def analyze(args: argparse.Namespace) -> dict[str, Any]:
    work = args.work_root.resolve()
    output = work / "analysis"
    wrapper, r_script = args.netbid_wrapper.resolve(), args.r_script.resolve()
    source_records = {"wrapper": pin_script(wrapper, WRAPPER_LF_SHA256),
                      "r_script": pin_script(r_script, R_SOURCE_LF_SHA256),
                      "analyzer": record(Path(__file__).resolve())}
    genes = expression_ids(work / "inputs/BRCA100.exp")
    input_records = [record(work / "inputs/BRCA100.exp"), record(work / "design.json"),
                     record(work / "run_manifest.json")]
    for driver, filename in DRIVERS.items():
        input_records.extend([record(work / "inputs" / filename),
                              record(work / "arms" / driver / "consensus_manifest.json"),
                              record(work / "arms" / driver / "consensus/final_consensus_network.txt")])
        if args.reference_root:
            historical = (args.reference_root / "results" / OLD_POINTS[driver] / driver
                          / "consensus/consensus_network_ncol_.txt")
            if historical.is_file():
                input_records.append(record(historical))
    signature = {"schema": SCHEMA, "sources": source_records, "inputs": input_records,
                 "reference_root": str(args.reference_root.resolve()) if args.reference_root else None,
                 "expected_environment": ENVIRONMENT}
    manifest_path = output / "analysis_manifest.json"
    if output.exists():
        if not manifest_path.is_file():
            raise ValueError(f"Incomplete analysis directory; inspect rather than overwrite: {output}")
        manifest = read_json(manifest_path)
        files = [item for item in inventory(output) if item["path"] != "analysis_manifest.json"]
        if manifest.get("signature") != signature or manifest.get("files") != files:
            raise ValueError(f"Existing analysis is stale or modified: {output}")
        return manifest
    output.mkdir()
    (output / "netbid2").mkdir()
    metrics_rows, comparisons, arms = [], [], []
    for driver, filename in DRIVERS.items():
        drivers = read_drivers(work / "inputs" / filename)
        network = work / "arms" / driver / "consensus/final_consensus_network.txt"
        loaded = load_network(network, drivers, genes)
        qc_dir = output / "netbid2" / driver
        command = [str(wrapper), "Rscript", str(r_script), str(network),
                   str(work / "inputs" / filename), str(qc_dir), driver.upper() + "_", "true"]
        with (output / f"{driver}.stdout.log").open("xb") as stdout, \
                (output / f"{driver}.stderr.log").open("xb") as stderr:
            subprocess.run(command, stdout=stdout, stderr=stderr, check=True, cwd=work)
        values = check_qc(qc_dir, loaded)
        check_html(qc_dir / f"{driver.upper()}_netQC.html")
        metrics_rows.append({"network": driver.upper(), **values})
        arm = {"driver": driver, "command": command, "network": record(network),
               "metrics": values}
        historical = None
        if args.reference_root:
            historical = (args.reference_root / "results" / OLD_POINTS[driver] / driver
                          / "consensus/consensus_network_ncol_.txt")
        if historical and historical.is_file():
            old = load_network(historical, drivers, genes)
            comparison = {"network": driver.upper(), "historical_point": OLD_POINTS[driver],
                          **edge_overlap(old["edges"], loaded["edges"])}
            comparisons.append(comparison)
            arm["historical_network"] = record(historical)
            arm["historical_topology"] = old["metrics"]
            arm["historical_overlap"] = comparison
            write_tsv(output / f"{driver}_paired_target_sizes.tsv", [
                {"driver": name, "historical_targets": old["degree"][name],
                 "pchip_targets": loaded["degree"][name]} for name in drivers
            ], ["driver", "historical_targets", "pchip_targets"])
        else:
            arm["historical_comparison_status"] = "not available; no network was substituted"
        arms.append(arm)
    write_tsv(output / "network_metrics.tsv", metrics_rows, ["network", *SUMMARY_FIELDS])
    if comparisons:
        write_tsv(output / "historical_edge_overlap.tsv", comparisons, list(comparisons[0]))
    # All inputs must remain unchanged throughout analysis.
    for item in [*input_records, *source_records.values()]:
        if sha256(Path(item["path"])) != item["sha256"]:
            raise ValueError(f"Input changed while running QC: {item['path']}")
    manifest = {"schema": SCHEMA, "signature": signature, "arms": arms,
                "finished_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "interpretation": "Post-DPI consensus topology QC, not biological validation. "
                "Historical comparison matches inputs, seeds, sampling, DPI and consensus settings; "
                "the cutoff function changes. AP-MI kernel and consensus source are unchanged. "
                "Compiler/runtime equivalence is qualified by the explicit-cutoff anchor check.",
                "files": inventory(output)}
    write_json(manifest_path, manifest)
    return manifest


def package(work: Path, destination: Path, manifest: dict[str, Any]) -> None:
    """Package only compact QC products, never native adjacency or expression."""
    source = work / "analysis"
    if destination.exists():
        raise ValueError(f"Package destination already exists; not overwriting: {destination}")
    if destination.resolve().is_relative_to(work.resolve()):
        raise ValueError("Package destination must be outside the native work root")
    destination.mkdir(parents=True)
    (destination / "provenance").mkdir()
    for filename in ("network_metrics.tsv", "historical_edge_overlap.tsv",
                     "tf_paired_target_sizes.tsv", "sig_paired_target_sizes.tsv"):
        if (source / filename).is_file():
            shutil.copyfile(source / filename, destination / filename)
    for driver in DRIVERS:
        shutil.copyfile(source / "netbid2" / driver / f"{driver.upper()}_netQC.html",
                        destination / f"{driver}_netbid2_qc.html")
        arm_dir = destination / "provenance" / driver
        arm_dir.mkdir()
        for filename in ("network_summary.tsv", "driver_target_sizes.tsv", "netbid_environment.tsv",
                         f"{driver.upper()}_netQC.Rmd"):
            shutil.copyfile(source / "netbid2" / driver / filename, arm_dir / filename)
        for suffix in ("stdout.log", "stderr.log"):
            shutil.copyfile(source / f"{driver}.{suffix}", arm_dir / suffix)
        shutil.copyfile(work / "arms" / driver / "consensus_manifest.json",
                        arm_dir / "consensus_manifest.json")
    for filename in ("design.json", "run_manifest.json"):
        shutil.copyfile(work / filename, destination / "provenance" / filename)
    shutil.copyfile(source / "analysis_manifest.json", destination / "provenance/analysis_manifest.json")
    for name, item in manifest["signature"]["sources"].items():
        shutil.copyfile(item["path"], destination / "provenance" / Path(item["path"]).name)
    (destination / ".gitattributes").write_text("* -text -whitespace\n", encoding="utf-8", newline="\n")
    (destination / "README.md").write_text(
        "# BRCA100 PCHIP network-QC results\n\n"
        "Inputs are final post-DPI consensus networks from the fresh PCHIP run.\n"
        "Network metrics use the full supplied driver lists, including zero-target drivers.\n"
        "Scale-free R2 is NetBID2's adjusted log-degree regression R2, not evidence of edge truth.\n\n"
        "- [TF QC HTML](tf_netbid2_qc.html)\n"
        "- [SIG QC HTML](sig_netbid2_qc.html)\n"
        "- [Network metrics](network_metrics.tsv)\n\n"
        "Download HTML files and open locally: GitHub displays source instead of rendering HTML.\n"
        "Figures and normal assets are embedded. The standard template may request MathJax online;\n"
        "offline viewing can omit mathematical typesetting. Verify with `sha256sum -c SHA256SUMS`.\n\n"
        "Historical sweep overlap, when present, is a matched-setting cutoff-function comparison:\n"
        "inputs, seeds, sampling, DPI and consensus settings match, and AP-MI kernel and consensus\n"
        "source are unchanged. Compiler/runtime equivalence is qualified by the explicit-cutoff\n"
        "anchor check. These comparisons are descriptive, without biological edge truth.\n"
        "Network shape cannot establish reliability or a final-network FDR.\n",
        encoding="utf-8", newline="\n")
    files = inventory(destination)
    write_json(destination / "package_manifest.json", {"schema": SCHEMA + "-package",
               "analysis_manifest_sha256": sha256(source / "analysis_manifest.json"), "files": files})
    checksum_files = inventory(destination)
    with (destination / "SHA256SUMS").open("x", encoding="utf-8", newline="\n") as handle:
        for item in checksum_files:
            handle.write(f"{item['sha256']}  {item['path']}\n")
    for item in files:
        if sha256(destination / item["path"]) != item["sha256"]:
            raise ValueError(f"Packaged product changed: {item['path']}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--netbid-wrapper", type=Path, required=True,
                        help="Existing pinned external environment's netbid2-r wrapper")
    parser.add_argument("--r-script", type=Path,
                        default=Path(__file__).resolve().parents[1] / "brca100_pr67_threshold_sweep/run_netbid_qc.R")
    parser.add_argument("--reference-root", type=Path,
                        help="Optional frozen old sweep root for TF1e-3/SIG5e-4 edge overlap")
    parser.add_argument("--package-root", type=Path,
                        help="Optional fresh compact report directory outside native work root")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = analyze(args)
    if args.package_root:
        package(args.work_root.resolve(), args.package_root.resolve(), manifest)
    print(json.dumps({"analysis": str(args.work_root / "analysis"),
                      "metrics": [arm["metrics"] for arm in manifest["arms"]]}, indent=2))


if __name__ == "__main__":
    main()
