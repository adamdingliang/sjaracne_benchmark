"""Small synthetic package tests; production evidence is never read."""
import copy
import csv
import importlib.util
import json
import math
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location("expanded_apmi_compare", Path(__file__).with_name("compare.py"))
COMPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPARE)


def write_json(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def manifest(package):
    hashes = {p.relative_to(package).as_posix(): COMPARE.sha256(p)
              for p in sorted(package.rglob("*")) if p.is_file() and p.name != "package_sha256.json"}
    write_json(package / "package_sha256.json", hashes)


def fixture(package, current=False, statuses=None):
    package.mkdir()
    draws = 10_000_000 if current else 5_000_000
    seed = 20261017 if current else 20261015
    config = {**copy.deepcopy(COMPARE.COMMON_CONFIG), "fit_draws": draws, "validation_draws": draws,
              "fit_seed": seed, "validation_seed": seed + 1}
    rows = []
    for m in COMPARE.CURRENT_M if current else COMPARE.PREVIOUS_M:
        status = (statuses or {}).get(m, "rejected" if current else "accepted")
        diagnostics = []
        if status in {"accepted", "rejected"}:
            for p, _ in COMPARE.PROBABILITIES:
                cutoff = (1 / math.sqrt(m)) * (1 if p == 1e-3 else 1.2) * (1.02 if current else 1)
                diagnostics.append({"nominal_p": p, "cutoff": cutoff,
                                    "ratio_observed_to_nominal": 1.03 if current else 0.99})
        rows.append({"m": m, "status": status, "accepted": status == "accepted", "gpd": diagnostics})
    summary = {"format": COMPARE.CURRENT_SCHEMA if current else COMPARE.PREVIOUS_SCHEMA,
               "config": config, "results": rows,
               "counts": {s: sum(r["status"] == s for r in rows) for s in COMPARE.STATUSES}}
    write_json(package / "summary.json", summary)
    (package / "log.txt").write_text("synthetic compact evidence", encoding="utf-8")
    # A source model file is retained and checked, never copied or rewritten.
    if any(r["accepted"] for r in rows):
        (package / "synthetic.model").write_text("synthetic accepted source artifact", encoding="utf-8")
    manifest(package)
    return summary


class TestDescriptiveComparison(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.previous, self.current, self.out = (self.root / name for name in ("previous", "current", "comparison"))
        self.old_summary = fixture(self.previous)
        self.new_summary = fixture(self.current, current=True)

    def rewrite_summary(self, package, summary):
        write_json(package / "summary.json", summary)
        manifest(package)

    def test_nineteen_sorted_rows_cutoffs_ratios_deltas_and_new_sizes(self):
        old_hash, new_hash = COMPARE.sha256(self.previous / "summary.json"), COMPARE.sha256(self.current / "summary.json")
        result = COMPARE.compare_packages(self.previous, self.current, self.out)
        rows = result["results"]
        self.assertEqual([r["m"] for r in rows], sorted(COMPARE.PREVIOUS_M + COMPARE.NEW_M))
        self.assertEqual(len(rows), 19)
        self.assertEqual(result["new_m"], COMPARE.NEW_M)
        self.assertEqual(len(result["common_m"]), 11)
        self.assertEqual(result["transitions"], {"accepted -> rejected": 11, "not_run -> rejected": 8})
        for row in rows:
            self.assertEqual(row["current_status"], "rejected")
            for _, suffix in COMPARE.PROBABILITIES:
                if row["m"] in COMPARE.NEW_M:
                    self.assertEqual(row["previous_status"], "not_run")
                    self.assertIsNone(row["previous_gpd_cutoff_p_" + suffix])
                    self.assertIsNone(row["previous_actual_to_nominal_p_" + suffix])
                    self.assertIsNone(row["cutoff_change_percent_p_" + suffix])
                else:
                    self.assertAlmostEqual(row["cutoff_change_percent_p_" + suffix], 2.0)
                    self.assertEqual(row["previous_actual_to_nominal_p_" + suffix], 0.99)
                self.assertEqual(row["current_actual_to_nominal_p_" + suffix], 1.03)
        with (self.out / "comparison.csv").open(newline="") as handle:
            self.assertEqual(len(list(csv.DictReader(handle))), 19)
        report = (self.out / "REPORT.md").read_text()
        self.assertEqual(sum(line.startswith("| ") and line.split("|")[1].strip().isdigit() for line in report.splitlines()), 19)
        self.assertIn("not a matched causal test", report)
        self.assertIn("No threshold refitting", report)
        self.assertIn("Rejected GPD cutoffs are diagnostic only", report)
        self.assertEqual(list(self.out.rglob("*.model")), [])
        self.assertEqual(COMPARE.sha256(self.previous / "summary.json"), old_hash)
        self.assertEqual(COMPARE.sha256(self.current / "summary.json"), new_hash)
        for name, digest in COMPARE.read_object(self.out / "package_sha256.json").items():
            self.assertEqual(COMPARE.sha256(self.out / name), digest)

    def test_failures_and_unrun_or_incomplete_are_not_scientific_rejections(self):
        previous = self.root / "previous_partial"
        current = self.root / "current_partial"
        fixture(previous, statuses={30: "failed", 50: "not_started", 80: "rejected"})
        fixture(current, current=True, statuses={30: "accepted", 50: "incomplete", 80: "failed", 200: "not_started"})
        result = COMPARE.compare_packages(previous, current, self.out)
        rows = {r["m"]: r for r in result["results"]}
        self.assertEqual((rows[30]["previous_status"], rows[30]["current_status"]), ("failed", "accepted"))
        self.assertEqual((rows[50]["previous_status"], rows[50]["current_status"]), ("not_started", "incomplete"))
        self.assertEqual((rows[80]["previous_status"], rows[80]["current_status"]), ("rejected", "failed"))
        self.assertEqual((rows[200]["previous_status"], rows[200]["current_status"]), ("not_run", "not_started"))
        for m in (30, 50, 80, 200):
            self.assertIsNone(rows[m]["cutoff_change_percent_p_1e_3"])

    def test_rejected_status_is_not_changed_by_near_nominal_rate(self):
        self.new_summary["results"][0]["gpd"][0]["ratio_observed_to_nominal"] = 1.0
        self.rewrite_summary(self.current, self.new_summary)
        result = COMPARE.compare_packages(self.previous, self.current, self.out)
        self.assertEqual(result["results"][0]["current_status"], "rejected")

    def test_finite_rejected_candidate_is_reported_without_new_scientific_gate(self):
        # Comparison preserves recorded diagnostic values; it is not another calibrator.
        self.new_summary["results"][0]["gpd"][0].update(cutoff=10.0, ratio_observed_to_nominal=0.0)
        self.rewrite_summary(self.current, self.new_summary)
        result = COMPARE.compare_packages(self.previous, self.current, self.out)
        row = result["results"][0]
        self.assertEqual(row["current_status"], "rejected")
        self.assertEqual(row["current_gpd_cutoff_p_1e_3"], 10.0)
        self.assertEqual(row["current_actual_to_nominal_p_1e_3"], 0.0)

    def test_manifest_tamper_fails_before_creating_output(self):
        (self.current / "log.txt").write_text("changed evidence")
        with self.assertRaisesRegex(ValueError, "files/hashes"):
            COMPARE.compare_packages(self.previous, self.current, self.out)
        self.assertFalse(self.out.exists())

    def test_missing_manifest_and_malformed_manifest_fail(self):
        (self.current / "package_sha256.json").unlink()
        with self.assertRaises(OSError):
            COMPARE.compare_packages(self.previous, self.current, self.out)
        write_json(self.current / "package_sha256.json", [])
        with self.assertRaisesRegex(ValueError, "expected JSON object"):
            COMPARE.compare_packages(self.previous, self.current, self.out)
        self.assertFalse(self.out.exists())

    def test_manifest_path_escape_and_extra_unlisted_files_fail(self):
        write_json(self.current / "package_sha256.json", {"../outside": "0" * 64})
        with self.assertRaisesRegex(ValueError, "manifest path"):
            COMPARE.compare_packages(self.previous, self.current, self.out)
        manifest(self.current)
        (self.current / "unlisted.txt").write_text("not in manifest")
        with self.assertRaisesRegex(ValueError, "files/hashes"):
            COMPARE.compare_packages(self.previous, self.current, self.out)

    def test_wrong_larger_draw_counts_or_stale_seeds_fail_with_valid_manifest(self):
        for key, value in (("fit_draws", 20_000_000), ("validation_draws", 5_000_000),
                           ("fit_seed", 20261015), ("validation_seed", 20261016)):
            with self.subTest(key=key):
                summary = copy.deepcopy(self.new_summary)
                summary["config"][key] = value
                self.rewrite_summary(self.current, summary)
                with self.assertRaisesRegex(ValueError, "frozen draw counts"):
                    COMPARE.compare_packages(self.previous, self.current, self.out)
                self.assertFalse(self.out.exists())

    def test_wrong_schema_or_counts_fail_with_valid_manifest(self):
        summary = copy.deepcopy(self.new_summary)
        summary["format"] = COMPARE.PREVIOUS_SCHEMA
        self.rewrite_summary(self.current, summary)
        with self.assertRaisesRegex(ValueError, "summary schema"):
            COMPARE.compare_packages(self.previous, self.current, self.out)
        summary = copy.deepcopy(self.new_summary)
        summary["counts"]["accepted"] += 1
        self.rewrite_summary(self.current, summary)
        with self.assertRaisesRegex(ValueError, "status counts"):
            COMPARE.compare_packages(self.previous, self.current, self.out)

    def test_duplicate_missing_or_unplanned_m_fails(self):
        mutations = (lambda rows: rows.append(copy.deepcopy(rows[0])),
                     lambda rows: rows.pop(),
                     lambda rows: rows[0].update(m=999))
        for mutate in mutations:
            summary = copy.deepcopy(self.new_summary)
            mutate(summary["results"])
            self.rewrite_summary(self.current, summary)
            with self.assertRaises(ValueError):
                COMPARE.compare_packages(self.previous, self.current, self.out)

    def test_inconsistent_acceptance_or_partial_completed_diagnostics_fail(self):
        summary = copy.deepcopy(self.new_summary)
        summary["results"][0]["accepted"] = True
        self.rewrite_summary(self.current, summary)
        with self.assertRaisesRegex(ValueError, "status/acceptance"):
            COMPARE.compare_packages(self.previous, self.current, self.out)
        summary = copy.deepcopy(self.new_summary)
        summary["results"][0]["gpd"].pop()
        self.rewrite_summary(self.current, summary)
        with self.assertRaisesRegex(ValueError, "availability"):
            COMPARE.compare_packages(self.previous, self.current, self.out)

    def test_zero_previous_cutoff_has_no_percent_change(self):
        self.old_summary["results"][0]["gpd"][0]["cutoff"] = 0.0
        self.rewrite_summary(self.previous, self.old_summary)
        result = COMPARE.compare_packages(self.previous, self.current, self.out)
        self.assertIsNone(result["results"][0]["cutoff_change_percent_p_1e_3"])

    def test_output_is_exclusive_and_sources_are_protected(self):
        COMPARE.compare_packages(self.previous, self.current, self.out)
        with self.assertRaisesRegex(ValueError, "fresh nonexistent"):
            COMPARE.compare_packages(self.previous, self.current, self.out)
        with self.assertRaisesRegex(ValueError, "contain each other"):
            COMPARE.compare_packages(self.previous, self.current, self.current / "nested")


if __name__ == "__main__":
    unittest.main()
