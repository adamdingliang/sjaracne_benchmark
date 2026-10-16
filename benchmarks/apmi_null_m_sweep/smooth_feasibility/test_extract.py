"""Synthetic-only extraction tests; no production streams or generator used."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


EXTRACT = load("smooth_extract_test", Path(__file__).with_name("extract.py"))
FIXTURE = load("expanded_fixture_for_smooth", Path(__file__).resolve().parents[1] /
               "expanded_10m" / "test_summarize.py")


class TestSortedMath(unittest.TestCase):
    def test_quantile_matches_numpy_higher_with_ties_and_rare_p(self):
        for values in (np.array([0., 0., 0., .1, .1, .5]),
                       np.array([0., .1, .2, .4, .8, 1.]), np.array([0.])):
            for p in (.9, .5, .05, .001, 1e-7):
                self.assertEqual(EXTRACT.higher_quantile_sorted(values, p),
                                 float(np.quantile(values, 1-p, method="higher")))

    def test_counts_keep_greater_equal_and_strict_tail_distinct(self):
        values = np.array([0., 0., .1, .1, .1, .2])
        self.assertEqual(EXTRACT.count_sorted(values, .1), {"ge": 4, "gt": 1, "ties": 3})
        self.assertEqual(EXTRACT.count_sorted(values, 0), {"ge": 6, "gt": 4, "ties": 2})
        self.assertEqual(EXTRACT.count_sorted(values, 1), {"ge": 0, "gt": 0, "ties": 0})
        self.assertEqual(EXTRACT.count_sorted(values, -.1), {"ge": 6, "gt": 6, "ties": 0})

    def test_probabilities_and_lookup_shapes_fail_closed(self):
        for probabilities in ([], [0], [1], [-.1], [float("nan")], [float("inf")],
                              [True], [.1, .1]):
            with self.subTest(probabilities=probabilities), self.assertRaises(ValueError):
                EXTRACT.probabilities_checked(probabilities)
        for values in (np.array([]), np.array([[1.]]), np.array([1, 2])):
            with self.assertRaises(ValueError):
                EXTRACT.count_sorted(values, .1)
        with self.assertRaises(ValueError):
            EXTRACT.count_sorted(np.array([0.]), float("nan"))


class TestSyntheticExtraction(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.run = self.root / "original"
        self.run.mkdir()
        self.cache_root = self.root / "runs"
        self.cache_root.mkdir()
        self.plan, self.attempt, self.result = FIXTURE.fixture(self.run)
        (self.run / "plan.json").write_text(json.dumps(self.plan), encoding="utf-8")
        self.patch_runs = patch.object(EXTRACT, "RUNS_ROOT", self.cache_root)
        self.patch_plan = patch.object(EXTRACT.SUMMARY, "load_plan", return_value=self.plan)
        self.patch_runs.start()
        self.patch_plan.start()
        self.addCleanup(self.patch_runs.stop)
        self.addCleanup(self.patch_plan.stop)

    def snapshot(self):
        return {p.relative_to(self.run).as_posix(): EXTRACT.SUMMARY.sha256(p)
                for p in self.run.rglob("*") if p.is_file()}

    def process(self, name="new"):
        return EXTRACT.process_one_m(self.run, 80, [.05, .001, .0005], self.cache_root / name)

    def test_extraction_sorted_copies_with_no_original_modification(self):
        before = self.snapshot()
        row = self.process()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(row["m"], 80)
        self.assertEqual(row["original_gpd_status"], "accepted")
        self.assertEqual(row["primary_fit"]["threshold_quantile"], .995)
        self.assertEqual(row["exceedance_rule"], "APMI >= cutoff")
        for role in ("fit", "validation"):
            record = row["sorted_cache"][role]
            path = Path(record["path"])
            values = np.load(path, mmap_mode="r", allow_pickle=False)
            self.assertTrue(np.all(values[:-1] <= values[1:]))
            self.assertEqual(record["sha256"], EXTRACT.SUMMARY.sha256(path))
            self.assertEqual(len(values), 100_000)
            del values
        raw_path = self.attempt / "calibration" / "raw" / "m00080_npar040_fit.f64"
        raw = np.fromfile(raw_path, dtype="<f8")
        for item in row["quantiles"]:
            threshold = np.quantile(raw, 1-item["nominal_p"], method="higher")
            self.assertEqual(item["cutoff"], threshold)
            self.assertEqual(item["fit_ge"], np.count_nonzero(raw >= threshold))
            self.assertEqual(item["fit_gt"], np.count_nonzero(raw > threshold))
            self.assertEqual(item["fit_ties"], np.count_nonzero(raw == threshold))
        self.assertTrue((self.cache_root / "new" / "extraction.json").is_file())
        self.assertEqual(list((self.cache_root / "new").glob("*.f64")), [])

    def test_existing_and_outside_outputs_are_rejected(self):
        existing = self.cache_root / "exists"
        existing.mkdir()
        for out in (existing, self.root / "outside", self.cache_root,
                    self.run / "new-child", self.root):
            with self.subTest(out=out), self.assertRaises(ValueError):
                EXTRACT.process_one_m(self.run, 80, [.001], out)

    def test_cached_output_cannot_be_reused_or_overwritten(self):
        self.process()
        before = EXTRACT.SUMMARY.sha256(self.cache_root / "new" / "extraction.json")
        with self.assertRaises(ValueError):
            self.process()
        self.assertEqual(before, EXTRACT.SUMMARY.sha256(self.cache_root / "new" / "extraction.json"))

    def test_retry_prevents_silent_selection(self):
        (self.attempt.parent / "attempt_0002").mkdir()
        with self.assertRaisesRegex(ValueError, "exactly original"):
            self.process()
        self.assertFalse((self.cache_root / "new").exists())

    def test_raw_tampering_is_rejected_before_any_output(self):
        path = self.attempt / "calibration" / "raw" / "m00080_npar040_fit.f64"
        with path.open("r+b") as handle:
            handle.write(b"tampered")
        with self.assertRaisesRegex(ValueError, "artifact hashes"):
            self.process()
        self.assertFalse((self.cache_root / "new").exists())

    def test_scientifically_rejected_parameters_are_not_promoted(self):
        # A second synthetic fixture has a legitimate stability rejection.
        other = self.root / "rejected_original"
        other.mkdir()
        plan, _, _ = FIXTURE.fixture(other, "rejected")
        (other / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        with patch.object(EXTRACT.SUMMARY, "load_plan", return_value=plan):
            row = EXTRACT.process_one_m(other, 80, [.001], self.cache_root / "rejected")
        self.assertEqual(row["original_gpd_status"], "rejected")
        self.assertEqual(list((self.cache_root / "rejected").glob("*.model")), [])

    def test_unplanned_m_fails_before_output(self):
        for m in (True, 80.5, 999):
            with self.subTest(m=m), self.assertRaises(ValueError):
                EXTRACT.process_one_m(self.run, m, [.001], self.cache_root / "invalid")
        self.assertFalse((self.cache_root / "invalid").exists())


if __name__ == "__main__":
    unittest.main()
