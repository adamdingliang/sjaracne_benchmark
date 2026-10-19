#!/usr/bin/env python3
"""Bind completed QC/support proofs and export compact, non-narrative results.

Never read or copy raw adjacency payloads, infer networks, rerun QC, or modify
the QC package. The coordinator owns narrative and final presentation checksums.
"""
from __future__ import annotations

import argparse
import importlib.util
import math
from pathlib import Path
import shutil
import statistics
import sys


HERE = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location("recurrence_report_qc", HERE / "analyze_qc.py")
QC = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(QC)
BASE = QC.BASE
SCHEMA = "brca100-pchip-recurrence-report-v1"
LAUNCH_BENCHMARK_COMMIT = "46c992810d09593e41d92553611ca031de047cc3"
SOURCES = ("PROTOCOL.md", "run.py", "test_run.py", "validate_support.py", "test_validate_support.py",
           "analyze_qc.py", "test_analyze_qc.py", "report_results.py", "test_report_results.py")
OWNED = ("support_audits", "provenance", "overlap_summary.tsv", "coverage_summary.tsv",
         "tf_paired_target_sizes.tsv", "sig_paired_target_sizes.tsv", "report_manifest.json")
NETWORK_FILES = ("consensus_network_3col_.txt", "consensus_network_ncol_.txt", "bootstrap_info_.txt")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value):
    return type(value) is int and value >= 0


def histogram(value):
    require(isinstance(value, dict) and set(value) == {str(k) for k in range(1, 101)},
            "Support histogram must contain exactly bins 1..100")
    require(all(integer(count) for count in value.values()), "Support counts must be nonnegative integers")
    return {k: value[str(k)] for k in range(1, 101)}


