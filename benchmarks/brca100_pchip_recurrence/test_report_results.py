"""Small synthetic provenance proofs; no R, inference or raw-stream audit."""
from contextlib import ExitStack
import copy
import csv
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location("recurrence_report", Path(__file__).with_name("report_results.py"))
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.work, self.results = self.root / "work", self.root / "results"
        self.qc = self.results / "qc"
        (self.work / "inputs").mkdir(parents=True)
        (self.work / "support_audits").mkdir()
        (self.qc / "provenance").mkdir(parents=True)
        self.write_json(self.qc / "package_manifest.json", {"synthetic": True})
        self.manifests, self.audits, self.legacy = {}, {}, {}
        self.verification = {"passed": True, "adjacency_files_verified": 200, "rows": [], "inputs": {}, "baselines": {}}
        self.qc_arms, self.run_rows = [], []
        for driver, filename in REPORT.QC.DRIVERS.items():
            (self.work / "inputs" / filename).write_text("a\nb\n")
            self.verification["inputs"][filename] = REPORT.BASE.record(self.work / "inputs" / filename)
            for seed in range(1, 101):
                edge_count = 3 if seed <= 6 else 2 if seed <= 20 else 1 if seed <= 80 else 0
                self.verification["rows"].append({
                    "driver": driver, "seed": seed, "path": str(self.work / "raw" / driver / f"TF_run_{seed:03d}.adj"),
                    "full_sha256": REPORT.BASE.hashlib.sha256(f"{driver}:{seed}".encode()).hexdigest(),
                    "bytes": 100 + seed, "edges": edge_count, "source_rows": int(edge_count > 0)})
            for mode in REPORT.QC.MODES:
                self.make_arm(driver, mode)
            legacy_inventory = self.manifests[(driver, "legacy_pc")]["inventory"]
            self.verification["baselines"][driver] = {"inventory": {name: legacy_inventory[name] for name in REPORT.NETWORK_FILES}}
            self.legacy[driver] = {**legacy_inventory[REPORT.NETWORK_FILES[1]], "edges": 1}
            self.make_audit(driver)
        self.design = {"runner_sha256": REPORT.BASE.sha256(REPORT.HERE / "run.py"),
                       "B": 100, "K": 6, "K_over_B": .06, "legacy_p_value_consensus": 1e-5,
                       "engine_commit": "production", "inference_engine_commit": "inference",
                       "engine": {"python": "/pinned/python3.9"}}
        self.write_json(self.work / "design.json", self.design)
        self.write_json(self.work / "verification.json", self.verification)
        self.write_json(self.work / "run_manifest.json", {
            "complete": True, "passed": True, "status": "complete", "engine_commit": "production", "rows": self.run_rows,
            "design_sha256": REPORT.BASE.sha256(self.work / "design.json"),
            "verification_sha256": REPORT.BASE.sha256(self.work / "verification.json")})
        for name in ("design.json", "verification.json", "run_manifest.json"):
            REPORT.shutil.copyfile(self.work / name, self.qc / "provenance" / name)
        self.write_json(self.qc / "provenance/analysis_manifest.json", {"arms": self.qc_arms})
        self.stack = ExitStack()
        self.verify_qc = self.stack.enter_context(mock.patch.object(REPORT.QC, "verify_package"))
        self.stack.enter_context(mock.patch.object(REPORT.QC, "DRIVER_COUNTS", {"tf": 2, "sig": 2}))
        self.stack.enter_context(mock.patch.object(REPORT.QC, "LEGACY", self.legacy))

    def tearDown(self):
        self.stack.close()
        self.temp.cleanup()

    @staticmethod
    def write_json(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")

    def make_arm(self, driver, mode):
        arm = self.work / "arms" / driver / mode
        arm.mkdir(parents=True)
        pairs = [("a", "x"), ("b", "x")] if mode == "k6" else [("a", "x")]
        for name, header in ((REPORT.NETWORK_FILES[0], ["source", "target", "MI"]),
                             (REPORT.NETWORK_FILES[1], REPORT.BASE.HEADER)):
            with (arm / name).open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
                writer.writerow(header)
                for source, target in pairs:
                    writer.writerow([source, target, "0.2000"] if len(header) == 3 else
                                    [source, target, source, target, "0.2000", .1, .2, .3, .01])
        for name in ("bootstrap_info_.txt", "parameter_info_.txt"):
            (arm / name).write_text("synthetic metadata\n")
        inventory = {path.name: {key: REPORT.BASE.record(path)[key] for key in ("bytes", "sha256")}
                     for path in arm.iterdir()}
        log = self.work / "arms" / driver / "logs" / f"{mode}.stdout.log"
        log.parent.mkdir(exist_ok=True)
        log.write_bytes(b"")
        metadata = {"driver": driver, "mode": mode, "B": 100, "K": 6 if mode == "k6" else None,
                    "K_over_B": .06 if mode == "k6" else None,
                    "p_value_consensus": None if mode == "k6" else 1e-5,
                    "engine_commit": "production", "inference_engine_commit": "inference",
                    "inventory": inventory,
                    "log_inventory": {log.name: {key: REPORT.BASE.record(log)[key] for key in ("bytes", "sha256")}},
                    "legacy_comparison": {"passed": True, "exact_files": list(REPORT.NETWORK_FILES),
                                          "parameter_info": "exact_except_output_path"} if mode == "legacy_pc" else None}
        path = arm / "consensus_manifest.json"
        self.write_json(path, metadata)
        self.manifests[(driver, mode)] = metadata
        self.run_rows.append({"driver": driver, "mode": mode, "sha256": REPORT.BASE.sha256(path)})
        destination = self.qc / "provenance/qc" / driver / mode
        destination.mkdir(parents=True)
        REPORT.shutil.copyfile(path, destination / path.name)
        counts = {"a": 1, "b": int(mode == "k6")}
        REPORT.BASE.write_tsv(destination / "driver_target_sizes.tsv", [
            {"driver": name, "target_count": value} for name, value in counts.items()], ["driver", "target_count"])
        loaded = REPORT.QC.audit_network(arm / REPORT.NETWORK_FILES[1], ["a", "b"], {"a", "b", "x"})
        metrics = {**loaded["metrics"], "scale_free_adjusted_r2": .5,
                   **REPORT.QC.additional_metrics(loaded, 3)}
        self.qc_arms.append({"driver": driver, "mode": mode, "metrics": metrics,
                             "network": REPORT.BASE.record(arm / REPORT.NETWORK_FILES[1])})

    def make_audit(self, driver):
        rows = [row for row in self.verification["rows"] if row["driver"] == driver]
        runs = [{"file": Path(row["path"]).name, "path": row["path"], "sha256": row["full_sha256"],
                 "bytes": row["bytes"], "edge_count": row["edges"], "source_groups": row["source_rows"],
                 "source_order_verified": True} for row in rows]
        hist = {str(k): 80 if k == 1 else 1 if k in (6, 20) else 0 for k in range(1, 101)}
        q = [row["edge_count"] / 82 for row in runs]
        mu, sigma = sum(q), math.sqrt(sum(value * (1 - value) for value in q))
        gate = [{"support": k, "normal_tail": .5 * math.erfc((k - mu) / sigma / math.sqrt(2)),
                 "selected": .5 * math.erfc((k - mu) / sigma / math.sqrt(2)) < 1e-5,
                 "union_edges": hist[str(k)], "actual_legacy_edges": int(k == 20)} for k in range(1, 101)]
        audit = {"schema": "brca100-pchip-independent-support-audit-v1", "passed": True, "issues": {},
                 "B": 100, "K": 6, "K_over_B": .06, "legacy_p": 1e-5,
                 "auditor_sha256": REPORT.BASE.sha256(REPORT.HERE / "validate_support.py"),
                 "source_order_verified_for_all_files": True, "runs": runs,
                 "drivers": {"count": 2, "sha256": self.verification["inputs"][REPORT.QC.DRIVERS[driver]]["sha256"]},
                 "histogram": hist, "union_edges": 82, "pair_incidence": 106,
                 "selected_histograms": {mode: {str(k): int(k == 20 or mode == "k6" and k == 6)
                                               for k in range(1, 101)} for mode in REPORT.QC.MODES},
                 "legacy_mu": mu, "legacy_sigma": sigma, "legacy_gate_by_support": gate,
                 "legacy_minimum_eligible_support": min(row["support"] for row in gate if row["selected"]),
                 "legacy_observed_minimum_support": 20, "overlap": {"shared": 1, "k6_only": 1, "legacy_pc_only": 0},
                 "networks": {}, "enhanced_projection": {}, "metadata": {}}
        for mode in REPORT.QC.MODES:
            arm = self.work / "arms" / driver / mode
            inventory = self.manifests[(driver, mode)]["inventory"]
            audit["networks"][mode] = {"path": str(arm / REPORT.NETWORK_FILES[0]),
                                        "sha256": inventory[REPORT.NETWORK_FILES[0]]["sha256"],
                                        "edges": 2 if mode == "k6" else 1, "strict_lexical_order_verified": True}
            audit["enhanced_projection"][mode] = {"path": str(arm / REPORT.NETWORK_FILES[1]),
                                                   "sha256": inventory[REPORT.NETWORK_FILES[1]]["sha256"],
                                                   "rows_compared": 2 if mode == "k6" else 1}
            audit["metadata"][mode] = {"bootstrap_info_sha256": inventory["bootstrap_info_.txt"]["sha256"],
                                         "parameter_info_sha256": inventory["parameter_info_.txt"]["sha256"]}
        legacy_sha = audit["networks"]["legacy_pc"]["sha256"]
        audit["historical_legacy"] = {"matches_new_legacy_sha256": True, "sha256": legacy_sha, "expected_sha256": legacy_sha}
        self.audits[driver] = audit
        self.write_json(self.work / "support_audits" / f"{driver}.json", audit)

    def mutate_audit(self, mutate):
        audit = copy.deepcopy(self.audits["tf"])
        mutate(audit)
        self.write_json(self.work / "support_audits/tf.json", audit)

    def test_compact_report_binds_all_proofs_and_preserves_zero_target_sources(self):
        result = REPORT.report(self.work, self.results)
        self.verify_qc.assert_called_once_with(self.qc)
        overlap = REPORT.BASE.read_tsv(self.results / "overlap_summary.tsv")
        self.assertEqual(overlap[0]["jaccard"], "0.5")
        self.assertEqual(overlap[0]["edge_increase"], "1")
        self.assertEqual(overlap[0]["legacy_minimum_eligible_support"], "7")
        paired = REPORT.BASE.read_tsv(self.results / "tf_paired_target_sizes.tsv")
        self.assertEqual(paired[1], {"driver": "b", "legacy_pc_targets": "0", "k6_targets": "1", "delta_targets": "1"})
        self.assertEqual(len(REPORT.BASE.read_tsv(self.results / "coverage_summary.tsv")), 4)
        self.assertFalse(list((self.results / "provenance").rglob("*.adj")))
        self.assertFalse(list((self.results / "provenance").rglob("*.exp")))
        self.assertFalse(list((self.results / "provenance").rglob("consensus_network*.txt")))
        self.assertTrue((self.results / "provenance/arms/tf/k6/bootstrap_info_.txt").is_file())
        self.assertFalse((self.results / "SHA256SUMS").exists())
        self.assertFalse((self.results / "RESULTS.md").exists())
        for item in result["files"]:
            self.assertEqual(REPORT.BASE.sha256(self.results / item["path"]), item["sha256"])
        with self.assertRaisesRegex(ValueError, "existing or partial"):
            REPORT.report(self.work, self.results)

    def test_partial_owned_output_is_never_overwritten(self):
        (self.results / "support_audits").mkdir()
        with self.assertRaisesRegex(ValueError, "existing or partial"):
            REPORT.report(self.work, self.results)

    def test_failed_audit_and_missing_full_histogram_fail_before_writes(self):
        for mutate in (lambda value: value.update(passed=False), lambda value: value["histogram"].pop("100")):
            self.mutate_audit(mutate)
            with self.assertRaises(ValueError):
                REPORT.report(self.work, self.results)
            self.assertFalse((self.results / "provenance").exists())

    def test_raw_hash_size_count_and_network_identity_are_not_transferable(self):
        mutations = [lambda value: value["runs"][0].update(sha256="0" * 64),
                     lambda value: value["runs"][0].update(bytes=0),
                     lambda value: value["runs"][0].update(edge_count=0),
                     lambda value: value["networks"]["k6"].update(sha256="0" * 64),
                     lambda value: value["enhanced_projection"]["legacy_pc"].update(sha256="0" * 64)]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                self.mutate_audit(mutate)
                with self.assertRaises(ValueError):
                    REPORT.report(self.work, self.results)

    def test_wrong_contract_boundary_and_histogram_decision_fail(self):
        mutations = [lambda value: value.update(B=99), lambda value: value.update(K=5),
                     lambda value: value.update(legacy_minimum_eligible_support=9),
                     lambda value: value["selected_histograms"]["k6"].update({"6": 0}),
                     lambda value: value["legacy_gate_by_support"][5].update(selected=True)]
        for mutate in mutations:
            self.mutate_audit(mutate)
            with self.assertRaises(ValueError):
                REPORT.report(self.work, self.results)

    def test_invalid_qc_package_blocks_export(self):
        self.verify_qc.side_effect = ValueError("bad QC package")
        with self.assertRaisesRegex(ValueError, "bad QC package"):
            REPORT.report(self.work, self.results)

    def test_optional_passing_contract_tests_are_copied_without_becoming_required(self):
        validation = self.work / "validation"
        self.write_json(validation / "tests.json", {"passed": True, "tests": 1})
        (validation / "tests.stdout.log").write_text("synthetic pass\n")
        (validation / "tests.stderr.log").write_bytes(b"")
        REPORT.report(self.work, self.results)
        self.assertTrue((self.results / "provenance/validation/tests.json").is_file())

    def test_optional_failed_contract_tests_do_not_publish(self):
        self.write_json(self.work / "validation/tests.json", {"passed": False})
        with self.assertRaisesRegex(ValueError, "did not pass"):
            REPORT.report(self.work, self.results)


if __name__ == "__main__":
    unittest.main()
