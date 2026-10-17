"""Synthetic-only tests for the final-scoring operational continuation."""
from argparse import Namespace
import contextlib
import copy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import fit_finish as finish


def quantiles(m=350):
    return {"source": {"task": {"m": m}}, "quantiles": [
        {"p": p, "cutoff": 0.1, "cutoff_hex": (0.1).hex()} for p in finish.pipeline.GRID.ALL_P]}


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.runs = self.base / "runs"
        self.runs.mkdir()
        self.source = self.runs / "analysis_zero_corrected"
        self.source.mkdir()
        self.out = Path(str(self.source) + "_final_recovery")
        self.root_patch = patch.object(finish.gen, "repo_root", return_value=self.base)
        self.root_patch.start()
        self.request = {"output_dir": str(self.source), "plan_sha256": finish.pipeline.GENERATION_HASH,
                        "generation_plan": {"path": "synthetic-plan"},
                        "groups": finish.pipeline.groups()}
        self.selection = {"selected_model": "pchip", "selected_method": "pchip", "eligible": True,
                          "no_fallback": True}
        self.models = {"quadratic": {"synthetic": "quadratic"}, "pchip": {"synthetic": "pchip"}}
        self.primary = {"selected_model": "pchip", "surface": {"fit_models": self.models["pchip"]},
                        "training_m": sorted(self.request["groups"]["training"] + self.request["groups"]["development"])}
        self.values = {name: {} for name in finish.SOURCE_LOCKS}
        self.values.update(request=self.request, selection=self.selection, primary=self.primary,
                           refit_models={"models": self.models, "shape_checks": {"pchip": {"eligible": True}}})
        for name, value in self.values.items():
            finish.pipeline.locked_write(self.source / (name + ".json"), value)
        finish.gen.write_new(self.source / "failure.json", {"error": "PermissionError(13, 'Permission denied')"})
        for name in ("internal_scores.csv", "development_scores.csv"):
            (self.source / name).write_text("synthetic,only\n1,2\n", encoding="utf-8")
        self.cache_path = self.source / "fixture_cache.json"
        finish.gen.write_new(self.cache_path, {"synthetic": True})
        records = {phase: [{"m": m, "cache": finish.gen.record(self.cache_path)}]
                   for phase, m in (("validation", 50), ("refit", 50), ("test_fit", 350))}
        self.evidence = {"source": self.source, "request": self.request, "values": self.values,
                         "validation": {50: {}}, "refit": {50: quantiles(50)}, "test_fit": {350: quantiles(350)},
                         "records": records}

    def tearDown(self):
        self.root_patch.stop()
        self.temporary.cleanup()

    def snapshot(self):
        return {str(path.relative_to(self.source)): finish.gen.sha256(path)
                for path in self.source.rglob("*") if path.is_file()}

    def freeze_synthetic(self):
        with patch.object(finish, "collect", return_value=self.evidence), contextlib.redirect_stdout(io.StringIO()):
            finish.freeze(Namespace(analysis=self.source, out=self.out))
        return self.out / "recovery_request.json"

    def test_freeze_is_before_any_array_or_scoring_access(self):
        before = self.snapshot()
        with patch.object(finish.pipeline, "score_cache", side_effect=AssertionError("counting before freeze")), \
             patch.object(finish.data, "load_array", side_effect=AssertionError("array before freeze")):
            lock = self.freeze_synthetic()
        value = finish.pipeline.read_locked(lock)
        self.assertTrue(value["only_final_scoring"])
        self.assertFalse(value["new_fitting_selection_extraction_or_draws"])
        self.assertEqual(len([key for key in value["pins"] if key.startswith("cache_")]), 3)
        self.assertIn("fit_finish.py", value["pins"])
        self.assertIn("test_fit_finish.py", value["pins"])
        self.assertIn("CORRECTION_STATUS_IO_2026-10-17.md", value["pins"])
        self.assertEqual(before, self.snapshot())

    def test_one_fixed_fresh_recovery_path(self):
        with self.assertRaises(ValueError):
            finish._fresh_out(self.runs / "another_recovery", self.source)
        self.assertEqual(finish._fresh_out(self.out, self.source), self.out)
        self.out.mkdir()
        with self.assertRaises(ValueError):
            finish._fresh_out(self.out, self.source)

    def test_run_uses_frozen_models_and_original_scorer_once(self):
        lock = self.freeze_synthetic()
        before = self.snapshot()
        calls = []
        def score(*args, **kwargs):
            self.assertTrue(lock.is_file())
            self.assertTrue((self.out / "started.json").is_file())
            self.assertEqual(args[1], self.models)
            self.assertEqual(args[2:4], ("final_validation", "pchip"))
            self.assertTrue(kwargs["legacy"])
            self.assertEqual(set(kwargs["empirical"]), {50, 350})
            calls.append("score")
            return [{"m": 50, "p": 0.05, "method": "pchip", "phase": "final_validation", "count": 1}]
        with patch.object(finish, "collect", return_value=self.evidence), \
             patch.object(finish.pipeline, "score_cache", side_effect=score), \
             patch.object(finish.pipeline.fit_report, "summarize", return_value=[]), \
             patch.object(finish.pipeline.fit_models, "fit_surface", side_effect=AssertionError("fit forbidden")), \
             patch.object(finish.pipeline.fit_models, "select_surface", side_effect=AssertionError("selection forbidden")), \
             patch.object(finish.pipeline, "extract_phase", side_effect=AssertionError("extraction forbidden")), \
             patch.object(finish.gen, "atomic_status", side_effect=AssertionError("progress replacement forbidden")), \
             contextlib.redirect_stdout(io.StringIO()):
            finish.run(Namespace(request=lock))
        self.assertEqual(calls, ["score"])
        self.assertEqual(finish.gen.read_json(self.out / "status.json")["phase"], "complete")
        self.assertEqual(finish.pipeline.read_locked(self.out / "summary.json")["primary"], self.primary)
        self.assertEqual(before, self.snapshot())
        for name in ("request.json", "selection.json", "primary.json", "refit_models.json", "access_final.json",
                     "internal_scores.csv", "development_scores.csv"):
            self.assertEqual(finish.gen.sha256(self.source / name), finish.gen.sha256(self.out / name))
        with self.assertRaises(ValueError):
            finish.run(Namespace(request=lock))

    def test_pin_tampering_rejected_before_scoring(self):
        lock = self.freeze_synthetic()
        self.cache_path.write_text('{"changed":true}', encoding="utf-8")
        with patch.object(finish.pipeline, "score_cache", side_effect=AssertionError("must stay sealed")):
            with self.assertRaises(ValueError):
                finish.run(Namespace(request=lock))
        self.assertFalse((self.out / "started.json").exists())

    def test_invalid_frozen_gate_prevents_cache_or_array_opening(self):
        with patch.object(finish.pipeline, "check_request", return_value=self.request), \
             patch.object(finish.gen, "load_plan", return_value=({}, finish.pipeline.GENERATION_HASH)), \
             patch.object(finish.data, "_authorize", side_effect=ValueError("bad frozen gate")), \
             patch.object(finish, "indexed", side_effect=AssertionError("cache before gate")), \
             patch.object(finish.data, "load_array", side_effect=AssertionError("array before gate")):
            with self.assertRaisesRegex(ValueError, "bad frozen gate"):
                finish.collect(self.source)

    def test_missing_test_cache_refused_without_extraction(self):
        with patch.object(finish.pipeline, "check_request", return_value=self.request), \
             patch.object(finish.gen, "load_plan", return_value=({}, finish.pipeline.GENERATION_HASH)), \
             patch.object(finish.data, "_authorize", return_value={"stage": "frozen"}), \
             patch.object(finish, "indexed", return_value=({}, [])), \
             patch.object(finish.pipeline, "extract_phase", side_effect=AssertionError("no reextraction")):
            with self.assertRaisesRegex(ValueError, "missing completed test-fitting cache"):
                finish.collect(self.source)

    def test_existing_source_final_statistics_forbid_recovery(self):
        for name in ("final_scores.csv", "summary.json", "summary.sha256"):
            path = self.source / name
            path.write_text("synthetic", encoding="utf-8")
            with patch.object(finish.pipeline, "check_request", side_effect=AssertionError("must reject before protocol read")):
                with self.assertRaisesRegex(ValueError, "existing final statistics"):
                    finish.collect(self.source)
            path.unlink()

    def test_failure_reason_must_be_exact_operational_kind(self):
        for error in ("ValueError('bad fit')", "PermissionError(5, 'different')", "RuntimeError('status')"):
            with patch.object(finish.gen, "read_json", return_value={"error": error}):
                with self.assertRaisesRegex(ValueError, "PermissionError13"):
                    finish._failure(self.source)

    def test_wrong_primary_identity_refused_before_indexing(self):
        wrong = copy.deepcopy(self.values)
        wrong["selection"]["selected_model"] = "quadratic"
        def read(path):
            return wrong[Path(path).stem]
        with patch.object(finish.pipeline, "check_request", return_value=self.request), \
             patch.object(finish.gen, "load_plan", return_value=({}, finish.pipeline.GENERATION_HASH)), \
             patch.object(finish.data, "_authorize", return_value={}), \
             patch.object(finish.pipeline, "read_locked", side_effect=read), \
             patch.object(finish, "indexed", side_effect=AssertionError("cannot score wrong winner")):
            with self.assertRaisesRegex(ValueError, "PCHIP primary"):
                finish.collect(self.source)

    def test_exact49_literal_quantile_policy(self):
        finish._quantiles(quantiles())
        for change in ("missing", "wrong_hex", "negative", "crossing"):
            value = quantiles()
            if change == "missing":
                value["quantiles"].pop()
            elif change == "wrong_hex":
                value["quantiles"][0]["cutoff_hex"] = (0.2).hex()
            elif change == "negative":
                value["quantiles"][0].update(cutoff=-0.1, cutoff_hex=(-0.1).hex())
            else:
                value["quantiles"][1].update(cutoff=0.09, cutoff_hex=(0.09).hex())
            with self.assertRaises(ValueError):
                finish._quantiles(value)

    def test_index_coverage_must_be_exact(self):
        with patch.object(finish.pipeline, "read_locked", return_value={"phase": "validation", "records": []}), \
             patch.object(finish, "validate_cache", side_effect=AssertionError("missing index cannot open cache")):
            with self.assertRaisesRegex(ValueError, "indexed cache sizes"):
                finish.indexed(self.source, "validation", [50], {}, "a" * 64)

    def test_cache_phase_lock_and_literal_quantiles(self):
        m, phase = 50, "refit"
        directory = self.source / "cache" / phase / "m00050"
        directory.mkdir(parents=True)
        path = directory / "cache.json"
        value = {**quantiles(m), "format": finish.data.SCHEMA, "purpose": finish.PURPOSES[phase],
                 "phase_lock": finish.gen.record(self.source / "access_selected.json"), "arrays": {}}
        finish.gen.write_new(path, value)
        with patch.object(finish, "_source"):
            self.assertEqual(finish.validate_cache(finish.gen.record(path), m, phase, self.source, {}, "a" * 64), value)
        value["phase_lock"] = finish.gen.record(self.source / "access_final.json")
        path.write_text(__import__("json").dumps(value), encoding="utf-8")
        with patch.object(finish, "_source", side_effect=AssertionError("wrong phase cannot check source")):
            with self.assertRaisesRegex(ValueError, "phase-lock"):
                finish.validate_cache(finish.gen.record(path), m, phase, self.source, {}, "a" * 64)

    def test_generation_checkpoint_lineage_without_raw_reads(self):
        generation = self.runs / "generation"
        directory = generation / "streams" / "m00050_fit"
        directory.mkdir(parents=True)
        task = {"id": "m00050_fit", "m": 50, "stream": "fit", "draws": finish.data.N_DRAWS}
        plan = {"output_dir": str(generation), "tasks": [task], "pins": {"generator": {"sha256": "a" * 64}},
                "engine_commit": "b" * 40}
        metadata = directory / "null.f64.meta"
        metadata.write_text("synthetic metadata", encoding="utf-8")
        raw = {"path": str(directory / "null.f64"), "bytes": 8 * finish.data.N_DRAWS, "sha256": "c" * 64}
        checkpoint = {"status": "complete", "returncode": 0, "task": task, "plan_sha256": "d" * 64,
                      "artifacts": {"null.f64": raw, "null.f64.meta": finish.gen.record(metadata)}}
        finish.gen.write_new(directory / "complete.json", checkpoint)
        cache = {"source": {"plan_sha256": "d" * 64, "task": task, "raw": raw,
                            "metadata": checkpoint["artifacts"]["null.f64.meta"],
                            "checkpoint": finish.gen.record(directory / "complete.json"),
                            "generator_sha256": "a" * 64, "engine_commit": "b" * 40,
                            "normalization": {"policy": finish.data.NORMALIZATION_POLICY,
                                              "tolerance": finish.data.SUPPORT_TOLERANCE, "negative_count": 0,
                                              "normalized_to_positive_zero_count": 0, "raw_minimum": 0.0}}}
        with patch.object(finish.data, "load_array", side_effect=AssertionError("raw/statistical read forbidden")):
            finish._source(cache, plan, "d" * 64, 50, "fit")
        self.assertFalse((directory / "null.f64").exists())
        cache["source"]["raw"] = {**raw, "sha256": "e" * 64}
        with self.assertRaisesRegex(ValueError, "lineage"):
            finish._source(cache, plan, "d" * 64, 50, "fit")

    def test_failed_scoring_preserves_one_shot_no_retry(self):
        lock = self.freeze_synthetic()
        with patch.object(finish, "collect", return_value=self.evidence), \
             patch.object(finish.pipeline, "score_cache", side_effect=RuntimeError("synthetic scoring failure")), \
             contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaisesRegex(RuntimeError, "synthetic"):
                finish.run(Namespace(request=lock))
        self.assertTrue((self.out / "failure.json").exists())
        self.assertFalse((self.out / "status.json").exists())
        with self.assertRaisesRegex(ValueError, "one-shot"):
            finish.run(Namespace(request=lock))


if __name__ == "__main__":
    unittest.main()