def check_audit(driver, audit, verification, manifests, work):
    require(audit.get("schema") == "brca100-pchip-independent-support-audit-v1"
            and audit.get("passed") is True and audit.get("issues") == {}, "Support audit did not pass")
    require((audit.get("B"), audit.get("K"), audit.get("K_over_B"), audit.get("legacy_p"))
            == (100, 6, .06, 1e-5), "Support audit selection contract changed")
    require(audit.get("auditor_sha256") == BASE.sha256(HERE / "validate_support.py"),
            "Auditor source differs from the executed audit")
    require(audit.get("source_order_verified_for_all_files") is True, "Source order was not verified")
    wanted_drivers = verification["inputs"][QC.DRIVERS[driver]]["sha256"]
    require(audit["drivers"]["sha256"] == wanted_drivers
            and audit["drivers"]["count"] == QC.DRIVER_COUNTS[driver], "Audit driver universe mismatch")
    rows = [row for row in verification["rows"] if row["driver"] == driver]
    expected = {Path(row["path"]).name: row for row in rows}
    require(len(rows) == len(expected) == 100 and {row["seed"] for row in rows} == set(range(1, 101)),
            "Verification must contain exactly 100 distinct seeds per class")
    require(all(Path(row["path"]).name == f"TF_run_{row['seed']:03d}.adj" for row in rows),
            "Raw filename/seed identities disagree")
    runs = audit.get("runs", [])
    require(len(runs) == 100 and {row["file"] for row in runs} == set(expected), "Audit raw seed set mismatch")
    for row in runs:
        wanted = expected[row["file"]]
        require(Path(row["path"]).resolve() == Path(wanted["path"]).resolve(), "Audit raw input path mismatch")
        require(all(integer(row.get(key)) for key in ("bytes", "edge_count", "source_groups")),
                "Audit raw sizes/counts must be nonnegative integers")
        for audit_key, verified_key in (("sha256", "full_sha256"), ("bytes", "bytes"),
                                        ("edge_count", "edges"), ("source_groups", "source_rows")):
            require(row.get(audit_key) == wanted[verified_key], "Audit raw SHA/size/count mismatch")
        require(row.get("source_order_verified") is True, "An audit stream did not verify source order")
    hist = histogram(audit["histogram"])
    require(sum(hist.values()) == audit["union_edges"] > 0, "Histogram union mismatch")
    incidence = sum(k * count for k, count in hist.items())
    require(incidence == audit["pair_incidence"] == sum(row["edge_count"] for row in runs),
            "Histogram/raw incidence mismatch")
    selected = {mode: histogram(audit["selected_histograms"][mode]) for mode in QC.MODES}
    q = [row["edge_count"] / audit["union_edges"] for row in runs]
    require(all(0 <= value <= 1 for value in q), "Invalid run occupancy")
    mu, sigma = sum(q), math.sqrt(sum(value * (1 - value) for value in q))
    require(math.isclose(audit["legacy_mu"], mu, rel_tol=1e-12, abs_tol=1e-12)
            and math.isclose(audit["legacy_sigma"], sigma, rel_tol=1e-12, abs_tol=1e-12),
            "Legacy occupancy parameters mismatch")
    eligible = []
    gate_rows = audit.get("legacy_gate_by_support", [])
    require(len(gate_rows) == 100 and [row["support"] for row in gate_rows] == list(range(1, 101)),
            "Incomplete legacy support gate")
    for support, gate in enumerate(gate_rows, 1):
        z = (support - mu) / sigma if sigma else 100.0
        tail = .5 * math.erfc(z / math.sqrt(2))
        accepted = tail < 1e-5
        if accepted:
            eligible.append(support)
        require(type(gate["selected"]) is bool and gate["selected"] == accepted
                and math.isclose(gate["normal_tail"], tail, rel_tol=1e-12, abs_tol=1e-300)
                and gate["union_edges"] == hist[support]
                and gate["actual_legacy_edges"] == selected["legacy_pc"][support], "Legacy gate bin mismatch")
        require(selected["k6"][support] == (hist[support] if support >= 6 else 0)
                and selected["legacy_pc"][support] == (hist[support] if accepted else 0),
                "Selected support histogram does not prove membership")
    observed = [k for k in hist if selected["legacy_pc"][k]]
    require(audit["legacy_minimum_eligible_support"] == (min(eligible) if eligible else None)
            and audit["legacy_observed_minimum_support"] == (min(observed) if observed else None),
            "Reported legacy support boundary mismatch")
    for mode in QC.MODES:
        arm = work / "arms" / driver / mode
        manifest = manifests[(driver, mode)]
        network = audit["networks"][mode]
        require(Path(network["path"]).resolve() == (arm / NETWORK_FILES[0]).resolve(),
                "Audit must bind the three-column consensus projection")
        require(network["sha256"] == manifest["inventory"][NETWORK_FILES[0]]["sha256"]
                and network["edges"] == sum(selected[mode].values())
                and network.get("strict_lexical_order_verified") is True, "Audited consensus identity/count mismatch")
        enhanced = audit["enhanced_projection"][mode]
        require(Path(enhanced["path"]).resolve() == (arm / NETWORK_FILES[1]).resolve()
                and enhanced["sha256"] == manifest["inventory"][NETWORK_FILES[1]]["sha256"]
                and enhanced["rows_compared"] == network["edges"], "Enhanced projection identity mismatch")
        require(audit["metadata"][mode]["bootstrap_info_sha256"]
                == manifest["inventory"]["bootstrap_info_.txt"]["sha256"]
                and audit["metadata"][mode]["parameter_info_sha256"]
                == manifest["inventory"]["parameter_info_.txt"]["sha256"], "Audit metadata identity mismatch")
    overlap = audit["overlap"]
    require(set(overlap) == {"shared", "k6_only", "legacy_pc_only"}
            and all(integer(value) for value in overlap.values())
            and overlap["shared"] + overlap["k6_only"] == audit["networks"]["k6"]["edges"]
            and overlap["shared"] + overlap["legacy_pc_only"] == audit["networks"]["legacy_pc"]["edges"],
            "Edge-overlap conservation mismatch")
    legacy = manifests[(driver, "legacy_pc")]
    baseline = verification["baselines"][driver]
    require(legacy.get("legacy_comparison", {}).get("passed") is True
            and set(legacy["legacy_comparison"]["exact_files"]) == set(NETWORK_FILES)
            and legacy["legacy_comparison"]["parameter_info"] == "exact_except_output_path",
            "Legacy production comparison did not pass exact compatibility")
    for name in NETWORK_FILES:
        require(legacy["inventory"][name] == baseline["inventory"][name], "Legacy baseline bytes changed")
    require(legacy["inventory"][NETWORK_FILES[1]] == {
        key: QC.LEGACY[driver][key] for key in ("bytes", "sha256")}, "Published legacy network bytes changed")
    historical = audit.get("historical_legacy") or {}
    require(historical.get("matches_new_legacy_sha256") is True
            and historical.get("sha256") == historical.get("expected_sha256")
            == baseline["inventory"][NETWORK_FILES[0]]["sha256"], "Legacy audit baseline identity mismatch")


