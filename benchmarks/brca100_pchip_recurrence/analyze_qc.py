#!/usr/bin/env python3
"""Pinned, four-network NetBID2 QC; never infer or alter consensus networks.

Run only after the recurrence runner has verified its inputs and completed both
consensus modes. The original PCHIP refresh's unchanged R script defines the
scale-free fit: lm(log10(P(k)+1/V) ~ log10(k)), k=1..max(total degree), where V
counts incident nodes. This descriptive QC is not biological edge validation.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
from pathlib import Path
import shutil
import subprocess
from typing import Any


BASE_PATH = Path(__file__).resolve().parents[1] / "brca100_pchip_refresh/analyze_qc.py"
_SPEC = importlib.util.spec_from_file_location("brca100_pchip_refresh_qc", BASE_PATH)
BASE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(BASE)

SCHEMA = "sjaracne-brca100-pchip-recurrence-netbid-qc-v1"
MODES = ("k6", "legacy_pc")
DRIVERS = BASE.DRIVERS
ENVIRONMENT = BASE.ENVIRONMENT
R_SOURCE_LF_SHA256 = BASE.R_SOURCE_LF_SHA256
WRAPPER_LF_SHA256 = BASE.WRAPPER_LF_SHA256
EXPRESSION_NODES = 28278
DRIVER_COUNTS = {"tf": 2608, "sig": 10680}
INPUT_HASHES = {
    "BRCA100.exp": "ad8a334f5f8cdf46a1000d3ee259b35258a18b3da2e314bb3a0cf7a421d98bc8",
    "BRCA100_TF.txt": "9b1219a489b99432175e4c4ad46add7b06f25aae388ee8dd3261fa91e4c43ffd",
    "BRCA100_SIG.txt": "16ca27df655f16684f880a4ad719c4e2ae3f8dc0d7e6b9eccdd24cd97c40797c",
}
LEGACY = {
    "tf": {"edges": 221487, "bytes": 16561983,
           "sha256": "4fd4385518f5645e441e9c78c3afeb253417a16aed5fad347bb934b38bed2d09"},
    "sig": {"edges": 379059, "bytes": 28310152,
            "sha256": "f6361e2df3e9fb758a4f1b2079b0aca27e5fa41f88a6927128d1f6366fc08c63"},
}
BASELINE_PACKAGE = BASE_PATH.parent / "results_2026-10-17"
SCALE_FREE_DEFINITION = (
    "Unchanged pinned R summary script: lm(log10(P(k)+1/V) ~ log10(k)), "
    "k=1..max(total degree), V=incident nodes; descriptive, not edge accuracy."
)
EXTRA_FIELDS = ["expression_nodes", "incident_node_fraction", *[
    name for threshold in (10, 20, 50)
    for name in (f"drivers_ge_{threshold}_targets", f"driver_fraction_ge_{threshold}_targets")
]]
SOURCE_PACKAGE_NAMES = {
    "netbid_wrapper": "netbid2-r", "r_script": "run_netbid_qc.R",
    "analyzer": "analyze_qc.py", "refresh_analyzer": "pchip_refresh_analyze_qc.py",
}


def quantile_type7(values: list[int], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("Cannot compute a target-size quantile without drivers")
    position = (len(ordered) - 1) * probability
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (position - lower) * (ordered[upper] - ordered[lower])


def audit_network(path: Path, drivers: list[str], genes: set[str]) -> dict[str, Any]:
    loaded = BASE.load_network(path, drivers, genes)
    zero = list(loaded["degree"].values())
    active = [value for value in zero if value]
    for scope, values in (("zero", zero), ("active", active)):
        for label, probability in (("q25", .25), ("q75", .75)):
            loaded["metrics"][f"target_size_{scope}_{label}"] = quantile_type7(values, probability)
    return loaded


def additional_metrics(loaded: dict[str, Any], gene_count: int) -> dict[str, Any]:
    counts = list(loaded["degree"].values())
    result = {"expression_nodes": gene_count,
              "incident_node_fraction": loaded["metrics"]["incident_nodes"] / gene_count}
    for threshold in (10, 20, 50):
        number = sum(value >= threshold for value in counts)
        result[f"drivers_ge_{threshold}_targets"] = number
        result[f"driver_fraction_ge_{threshold}_targets"] = number / len(counts)
    return result


def verify_inventory_record(path: Path, expected: dict[str, Any]) -> dict[str, Any]:
    actual = BASE.record(path)
    if any(actual[key] != expected.get(key) for key in ("bytes", "sha256")):
        raise ValueError(f"Network differs from frozen inventory: {path}")
    return actual


def verify_legacy(path: Path, driver: str, baseline_manifest: Path) -> dict[str, Any]:
    baseline = BASE.read_json(baseline_manifest)
    expected = LEGACY[driver]
    if baseline.get("ncol", {}).get("edges") != expected["edges"]:
        raise ValueError(f"Published legacy edge-count pin changed for {driver}")
    for key in ("bytes", "sha256"):
        if baseline.get("inventory", {}).get("consensus_network_ncol_.txt", {}).get(key) != expected[key]:
            raise ValueError(f"Published legacy network pin changed for {driver}")
    verify_inventory_record(path, expected)
    return {"status": "byte-identical to frozen current-PCHIP legacy consensus",
            "expected": expected, "baseline_manifest": BASE.record(baseline_manifest)}


def prepare(args: argparse.Namespace) -> tuple[dict[str, Any], set[str], dict[str, list[str]]]:
    work = args.work_root.resolve()
    if BASE.read_json(work / "run_manifest.json").get("complete") is not True:
        raise ValueError("Consensus run is not marked complete; do not start QC")
    sources = {
        "netbid_wrapper": BASE.pin_script(args.netbid_wrapper.resolve(), WRAPPER_LF_SHA256),
        "r_script": BASE.pin_script(args.r_script.resolve(), R_SOURCE_LF_SHA256),
        "analyzer": BASE.record(Path(__file__).resolve()),
        "refresh_analyzer": BASE.record(BASE_PATH),
    }
    inputs = [BASE.record(work / name)
              for name in ("design.json", "verification.json", "run_manifest.json")]
    for filename, expected in INPUT_HASHES.items():
        item = BASE.record(work / "inputs" / filename)
        if item["sha256"] != expected:
            raise ValueError(f"Frozen BRCA100 input changed: {filename}")
        inputs.append(item)
    genes = BASE.expression_ids(work / "inputs/BRCA100.exp")
    if len(genes) != EXPRESSION_NODES:
        raise ValueError("The full BRCA100 expression universe is required")
    driver_lists, baselines = {}, {}
    for driver, filename in DRIVERS.items():
        drivers = BASE.read_drivers(work / "inputs" / filename)
        if len(drivers) != DRIVER_COUNTS[driver] or not set(drivers) <= genes:
            raise ValueError(f"The full {driver} candidate-source universe is required")
        driver_lists[driver] = drivers
        for mode in MODES:
            arm = work / "arms" / driver / mode
            metadata = BASE.read_json(arm / "consensus_manifest.json")
            if metadata.get("driver") != driver or metadata.get("mode") != mode:
                raise ValueError(f"Consensus manifest arm identity mismatch: {arm}")
            if metadata.get("B") != 100:
                raise ValueError(f"Expected exactly 100 post-DPI inputs: {arm}")
            parameters = ((metadata.get("K"), metadata.get("K_over_B"), metadata.get("p_value_consensus")))
            expected_parameters = (6, .06, None) if mode == "k6" else (None, None, 1e-5)
            if parameters != expected_parameters:
                raise ValueError(f"Consensus selection parameters changed: {arm}")
            expected = metadata.get("inventory", {}).get("consensus_network_ncol_.txt")
            if not isinstance(expected, dict):
                raise ValueError(f"Missing consensus network inventory: {arm}")
            network = arm / "consensus_network_ncol_.txt"
            inputs.extend([BASE.record(arm / "consensus_manifest.json"),
                           verify_inventory_record(network, expected)])
            if mode == "legacy_pc":
                baseline_manifest = BASELINE_PACKAGE / "provenance" / driver / "consensus_manifest.json"
                baselines[driver] = verify_legacy(network, driver, baseline_manifest)
                inputs.append(BASE.record(baseline_manifest))
    return {"schema": SCHEMA, "sources": sources, "inputs": inputs,
            "expected_environment": ENVIRONMENT, "baseline_checks": baselines,
            "scale_free_definition": SCALE_FREE_DEFINITION}, genes, driver_lists


def verify_analysis(work: Path, signature: dict[str, Any]) -> dict[str, Any]:
    output = work / "analysis"
    path = output / "analysis_manifest.json"
    if not path.is_file():
        raise ValueError(f"Incomplete analysis; inspect rather than overwrite: {output}")
    manifest = BASE.read_json(path)
    files = [item for item in BASE.inventory(output) if item["path"] != path.name]
    if manifest.get("signature") != signature or manifest.get("files") != files:
        raise ValueError(f"Existing analysis is stale or modified: {output}")
    return manifest


def analyze(args: argparse.Namespace) -> dict[str, Any]:
    work = args.work_root.resolve()
    signature, genes, driver_lists = prepare(args)
    output = work / "analysis"
    if output.exists():
        return verify_analysis(work, signature)
    output.mkdir()
    (output / "netbid2").mkdir()
    rows, arms = [], []
    for driver in DRIVERS:
        for mode in MODES:
            network = work / "arms" / driver / mode / "consensus_network_ncol_.txt"
            loaded = audit_network(network, driver_lists[driver], genes)
            if mode == "legacy_pc" and loaded["metrics"]["edges"] != LEGACY[driver]["edges"]:
                raise ValueError(f"Legacy edge count changed: {driver}")
            qc_dir = output / "netbid2" / driver / mode
            prefix = f"{driver.upper()}_{mode}_"
            command = [str(args.netbid_wrapper.resolve()), "Rscript", str(args.r_script.resolve()),
                       str(network), str(work / "inputs" / DRIVERS[driver]),
                       str(qc_dir), prefix, "true"]
            stem = f"{driver}_{mode}"
            with (output / f"{stem}.stdout.log").open("xb") as stdout, \
                    (output / f"{stem}.stderr.log").open("xb") as stderr:
                subprocess.run(command, cwd=work, stdout=stdout, stderr=stderr, check=True)
            values = BASE.check_qc(qc_dir, loaded)
            BASE.check_html(qc_dir / f"{prefix}netQC.html")
            metrics = {**values, **additional_metrics(loaded, len(genes))}
            rows.append({"driver": driver, "mode": mode, **metrics})
            arms.append({"driver": driver, "mode": mode, "command": command,
                         "network": BASE.record(network), "metrics": metrics})
    BASE.write_tsv(output / "network_metrics.tsv", rows,
                   ["driver", "mode", *BASE.SUMMARY_FIELDS, *EXTRA_FIELDS])
    for item in [*signature["inputs"], *signature["sources"].values()]:
        if BASE.sha256(Path(item["path"])) != item["sha256"]:
            raise ValueError(f"Input changed during QC: {item['path']}")
    manifest = {"schema": SCHEMA, "signature": signature, "arms": arms,
                "finished_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
                "interpretation": "Same PCHIP post-DPI inputs; only consensus selection changes. "
                "Topology, coverage and scale-free fit are descriptive QC, not biological accuracy or FDR.",
                "files": BASE.inventory(output)}
    BASE.write_json(output / "analysis_manifest.json", manifest)
    return manifest


def verify_package(destination: Path) -> None:
    manifest = BASE.read_json(destination / "package_manifest.json")
    actual = [item for item in BASE.inventory(destination)
              if item["path"] not in ("package_manifest.json", "SHA256SUMS")]
    if manifest.get("schema") != SCHEMA + "-package" or manifest.get("files") != actual:
        raise ValueError("Compact QC package inventory changed")
    if manifest.get("analysis_manifest_sha256") != BASE.sha256(destination / "provenance/analysis_manifest.json"):
        raise ValueError("Packaged analysis manifest identity changed")
    BASE.pin_script(destination / "provenance/sources/netbid2-r", WRAPPER_LF_SHA256)
    BASE.pin_script(destination / "provenance/sources/run_netbid_qc.R", R_SOURCE_LF_SHA256)
    links = BASE.re.findall(r"\]\(([^)]+)\)", (destination / "QC_INDEX.md").read_text(encoding="utf-8"))
    if sorted(links) != sorted(f"{driver}_{mode}_netbid2_qc.html" for driver in DRIVERS for mode in MODES):
        raise ValueError("QC index must link to exactly the four packaged HTML reports")
    for driver in DRIVERS:
        for mode in MODES:
            BASE.check_html(destination / f"{driver}_{mode}_netbid2_qc.html")
            environment = {row["component"]: row["version"] for row in BASE.read_tsv(
                destination / "provenance/qc" / driver / mode / "netbid_environment.tsv")}
            if environment != ENVIRONMENT:
                raise ValueError("Packaged NetBID2 environment changed")
    checksums = (destination / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    expected_paths = {item["path"] for item in BASE.inventory(destination)
                      if item["path"] != "SHA256SUMS"}
    recorded = set()
    for line in checksums:
        digest, relative = line.split("  ", 1)
        if relative in recorded or relative not in expected_paths or BASE.sha256(destination / relative) != digest:
            raise ValueError("Compact QC checksum mismatch")
        recorded.add(relative)
    if recorded != expected_paths:
        raise ValueError("Incomplete compact QC checksums")


def package(work: Path, destination: Path, manifest: dict[str, Any]) -> None:
    work, destination = work.resolve(), destination.resolve()
    verify_analysis(work, manifest["signature"])
    for item in [*manifest["signature"]["inputs"], *manifest["signature"]["sources"].values()]:
        if BASE.sha256(Path(item["path"])) != item["sha256"]:
            raise ValueError(f"Input changed before packaging: {item['path']}")
    if destination.exists() or destination.is_relative_to(work):
        raise ValueError("Package must be a fresh directory outside the raw work root")
    destination.mkdir(parents=True)
    provenance = destination / "provenance"
    provenance.mkdir()
    shutil.copyfile(work / "analysis/network_metrics.tsv", destination / "network_metrics.tsv")
    shutil.copyfile(work / "analysis/analysis_manifest.json", provenance / "analysis_manifest.json")
    for filename in ("design.json", "verification.json", "run_manifest.json"):
        shutil.copyfile(work / filename, provenance / filename)
    links = []
    for driver in DRIVERS:
        for mode in MODES:
            qc = work / "analysis/netbid2" / driver / mode
            target = provenance / "qc" / driver / mode
            target.mkdir(parents=True)
            html_name = f"{driver}_{mode}_netbid2_qc.html"
            shutil.copyfile(qc / f"{driver.upper()}_{mode}_netQC.html", destination / html_name)
            for name in ("network_summary.tsv", "driver_target_sizes.tsv", "netbid_environment.tsv",
                         f"{driver.upper()}_{mode}_netQC.Rmd"):
                shutil.copyfile(qc / name, target / name)
            for suffix in ("stdout.log", "stderr.log"):
                shutil.copyfile(work / "analysis" / f"{driver}_{mode}.{suffix}", target / suffix)
            shutil.copyfile(work / "arms" / driver / mode / "consensus_manifest.json",
                            target / "consensus_manifest.json")
            links.append(f"- [{driver.upper()} / {mode}]({html_name})")
    source_dir = provenance / "sources"
    source_dir.mkdir()
    for name, item in manifest["signature"]["sources"].items():
        shutil.copyfile(item["path"], source_dir / SOURCE_PACKAGE_NAMES[name])
    (destination / ".gitattributes").write_text("* -text -whitespace\n", encoding="utf-8", newline="\n")
    (destination / "QC_INDEX.md").write_text(
        "# Four-network NetBID2 QC\n\n" + "\n".join(links) + "\n\n"
        "Download HTML and open locally; figures are embedded. Standard MathJax may need network access.\n"
        "Target sizes include every candidate source, including zero-target sources.\n"
        "These are descriptive QC reports, not biological validation or FDR estimates.\n",
        encoding="utf-8", newline="\n")
    BASE.write_json(destination / "package_manifest.json", {
        "schema": SCHEMA + "-package", "analysis_manifest_sha256": BASE.sha256(work / "analysis/analysis_manifest.json"),
        "files": BASE.inventory(destination)})
    checksum_files = BASE.inventory(destination)
    with (destination / "SHA256SUMS").open("x", encoding="utf-8", newline="\n") as handle:
        for item in checksum_files:
            handle.write(f"{item['sha256']}  {item['path']}\n")
    verify_package(destination)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--netbid-wrapper", type=Path, required=True)
    parser.add_argument("--r-script", type=Path,
                        default=BASE_PATH.parents[1] / "brca100_pr67_threshold_sweep/run_netbid_qc.R")
    parser.add_argument("--package-root", type=Path,
                        help="Optional fresh compact QC directory; does not write report narrative")
    parser.add_argument("--verify-only", action="store_true",
                        help="Verify all input/script/baseline pins without running R or writing outputs")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.verify_only:
        if args.package_root:
            raise ValueError("--verify-only cannot package outputs")
        signature, _, _ = prepare(args)
        print(BASE.json.dumps({"status": "verified; no R/QC execution", "signature": signature}, indent=2))
        return
    manifest = analyze(args)
    if args.package_root:
        package(args.work_root, args.package_root, manifest)
    print(BASE.json.dumps({"analysis": str(args.work_root / "analysis"), "arms": len(manifest["arms"])}, indent=2))


if __name__ == "__main__":
    main()
