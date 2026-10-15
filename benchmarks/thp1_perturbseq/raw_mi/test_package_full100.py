"""Synthetic compact evidence tests; no inference or real output writes."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import package_full100 as module


class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.size, cls.positive = 200000, 50000
        cls.plan = {"seeds": list(range(1, 101)), "arms": ["before", "after"],
                    "parameters": {"primary_k": 5000, "ks": list(module.PRESPECIFIED)},
                    "universe": {"candidate_pairs": cls.size, "reference_positive_pairs": cls.positive,
                                 "reference_negative_pairs": cls.size - cls.positive, "random_positive_fraction": .25}}
        cls.results = []
        for seed in range(1, 101):
            for arm in ("before", "after"):
                curve = []
                fraction = .3 if arm == "before" else .4
                for k in [0, *module.BUDGETS, cls.size]:
                    tp = k * fraction if k < cls.size else cls.positive
                    fp = k - tp
                    curve.append({"k": k, "TP_tie_expected": tp, "FP_tie_expected": fp,
                                  "TP_min": int(tp), "TP_max": int(tp),
                                  "precision_tie_expected": tp / k if k else None,
                                  "EPR_tie_expected": (tp / k) / .25 if k else None,
                                  "sensitivity_tie_expected": tp / cls.positive,
                                  "specificity_tie_expected": 1 - fp / (cls.size - cls.positive),
                                  "FPR_tie_expected": fp / (cls.size - cls.positive),
                                  "random_TP_expectation_at_k": k * .25})
                cls.results.append({"status": "complete", "arm": arm, "seed": seed,
                                    **cls.plan["universe"], "AUROC_MI_ties": .6,
                                    "AUROC_ROC_integral_check": .6, "curve": curve,
                                    "top_k": [copy.deepcopy(row) for row in curve if row["k"] in module.PRESPECIFIED]})

    def values(self):
        return copy.deepcopy(self.results), copy.deepcopy(self.plan)

    def test_complete_population_budget_roles_directions_and_no_metric_pooling(self):
        summary, rows, per_seed = module.build_evidence(self.results, self.plan)
        self.assertEqual(summary["matched_seeds"], 100)
        self.assertEqual(len(rows), 100)
        self.assertEqual(len(per_seed), 20000)
        primary = next(row for row in rows if row["k"] == 5000)
        self.assertEqual(primary["role"], "prespecified_primary")
        self.assertEqual(primary["before_TP_median"], 1500)
        self.assertEqual(primary["after_TP_median"], 2000)
        self.assertEqual(primary["paired_TP_after_higher"], 100)
        self.assertEqual(primary["paired_FP_after_lower"], 100)
        self.assertEqual(primary["paired_TP_delta_median"], 500)
        self.assertEqual(next(row for row in rows if row["k"] == 20000)["role"], "descriptive_existing_curve_point")
        self.assertIn("after examining", summary["selection_history"])
        self.assertEqual(summary["paired_AUROC"]["after_equal"], 100)

    def test_missing_and_duplicate_identity_rejected(self):
        for results in (self.results[:-1], self.results + [self.results[0]]):
            with self.assertRaises(ValueError):
                module.build_evidence(results, self.plan)

    def test_changed_seed_population_or_original_budgets_rejected(self):
        for mutate in (lambda p: p.update(seeds=list(range(1, 100))),
                       lambda p: p["parameters"].update(primary_k=20000),
                       lambda p: p["parameters"].update(ks=[5000])):
            plan = copy.deepcopy(self.plan)
            mutate(plan)
            with self.assertRaises(ValueError):
                module.build_evidence(self.results, plan)

    def test_wrong_class_totals_or_prevalence_rejected(self):
        for key, value in (("candidate_pairs", 200001), ("reference_positive_pairs", 50001), ("random_positive_fraction", .5)):
            results, plan = self.values()
            results[0][key] = value
            with self.assertRaises(ValueError):
                module.build_evidence(results, plan)

    def test_missing_duplicate_or_changed_curve_grid_rejected(self):
        for mutate in (lambda r: r["curve"].pop(20), lambda r: r["curve"].insert(1, copy.deepcopy(r["curve"][1])),
                       lambda r: r["curve"].reverse()):
            results, plan = self.values()
            mutate(results[0])
            with self.assertRaises(ValueError):
                module.build_evidence(results, plan)

    def test_TP_FP_precision_EPR_and_tie_inconsistency_rejected(self):
        for key, value in (("TP_tie_expected", 999), ("FP_tie_expected", 999), ("precision_tie_expected", .9),
                           ("EPR_tie_expected", .2), ("TP_min", 999), ("specificity_tie_expected", .2)):
            results, plan = self.values()
            results[0]["curve"][1][key] = value
            with self.assertRaises(ValueError):
                module.build_evidence(results, plan)

    def test_topk_curve_disagreement_and_nonfinite_auc_rejected(self):
        results, plan = self.values()
        results[0]["top_k"][0]["TP_tie_expected"] += 1
        with self.assertRaises(ValueError):
            module.build_evidence(results, plan)
        results, plan = self.values()
        results[0]["AUROC_MI_ties"] = float("nan")
        with self.assertRaises(ValueError):
            module.build_evidence(results, plan)

    def test_hash_and_expected_path_checks(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "metrics.json"
            path.write_text("{}")
            record = module.record(path)
            module.verify_record(record, path)
            with self.assertRaises(ValueError):
                module.verify_record(record, Path(temporary) / "other.json")
            path.write_text("changed")
            with self.assertRaises(ValueError):
                module.verify_record(record)

    def test_existing_output_rejected_before_input_reads(self):
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(module, "load_run") as load:
                with self.assertRaises(FileExistsError):
                    module.package("missing-source", temporary)
                load.assert_not_called()

    def test_validation_failure_creates_no_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            out = root / "fresh"
            with patch.object(module, "load_run", return_value=(self.plan, self.results[:-1], {}, root)):
                with self.assertRaises(ValueError):
                    module.package(root, out)
            self.assertFalse(out.exists())

    def _mock_run(self, root):
        root = Path(root).resolve()
        plan = copy.deepcopy(self.plan)
        plan.update(out=str(root), universe_file={"path": str(root / "inputs/universe.json")})
        plan_record, extension_record = {"path": str(root / "plan.json")}, {"path": str(root / "extension.json")}
        jobs, records, documents = [], [], {}
        for result in self.results:
            path = root / "jobs" / result["arm"] / f"seed_{result['seed']:03d}" / "metrics.json"
            record = {"path": str(path), "sha256": "synthetic", "bytes": 1}
            records.append(record)
            jobs.append({"status": "complete", "arm": result["arm"], "seed": result["seed"], "artifacts": {"metrics.json": record}})
            documents[str(path)] = result
        documents.update({str(root / "plan.json"): plan,
                          str(root / "status.json"): {"status": "complete", "completed": 200, "total": 200, "failures": [],
                                                       "plan": plan_record, "extension": extension_record, "jobs": jobs},
                          str(root / "extension.json"): {"new_plan": plan_record},
                          str(root / "report_20261015/report_provenance.json"): {"plan": plan_record, "extension": extension_record,
                                                                                "score_results": records}})
        return documents

    def _load_mock(self, root, documents):
        with patch.object(module, "read_json", side_effect=lambda path: documents[str(Path(path))]), \
             patch.object(module, "verify_record", side_effect=lambda value, expected_path=None: Path(value["path"]).resolve()):
            return module.load_run(root)

    def test_completed_provenance_population_loads_all_200_metrics(self):
        with tempfile.TemporaryDirectory() as root:
            plan, results, records, report = self._load_mock(root, self._mock_run(root))
            self.assertEqual(len(results), 200)
            self.assertEqual(len(records), 200)

    def test_incomplete_status_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            docs = self._mock_run(root)
            docs[str(Path(root) / "status.json")]["completed"] = 199
            with self.assertRaises(ValueError):
                self._load_mock(root, docs)

    def test_duplicate_completed_job_record_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            docs = self._mock_run(root)
            jobs = docs[str(Path(root) / "status.json")]["jobs"]
            jobs[-1] = jobs[0]
            with self.assertRaisesRegex(ValueError, "duplicate"):
                self._load_mock(root, docs)

    def test_metric_content_identity_must_match_completed_job(self):
        with tempfile.TemporaryDirectory() as root:
            docs = self._mock_run(root)
            path = str(Path(root) / "jobs/before/seed_001/metrics.json")
            docs[path] = {**docs[path], "seed": 2}
            with self.assertRaisesRegex(ValueError, "identity"):
                self._load_mock(root, docs)

    def test_report_metric_hash_records_must_match_status_records(self):
        with tempfile.TemporaryDirectory() as root:
            docs = self._mock_run(root)
            provenance = docs[str(Path(root) / "report_20261015/report_provenance.json")]
            provenance["score_results"] = copy.deepcopy(provenance["score_results"])
            provenance["score_results"][0]["sha256"] = "different"
            with self.assertRaisesRegex(ValueError, "provenance"):
                self._load_mock(root, docs)

    def test_compact_package_preserves_source_bytes_and_omits_large_artifacts(self):
        with tempfile.TemporaryDirectory() as temporary:
            run = Path(temporary) / "run"
            report = run / "report_20261015"
            report.mkdir(parents=True)
            (run / "inputs").mkdir()
            sources = {report / "raw_mi_comparison.png": b"synthetic PNG bytes\n",
                       report / "summary.json": b'{"status":"complete","n_matched_seeds":100}\n',
                       report / "paired_seed_metrics.tsv": b"seed\tmetric\n1\t2\n",
                       report / "REPORT.md": b"Original generated report\n",
                       report / "report_provenance.json": b"{}\n",
                       run / "plan.json": b"{}\n", run / "status.json": b"{}\n",
                       run / "extension.json": b"{}\n", run / "inputs/universe.json": b"{}\n"}
            for path, content in sources.items():
                path.write_bytes(content)
            original_pilot = run / "original_pilot.json"
            smoke_proof = run / "smoke_proof.json"
            original_pilot.write_text("Original immutable pilot plan\n")
            smoke_proof.write_text("Original immutable smoke proof\n")
            (run / "extension.json").write_text(json.dumps({"original_pilot_plan": module.record(original_pilot)}))
            plan = {**self.plan, "smoke_proof": module.record(smoke_proof)}
            out = Path(temporary) / "package"
            with patch.object(module, "load_run", return_value=(plan, self.results, {}, report)):
                module.package(run, out)
            self.assertEqual((out / "provenance/generated_REPORT.md").read_bytes(), sources[report / "REPORT.md"])
            self.assertEqual((out / "provenance/generated_summary.json").read_bytes(), sources[report / "summary.json"])
            self.assertEqual((out / "provenance/original_pilot_plan.json").read_bytes(), original_pilot.read_bytes())
            self.assertEqual((out / "provenance/smoke_proof.json").read_bytes(), smoke_proof.read_bytes())
            self.assertEqual((out / "raw_mi_comparison.png").read_bytes(), sources[report / "raw_mi_comparison.png"])
            self.assertTrue((out / "package_manifest.json").is_file())
            self.assertTrue((out / "analysis_summary.json").is_file())
            self.assertTrue((out / "budget_summary.tsv").is_file())
            self.assertTrue((out / "per_seed_budget_metrics.tsv").is_file())
            self.assertFalse(any(path.name in ("raw.adj", "scores.npz", "labels.npy") for path in out.rglob("*")))


if __name__ == "__main__":
    unittest.main()
