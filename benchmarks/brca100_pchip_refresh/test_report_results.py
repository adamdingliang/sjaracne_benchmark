"""Focused report contracts; synthetic files only, no native inference or R."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location("brca_presentation", Path(__file__).with_name("report_results.py"))
report = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(report)


def ledger():
    return {"complete": True, "completed_seed_jobs": 200, "design_sha256": "design",
            "rows": [{"driver": driver, "seed": seed} for driver in ("tf", "sig")
                     for seed in range(1, 101)]}


def metrics(values):
    result = dict.fromkeys(report.qc.SUMMARY_FIELDS, 0.0)
    result.update(candidate_drivers=len(values), edges=sum(values),
                  active_drivers=sum(value > 0 for value in values),
                  active_driver_fraction=sum(value > 0 for value in values) / len(values),
                  target_size_zero_median=report.statistics.median(values),
                  incident_nodes=8, largest_weak_component_fraction=1,
                  scale_free_adjusted_r2=.8)
    return result


class ReportContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_ledger_rejects_incomplete_duplicate_or_wrong_design(self):
        self.assertEqual(len(report.validate_ledger(ledger(), "design")), 200)
        for key, value in (("complete", False), ("completed_seed_jobs", 199),
                           ("design_sha256", "wrong")):
            value_ledger = ledger()
            value_ledger[key] = value
            with self.assertRaises(ValueError):
                report.validate_ledger(value_ledger, "design")
        value_ledger = ledger()
        value_ledger["rows"][-1] = value_ledger["rows"][0]
        with self.assertRaises(ValueError):
            report.validate_ledger(value_ledger, "design")

    def test_metadata_hash_tampering_is_rejected(self):
        path = self.root / "metadata.json"
        path.write_text('{"m":80}\n')
        item = report.qc.record(path)
        report.verify_record(path, item)
        path.write_text('{"m":90}\n')
        with self.assertRaises(ValueError):
            report.verify_record(path, item)

    def test_inventory_rejects_escape_and_duplicate_paths(self):
        with self.assertRaises(ValueError):
            report.child(self.root, "../outside")
        with self.assertRaises(ValueError):
            report.verify_entries(self.root, [{"path": "same"}, {"path": "same"}])

    def test_paired_counts_require_all_candidates_and_consistent_totals(self):
        path = self.root / "pairs.tsv"
        path.write_text("driver\thistorical_targets\tpchip_targets\na\t0\t1\nb\t2\t2\nc\t2\t1\n")
        old, current = metrics([0, 2, 2]), metrics([1, 2, 1])
        result = report.paired_counts(path, ["a", "b", "c"], old, current)
        self.assertEqual((result["increased"], result["unchanged"], result["decreased"]), (1, 1, 1))
        with self.assertRaises(ValueError):
            report.paired_counts(path, ["a", "b"], old, current)
        with self.assertRaises(ValueError):
            report.paired_counts(path, ["a", "b", "c"], {**old, "edges": 5}, current)

    def test_overlap_is_directed_and_algebra_checked(self):
        old, current = {"edges": 4}, {"edges": 5}
        row = {"historical_edges": "4", "pchip_edges": "5", "common_edges": "3",
               "historical_only_edges": "1", "pchip_only_edges": "2",
               "jaccard": str(3 / 6), "fraction_historical_retained": str(3 / 4),
               "fraction_pchip_shared": str(3 / 5)}
        self.assertEqual(report.validate_overlap(row, old, current)["jaccard"], .5)
        with self.assertRaises(ValueError):
            report.validate_overlap({**row, "historical_only_edges": "2"}, old, current)

    def context(self, source):
        values = metrics([0, 2, 2])
        overlap = {"historical_edges": 4, "pchip_edges": 4, "common_edges": 3,
                   "historical_only_edges": 1, "pchip_only_edges": 1,
                   "jaccard": .6, "fraction_historical_retained": .75,
                   "fraction_pchip_shared": .75}
        return {"design": {"arms": {driver: {"p_token": p, "mi_cutoff": .15}
                                    for driver, p in (("tf", "0.001"), ("sig", "0.0005"))}},
                "build": {"compiler": "test compiler"},
                "metrics": {driver: copy.deepcopy(values) for driver in ("tf", "sig")},
                "historical_metrics": {driver: copy.deepcopy(values) for driver in ("tf", "sig")},
                "old_points": {point: {"mi_cutoff": .16} for point in ("p1e-03", "p5e-04")},
                "pairs": {driver: {"historical": [0, 2, 2], "pchip": [0, 2, 2],
                                   "increased": 0, "unchanged": 3, "decreased": 0}
                          for driver in ("tf", "sig")},
                "overlaps": {driver: overlap.copy() for driver in ("tf", "sig")},
                "anchor": {"status": "match"}, "pins": [report.qc.record(source)],
                "copies": {"provenance/native/example.json": source}, "header_excerpts": {}}

    def test_publication_preserves_original_qc_and_separate_checksums(self):
        work, old, package = self.root / "work", self.root / "old", self.root / "package"
        for path in (work, old, package):
            path.mkdir()
        source = self.root / "input.json"
        source.write_text('{"fixed":true}\n')
        frozen = {}
        for filename in ("package_manifest.json", "SHA256SUMS", "tf_netbid2_qc.html"):
            (package / filename).write_text("original QC bytes\n")
            frozen[filename] = report.qc.sha256(package / filename)
        context = self.context(source)
        with mock.patch.object(report, "collect", return_value=context):
            first = report.publish(work, package, old)
            self.assertEqual(first["validation"]["seed_metadata_records"], 200)
            self.assertEqual(report.publish(work, package, old), first)
            report.verify_checksums(package, "PRESENTATION_SHA256SUMS")
            for filename, expected in frozen.items():
                self.assertEqual(report.qc.sha256(package / filename), expected)
            self.assertIn("match", first["validation"]["implementation_anchor"])
            text = (package / "RESULTS.md").read_text(encoding="utf-8")
            self.assertNotIn("pending", text.lower())
            self.assertIn("K=6 is not used", text)
            self.assertIn("one example", text)
            (package / "comparison_metrics.tsv").write_text("tampered\n")
            with self.assertRaises(ValueError):
                report.publish(work, package, old)

    def test_failed_anchor_does_not_claim_data_equivalence(self):
        source = self.root / "example"
        source.write_text("pin")
        context = self.context(source)
        context["anchor"]["status"] = "differ"
        text = report.markdown(context, False)
        self.assertIn("cutoff-only causation is not established", text)
        self.assertNotIn("data sections matched exactly", text)

    def test_no_output_is_created_when_collect_rejects_incomplete_run(self):
        package = self.root / "package"
        with mock.patch.object(report, "collect", side_effect=ValueError("incomplete")):
            with self.assertRaises(ValueError):
                report.publish(self.root / "work", package, self.root / "old")
        self.assertFalse(package.exists())


if __name__ == "__main__":
    unittest.main()
