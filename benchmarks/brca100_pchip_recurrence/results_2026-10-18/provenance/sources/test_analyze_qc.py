"""Synthetic-only QC tests: no R, inference, installs or network access."""
import argparse
from contextlib import ExitStack
import csv
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location("recurrence_qc", Path(__file__).with_name("analyze_qc.py"))
QC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QC)


class FourNetworkQCTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.work = self.root / "work"
        (self.work / "inputs").mkdir(parents=True)
        self.genes = {"a", "b", "x"}
        self.drivers = ["a", "b"]
        (self.work / "inputs/BRCA100.exp").write_text(
            "isoformId\tgeneSymbol\ts1\ts2\na\ta\t1\t2\nb\tb\t2\t3\nx\tx\t3\t4\n")
        for filename in QC.DRIVERS.values():
            (self.work / "inputs" / filename).write_text("a\nb\n")
        for filename, value in (("design.json", {}), ("verification.json", {"verified": True}),
                                ("run_manifest.json", {"complete": True})):
            QC.BASE.write_json(self.work / filename, value)
        self.baseline = self.root / "baseline"
        legacy = {}
        for driver in QC.DRIVERS:
            for mode in QC.MODES:
                arm = self.work / "arms" / driver / mode
                arm.mkdir(parents=True)
                pairs = [("a", "x"), ("b", "x")] if mode == "k6" else [("a", "x")]
                path = arm / "consensus_network_ncol_.txt"
                self.write_network(path, pairs)
                item = QC.BASE.record(path)
                QC.BASE.write_json(arm / "consensus_manifest.json", {
                    "driver": driver, "mode": mode, "B": 100,
                    "K": 6 if mode == "k6" else None,
                    "K_over_B": .06 if mode == "k6" else None,
                    "p_value_consensus": None if mode == "k6" else 1e-5,
                    "inventory": {path.name: item}})
                if mode == "legacy_pc":
                    legacy[driver] = {"bytes": item["bytes"], "sha256": item["sha256"], "edges": 1}
                    QC.BASE.write_json(self.baseline / "provenance" / driver / "consensus_manifest.json", {
                        "inventory": {path.name: item}, "ncol": {"edges": 1}})
        self.wrapper, self.r_script = self.root / "netbid2-r", self.root / "run_netbid_qc.R"
        self.wrapper.write_text("wrapper\n", newline="\n")
        self.r_script.write_text("runner\n", newline="\n")
        self.args = argparse.Namespace(work_root=self.work, netbid_wrapper=self.wrapper,
                                       r_script=self.r_script, package_root=None, verify_only=False)
        patches = {
            "BASELINE_PACKAGE": self.baseline, "LEGACY": legacy, "EXPRESSION_NODES": 3,
            "DRIVER_COUNTS": {driver: 2 for driver in QC.DRIVERS},
            "INPUT_HASHES": {path.name: QC.BASE.sha256(path) for path in (self.work / "inputs").iterdir()},
            "WRAPPER_LF_SHA256": QC.BASE.sha256(self.wrapper),
            "R_SOURCE_LF_SHA256": QC.BASE.sha256(self.r_script),
        }
        self.stack = ExitStack()
        for name, value in patches.items():
            self.stack.enter_context(mock.patch.object(QC, name, value))

    def tearDown(self):
        self.stack.close()
        self.temporary.cleanup()

    def write_network(self, path, pairs):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
            writer.writerow(QC.BASE.HEADER)
            for source, target in pairs:
                writer.writerow([source, target, source, target, .2, .3, .4, .5, .001])

    def fake_r(self, command, **kwargs):
        network, drivers, output = map(Path, command[3:6])
        prefix = command[6]
        output.mkdir(parents=True)
        loaded = QC.audit_network(network, QC.BASE.read_drivers(drivers), self.genes)
        values = {**loaded["metrics"], "scale_free_adjusted_r2": .5}
        QC.BASE.write_tsv(output / "network_summary.tsv", [
            {"metric": field, "value": values[field]} for field in QC.BASE.SUMMARY_FIELDS],
            ["metric", "value"])
        QC.BASE.write_tsv(output / "driver_target_sizes.tsv", [
            {"driver": name, "target_count": count} for name, count in loaded["degree"].items()],
            ["driver", "target_count"])
        QC.BASE.write_tsv(output / "netbid_environment.tsv", [
            {"component": key, "version": value} for key, value in QC.ENVIRONMENT.items()],
            ["component", "version"])
        (output / f"{prefix}netQC.html").write_text('<html><img src="data:image/png;base64,a"></html>')
        (output / f"{prefix}netQC.Rmd").write_text("# Synthetic QC\n")

    def test_zero_filled_coverage_uses_full_candidate_and_expression_denominators(self):
        loaded = {"degree": {"zero": 0, "nine": 9, "ten": 10, "twenty": 20, "fifty": 50},
                  "metrics": {"incident_nodes": 3}}
        values = QC.additional_metrics(loaded, 10)
        self.assertEqual(values["incident_node_fraction"], .3)
        self.assertEqual(values["drivers_ge_10_targets"], 3)
        self.assertEqual(values["driver_fraction_ge_10_targets"], .6)
        self.assertEqual(values["driver_fraction_ge_20_targets"], .4)
        self.assertEqual(values["driver_fraction_ge_50_targets"], .2)

    def test_quantiles_match_type7_and_include_zero_targets(self):
        path = self.work / "arms/tf/legacy_pc/consensus_network_ncol_.txt"
        values = QC.audit_network(path, self.drivers, self.genes)["metrics"]
        self.assertEqual(values["target_size_zero_q25"], .25)
        self.assertEqual(values["target_size_zero_q75"], .75)
        self.assertEqual(values["target_size_active_q25"], 1)
        self.assertEqual(QC.quantile_type7([1, 2, 3, 4], .25), 1.75)
        with self.assertRaises(ValueError):
            QC.quantile_type7([], .25)

    def test_legacy_pin_is_byte_exact_not_just_edge_count(self):
        path = self.work / "arms/tf/legacy_pc/consensus_network_ncol_.txt"
        baseline = self.baseline / "provenance/tf/consensus_manifest.json"
        QC.verify_legacy(path, "tf", baseline)
        path.write_text(path.read_text().replace("0.2", "0.3"))
        with self.assertRaisesRegex(ValueError, "frozen inventory"):
            QC.verify_legacy(path, "tf", baseline)

    def test_manifest_network_identity_must_match_actual_file(self):
        path = self.work / "arms/tf/k6/consensus_network_ncol_.txt"
        self.write_network(path, [("a", "x")])
        with self.assertRaisesRegex(ValueError, "frozen inventory"):
            QC.prepare(self.args)

    def test_incomplete_run_cannot_start_qc(self):
        (self.work / "run_manifest.json").write_text('{"complete":false}\n')
        with mock.patch.object(QC.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "not marked complete"):
                QC.analyze(self.args)
        run.assert_not_called()
        self.assertFalse((self.work / "analysis").exists())

    def test_mode_parameters_are_bound_to_the_same_arm(self):
        path = self.work / "arms/tf/k6/consensus_manifest.json"
        metadata = QC.BASE.read_json(path)
        for key, value in (("B", 99), ("K", 5), ("p_value_consensus", 1e-5)):
            with self.subTest(key=key):
                path.write_text(QC.BASE.json.dumps({**metadata, key: value}))
                with self.assertRaisesRegex(ValueError, "100 post-DPI|parameters changed"):
                    QC.prepare(self.args)
        path.write_text(QC.BASE.json.dumps(metadata))

    def test_input_universe_and_script_pins_fail_closed(self):
        with mock.patch.object(QC, "EXPRESSION_NODES", 4):
            with self.assertRaisesRegex(ValueError, "expression universe"):
                QC.prepare(self.args)
        with mock.patch.object(QC, "DRIVER_COUNTS", {"tf": 3, "sig": 2}):
            with self.assertRaisesRegex(ValueError, "candidate-source"):
                QC.prepare(self.args)
        self.r_script.write_text("changed script\n")
        with self.assertRaisesRegex(ValueError, "method source changed"):
            QC.prepare(self.args)

    def test_four_real_command_shapes_mocked_resume_and_portable_package(self):
        with mock.patch.object(QC.subprocess, "run", side_effect=self.fake_r) as run:
            manifest = QC.analyze(self.args)
            self.assertEqual(run.call_count, 4)
            self.assertEqual({(arm["driver"], arm["mode"]) for arm in manifest["arms"]},
                             {(driver, mode) for driver in QC.DRIVERS for mode in QC.MODES})
            self.assertTrue(all(arm["metrics"]["candidate_drivers"] == 2 for arm in manifest["arms"]))
            self.assertEqual(QC.analyze(self.args), manifest)
            self.assertEqual(run.call_count, 4)
            destination = self.root / "package"
            QC.package(self.work, destination, manifest)
            QC.verify_package(destination)
            self.assertEqual(len(list(destination.glob("*.html"))), 4)
            self.assertFalse(list(destination.rglob("*.adj")))
            self.assertFalse(list(destination.rglob("*.exp")))
            self.assertIn("tf_k6_netbid2_qc.html", (destination / "QC_INDEX.md").read_text())
            for driver in QC.DRIVERS:
                for mode in QC.MODES:
                    self.assertEqual(QC.BASE.sha256(destination / f"{driver}_{mode}_netbid2_qc.html"),
                                     QC.BASE.sha256(self.work / "analysis/netbid2" / driver / mode /
                                                    f"{driver.upper()}_{mode}_netQC.html"))
            with self.assertRaisesRegex(ValueError, "fresh directory"):
                QC.package(self.work, destination, manifest)
            (self.work / "analysis/network_metrics.tsv").write_text("changed")
            with self.assertRaisesRegex(ValueError, "stale or modified"):
                QC.analyze(self.args)

    def test_environment_mismatch_rejects_analysis(self):
        def bad_r(command, **kwargs):
            self.fake_r(command, **kwargs)
            path = Path(command[5]) / "netbid_environment.tsv"
            path.write_text(path.read_text().replace("2.2.0", "9.9.9"))
        with mock.patch.object(QC.subprocess, "run", side_effect=bad_r):
            with self.assertRaisesRegex(ValueError, "environment changed"):
                QC.analyze(self.args)
        self.assertFalse((self.work / "analysis/analysis_manifest.json").exists())

    def test_package_detects_tampered_html_and_never_overwrites_partial_analysis(self):
        with mock.patch.object(QC.subprocess, "run", side_effect=self.fake_r):
            manifest = QC.analyze(self.args)
        destination = self.root / "package"
        QC.package(self.work, destination, manifest)
        (destination / "tf_k6_netbid2_qc.html").write_text("tampered")
        with self.assertRaisesRegex(ValueError, "inventory changed"):
            QC.verify_package(destination)
        (self.work / "analysis/analysis_manifest.json").unlink()
        with self.assertRaisesRegex(ValueError, "Incomplete analysis"):
            QC.analyze(self.args)

    def test_changed_input_prevents_packaging(self):
        with mock.patch.object(QC.subprocess, "run", side_effect=self.fake_r):
            manifest = QC.analyze(self.args)
        self.wrapper.write_text("changed wrapper\n")
        with self.assertRaisesRegex(ValueError, "Input changed before packaging"):
            QC.package(self.work, self.root / "package", manifest)


if __name__ == "__main__":
    unittest.main()
