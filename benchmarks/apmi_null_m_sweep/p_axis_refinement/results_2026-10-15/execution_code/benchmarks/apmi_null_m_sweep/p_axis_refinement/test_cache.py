"""Synthetic-only tests: never open scientific streams or generate MI draws."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np


_SPEC = importlib.util.spec_from_file_location("p_refinement_cache_test", Path(__file__).with_name("cache.py"))
CACHE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(CACHE)


class TestFrozenCache(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve() / "runs"
        self.run = self.root / "original"
        self.attempt = self.run / "jobs" / "m00080" / "attempt_0001"
        self.raw_dir = self.attempt / "calibration" / "raw"
        self.raw_dir.mkdir(parents=True)
        self.cache_dir = self.root / "cached" / "m00080"
        self.cache_dir.mkdir(parents=True)
        self.draws = 8
        self.fit = np.array([0., .1, .1, .2, .3, .3, .3, .5], dtype="<f8")
        self.validation = np.array([0., .05, .1, .2, .3, .3, .4, .6], dtype="<f8")
        config = dict(CACHE.SUMMARY.EXPECTED_CONFIG,
                      fit_draws=self.draws, validation_draws=self.draws)
        plan = {"format": CACHE.SUMMARY.PLAN_SCHEMA, "stages": CACHE.SUMMARY.STAGES,
                "m": CACHE.SUMMARY.GRID, "config": config,
                "stability_quantiles": [.9925, .995, .9975],
                "generator_sha256": "a" * 64, "calibrator_sha256": "b" * 64}
        self._write_json(self.run / "plan.json", plan)
        artifacts, provenance, caches, model = {}, {}, {}, {}
        for role, values in (("fit", self.fit), ("validation", self.validation)):
            raw = self.raw_dir / ("m00080_npar040_%s.f64" % role)
            values[::-1].tofile(raw)
            seed = config[role + "_seed"] + 80 + (1_000_000_000 if role == "validation" else 0)
            metadata = {"format": "sjaracne-apmi-null-binary-v1", "kernel_schema": "sjaracne-apmi-v1",
                "estimator": "sjaracne-adaptive-partitioning", "rng": "mt19937-rejection-fisher-yates-v1",
                "m": "80", "draws": str(self.draws), "npar_limit": "40", "seed": str(seed),
                "dtype": "float64", "byte_order": "little", "record_bytes": "8"}
            Path(str(raw) + ".meta").write_text("\n".join(k + "=" + v for k, v in metadata.items()), encoding="utf-8")
            self._write_json(Path(str(raw) + ".provenance.json"),
                             {"format": "sjaracne-apmi-null-raw-provenance-v1", "generator_sha256": "a" * 64})
            for path in (raw, Path(str(raw) + ".meta"), Path(str(raw) + ".provenance.json")):
                artifacts[path.relative_to(self.attempt).as_posix()] = CACHE.SUMMARY.sha256(path)
            digest = CACHE.SUMMARY.sha256(raw)
            provenance[role] = {"sha256": digest, "draws": self.draws, "seed": seed,
                                "bytes": self.draws * 8, "metadata": metadata}
            model[role + "_values_sha256"] = digest
            path = self.cache_dir / (role + "_sorted.npy")
            np.save(path, values, allow_pickle=False)
            caches[role] = {"path": str(path), "sha256": CACHE.SUMMARY.sha256(path),
                "draws": self.draws, "bytes": path.stat().st_size, "dtype": "<f8",
                "minimum": float(values[0]), "maximum": float(values[-1]),
                "sort": "ascending independent copy"}
        primary = {"threshold": .1, "shape": -.1, "scale": .2}
        self._write_json(self.attempt / "result.json", {"m": 80, "status": "rejected", "artifacts_sha256": artifacts})
        self._write_json(self.attempt / "calibration" / "calibration_report.json",
                         {"results": [{"m": 80, "primary_fit": primary, "model": model}]})
        source = {"run": str(self.run), "attempt": "jobs/m00080/attempt_0001",
                  "plan_sha256": CACHE.SUMMARY.sha256(self.run / "plan.json"),
                  "result_sha256": CACHE.SUMMARY.sha256(self.attempt / "result.json"),
                  "report_sha256": CACHE.SUMMARY.sha256(self.attempt / "calibration" / "calibration_report.json"),
                  "artifact_sha256": artifacts, "generator_sha256": "a" * 64,
                  "calibrator_sha256": "b" * 64}
        self.item = {"format": CACHE.EXTRACT.SCHEMA, "m": 80, "stage": "anchors", "npar": 40,
                     "original_gpd_status": "rejected", "primary_fit": primary,
                     "source": source, "raw_provenance": provenance,
                     "sorted_cache": caches, "exceedance_rule": "APMI >= cutoff"}

    @staticmethod
    def _write_json(path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def verify(self, item=None, probabilities=(.5, .25, .01)):
        return CACHE._verify_cache_one(self.item if item is None else item, probabilities,
                                        expected_draws=self.draws, runs_root=self.root)

    def snapshot(self):
        return {str(p): CACHE.SUMMARY.sha256(p) for p in self.root.rglob("*") if p.is_file()}

    def rewrite_cache(self, values, *, role="fit", trailing=b""):
        record = self.item["sorted_cache"][role]
        path = Path(record["path"])
        np.save(path, values, allow_pickle=False)
        if trailing:
            with path.open("ab") as handle:
                handle.write(trailing)
        record["sha256"] = CACHE.SUMMARY.sha256(path)
        record["bytes"] = path.stat().st_size

    def test_fit_quantiles_counts_ties_and_json_safe_read_only_result(self):
        before = self.snapshot()
        original = deepcopy(self.item)
        result = self.verify()
        self.assertEqual(before, self.snapshot())
        self.assertEqual(original, self.item)
        self.assertEqual(result["original_gpd_status"], "rejected")
        self.assertEqual(result["sorted_cache"], self.item["sorted_cache"])
        self.assertEqual(result["source"], self.item["source"])
        self.assertGreaterEqual(result["elapsed_seconds"], 0)
        json.dumps(result, allow_nan=False)
        for row in result["quantiles"]:
            cutoff = float(np.quantile(self.fit, 1 - row["nominal_p"], method="higher"))
            self.assertEqual(row["cutoff"], cutoff)
            self.assertEqual(row["fit_ge"], np.count_nonzero(self.fit >= cutoff))
            self.assertEqual(row["fit_gt"], np.count_nonzero(self.fit > cutoff))
            self.assertEqual(row["fit_ties"], np.count_nonzero(self.fit == cutoff))
        self.assertEqual(result["quantiles"][0]["fit_ties"], 3)

    def test_public_entry_point_does_not_accept_synthetic_draw_counts(self):
        with patch.object(CACHE, "RUNS_ROOT", self.root), self.assertRaises(ValueError):
            CACHE.verify_cache_one(self.item, [.001])

    def test_invalid_m_status_stage_npar_and_rule(self):
        for key, value in (("m", True), ("m", 80.), ("m", 999), ("stage", "dream"),
                           ("original_gpd_status", "pending"), ("npar", 1),
                           ("exceedance_rule", "APMI > cutoff"), ("format", "other")):
            item = deepcopy(self.item)
            item[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.verify(item)

    def test_invalid_probabilities(self):
        for probabilities in ([], [True], [0], [1], [.1, .1], [float("nan")]):
            with self.subTest(probabilities=probabilities), self.assertRaises(ValueError):
                self.verify(probabilities=probabilities)

    def test_cache_sha_tampering(self):
        path = Path(self.item["sorted_cache"]["fit"]["path"])
        with path.open("r+b") as handle:
            handle.seek(-1, 2)
            handle.write(b"x")
        with self.assertRaisesRegex(ValueError, "SHA256"):
            self.verify()

    def test_raw_sha_tampering(self):
        raw = self.raw_dir / "m00080_npar040_fit.f64"
        raw.write_bytes(b"x" * (self.draws * 8))
        with self.assertRaisesRegex(ValueError, "SHA256"):
            self.verify()

    def test_metadata_type_and_draw_count_tampering(self):
        for key, value in (("dtype", ">f8"), ("draws", 10_000_000), ("bytes", 8),
                           ("sort", "descending"), ("minimum", -1.), ("maximum", 999.)):
            item = deepcopy(self.item)
            item["sorted_cache"]["fit"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.verify(item)

    def test_actual_wrong_dtype(self):
        self.rewrite_cache(self.fit.astype("<f4"))
        with self.assertRaisesRegex(ValueError, "float64"):
            self.verify()

    def test_actual_wrong_shape(self):
        self.rewrite_cache(self.fit.reshape((2, 4)))
        with self.assertRaisesRegex(ValueError, "one-dimensional"):
            self.verify()

    def test_actual_wrong_length(self):
        self.rewrite_cache(self.fit[:-1])
        with self.assertRaisesRegex(ValueError, "one-dimensional"):
            self.verify()

    def test_trailing_payload_rejected(self):
        self.rewrite_cache(self.fit, trailing=b"extra")
        with self.assertRaisesRegex(ValueError, "byte length"):
            self.verify()

    def test_nonfinite_and_out_of_support_values(self):
        for value in (float("nan"), float("inf"), -1., 100.):
            values = self.fit.copy()
            values[4] = value
            self.rewrite_cache(values)
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "finite AP-MI support"):
                self.verify()

    def test_unsorted_rejected_in_chunk_and_across_chunk_boundary(self):
        values = self.fit.copy()
        values[2], values[3] = values[3], values[2]
        self.rewrite_cache(values)
        path = Path(self.item["sorted_cache"]["fit"]["path"])
        for chunk_size in (2, 8):
            with self.subTest(chunk_size=chunk_size), self.assertRaisesRegex(ValueError, "not ascending"):
                CACHE._verified_sorted(path, self.item["sorted_cache"]["fit"], 80, self.draws, chunk_size)

    def test_source_identity_and_primary_fit_tampering(self):
        for kind in ("plan", "result", "report", "generator", "primary"):
            item = deepcopy(self.item)
            if kind == "primary":
                item["primary_fit"]["shape"] = 100.
            else:
                item["source"][kind + "_sha256"] = "f" * 64
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.verify(item)

    def test_recorded_frozen_helper_hash_tampering(self):
        for key in ("extractor_sha256", "verification_helper_sha256"):
            item = deepcopy(self.item)
            item["source"][key] = "f" * 64
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "SHA256"):
                self.verify(item)

    def test_raw_metadata_design_checked_after_consistent_hashes(self):
        sidecar = self.raw_dir / "m00080_npar040_fit.f64.meta"
        sidecar.write_text(sidecar.read_text(encoding="utf-8").replace("npar_limit=40", "npar_limit=41"), encoding="utf-8")
        digest = CACHE.SUMMARY.sha256(sidecar)
        relative = sidecar.relative_to(self.attempt).as_posix()
        self.item["source"]["artifact_sha256"][relative] = digest
        record_path = self.attempt / "result.json"
        record = CACHE.SUMMARY.read_json(record_path)
        record["artifacts_sha256"][relative] = digest
        self._write_json(record_path, record)
        self.item["source"]["result_sha256"] = CACHE.SUMMARY.sha256(record_path)
        with self.assertRaisesRegex(ValueError, "raw metadata"):
            self.verify()

    def test_validation_cache_is_independently_checked(self):
        self.rewrite_cache(self.validation[::-1], role="validation")
        with self.assertRaisesRegex(ValueError, "not ascending"):
            self.verify()

    def test_cache_outside_runs_rejected_even_if_existing(self):
        outside = Path(self.temporary.name) / "m00080"
        outside.mkdir()
        path = outside / "fit_sorted.npy"
        np.save(path, self.fit)
        self.item["sorted_cache"]["fit"]["path"] = str(path)
        with self.assertRaisesRegex(ValueError, "inside repository ignored runs"):
            self.verify()

    def test_relative_and_traversal_source_paths_rejected(self):
        for value in ("relative/run", str(self.run / ".." / "original")):
            item = deepcopy(self.item)
            item["source"]["run"] = value
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "absolute without traversal"):
                self.verify(item)

    def test_wrong_attempt_and_role_paths(self):
        item = deepcopy(self.item)
        item["source"]["attempt"] = "jobs/m00080/attempt_0002"
        with self.assertRaisesRegex(ValueError, "attempt_0001"):
            self.verify(item)
        item = deepcopy(self.item)
        item["sorted_cache"]["fit"]["path"] = item["sorted_cache"]["validation"]["path"]
        with self.assertRaisesRegex(ValueError, "m and role"):
            self.verify(item)

    def test_retry_cannot_be_silently_selected(self):
        (self.attempt.parent / "attempt_0002").mkdir()
        with self.assertRaisesRegex(ValueError, "not a retry"):
            self.verify()

    def test_symlink_component_rejected(self):
        linked = self.root / "linked"
        try:
            linked.symlink_to(self.run, target_is_directory=True)
        except OSError:
            # Windows often denies real symlink creation; exercise fail-closed
            # handling directly instead of silently skipping coverage.
            with patch.object(Path, "is_symlink", return_value=True), self.assertRaisesRegex(ValueError, "symlink"):
                CACHE._safe_existing(self.run, self.root)
            return
        item = deepcopy(self.item)
        item["source"]["run"] = str(linked)
        with self.assertRaisesRegex(ValueError, "symlink"):
            self.verify(item)


if __name__ == "__main__":
    unittest.main()
