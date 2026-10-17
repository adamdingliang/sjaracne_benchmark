"""Small synthetic tests; no inference, R, package installs, or network access."""
import csv
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location("pchip_qc", Path(__file__).with_name("analyze_qc.py"))
QC = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(QC)


class NetworkAuditTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def network(self, pairs):
        path = self.root / "network.tsv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, delimiter="\t")
            writer.writerow(QC.HEADER)
            for source, target in pairs:
                writer.writerow([source, target, source, target, .2, .3, .4, .5, .001])
        return path

    def test_zero_filled_degree_and_weak_components(self):
        path = self.network([("a", "x"), ("b", "x"), ("c", "y")])
        result = QC.load_network(path, ["a", "b", "c", "d"], {"a", "b", "c", "d", "x", "y"})
        self.assertEqual(result["degree"], {"a": 1, "b": 1, "c": 1, "d": 0})
        self.assertEqual(result["metrics"]["target_size_zero_median"], 1)
        self.assertEqual(result["metrics"]["weak_components"], 2)
        self.assertEqual(result["metrics"]["largest_weak_component"], 3)
        self.assertEqual(result["metrics"]["incident_nodes"], 5)
        self.assertEqual(result["metrics"]["density"], .15)

    def test_invalid_edges_fail(self):
        for pairs in [[("a", "x"), ("a", "x")], [("a", "a")], [("x", "a")]]:
            with self.subTest(pairs=pairs):
                path = self.network(pairs)
                with self.assertRaises(ValueError):
                    QC.load_network(path, ["a"], {"a", "x"})

    def test_directed_overlap(self):
        result = QC.edge_overlap({("a", "b"), ("b", "a")}, {("a", "b"), ("a", "c")})
        self.assertEqual(result["common_edges"], 1)
        self.assertEqual(result["jaccard"], 1 / 3)
        self.assertEqual(result["historical_only_edges"], 1)

    def test_html_rejects_local_sidecars(self):
        path = self.root / "qc.html"
        path.write_text('<html><img src="data:image/png;base64,a"></html>')
        QC.check_html(path)
        path.write_text('<html><img src="data:image/png;base64,a"><script src="qc_files/a.js"></script></html>')
        with self.assertRaises(ValueError):
            QC.check_html(path)

    def test_lf_pin_preserves_actual_byte_hash(self):
        path = self.root / "pin.R"
        path.write_bytes(b"a\r\nb\r\n")
        expected = QC.hashlib.sha256(b"a\nb\n").hexdigest()
        pinned = QC.pin_script(path, expected)
        self.assertNotEqual(pinned["sha256"], pinned["lf_normalized_sha256"])
        with self.assertRaises(ValueError):
            QC.pin_script(path, "0" * 64)

    def test_manifest_atomic_write_and_inventory(self):
        path = self.root / "manifest.json"
        QC.write_json(path, {"example": 1})
        self.assertEqual(QC.read_json(path), {"example": 1})
        self.assertEqual(QC.inventory(self.root)[0]["sha256"], QC.sha256(path))
        self.assertFalse(path.with_name("manifest.json.partial").exists())

    def test_metric_schema_strict(self):
        path = self.root / "network_summary.tsv"
        with path.open("w", newline="") as handle:
            writer = csv.writer(handle, delimiter="\t")
            writer.writerow(["metric", "value"])
            writer.writerows((field, 1) for field in QC.SUMMARY_FIELDS)
        self.assertEqual(set(QC.read_summary(path)), set(QC.SUMMARY_FIELDS))
        with path.open("a") as handle:
            handle.write("edges\t2\n")
        with self.assertRaises(ValueError):
            QC.read_summary(path)

    def test_mocked_qc_package_and_resume_integrity(self):
        work = self.root / "work"
        (work / "inputs").mkdir(parents=True)
        (work / "inputs/BRCA100.exp").write_text(
            "isoformId\tgeneSymbol\ts1\ts2\na\ta\t1\t2\nx\tx\t2\t3\nb\tb\t3\t4\n")
        for filename in ("design.json", "run_manifest.json"):
            (work / filename).write_text("{}\n")
        for driver, filename in QC.DRIVERS.items():
            (work / "inputs" / filename).write_text("a\nb\n")
            consensus = work / "arms" / driver / "consensus"
            consensus.mkdir(parents=True)
            (consensus.parent / "consensus_manifest.json").write_text("{}\n")
            QC.shutil.copyfile(self.network([("a", "x")]),
                               consensus / "final_consensus_network.txt")
        wrapper, r_script = self.root / "wrapper", self.root / "runner.R"
        wrapper.write_text("wrapper\n", newline="\n")
        r_script.write_text("runner\n", newline="\n")

        def fake_r(command, **kwargs):
            network, drivers, output = map(Path, command[3:6])
            prefix = command[6]
            output.mkdir()
            loaded = QC.load_network(network, QC.read_drivers(drivers), {"a", "b", "x"})
            metrics = {field: 1.0 for field in QC.SUMMARY_FIELDS}
            metrics.update(loaded["metrics"])
            QC.write_tsv(output / "network_summary.tsv",
                         [{"metric": name, "value": value} for name, value in metrics.items()],
                         ["metric", "value"])
            QC.write_tsv(output / "driver_target_sizes.tsv",
                         [{"driver": name, "target_count": value}
                          for name, value in loaded["degree"].items()], ["driver", "target_count"])
            QC.write_tsv(output / "netbid_environment.tsv",
                         [{"component": name, "version": value} for name, value in QC.ENVIRONMENT.items()],
                         ["component", "version"])
            (output / f"{prefix}netQC.html").write_text('<html><img src="data:image/png;base64,a"></html>')
            (output / f"{prefix}netQC.Rmd").write_text("# Test\n")

        args = QC.argparse.Namespace(work_root=work, netbid_wrapper=wrapper,
                                     r_script=r_script, reference_root=None)
        with mock.patch.object(QC, "WRAPPER_LF_SHA256", QC.sha256(wrapper)), \
                mock.patch.object(QC, "R_SOURCE_LF_SHA256", QC.sha256(r_script)), \
                mock.patch.object(QC.subprocess, "run", side_effect=fake_r) as runner:
            manifest = QC.analyze(args)
            self.assertEqual(runner.call_count, 2)
            self.assertEqual(QC.analyze(args), manifest)
            self.assertEqual(runner.call_count, 2)
            destination = self.root / "package"
            QC.package(work, destination, manifest)
            sums = (destination / "SHA256SUMS").read_text().splitlines()
            self.assertTrue(sums)
            for line in sums:
                expected, filename = line.split("  ", 1)
                self.assertNotEqual(filename, "SHA256SUMS")
                self.assertEqual(QC.sha256(destination / filename), expected)
            self.assertEqual(QC.sha256(destination / "tf_netbid2_qc.html"),
                             QC.sha256(work / "analysis/netbid2/tf/TF_netQC.html"))
            (work / "analysis/network_metrics.tsv").write_text("changed")
            with self.assertRaises(ValueError):
                QC.analyze(args)


if __name__ == "__main__":
    unittest.main()
