"""Small frozen-bootstrap count tests; no real benchmark inputs or inference."""

import copy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import score_bootstrap_counts as module
import score_fixed_universe as fixed


class AdjacencyCountTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="bootstrap-count-test-")
        self.root = Path(self.temporary.name)
        self.adjacency = self.root / "bootstrap_001.adj"
        identifiers = ("A", "B", "C", "D", "E")
        gene_ids = {gene: index for index, gene in enumerate(identifiers)}
        self.universe = fixed.Universe(
            sources=("A", "B"), targets=("A", "B", "C", "D"),
            gene_ids=gene_ids, positives=set(), full_reference_count=2,
            excluded_reference={"source_not_eligible_inference_hub": 0,
                                "target_not_inference_gene": 0, "self_pair": 0})
        self.universe.positives = {self.universe.key("A", "B"),
                                   self.universe.key("B", "D")}
        self.hubs = {"A", "B", "C"}
        self.expected_header = {"MI threshold": .2, "MI P-value": 1e-7,
                                "DPI tolerance": 0}

    def tearDown(self):
        self.temporary.cleanup()

    def write_adjacency(self, body, header=None):
        values = self.expected_header if header is None else header
        text = "".join(f">  {key}    {value}\n" for key, value in values.items())
        self.adjacency.write_text(text + body, encoding="utf-8")

    def score(self, body, header=None, expected_header=None):
        self.write_adjacency(body, header)
        return module.score_adjacency(
            self.adjacency, self.universe, self.hubs,
            self.expected_header if expected_header is None else expected_header)

    def test_counts_only_eligible_directed_pairs_and_keeps_integer_ids(self):
        counts, pairs = self.score(
            "A\tB\t0.8\tC\t0.2\nB\tD\t0.7\nC\tA\t0.5\tB\t0.3\n")
        self.assertEqual(
            {key: counts[key] for key in ("full_edges", "source_rows",
                                         "eligible_sources_with_edges", "eligible_edges",
                                         "TP", "FP", "FN", "TN")},
            {"full_edges": 5, "source_rows": 3, "eligible_sources_with_edges": 2,
             "eligible_edges": 3, "TP": 2, "FP": 1, "FN": 0, "TN": 3})
        self.assertAlmostEqual(counts["precision"], 2 / 3)
        self.assertEqual(counts["sensitivity"], 1)
        self.assertEqual(counts["specificity"], .75)
        self.assertEqual(pairs, {self.universe.key("A", "B"),
                                 self.universe.key("A", "C"),
                                 self.universe.key("B", "D")})
        self.assertTrue(all(isinstance(key, int) for key in pairs))
        self.assertEqual(counts["TP"] + counts["FN"], len(self.universe.positives))
        self.assertEqual(counts["FP"] + counts["TN"],
                         self.universe.size - len(self.universe.positives))

    def test_zero_edge_source_rows_and_header_only_network(self):
        for body, rows in (("A\nB\nC\n", 3), ("", 0)):
            with self.subTest(body=body):
                counts, pairs = self.score(body)
                self.assertEqual(counts["source_rows"], rows)
                self.assertEqual(counts["eligible_sources_with_edges"], 0)
                self.assertEqual((counts["full_edges"], counts["eligible_edges"],
                                  counts["TP"], counts["FP"], counts["FN"], counts["TN"]),
                                 (0, 0, 0, 0, 2, 4))
                self.assertIsNone(counts["precision"])
                self.assertEqual(counts["sensitivity"], 0)
                self.assertEqual(counts["specificity"], 1)
                self.assertEqual(pairs, set())

    def test_unassayed_predictions_do_not_change_eligible_operating_point(self):
        counts, pairs = self.score("C\tA\t0.5\tB\t0.4\n")
        self.assertEqual(counts["full_edges"], 2)
        self.assertEqual(counts["eligible_edges"], 0)
        self.assertEqual((counts["TP"], counts["FP"], counts["FN"], counts["TN"]),
                         (0, 0, 2, 4))
        self.assertIsNone(counts["precision"])
        self.assertEqual(pairs, set())

    def test_hyphenated_gene_symbols_cannot_collide(self):
        identifiers = ("A-B", "C", "A", "B-C")
        gene_ids = {gene: index for index, gene in enumerate(identifiers)}
        self.universe = fixed.Universe(
            sources=("A-B", "A"), targets=identifiers, gene_ids=gene_ids,
            positives=set(), full_reference_count=1, excluded_reference={})
        positive = self.universe.key("A-B", "C")
        negative = self.universe.key("A", "B-C")
        self.universe.positives = {positive}
        self.hubs = {"A-B", "A"}
        counts, pairs = self.score("A-B\tC\t0.5\nA\tB-C\t0.4\n")
        self.assertNotEqual(positive, negative)
        self.assertEqual(pairs, {positive, negative})
        self.assertEqual((counts["TP"], counts["FP"], counts["FN"], counts["TN"]),
                         (1, 1, 0, 4))

    def test_rejects_malformed_duplicate_and_out_of_input_pairs(self):
        bad_rows = {
            "incomplete target/MI pair": "A\tB\t0.3\tC\n",
            "empty source": "\tB\t0.3\n",
            "unknown source": "UNKNOWN\tB\t0.3\n",
            "known nonhub source": "D\tB\t0.3\n",
            "unknown target": "A\tUNKNOWN\t0.3\n",
            "raw noninference target": "A\tE\t0.3\n",
            "self pair": "A\tA\t0.3\n",
            "duplicate target": "A\tB\t0.3\tB\t0.4\n",
            "duplicate source row": "A\tB\t0.3\nA\tC\t0.4\n",
            "duplicate zero edge source row": "A\nA\n",
            "invalid unassayed self pair": "C\tC\t0.3\n",
            "duplicate unassayed target": "C\tA\t0.3\tA\t0.4\n",
        }
        for description, body in bad_rows.items():
            with self.subTest(description=description):
                with self.assertRaises(ValueError):
                    self.score(body)

    def test_rejects_invalid_mi_even_for_unassayed_sources(self):
        for source, target in (("A", "B"), ("C", "A")):
            for value in ("nan", "inf", "-inf", "-0.1", "not-a-number", ""):
                with self.subTest(source=source, value=value):
                    with self.assertRaises(ValueError):
                        self.score(f"{source}\t{target}\t{value}\n")

    def test_accepts_native_header_rounding_and_mi_cutoff_rounding(self):
        expected = dict(self.expected_header, **{"MI threshold": .123456789})
        printed = dict(expected, **{"MI threshold": .123457})
        counts, _ = self.score("A\tB\t0.2\n", printed, expected)
        self.assertAlmostEqual(counts["header"]["MI threshold"], .123457)
        counts, _ = self.score("A\tB\t0.1999995\n")
        self.assertEqual(counts["TP"], 1)
        with self.assertRaises(ValueError):
            self.score("A\tB\t0.199998\n")

    def test_rejects_missing_duplicate_invalid_and_mismatched_required_headers(self):
        for key in self.expected_header:
            with self.subTest(kind="missing", key=key):
                header = dict(self.expected_header)
                del header[key]
                with self.assertRaises(ValueError):
                    self.score("A\tB\t0.8\n", header)
            with self.subTest(kind="duplicate", key=key):
                self.write_adjacency(f">  {key}    {self.expected_header[key]}\nA\tB\t0.8\n")
                with self.assertRaises(ValueError):
                    module.score_adjacency(self.adjacency, self.universe,
                                           self.hubs, self.expected_header)
            for value in (float("nan"), float("inf"), "invalid"):
                with self.subTest(kind="invalid", key=key, value=value):
                    header = dict(self.expected_header, **{key: value})
                    with self.assertRaises(ValueError):
                        self.score("A\tB\t0.8\n", header)
        for key, value in (("MI threshold", .21), ("MI P-value", 1e-6),
                           ("DPI tolerance", .1)):
            with self.subTest(kind="mismatch", key=key):
                with self.assertRaises(ValueError):
                    self.score("A\tB\t0.8\n", dict(self.expected_header, **{key: value}))

    def test_informational_headers_are_allowed_but_sampling_headers_are_bound(self):
        expected = dict(self.expected_header, **{
            "Eligible observations": 121, "Sampled observations": 97,
            "Sampling method": "fixed-size without replacement", "Sampling request": "80%"})
        header = dict(expected, **{"Version": "synthetic fixture", "Input file": "unused.exp"})
        counts, _ = self.score("A\tB\t0.8\n", header, expected)
        self.assertEqual(counts["header"]["Sampled observations"], 97)
        for key, value in (("Eligible observations", 120), ("Sampled observations", 96),
                           ("Sampling method", "legacy bootstrap"), ("Sampling request", "79%")):
            with self.subTest(key=key):
                with self.assertRaises(ValueError):
                    self.score("A\tB\t0.8\n", dict(header, **{key: value}), expected)
        for key in ("Eligible observations", "Sampled observations",
                    "Sampling method", "Sampling request"):
            with self.subTest(kind="missing", key=key):
                missing = dict(header)
                del missing[key]
                with self.assertRaises(ValueError):
                    self.score("A\tB\t0.8\n", missing, expected)