def report(work: Path, results: Path):
    work, results = work.resolve(), results.resolve()
    require(not results.is_relative_to(work), "Compact results must be outside the raw work root")
    require(not any((results / name).exists() for name in OWNED), "Refusing existing or partial owned report outputs")
    qc = results / "qc"
    QC.verify_package(qc)
    design, verification, run = (BASE.read_json(work / name)
                                 for name in ("design.json", "verification.json", "run_manifest.json"))
    require(verification.get("passed") is True and verification.get("adjacency_files_verified") == 200,
            "Raw verification is incomplete")
    require(len(verification["rows"]) == 200 and all(row["driver"] in QC.DRIVERS for row in verification["rows"]),
            "Verification contains extra or missing raw rows")
    require((design.get("B"), design.get("K"), design.get("K_over_B"), design.get("legacy_p_value_consensus"))
            == (100, 6, .06, 1e-5), "Design selection contract changed")
    require(run.get("complete") is True and run.get("passed") is True and run.get("status") == "complete"
            and run.get("design_sha256") == BASE.sha256(work / "design.json")
            and run.get("verification_sha256") == BASE.sha256(work / "verification.json"),
            "Run is incomplete or detached from its verified design")
    require(run.get("engine_commit") == design["engine_commit"], "Run/engine commit identity mismatch")
    require(design.get("runner_sha256") == BASE.sha256(HERE / "run.py"), "Runner source changed")
    inputs, copies = [], []

    def capture(source, destination=None, expected=None):
        item = BASE.record(source)
        if expected is not None:
            require(all(item[key] == expected[key] for key in ("bytes", "sha256")), "Input inventory mismatch")
        inputs.append(item)
        if destination is not None:
            copies.append((Path(source), results / destination))
        return item

    for name in ("design.json", "verification.json", "run_manifest.json"):
        capture(work / name, Path("provenance") / name)
        require(BASE.sha256(qc / "provenance" / name) == BASE.sha256(work / name), "QC/work run metadata mismatch")
    qc_manifest = BASE.read_json(qc / "provenance/analysis_manifest.json")
    qc_arms = {(arm["driver"], arm["mode"]): arm for arm in qc_manifest["arms"]}
    expected_arms = {(driver, mode) for driver in QC.DRIVERS for mode in QC.MODES}
    require(len(qc_manifest["arms"]) == 4 and set(qc_arms) == expected_arms, "QC must contain exactly four arms")
    run_arms = {(row["driver"], row["mode"]): row for row in run["rows"]}
    require(len(run["rows"]) == 4 and set(run_arms) == expected_arms, "Run must contain exactly four arms")
    manifests = {}
    for driver, mode in sorted(expected_arms):
        arm = work / "arms" / driver / mode
        path = arm / "consensus_manifest.json"
        item = capture(path, Path("provenance/arms") / driver / mode / path.name)
        require(item["sha256"] == run_arms[(driver, mode)]["sha256"], "Consensus/run manifest link mismatch")
        manifest = manifests[(driver, mode)] = BASE.read_json(path)
        require(manifest.get("engine_commit") == design["engine_commit"]
                and manifest.get("inference_engine_commit") == design["inference_engine_commit"],
                "Consensus engine/inference identities mismatch")
        parameters = (manifest.get("driver"), manifest.get("mode"), manifest.get("B"), manifest.get("K"),
                      manifest.get("K_over_B"), manifest.get("p_value_consensus"))
        require(parameters == (driver, mode, 100, *( (6, .06, None) if mode == "k6" else (None, None, 1e-5))),
                "Consensus arm selection mismatch")
        require(BASE.sha256(qc / "provenance/qc" / driver / mode / path.name) == item["sha256"],
                "QC consensus manifest identity mismatch")
        require(set(manifest["inventory"]) == {*NETWORK_FILES, "parameter_info_.txt"},
                "Unexpected consensus inventory domain")
        for name, expected in manifest["inventory"].items():
            compact = Path("provenance/arms") / driver / mode / name if name in (
                "bootstrap_info_.txt", "parameter_info_.txt") else None
            capture(arm / name, compact, expected)  # never copy network payloads
        require({key: qc_arms[(driver, mode)]["network"][key] for key in ("bytes", "sha256")}
                == manifest["inventory"][NETWORK_FILES[1]], "QC network identity mismatch")
        for name, expected in manifest["log_inventory"].items():
            require(Path(name).name == name, "Unsafe consensus log name")
            capture(work / "arms" / driver / "logs" / name,
                    Path("provenance/logs") / driver / name, expected)
    overlaps, coverage, pairs = [], [], {}
    for driver, filename in QC.DRIVERS.items():
        audit_path = work / "support_audits" / f"{driver}.json"
        capture(audit_path, Path("support_audits") / audit_path.name)
        audit = BASE.read_json(audit_path)
        check_audit(driver, audit, verification, manifests, work)
        for suffix in ("stdout.log", "stderr.log"):
            path = audit_path.with_name(f"{driver}.{suffix}")
            if path.is_file():
                capture(path, Path("support_audits") / path.name)
        k6, legacy = (audit["networks"][mode]["edges"] for mode in QC.MODES)
        require(legacy == QC.LEGACY[driver]["edges"], "Published legacy edge count changed")
        overlap = audit["overlap"]
        overlaps.append({"driver": driver, "B": 100, "K": 6, "K_over_B": .06,
                         "k6_edges": k6, "legacy_pc_edges": legacy, "shared_edges": overlap["shared"],
                         "k6_only_edges": overlap["k6_only"], "legacy_pc_only_edges": overlap["legacy_pc_only"],
                         "jaccard": overlap["shared"] / (k6 + legacy - overlap["shared"]),
                         "edge_increase": k6 - legacy, "edge_increase_fraction": (k6 - legacy) / legacy,
                         "legacy_minimum_eligible_support": audit["legacy_minimum_eligible_support"],
                         "legacy_observed_minimum_support": audit["legacy_observed_minimum_support"]})
        drivers = BASE.read_drivers(work / "inputs" / filename)
        capture(work / "inputs" / filename)
        require(len(drivers) == QC.DRIVER_COUNTS[driver]
                and BASE.sha256(work / "inputs" / filename) == verification["inputs"][filename]["sha256"],
                "Full candidate-source identity mismatch")
        counts = {}
        for mode in QC.MODES:
            path = qc / "provenance/qc" / driver / mode / "driver_target_sizes.tsv"
            capture(path)
            rows = BASE.read_tsv(path)
            counts[mode] = {row["driver"]: int(row["target_count"]) for row in rows}
            require(len(rows) == len(counts[mode]) == len(drivers)
                    and set(counts[mode]) == set(drivers) and all(value >= 0 for value in counts[mode].values())
                    and sum(counts[mode].values()) == audit["networks"][mode]["edges"],
                    "QC target sizes omit candidates or disagree with audited edges")
            values = qc_arms[(driver, mode)]["metrics"]
            require(values["edges"] == audit["networks"][mode]["edges"]
                    and values["candidate_drivers"] == len(drivers)
                    and values["target_size_zero_median"] == statistics.median(counts[mode].values()),
                    "QC summary and zero-filled target counts disagree")
            for threshold in (10, 20, 50):
                count = sum(value >= threshold for value in counts[mode].values())
                require(values[f"drivers_ge_{threshold}_targets"] == count
                        and values[f"driver_fraction_ge_{threshold}_targets"] == count / len(drivers),
                        "QC coverage fraction denominator changed")
            coverage.append({"driver": driver, "mode": mode, **values})
        pairs[driver] = [{"driver": name, "legacy_pc_targets": counts["legacy_pc"][name],
                          "k6_targets": counts["k6"][name],
                          "delta_targets": counts["k6"][name] - counts["legacy_pc"][name]} for name in drivers]
    for filename in SOURCES:
        capture(HERE / filename, Path("provenance/sources") / filename)
    validation = work / "validation"
    validation_files = ("tests.json", "tests.stdout.log", "tests.stderr.log")
    if any((validation / name).exists() for name in validation_files):
        require(BASE.read_json(validation / "tests.json").get("passed") is True,
                "Optional contract-test validation did not pass")
        for name in validation_files:
            capture(validation / name, Path("provenance/validation") / name)
    # No writes until every identity and support proof above succeeds.
    for source, destination in copies:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
    BASE.write_tsv(results / "overlap_summary.tsv", overlaps, list(overlaps[0]))
    BASE.write_tsv(results / "coverage_summary.tsv", coverage,
                   ["driver", "mode", *BASE.SUMMARY_FIELDS, *QC.EXTRA_FIELDS])
    for driver, rows in pairs.items():
        BASE.write_tsv(results / f"{driver}_paired_target_sizes.tsv", rows, list(rows[0]))
    BASE.write_json(results / "provenance/source_context.json", {
        "launch_benchmark_commit": LAUNCH_BENCHMARK_COMMIT,
        "report_controller": {"executable": sys.executable, "version": sys.version},
        "production_engine": design["engine"],
        "note": "Source snapshots retain actual bytes; reporting code was added after the launch commit."})
    for item in inputs:
        require(BASE.sha256(Path(item["path"])) == item["sha256"], "Report input changed during export")
    generated = []
    for name in OWNED:
        path = results / name
        if path.is_dir():
            generated.extend({**item, "path": f"{name}/{item['path']}"} for item in BASE.inventory(path))
        elif path.is_file():
            generated.append({**BASE.record(path), "path": name})
    manifest = {"schema": SCHEMA, "launch_benchmark_commit": LAUNCH_BENCHMARK_COMMIT,
                "inputs": inputs, "qc_package_manifest": BASE.record(qc / "package_manifest.json"),
                "files": generated, "narrative_and_presentation_checksums": "coordinator-owned; not generated here"}
    BASE.write_json(results / "report_manifest.json", manifest)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--results-root", type=Path, required=True)
    args = parser.parse_args()
    result = report(args.work_root, args.results_root)
    print(BASE.json.dumps({"schema": result["schema"], "files": len(result["files"])}, indent=2))


if __name__ == "__main__":
    main()
