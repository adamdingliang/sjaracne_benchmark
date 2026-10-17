#!/usr/bin/env python3
"""Publish a validated BRCA100 comparison without changing frozen QC products.

Run only after inference, consensus, the implementation anchor and NetBID2 QC
have completed. Large expression/adjacency files are never copied. The original
QC package manifest/checksums remain untouched; a separate presentation manifest
and checksum list cover the complete augmented package.
"""
from __future__ import annotations

import argparse
import importlib.util
import math
from pathlib import Path
import shutil
import statistics

HERE = Path(__file__).resolve().parent


def import_local(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


qc = import_local("brca_presentation_qc", "analyze_qc.py")
run = import_local("brca_presentation_run", "run.py")
anchor = import_local("brca_presentation_anchor", "validate_anchor.py")
SCHEMA = "brca100-pchip-presentation-v1"
EXPRESSION_NODES = 28278
EXPECTED_DRIVERS = {"tf": 2608, "sig": 10680}
METRIC_FIELDS = ["network", "function", "per_resample_p", "mi_cutoff", *qc.SUMMARY_FIELDS]


def verify_record(path: Path, item: dict) -> dict:
    actual = qc.record(path)
    if actual["sha256"] != item["sha256"] or actual["bytes"] != item["bytes"]:
        raise ValueError(f"Hash/size mismatch: {path}")
    return actual


def child(root: Path, relative: str) -> Path:
    path = root / relative
    if Path(relative).is_absolute() or not path.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Inventory path escapes its root: {relative}")
    return path


def verify_entries(root: Path, entries: list[dict]) -> None:
    names = [item["path"] for item in entries]
    if len(names) != len(set(names)):
        raise ValueError("Duplicate inventory paths")
    for item in entries:
        verify_record(child(root, item["path"]), item)


def verify_checksums(root: Path, filename: str) -> None:
    seen = set()
    for line in qc.require_file(root / filename).read_text(encoding="utf-8").splitlines():
        expected, relative = line.split("  ", 1)
        if relative in seen or qc.sha256(qc.require_file(child(root, relative))) != expected:
            raise ValueError(f"Invalid checksum entry: {relative}")
        seen.add(relative)
    if not seen:
        raise ValueError("Empty checksum file")


def validate_ledger(ledger: dict, design_sha256: str) -> dict[tuple[str, int], dict]:
    if (ledger.get("complete") is not True or ledger.get("completed_seed_jobs") != 200
            or ledger.get("design_sha256") != design_sha256 or len(ledger.get("rows", [])) != 200):
        raise ValueError("Full 200-job inference ledger is not complete and design-bound")
    rows = {(item["driver"], item["seed"]): item for item in ledger["rows"]}
    expected = {(driver, seed) for driver in EXPECTED_DRIVERS for seed in range(1, 101)}
    if set(rows) != expected:
        raise ValueError("Ledger contains missing, duplicate or unexpected seed identities")
    return rows


def read_metrics(path: Path) -> dict[str, dict[str, float]]:
    rows = qc.read_tsv(path)
    if len(rows) != 2 or {row["network"] for row in rows} != {"TF", "SIG"}:
        raise ValueError("Exactly two network metric rows are required")
    result = {}
    for row in rows:
        if set(row) != {"network", *qc.SUMMARY_FIELDS}:
            raise ValueError("Unexpected network metric columns")
        values = {name: float(row[name]) for name in qc.SUMMARY_FIELDS}
        if any(not math.isfinite(value) for value in values.values()):
            raise ValueError("Nonfinite network metric")
        result[row["network"].lower()] = values
    return result


def paired_counts(path: Path, drivers: list[str], old: dict, current: dict) -> dict:
    rows = qc.read_tsv(path)
    if any(set(row) != {"driver", "historical_targets", "pchip_targets"} for row in rows):
        raise ValueError("Unexpected paired-target columns")
    names = [row["driver"] for row in rows]
    if len(names) != len(set(names)) or set(names) != set(drivers):
        raise ValueError("Paired targets must contain each candidate source exactly once")
    old_values = [int(row["historical_targets"]) for row in rows]
    new_values = [int(row["pchip_targets"]) for row in rows]
    if min([*old_values, *new_values], default=-1) < 0:
        raise ValueError("Negative or empty target counts")
    for values, metrics in ((old_values, old), (new_values, current)):
        checks = {"candidate_drivers": len(values), "edges": sum(values),
                  "target_size_zero_median": statistics.median(values),
                  "active_drivers": sum(value > 0 for value in values)}
        for name, value in checks.items():
            if not math.isclose(metrics[name], value, rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError(f"Paired-target/summary disagreement: {name}")
    return {"historical": old_values, "pchip": new_values,
            "increased": sum(new > previous for previous, new in zip(old_values, new_values)),
            "unchanged": sum(new == previous for previous, new in zip(old_values, new_values)),
            "decreased": sum(new < previous for previous, new in zip(old_values, new_values))}


def validate_overlap(row: dict, old: dict, current: dict) -> dict:
    fields = ("historical_edges", "pchip_edges", "common_edges",
              "historical_only_edges", "pchip_only_edges")
    values = {name: int(row[name]) for name in fields}
    if (min(values.values()) < 0 or values["historical_edges"] != old["edges"]
            or values["pchip_edges"] != current["edges"]
            or values["common_edges"] + values["historical_only_edges"] != old["edges"]
            or values["common_edges"] + values["pchip_only_edges"] != current["edges"]):
        raise ValueError("Inconsistent directed-edge overlap counts")
    common, union = values["common_edges"], old["edges"] + current["edges"] - values["common_edges"]
    wanted = {"jaccard": common / union,
              "fraction_historical_retained": common / old["edges"],
              "fraction_pchip_shared": common / current["edges"]}
    for name, value in wanted.items():
        if not math.isclose(float(row[name]), value, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError(f"Inconsistent overlap fraction: {name}")
    return {**values, **wanted}


def collect(work: Path, destination: Path, historical: Path) -> dict:
    """Validate every metadata link before creating any presentation products."""
    pins = {}
    copies = {}
    header_excerpts = {}

    def pin(path: Path) -> dict:
        item = qc.record(path)
        pins[str(path.resolve())] = item
        return item

    def copy(path: Path, relative: str) -> None:
        pin(path)
        copies[relative] = path

    design_path, ledger_path = work / "design.json", work / "run_manifest.json"
    design, ledger = qc.read_json(design_path), qc.read_json(ledger_path)
    pin(design_path)
    pin(ledger_path)
    if (design.get("engine_commit") != run.ENGINE_COMMIT or design.get("m") != 80
            or design.get("npar") != 40 or design.get("dpi_epsilon") != 0
            or design.get("consensus_p") != 1e-5 or design.get("seeds") != list(range(1, 101))
            or design.get("pchip_data_sha256") != run.DATA_SHA256
            or design.get("pchip_primary_sha256") != run.PRIMARY_SHA256):
        raise ValueError("Run design differs from the declared protocol")
    rows = validate_ledger(ledger, qc.sha256(design_path))
    for filename, expected in run.core.EXPECTED_LF_SHA256.items():
        item = verify_record(work / "inputs" / filename, design["inputs"][filename])
        if item["sha256"] != expected:
            raise ValueError(f"Unexpected input blob: {filename}")
        pin(work / "inputs" / filename)
    for relative, expected in design["runner_source_sha256"].items():
        path = child(HERE.parent, relative)
        if pin(path)["sha256"] != expected:
            raise ValueError(f"Frozen runner source changed: {relative}")

    build_root = work / "builds" / run.STAGE_KEY
    build_path = build_root / "build_manifest.json"
    build = qc.read_json(build_path)
    if build.get("commit") != run.ENGINE_COMMIT or build["binary_sha256"] != design["binary_sha256"]:
        raise ValueError("Build and run design disagree")
    run.verify_inventory(build_root, build["inventory"])
    copy(build_path, "provenance/native/build_manifest.json")

    analysis_root = work / "analysis"
    analysis_path = analysis_root / "analysis_manifest.json"
    analysis = qc.read_json(analysis_path)
    verify_entries(analysis_root, analysis["files"])
    pin(analysis_path)
    for item in [*analysis["signature"]["inputs"], *analysis["signature"]["sources"].values()]:
        verify_record(Path(item["path"]), item)
        pin(Path(item["path"]))
    if analysis["signature"]["expected_environment"] != qc.ENVIRONMENT:
        raise ValueError("Unexpected NetBID2 environment")
    arms = {item["driver"]: item for item in analysis["arms"]}
    if len(analysis["arms"]) != 2 or set(arms) != set(EXPECTED_DRIVERS):
        raise ValueError("Two completed QC arms are required")

    package_path = destination / "package_manifest.json"
    package = qc.read_json(package_path)
    verify_entries(destination, package["files"])
    verify_checksums(destination, "SHA256SUMS")
    if package["analysis_manifest_sha256"] != qc.sha256(analysis_path):
        raise ValueError("Frozen QC package does not correspond to this analysis")
    packaged_sources = {"provenance/design.json": design_path,
                        "provenance/run_manifest.json": ledger_path,
                        "provenance/analysis_manifest.json": analysis_path}
    for filename in ("network_metrics.tsv", "historical_edge_overlap.tsv",
                     "tf_paired_target_sizes.tsv", "sig_paired_target_sizes.tsv"):
        packaged_sources[filename] = analysis_root / filename
    for driver in EXPECTED_DRIVERS:
        packaged_sources[f"{driver}_netbid2_qc.html"] = (
            analysis_root / "netbid2" / driver / f"{driver.upper()}_netQC.html")
        packaged_sources[f"provenance/{driver}/consensus_manifest.json"] = (
            work / "arms" / driver / "consensus_manifest.json")
    for relative, source in packaged_sources.items():
        if qc.sha256(qc.require_file(destination / relative)) != qc.sha256(qc.require_file(source)):
            raise ValueError(f"Packaged QC product differs from its analyzed source: {relative}")
    pin(package_path)
    pin(destination / "SHA256SUMS")

    metrics_path = analysis_root / "network_metrics.tsv"
    metrics = read_metrics(metrics_path)
    pin(metrics_path)
    overlap_path = analysis_root / "historical_edge_overlap.tsv"
    overlaps_raw = qc.read_tsv(overlap_path)
    if len(overlaps_raw) != 2 or {item["network"] for item in overlaps_raw} != {"TF", "SIG"}:
        raise ValueError("Two historical overlap comparisons are required")
    overlaps_by_driver = {item["network"].lower(): item for item in overlaps_raw}
    pin(overlap_path)
    old_design_path = historical / "sweep_design.json"
    if pin(old_design_path)["sha256"] != anchor.OLD_DESIGN_SHA256:
        raise ValueError("Historical sweep design hash differs")
    old_design = qc.read_json(old_design_path)
    old_points = {item["key"]: item for item in old_design["all_points"]}
    old_metrics, pairs, overlaps = {}, {}, {}
    for driver, count in EXPECTED_DRIVERS.items():
        if metrics[driver]["candidate_drivers"] != count:
            raise ValueError(f"Wrong candidate source count: {driver}")
        arm = work / "arms" / driver
        for seed in range(1, 101):
            metadata = arm / "seed_metadata" / f"TF_run_{seed:03d}.json"
            row = rows[driver, seed]
            if pin(metadata)["sha256"] != row["metadata_sha256"]:
                raise ValueError(f"Seed metadata hash disagrees with ledger: {metadata}")
            item = qc.read_json(metadata)
            final = arm / "adj" / f"TF_run_{seed:03d}.adj"
            command = run.seed_command(build, work, driver, seed, final.with_suffix(".adj.partial"))
            fingerprint = run.core.json_fingerprint({"design_sha256": qc.sha256(design_path),
                "executed_command": command, "final_output": str(final)})
            if (item.get("driver") != driver or item.get("seed") != seed
                    or item["command"] != command or item["fingerprint"] != fingerprint
                    or item["adjacency"]["full_sha256"] != row["sha256"]
                    or item["adjacency"]["edges"] != row["edges"]):
                raise ValueError(f"Seed metadata is inconsistent: {metadata}")
            copy(metadata, f"provenance/native/{driver}/seed_metadata/{metadata.name}")
            if seed == 1:
                source_record = pin(final)
                if (source_record["sha256"] != item["adjacency"]["full_sha256"]
                        or source_record["bytes"] != item["adjacency"]["bytes"]):
                    raise ValueError("Seed-001 header source differs from its validated metadata")
                header_lines = []
                with final.open(encoding="utf-8") as handle:
                    for line in handle:
                        if not line.startswith(">"):
                            break
                        header_lines.append(line.rstrip("\r\n"))
                header_text = "\n".join(header_lines)
                if any(value not in header_text for value in run.required_headers(driver)):
                    raise ValueError("Seed-001 PCHIP method/provenance header differs")
                relative = f"provenance/native/{driver}/TF_run_001.adj_header_only.txt"
                header_excerpts[relative] = ("HEADER-ONLY EXCERPT — NOT AN ADJACENCY NETWORK\n"
                    f"Original adjacency SHA256: {source_record['sha256']}\n\n" + header_text + "\n")
                run.verify_inventory(arm, item["log_inventory"])
                for suffix in ("stdout.log", "stderr.log", "time.txt"):
                    copy(arm / "logs" / f"TF_run_001.{suffix}",
                         f"provenance/native/{driver}/TF_run_001.{suffix}")
        manifest_path = arm / "consensus_manifest.json"
        manifest = qc.read_json(manifest_path)
        if manifest["driver"] != driver or manifest["consensus_p"] != 1e-5:
            raise ValueError("Consensus configuration differs")
        run.verify_inventory(arm / "consensus", manifest["inventory"])
        run.verify_inventory(arm, manifest["log_inventory"])
        script = Path(build["source"]) / "SJARACNe/bin/create_consensus_network.py"
        expected = run.core.json_fingerprint({"command": manifest["command"],
            "script_sha256": qc.sha256(script), "design_sha256": qc.sha256(design_path),
            "adjacency_sha256": [rows[driver, seed]["sha256"] for seed in range(1, 101)]})
        if manifest["fingerprint"] != expected or manifest["ncol"]["edges"] != metrics[driver]["edges"]:
            raise ValueError("Consensus is not bound to the completed seed ledger and reported network")
        pin(manifest_path)
        for filename in ("parameter_info_.txt", "bootstrap_info_.txt"):
            copy(arm / "consensus" / filename, f"provenance/native/{driver}/{filename}")
        if ">  Bootstrap No: 100" not in (arm / "consensus/parameter_info_.txt").read_text():
            raise ValueError("Consensus did not record exactly 100 subnetworks")
        for suffix in ("stdout.log", "stderr.log", "time.txt"):
            copy(arm / "logs" / f"consensus.{suffix}", f"provenance/native/{driver}/consensus.{suffix}")
        summary = qc.read_summary(analysis_root / "netbid2" / driver / "network_summary.tsv")
        if metrics[driver] != summary or arms[driver]["metrics"] != summary:
            raise ValueError("Current metric sources disagree")
        point = qc.OLD_POINTS[driver]
        old_manifest_path = (HERE.parent / "brca100_pr67_threshold_sweep/results_extended_2026-08-19"
                             / "provenance/arms" / point / driver / "netbid2_qc_manifest.json")
        old_manifest = qc.read_json(old_manifest_path)
        pin(old_manifest_path)
        if old_manifest["environment"] != qc.ENVIRONMENT or old_manifest["point"] != point:
            raise ValueError("Historical QC context differs")
        summary_entry = next(item for item in old_manifest["output_inventory"]
                             if item["path"] == "network_summary.tsv")
        old_summary = historical / "results" / point / driver / "netbid2_qc/network_summary.tsv"
        verify_record(old_summary, summary_entry)
        pin(old_summary)
        old_metrics[driver] = qc.read_summary(old_summary)
        for name, value in arms[driver]["historical_topology"].items():
            if not math.isclose(old_metrics[driver][name], value, rel_tol=1e-12, abs_tol=1e-12):
                raise ValueError("Historical NetBID2 and fresh Python topology audit disagree")
        if arms[driver]["historical_network"]["sha256"] != old_manifest["consensus_sha256"]:
            raise ValueError("Historical network identity differs")
        pair_path = analysis_root / f"{driver}_paired_target_sizes.tsv"
        pin(pair_path)
        driver_list = qc.read_drivers(work / "inputs" / qc.DRIVERS[driver])
        pairs[driver] = paired_counts(pair_path, driver_list, old_metrics[driver], metrics[driver])
        overlaps[driver] = validate_overlap(overlaps_by_driver[driver], old_metrics[driver], metrics[driver])
        if old_points[point]["mi_cutoff"] != old_manifest["mi_cutoff"]:
            raise ValueError("Historical numerical cutoff provenance differs")

    anchor_root = work / "validation/explicit_threshold_tf_seed001"
    anchor_path = anchor_root / "anchor_result.json"
    anchor_result = qc.read_json(anchor_path)
    if (anchor_result.get("status") not in ("match", "differ")
            or anchor_result.get("current_commit") != run.ENGINE_COMMIT
            or anchor_result.get("historical_commit") != anchor.OLD_COMMIT
            or anchor_result.get("seed") != 1 or anchor_result.get("driver") != "tf"):
        raise ValueError("Explicit-threshold implementation anchor is missing or inconsistent")
    expected_status = ("match" if anchor_result["old_adjacency"]["data_sha256"]
                       == anchor_result["new_adjacency"]["data_sha256"] else "differ")
    if (anchor_result["status"] != expected_status
            or anchor_result["current_binary_sha256"] != build["binary_sha256"]
            or anchor_result["mi_cutoff"] != old_points["p1e-03"]["mi_cutoff"]):
        raise ValueError("Anchor outcome/build/cutoff binding differs")
    for item in anchor_result["pins"].values():
        if pin(Path(item["path"]))["sha256"] != item["sha256"]:
            raise ValueError("Anchor input/source hash differs")
    run.verify_inventory(anchor_root, anchor_result["inventory"])
    copy(anchor_path, "provenance/native/implementation_anchor/anchor_result.json")
    for path in sorted((anchor_root / "logs").iterdir()):
        copy(path, "provenance/native/implementation_anchor/logs/" + path.name)
    for filename in ("PROTOCOL.md", "run.py", "validate_anchor.py", "report_results.py"):
        copy(HERE / filename, "provenance/native/source/" + filename)
    return {"design": design, "build": build, "metrics": metrics, "historical_metrics": old_metrics,
            "old_points": old_points, "pairs": pairs, "overlaps": overlaps,
            "anchor": anchor_result, "pins": sorted(pins.values(), key=lambda item: item["path"]),
            "copies": copies, "header_excerpts": header_excerpts}


def comparison_rows(context: dict) -> list[dict]:
    rows = []
    for driver in EXPECTED_DRIVERS:
        for mode, metrics, cutoff in (
            ("historical", context["historical_metrics"][driver],
             context["old_points"][qc.OLD_POINTS[driver]]["mi_cutoff"]),
            ("pchip", context["metrics"][driver], context["design"]["arms"][driver]["mi_cutoff"])):
            rows.append({"network": driver.upper(), "function": mode,
                         "per_resample_p": float(context["design"]["arms"][driver]["p_token"]),
                         "mi_cutoff": cutoff, **metrics})
    return rows


def markdown(context: dict, plot: bool) -> str:
    lines = ["# BRCA100: current PCHIP end-to-end workflow and NetBID2 QC", "",
        "## Outcome", "",
        "Fresh inference completed **200/200 seed networks** (100 TF and 100 SIG), both post-DPI consensus networks, and **2/2 pinned NetBID2 QC reports**. The table reports the measured current networks beside the matched historical configurations; no probabilities were selected from these outcomes.", "",
        "| Network / cutoff function | Per-resample p | MI cutoff | Consensus edges | Median targets | Active sources | Incident nodes | LCC | NetBID2 adjusted R-squared |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for row in comparison_rows(context):
        lines.append(f"| {row['network']} / {row['function']} | {row['per_resample_p']:g} | {row['mi_cutoff']:.17g} | {row['edges']:,.0f} | {row['target_size_zero_median']:g} | {row['active_driver_fraction']:.3%} | {row['incident_nodes'] / EXPRESSION_NODES:.3%} | {row['largest_weak_component_fraction']:.3%} | {row['scale_free_adjusted_r2']:.6f} |")
    lines += ["", "Display fractions/fit values are rounded; [comparison_metrics.tsv](comparison_metrics.tsv) retains the numerical metrics read from the source summaries. All outcomes are **after seed-level MI filtering, DPI and consensus**.", "",
        "## Matched design and metric definitions", "",
        "- Frozen engine: `" + run.ENGINE_COMMIT + "`; [declared process/protocol](../PROTOCOL.md).",
        "- BRCA100: 28,278 expression nodes, 100 samples; full lists of 2,608 TF and 10,680 SIG candidates.",
        "- Seeds 1–100; 80/100 samples without replacement, `m=80`, `Npar=40`, DPI epsilon 0. Each class uses its full source list as DPI annotation (`-l`).",
        "- Explicit TF `p_b=0.001` and SIG `p_b=0.0005`; these are provisional starting settings, not software defaults or selected optima.",
        "- Stock normal-approximation consensus at `p_c=1e-5`; **minimum recurrence K=6 is not used**. Twelve native workers, one numerical thread per worker; consensus serialized.",
        "- Median targets include zero-target candidates. Active sources are candidates with at least one consensus edge. Incident-node coverage uses all 28,278 expression nodes. LCC is the largest weak component divided by incident nodes. NetBID2 adjusted R-squared is scale-free-fit QC, not a measure of edge correctness.", "",
        "## Directed-edge and source-target-size comparison", "",
        "| Network | Shared directed edges | Historical-only | PCHIP-only | Jaccard | Historical edges retained |",
        "| --- | ---: | ---: | ---: | ---: | ---: |"]
    for driver in EXPECTED_DRIVERS:
        item = context["overlaps"][driver]
        lines.append(f"| {driver.upper()} | {item['common_edges']:,} | {item['historical_only_edges']:,} | {item['pchip_only_edges']:,} | {item['jaccard']:.6f} | {item['fraction_historical_retained']:.3%} |")
    lines += ["", "[Full directed-overlap values](historical_edge_overlap.tsv). Reverse directions are distinct; neither added nor removed pairs are labeled biologically true or false.", ""]
    for driver in EXPECTED_DRIVERS:
        item = context["pairs"][driver]
        lines.append(f"- {driver.upper()}: {item['increased']:,} candidate sources have more targets, {item['unchanged']:,} the same number, and {item['decreased']:,} fewer; [paired counts]({driver}_paired_target_sizes.tsv).")
    if plot:
        lines += ["", "![Zero-filled per-source target-count distributions](target_size_ecdf.png)", "",
                  "Each curve uses the complete candidate-source list, including zero-target sources. The horizontal axis is symmetric-log scaled with a linear region around zero; curves describe target-set sizes, not biological accuracy."]
    anchor_result = context["anchor"]
    anchor_statement = ("The serialized post-DPI data sections matched exactly at that identical explicit cutoff."
                        if anchor_result["status"] == "match" else
                        "The serialized post-DPI data sections differed; cutoff-only causation is not established.")
    lines += ["", "## Provenance and validation", "",
        "The input blobs, frozen model hashes, runner source, 200 design-bound seed metadata records, both consensus inventories and both QC inventories were checked before publication. The consensus fingerprints bind each network to its ordered 100-seed ledger. NetBID2 summaries were independently cross-checked against the analyzer's topology/target-count audit; historical summary files matched their archived hashes.", "",
        "The AP-MI kernel and stock consensus source are unchanged between the historical and current engine versions. A separate implementation/compiler/runtime anchor reran **TF seed 1 only**, at the exact historical MI cutoff with explicit `-t`, bypassing probability conversion and PCHIP. " + anchor_statement + " This is one example, not proof of equivalence for every seed, threshold, dataset or environment. It is not a PCHIP run or null-rate calibration. [Anchor provenance](provenance/native/implementation_anchor/anchor_result.json).", "",
        "- Current compiler: `" + context["build"]["compiler"] + "`.",
        "- PCHIP data SHA256: `" + run.DATA_SHA256 + "`.",
        "- Calibration primary SHA256: `" + run.PRIMARY_SHA256 + "`.",
        "- [Build manifest](provenance/native/build_manifest.json), [native metadata/commands/logs](provenance/native/), [QC provenance](provenance/analysis_manifest.json), and [presentation manifest](presentation_manifest.json).",
        "- Seed-001 [TF header-only excerpt](provenance/native/tf/TF_run_001.adj_header_only.txt) and [SIG header-only excerpt](provenance/native/sig/TF_run_001.adj_header_only.txt), with corresponding logs, show actual PCHIP method, sampled m, model hashes, full-precision cutoff and warnings. These excerpts contain no adjacency data rows.",
        "- [Historical 13-point sweep](../../brca100_pr67_threshold_sweep/COMBINED_RESULTS.md) motivates the initial density-oriented settings; it is not current PCHIP calibration.", "",
        "## NetBID2 reports", "",
        "- [TF network-QC HTML](tf_netbid2_qc.html)",
        "- [SIG network-QC HTML](sig_netbid2_qc.html)", "",
        "Download and open the HTML locally; GitHub does not render it as a normal web page. Figures are embedded. Standard R Markdown may request MathJax online; offline viewing can omit mathematical typesetting. R 4.4.3, NetBID2 2.2.0 (`5defa454d600b94f5dd6d1f9f4428f99759a6821`) and igraph 2.3.3 match the historical QC environment.", "",
        "## Conditional conclusion", "",
        "If the measured coverage and target-set sizes meet a stated application requirement, these two explicit probabilities remain reasonable **provisional BRCA100 starting settings**. This completed workflow/QC check does not identify optimal probabilities, justify universal defaults, or establish improved biological accuracy or downstream activity robustness.", "",
        "This is one dataset without independent edge-level truth. Density, connectivity, overlap and scale-free fit are descriptive QC, not biological reliability or edge FDR. TF/SIG comparisons also reflect different hub-list/DPI contexts. `m=80` lies between the broad calibration study's tested 50-step sizes; a callable cutoff is not a directly validated null-rate guarantee at this off-grid query. No new null fitting, calibration draws or consensus-rule tuning was performed.", "",
        "Original QC files, `package_manifest.json` and `SHA256SUMS` remain unchanged. Verify the augmented package separately with `sha256sum -c PRESENTATION_SHA256SUMS`; it covers original QC and added presentation/provenance files, including the new presentation manifest. Large native adjacency/expression files and raw calibration draws remain local.", ""]
    return "\n".join(lines)


def plot_ecdf(context: dict, output: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.7), sharey=True)
    for driver, axis in zip(EXPECTED_DRIVERS, axes):
        for key, label, color in (("historical", "Historical", "#666666"), ("pchip", "PCHIP", "#0072B2")):
            values = sorted(context["pairs"][driver][key])
            axis.step([0, *values], [0, *((index + 1) / len(values) for index in range(len(values)))],
                      where="post", label=label, color=color, linewidth=1.7)
        axis.set_xscale("symlog", linthresh=1)
        axis.set_xlim(left=0)
        axis.set_ylim(0, 1.01)
        axis.set_title(f"{driver.upper()} ({EXPECTED_DRIVERS[driver]:,} candidates)")
        axis.set_xlabel("Consensus targets per candidate source")
        axis.grid(alpha=.18)
        axis.legend(frameon=False, loc="lower right")
    axes[0].set_ylabel("Fraction of candidate sources")
    fig.suptitle("Post-DPI consensus target-count distributions")
    fig.tight_layout()
    fig.savefig(output, dpi=180, metadata={"Software": "SJARACNe BRCA100 benchmark"})
    plt.close(fig)


def publish(work: Path, destination: Path, historical: Path, make_plot: bool = False) -> dict:
    work, destination, historical = work.resolve(), destination.resolve(), historical.resolve()
    if destination.is_relative_to(work) or destination.is_relative_to(historical):
        raise ValueError("Presentation package must be outside current and historical native roots")
    context = collect(work, destination, historical)
    signature = {"inputs": context["pins"], "plot": make_plot, "schema": SCHEMA}
    manifest_path = destination / "presentation_manifest.json"
    if manifest_path.exists():
        existing = qc.read_json(manifest_path)
        if existing.get("signature") != signature:
            raise ValueError("Existing presentation has different input/source provenance")
        verify_entries(destination, existing["files"])
        verify_checksums(destination, "PRESENTATION_SHA256SUMS")
        current = [item for item in qc.inventory(destination)
                   if item["path"] not in ("presentation_manifest.json", "PRESENTATION_SHA256SUMS")]
        if current != existing["files"]:
            raise ValueError("Unexpected file changes in completed presentation")
        return existing
    owned = ["RESULTS.md", "comparison_metrics.tsv", "PRESENTATION_SHA256SUMS", "provenance/native"]
    if make_plot:
        import matplotlib  # Fail before creating partial products if unavailable.
        owned.append("target_size_ecdf.png")
    if any((destination / relative).exists() for relative in owned):
        raise ValueError("Incomplete/existing presentation products require explicit inspection")
    for relative, source in context["copies"].items():
        output = child(destination, relative)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, output)
    for relative, text in context["header_excerpts"].items():
        output = child(destination, relative)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    qc.write_tsv(destination / "comparison_metrics.tsv", comparison_rows(context), METRIC_FIELDS)
    if make_plot:
        plot_ecdf(context, destination / "target_size_ecdf.png")
    with (destination / "RESULTS.md").open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(markdown(context, make_plot))
    for item in context["pins"]:
        verify_record(Path(item["path"]), item)
    manifest = {"schema": SCHEMA, "signature": signature, "generated_at_utc": run.now(),
                "validation": {"seed_metadata_records": 200, "consensus_networks": 2,
                               "netbid2_qc_reports": 2, "implementation_anchor": context["anchor"]["status"]},
                "files": qc.inventory(destination)}
    qc.write_json(manifest_path, manifest)
    checksum_files = qc.inventory(destination)
    with (destination / "PRESENTATION_SHA256SUMS").open("x", encoding="utf-8", newline="\n") as handle:
        for item in checksum_files:
            handle.write(f"{item['sha256']}  {item['path']}\n")
    verify_entries(destination, manifest["files"])
    verify_checksums(destination, "PRESENTATION_SHA256SUMS")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--package-root", type=Path, required=True)
    parser.add_argument("--historical-root", type=Path, default=run.OLD_ROOT)
    parser.add_argument("--plot", action="store_true", help="Add a compact static target-size ECDF (requires matplotlib)")
    args = parser.parse_args()
    result = publish(args.work_root, args.package_root, args.historical_root, args.plot)
    print(f"Validated presentation: {args.package_root / 'RESULTS.md'} ({len(result['files'])} files)")


if __name__ == "__main__":
    main()