class RunSummaryTests(unittest.TestCase):
    def test_statistics_summarize_individual_bootstraps_not_pooled_counts(self):
        rows = [
            {"full_edges": 1, "eligible_edges": 1, "TP": 0, "FP": 1,
             "precision": 0., "sensitivity": 0., "specificity": .99},
            {"full_edges": 2, "eligible_edges": 2, "TP": 1, "FP": 1,
             "precision": .5, "sensitivity": .01, "specificity": .99},
            {"full_edges": 100, "eligible_edges": 100, "TP": 90, "FP": 10,
             "precision": .9, "sensitivity": .9, "specificity": .9},
        ]
        original = copy.deepcopy(rows)
        summary = module.summarize_runs(rows)
        self.assertEqual(summary["precision"]["n"], 3)
        self.assertEqual(summary["precision"]["median"], .5)
        self.assertAlmostEqual(summary["precision"]["mean"], 1.4 / 3)
        self.assertEqual(summary["precision"]["q1"], .25)
        self.assertAlmostEqual(summary["precision"]["q3"], .7)
        self.assertEqual((summary["precision"]["min"], summary["precision"]["max"]), (0., .9))
        self.assertNotAlmostEqual(summary["precision"]["median"], 91 / 103)
        self.assertEqual(summary["TP"]["median"], 1)
        self.assertEqual(summary["FP"]["median"], 1)
        self.assertEqual(summary["eligible_edges"]["median"], 2)
        self.assertEqual(summary["sensitivity"]["median"], .01)
        self.assertEqual(summary["specificity"]["median"], .99)
        self.assertEqual(summary, module.summarize_runs(list(reversed(rows))))
        self.assertEqual(rows, original)

    def test_undefined_precision_is_excluded_not_replaced_with_zero(self):
        rows = [
            {"full_edges": 0, "eligible_edges": 0, "TP": 0, "FP": 0,
             "precision": None, "sensitivity": 0., "specificity": 1.},
            {"full_edges": 1, "eligible_edges": 1, "TP": 1, "FP": 0,
             "precision": 1., "sensitivity": .1, "specificity": 1.},
        ]
        summary = module.summarize_runs(rows)
        self.assertEqual(summary["precision"]["n"], 1)
        self.assertEqual(summary["precision"]["median"], 1.)
        self.assertEqual(summary["precision"]["mean"], 1.)
        self.assertEqual(summary["sensitivity"]["n"], 2)
        self.assertEqual(summary["eligible_edges"]["median"], .5)
        empty_precision = module.summarize_runs(rows[:1])
        self.assertEqual(empty_precision["precision"]["n"], 0)


class RunValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="bootstrap-count-gate-test-")
        self.root = Path(self.temporary.name)
        self.run_root = self.root / "after"
        self.run_root.mkdir()
        (self.run_root / "adj").mkdir()
        self.manifest = self.run_root / "run_manifest.json"
        self.manifest.write_text("{}\n", encoding="utf-8")
        self.baseline = self.root / "before_run_manifest.json"
        self.baseline.write_text("{}\n", encoding="utf-8")
        self.run = {
            "status": "complete", "bootstraps": {}, "consensus": {},
            "frozen": {"profile": module.sampling.PROFILE, "baseline_binding": {
                "records": {"run_manifest": module.legacy.record_file(self.baseline)}}}}
        for seed in range(1, 101):
            adjacency = self.run_root / "adj" / f"bootstrap_{seed:03d}.adj"
            adjacency.write_text("A\tB\t0.7\n", encoding="utf-8")
            log = self.run_root / f"bootstrap_{seed:03d}.log"
            log.write_text("synthetic saved bootstrap\n", encoding="utf-8")
            self.run["bootstraps"][str(seed)] = {
                "seed": seed, "status": "complete", "returncode": 0,
                "artifacts": {"adjacency": module.legacy.record_file(adjacency),
                              "log": module.legacy.record_file(log)}}
        self.networks = {}
        for p in module.completion.PC:
            name = module.legacy.consensus_name(p)
            directory = self.run_root / name
            directory.mkdir()
            network = directory / "edges.tsv"
            network.write_text("source\ttarget\tMI\nA\tB\t0.7\n", encoding="utf-8")
            log = directory / "consensus.log"
            log.write_text("synthetic saved consensus\n", encoding="utf-8")
            self.run["consensus"][name] = {
                "p": p, "status": "complete", "returncode": 0,
                "artifacts": {"edges.tsv": module.legacy.record_file(network),
                              "log": module.legacy.record_file(log)}}
            self.networks[p] = network.resolve()

    def tearDown(self):
        self.temporary.cleanup()

    def validate_after(self, run=None):
        run = self.run if run is None else run
        native_args = object()
        # Real checkpoint/hash checks run; native input reconstruction is isolated.
        with patch.object(module.after, "native_arguments", return_value=native_args) as native, \
             patch.object(module.sampling, "make_frozen",
                          return_value=(copy.deepcopy(run["frozen"]), set(), set())) as reconstruct, \
             patch.object(module.sampling, "verify_frozen") as frozen:
            result = module.validate_run(self.manifest, run, self.root / "prepared",
                                         "after", self.baseline)
        native.assert_called_once_with(self.manifest, run["frozen"])
        reconstruct.assert_called_once_with(native_args)
        frozen.assert_called_once_with(run["frozen"])
        return result

    def test_accepts_100_completed_hash_bound_after_checkpoints(self):
        self.assertEqual(self.validate_after(), self.networks)

    def test_before_arm_delegates_immutable_protocol_and_artifact_validation(self):
        with patch.object(module.completion, "validate_native", return_value=self.networks) as validate:
            result = module.validate_run(self.manifest, self.run, self.root / "prepared", "before")
        self.assertEqual(result, self.networks)
        args, run = validate.call_args.args
        self.assertEqual(args.run_manifest, self.manifest)
        self.assertEqual(args.prepared_dir, self.root / "prepared")
        self.assertIs(run, self.run)

    def test_rejects_incomplete_or_locked_run_before_native_validation(self):
        for kind in ("incomplete", "locked"):
            with self.subTest(kind=kind):
                run = copy.deepcopy(self.run)
                lock = self.run_root / ".runner.lock"
                if kind == "incomplete":
                    run["status"] = "incomplete"
                else:
                    lock.write_text("synthetic lock\n", encoding="utf-8")
                with patch.object(module.completion, "validate_native") as validate:
                    with self.assertRaisesRegex(ValueError, "completed, unlocked"):
                        module.validate_run(self.manifest, run, self.root / "prepared", "before")
                validate.assert_not_called()

    def test_rejects_failed_bootstrap_or_before_consensus_returncode(self):
        for checkpoint in ("bootstrap", "consensus"):
            with self.subTest(checkpoint=checkpoint):
                run = copy.deepcopy(self.run)
                if checkpoint == "bootstrap":
                    run["bootstraps"]["1"]["returncode"] = 1
                else:
                    next(iter(run["consensus"].values()))["returncode"] = 1
                with patch.object(module.completion, "validate_native", return_value=self.networks) as validate:
                    with self.assertRaises(ValueError):
                        module.validate_run(self.manifest, run, self.root / "prepared", "before")
                if checkpoint == "bootstrap":
                    validate.assert_not_called()

    def test_rejects_missing_extra_or_failed_after_checkpoint(self):
        for kind in ("missing", "extra", "failed", "wrong seed"):
            with self.subTest(kind=kind):
                run = copy.deepcopy(self.run)
                if kind == "missing":
                    del run["bootstraps"]["100"]
                elif kind == "extra":
                    run["bootstraps"]["101"] = copy.deepcopy(run["bootstraps"]["100"])
                elif kind == "failed":
                    run["bootstraps"]["1"]["status"] = "failed"
                else:
                    run["bootstraps"]["1"]["seed"] = 2
                with self.assertRaises(ValueError):
                    self.validate_after(run)

    def test_rejects_tampered_after_adjacency_and_log(self):
        for artifact in ("adjacency", "log"):
            with self.subTest(artifact=artifact):
                path = Path(self.run["bootstraps"]["1"]["artifacts"][artifact]["path"])
                original = path.read_text(encoding="utf-8")
                path.write_text("tampered\n", encoding="utf-8")
                try:
                    with self.assertRaisesRegex(ValueError, "hash mismatch"):
                        self.validate_after()
                finally:
                    path.write_text(original, encoding="utf-8")

    def test_rejects_extra_after_adjacency_and_changed_baseline_binding(self):
        extra = self.run_root / "adj" / "unexpected.adj"
        extra.write_text("A\tB\t0.7\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.validate_after()
        extra.unlink()
        self.baseline.write_text("changed baseline\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.validate_after()


if __name__ == "__main__":
    unittest.main()
