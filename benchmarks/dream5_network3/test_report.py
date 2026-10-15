"""Synthetic reporting and packaging checks; no native or real scoring runs."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import metrics
import report


class ReportingTests(unittest.TestCase):
    def setUp(self):
        self.plan = {"arms": list(report.ARMS), "seeds": [1, 2, 3], "stages": list(report.STAGES),
                     "primary": {"contrast": ["legacy", "u80"], "stage": "nominal_post", "endpoint": "average_precision"},
                     "sampling": {arm: {"draws": 805 if arm == "legacy" else int(arm[1:]) * 8 + 4, "method": "synthetic sample"} for arm in report.ARMS},
                     "parameters": {"nominal_cutoffs": {arm: .03 for arm in report.ARMS}, "fixed_mi": .03759353615996272}}
        labels = np.zeros(report.U, dtype=bool)
        labels[:report.P] = True
        results = []
        for arm in report.ARMS:
            for seed in (1, 2, 3):
                stages = {}
                for stage in report.STAGES:
                    raw = stage == "raw"
                    tp = report.P if raw else 100
                    fp = report.N if raw else 1000
                    emitted = np.ones(report.U, dtype=bool) if raw else np.r_[np.ones(100, bool), np.zeros(report.P - 100, bool), np.ones(1000, bool), np.zeros(report.N - 1000, bool)]
                    values = emitted.astype(float)
                    stages[stage] = {"edges_all": tp + fp + 50, "edges_explicit_labelled": tp + fp, "edges_unlabelled": 50,
                                     "TP": tp, "FP": fp, "FN": report.P - tp, "TN": report.N - fp,
                                     "precision": tp / (tp + fp), "sensitivity": tp / report.P, "specificity": 1 - fp / report.N,
                                     **metrics.ranking_metrics(values, labels, raw=raw, emitted=emitted)}
                pruning = {prefix: {"global_pruning_fraction": 0., "labelled_pruning_fraction": 0., "TP_pruned": 0, "FP_pruned": 0,
                                    "TP_pruning_fraction": 0., "FP_pruning_fraction": 0.} for prefix in ("nominal", "fixed")}
                results.append({"arm": arm, "seed": seed, "stages": stages, "DPI_pruning": pruning,
                                "validation": {stage: {"status": "passed", "arm": arm, "stage": stage} for stage in report.STAGES}})
        self.payload = {"status": "complete", "results": results, "summary": metrics.aggregate(results)}

    def test_complete_cohort_reaggregation_and_primary_endpoint(self):
        summary, stages, pruning, paired = report.build_report_data(self.payload, self.plan)
        self.assertEqual((len(stages), len(pruning), len(paired)), (20, 8, 3))
        self.assertEqual(summary["primary_after_equal"], 3)
        self.assertEqual(summary["primary_paired_AP_delta_median"], 0)
        self.assertEqual(pruning[0]["TP_retention_fraction"], 1)
        text = report.markdown(summary, self.plan, plots=False)
        self.assertIn("1,354,060", text)
        self.assertIn("not false positives", text)
        self.assertIn("not proof", text)
        self.assertIn("precision/coverage tradeoff", text)
        self.assertIn("TP fraction retained", text)
        self.assertNotIn("![", text)

    def test_wrong_endpoint_and_missing_duplicate_identity_rejected(self):
        plan = copy.deepcopy(self.plan)
        plan["primary"]["stage"] = "raw"
        with self.assertRaises(ValueError):
            report.build_report_data(self.payload, plan)
        for mutate in (lambda p: p["results"].pop(), lambda p: p["results"].append(p["results"][0])):
            payload = copy.deepcopy(self.payload)
            mutate(payload)
            with self.assertRaises(ValueError):
                report.build_report_data(payload, self.plan)

    def test_unlabelled_count_and_precision_errors_rejected(self):
        for key, value in (("edges_unlabelled", 0), ("FP", 1001), ("precision", .9), ("random_precision", .2)):
            payload = copy.deepcopy(self.payload)
            payload["results"][0]["stages"]["nominal_post"][key] = value
            with self.assertRaises(ValueError):
                report.build_report_data(payload, self.plan)

    def test_unavailable_post_topk_must_not_be_padded(self):
        payload = copy.deepcopy(self.payload)
        point = payload["results"][0]["stages"]["nominal_post"]["top_k"][-1]
        point["status"] = "complete"
        with self.assertRaises(ValueError):
            report.build_report_data(payload, self.plan)

    def test_stage_validation_and_pruning_mismatch_rejected(self):
        for mutate in (lambda p: p["results"][0]["validation"]["raw"].update(status="failed"),
                       lambda p: p["results"][0]["DPI_pruning"]["nominal"].update(TP_pruned=1)):
            payload = copy.deepcopy(self.payload)
            mutate(payload)
            with self.assertRaises(ValueError):
                report.build_report_data(payload, self.plan)

    def test_changed_frozen_summary_rejected(self):
        payload = copy.deepcopy(self.payload)
        payload["summary"]["primary_paired_AP_delta_median"] = 1
        with self.assertRaises(ValueError):
            report.build_report_data(payload, self.plan)

    def test_hash_validation_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "metrics.json"
            path.write_text("original")
            value = report.record(path)
            report.verify_record(value)
            path.write_text("changed")
            with self.assertRaises(ValueError):
                report.verify_record(value)
            with patch.object(report, "validate_run") as validate:
                with self.assertRaises(FileExistsError):
                    report.package("missing", "missing", temporary)
                validate.assert_not_called()

    def test_validation_failure_leaves_no_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "metrics.json"
            source.write_text("{}")
            out = root / "new"
            with patch.object(report, "validate_run", side_effect=ValueError("invalid run")):
                with self.assertRaises(ValueError):
                    report.package(root, source, out)
            self.assertFalse(out.exists())

    def test_plot_creates_nonempty_png(self):
        summary, _, _, _ = report.build_report_data(self.payload, self.plan)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "comparison.png"
            report.plot_comparison(self.payload, summary, path)
            self.assertTrue(path.is_file())
            self.assertGreater(path.stat().st_size, 10000)

    def test_compact_package_copies_provenance_but_no_native_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            run = root / "run"
            run.mkdir()
            source = root / "scoring/metrics.json"
            source.parent.mkdir()
            source.write_text(json.dumps(self.payload))
            (source.parent / "REPORT.md").write_text("Original generated score report\n")
            for name in ("plan.json", "status.json", "smoke_gate.json", "prepared.json"):
                (run / name).write_text("{}\n")
            plan = {**self.plan, "inputs": {"preparation": {"path": str(run / "prepared.json")}}}
            out = root / "package"
            with patch.object(report, "validate_run", return_value=(plan, self.payload, [])):
                summary = report.package(run, source, out, plots=False)
            self.assertEqual(summary["matched_seeds"], 3)
            self.assertEqual((out / "metrics.json").read_bytes(), source.read_bytes())
            self.assertEqual((out / "provenance/generated_score_REPORT.md").read_text(), "Original generated score report\n")
            manifest = json.loads((out / "package_manifest.json").read_text())
            self.assertIn("python", manifest["environment"])
            self.assertIn("numpy", manifest["environment"])
            self.assertIn("matplotlib", manifest["environment"])
            self.assertFalse(manifest["native_inference_performed_by_report"])
            self.assertFalse(any(path.name in ("raw.adj", "stdout.log", "stderr.log", "time.tsv") for path in out.rglob("*")))


if __name__ == "__main__":
    unittest.main()
