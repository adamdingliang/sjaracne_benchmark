"""Synthetic-only tests: never open a scientific generation stream."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

import fit_data as data


def write_json(path, value):
    Path(path).write_text(json.dumps(value), encoding="utf-8")
    return data.generate.record(path)


class SyntheticStreams(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / "runs").mkdir()
        self.generation = self.root / "runs" / "generation"
        self.generation.mkdir()
        self.plan_path = self.generation / "plan.json"
        self.plan_path.write_text("{}", encoding="utf-8")
        self.plan_hash = "a" * 64
        self.analysis_hash = "b" * 64
        self.values = np.array([0, .1, .2, .3, .4, .5, .6, .7, .95, .8], dtype="<f8")
        self.raw = self.generation / "raw.f64"
        self.values.tofile(self.raw)
        self.meta = self.generation / "raw.f64.meta"
        self.meta.write_text("synthetic=true", encoding="utf-8")
        self.checkpoint = self.generation / "complete.json"
        self.checkpoint.write_text("{}", encoding="utf-8")
        tasks = [{"id": f"m{m:05d}_{stream}", "m": m, "stream": stream, "draws": 10,
                  "seed": m + (1 if stream == "fit" else 2), "m_group": data.m_group(m)}
                 for m in (50, 350, 450) for stream in ("fit", "validation")]
        self.plan = {"output_dir": str(self.generation), "tasks": tasks,
                     "pins": {"generator": {"sha256": "c" * 64}}, "engine_commit": "d" * 40}
        self.identity = {"plan_sha256": self.plan_hash, "task": tasks[0],
                         "raw": data.generate.record(self.raw), "metadata": data.generate.record(self.meta),
                         "checkpoint": data.generate.record(self.checkpoint),
                         "generator_sha256": "c" * 64, "engine_commit": "d" * 40}
        self.code = self.root / "pinned-code.py"
        self.code.write_text("# synthetic immutable code", encoding="utf-8")
        self.pins = {"code": data.generate.record(self.code)}
        self.patches = [patch.object(data, "N_DRAWS", 10),
                        patch.object(data, "N_CONSTRUCTION", 8),
                        patch.object(data.generate, "repo_root", return_value=self.root),
                        patch.object(data.generate, "load_plan", return_value=(self.plan, self.plan_hash)),
                        patch.object(data, "_identity", side_effect=self.fake_identity)]
        for mocked in self.patches:
            mocked.start()
            self.addCleanup(mocked.stop)
        self.initial = self.gate("analysis_frozen")
        self.selection_path = self.root / "selection.json"
        self.selection = {"format": "apmi-two-surface-selection-v1", "stage": "selected",
                          "plan_sha256": self.plan_hash, "analysis_plan_sha256": self.analysis_hash,
                          "selected_model": "pchip", "eligible": True, "no_fallback": True}
        write_json(self.selection_path, self.selection)
        self.selected = self.gate("selected", selection_lock=data.generate.record(self.selection_path))
        self.primary_path = self.root / "primary.json"
        self.primary = {"format": "apmi-two-surface-frozen-primary-v1", "selected_model": "pchip",
                        "generation_plan_sha256": self.plan_hash,
                        "training_m": [m for m in data.generate.GRID
                                       if data.m_group(m) != "final_interpolation_test"],
                        "selection_sha256": data.generate.sha256(self.selection_path),
                        "surface": {"fit_models": {"synthetic": {"coefficient": 1}}}}
        write_json(self.primary_path, self.primary)
        self.frozen = self.gate("frozen", selection_lock=data.generate.record(self.selection_path),
                                primary_model=data.generate.record(self.primary_path),
                                primary_eligible=True, no_fallback=True)

    def fake_identity(self, plan_path, m, stream):
        identity = copy.deepcopy(self.identity)
        identity["task"] = data._find_task(self.plan, m, stream)
        return self.plan, identity

    def gate(self, stage, **extra):
        path = self.root / (stage + ".json")
        value = {"format": data.GATE_SCHEMA, "stage": stage, "plan_sha256": self.plan_hash,
                 "analysis_plan_sha256": self.analysis_hash, "pins": self.pins, **extra}
        write_json(path, value)
        path.with_suffix(".sha256").write_text(data.generate.sha256(path), encoding="ascii")
        return path

    def change_gate(self, path, **updates):
        value = json.loads(path.read_text(encoding="utf-8"))
        value.update(updates)
        write_json(path, value)
        path.with_suffix(".sha256").write_text(data.generate.sha256(path), encoding="ascii")

    def out(self, name="cache"):
        return self.root / "runs" / "analysis" / name

    def test_training_split_quantiles_and_no_construction_copy(self):
        result = data.extract_training(self.plan_path, 50, self.out(), [.5, .25], self.initial)
        self.assertEqual(list(result["arrays"]), ["internal"])
        np.testing.assert_array_equal(data.load_array(result, "internal"), [.8, .95])
        self.assertEqual([q["cutoff"] for q in result["quantiles"]], [.4, .6])
        self.assertEqual(result["quantiles"][0]["cutoff_hex"], float(.4).hex())
        np.testing.assert_array_equal(np.fromfile(self.raw), self.values)
        self.assertFalse((self.out() / "construction.npy").exists())

    def test_training_rejects_development_before_raw_access(self):
        with patch.object(data, "_identity") as raw_access:
            with self.assertRaises(ValueError):
                data.extract_training(self.plan_path, 450, self.out(), [.1], self.initial)
            raw_access.assert_not_called()

    def test_training_rejects_final_test_before_raw_access(self):
        with patch.object(data, "_identity") as raw_access:
            with self.assertRaises(ValueError):
                data.extract_training(self.plan_path, 350, self.out(), [.1], self.initial)
            raw_access.assert_not_called()

    def test_wrong_phase_cannot_read_raw(self):
        with patch.object(data, "_identity") as raw_access:
            with self.assertRaises(ValueError):
                data.extract_final_validation(self.plan_path, 50, self.out(), self.initial)
            raw_access.assert_not_called()

    def test_wrong_plan_gate_cannot_read_raw(self):
        self.change_gate(self.initial, plan_sha256="e" * 64)
        with patch.object(data, "_identity") as raw_access:
            with self.assertRaises(ValueError):
                data.extract_training(self.plan_path, 50, self.out(), [.1], self.initial)
            raw_access.assert_not_called()

    def test_code_pin_change_cannot_read_raw(self):
        self.code.write_text("changed", encoding="utf-8")
        with patch.object(data, "_identity") as raw_access:
            with self.assertRaises(ValueError):
                data.extract_training(self.plan_path, 50, self.out(), [.1], self.initial)
            raw_access.assert_not_called()

    def test_gate_hash_tamper_cannot_read_raw(self):
        self.initial.write_text("{}", encoding="utf-8")
        with patch.object(data, "_identity") as raw_access:
            with self.assertRaises(ValueError):
                data.extract_training(self.plan_path, 50, self.out(), [.1], self.initial)
            raw_access.assert_not_called()

    def test_development_score_only(self):
        result = data.extract_development(self.plan_path, 450, self.out(), self.initial)
        self.assertEqual(result["quantiles"], [])
        np.testing.assert_array_equal(data.load_array(result, "score"), np.sort(self.values))

    def test_refit_requires_selection_and_excludes_test(self):
        result = data.extract_refit(self.plan_path, 450, self.out(), [.1], self.selected)
        self.assertEqual(result["arrays"], {})
        self.assertEqual(result["quantiles"][0]["cutoff"], .95)
        with patch.object(data, "_identity") as raw_access:
            with self.assertRaises(ValueError):
                data.extract_refit(self.plan_path, 350, self.out("other"), [.1], self.selected)
            raw_access.assert_not_called()

    def test_ineligible_selection_blocks_refit(self):
        self.selection["eligible"] = False
        write_json(self.selection_path, self.selection)
        self.change_gate(self.selected, selection_lock=data.generate.record(self.selection_path))
        with self.assertRaises(ValueError):
            data.extract_refit(self.plan_path, 50, self.out(), [.1], self.selected)

    def test_selected_model_name_is_fixed(self):
        self.selection["selected_model"] = "posthoc"
        write_json(self.selection_path, self.selection)
        self.change_gate(self.selected, selection_lock=data.generate.record(self.selection_path))
        with self.assertRaises(ValueError):
            data.extract_refit(self.plan_path, 50, self.out(), [.1], self.selected)

    def test_final_validation_requires_consistent_frozen_primary(self):
        result = data.extract_final_validation(self.plan_path, 350, self.out(), self.frozen)
        self.assertEqual(result["source"]["task"]["stream"], "validation")
        np.testing.assert_array_equal(data.load_array(result, "score"), np.sort(self.values))

    def test_final_test_fit_returns_diagnostic_quantiles_only(self):
        result = data.extract_final_test_fit(self.plan_path, 350, self.out(), [.1], self.frozen)
        self.assertEqual(result["arrays"], {})
        self.assertEqual(result["quantiles"][0]["cutoff"], .95)
        with self.assertRaises(ValueError):
            data.extract_final_test_fit(self.plan_path, 50, self.out("other"), [.1], self.frozen)

    def test_frozen_no_fallback_is_required(self):
        self.change_gate(self.frozen, no_fallback=False)
        with self.assertRaises(ValueError):
            data.extract_final_validation(self.plan_path, 50, self.out(), self.frozen)

    def test_frozen_model_mismatch_is_rejected(self):
        self.primary["selected_model"] = "quadratic"
        write_json(self.primary_path, self.primary)
        self.change_gate(self.frozen, primary_model=data.generate.record(self.primary_path))
        with patch.object(data, "_identity") as raw_access:
            with self.assertRaises(ValueError):
                data.extract_final_validation(self.plan_path, 50, self.out(), self.frozen)
            raw_access.assert_not_called()

    def test_frozen_refit_m_list_must_be_exact(self):
        self.primary["training_m"][-1] = 350
        write_json(self.primary_path, self.primary)
        self.change_gate(self.frozen, primary_model=data.generate.record(self.primary_path))
        with self.assertRaises(ValueError):
            data.extract_final_validation(self.plan_path, 50, self.out(), self.frozen)

    def test_frozen_selection_hash_mismatch_is_rejected(self):
        self.primary["selection_sha256"] = "e" * 64
        write_json(self.primary_path, self.primary)
        self.change_gate(self.frozen, primary_model=data.generate.record(self.primary_path))
        with self.assertRaises(ValueError):
            data.extract_final_validation(self.plan_path, 50, self.out(), self.frozen)

    def test_frozen_primary_must_pin_nonempty_fit_models(self):
        self.primary["surface"]["fit_models"] = {}
        write_json(self.primary_path, self.primary)
        self.change_gate(self.frozen, primary_model=data.generate.record(self.primary_path))
        with self.assertRaises(ValueError):
            data.extract_final_validation(self.plan_path, 50, self.out(), self.frozen)

    def test_cache_cannot_overwrite(self):
        data.extract_training(self.plan_path, 50, self.out(), [.1], self.initial)
        with self.assertRaises(ValueError):
            data.extract_training(self.plan_path, 50, self.out(), [.1], self.initial)

    def test_cache_cannot_write_generation_or_outside_runs(self):
        for output in (self.generation / "bad", self.root / "bad", self.root / "runs"):
            with self.subTest(output=output), self.assertRaises(ValueError):
                data.extract_training(self.plan_path, 50, output, [.1], self.initial)

    def test_cache_payload_tamper_detected(self):
        result = data.extract_training(self.plan_path, 50, self.out(), [.1], self.initial)
        Path(result["arrays"]["internal"]["artifact"]["path"]).write_bytes(b"changed")
        with self.assertRaises(ValueError):
            data.load_array(result, "internal")

    def test_statistically_loaded_bytes_must_match_checkpoint(self):
        self.raw.write_bytes(np.array([.2] * 10, dtype="<f8").tobytes())
        with self.assertRaises(ValueError):
            data.extract_training(self.plan_path, 50, self.out(), [.1], self.initial)

    def test_caches_open_read_only(self):
        result = data.extract_training(self.plan_path, 50, self.out(), [.1], self.initial)
        values = data.load_array(result, "internal")
        self.assertFalse(values.flags.writeable)
        with self.assertRaises(ValueError):
            values[0] = 0
        with self.assertRaises(ValueError):
            data.load_array(result, "internal", mmap_mode="r+")

    def test_invalid_p_is_rejected(self):
        for probabilities in ([0], [1], [np.nan], [.1, .1], []):
            with self.subTest(p=probabilities), self.assertRaises(ValueError):
                data.extract_training(self.plan_path, 50, self.out(), probabilities, self.initial)

    def test_invalid_m_and_stream_identity(self):
        for m in (True, 0, 1, 51, 10001, 50.0):
            with self.subTest(m=m), self.assertRaises(ValueError):
                data.m_group(m)
        with self.assertRaises(ValueError):
            data._find_task(self.plan, 50, "other")
        self.plan["tasks"][0]["draws"] = 11
        with self.assertRaises(ValueError):
            data._find_task(self.plan, 50, "fit")

    def test_identity_uses_frozen_generation_integrity_verifier(self):
        # Bypass only the _identity fixture patch for this isolated call.
        original = self.patches[-1]
        original.stop()
        self.addCleanup(original.start)
        expected_artifacts = {"null.f64": data.generate.record(self.raw),
                              "null.f64.meta": data.generate.record(self.meta)}
        with patch.object(data.generate, "verify_complete", return_value={"artifacts": expected_artifacts}) as verifier:
            task = data._find_task(self.plan, 50, "fit")
            directory = self.generation / "streams" / task["id"]
            directory.mkdir(parents=True)
            (directory / "complete.json").write_text("{}", encoding="utf-8")
            identity = data.verify_stream(self.plan_path, 50, "fit")
            self.assertEqual(identity["raw"], expected_artifacts["null.f64"])
            verifier.assert_called_once_with(self.plan, self.plan_hash, task, directory)


class CountPolicy(unittest.TestCase):
    def test_exact_ties_and_adjacent_float_counts(self):
        t = .3
        values = np.array([0, np.nextafter(t, -np.inf), t, t, np.nextafter(t, np.inf), 1], dtype=float)
        result = data.count_sorted(values, t)
        self.assertEqual((result["ge"], result["gt"], result["ties"]), (4, 2, 2))
        self.assertEqual((result["minus_ulp_ge"], result["plus_ulp_ge"]), (5, 2))
        self.assertEqual(result["threshold_hex"], t.hex())

    def test_zero_count_and_uniques_are_literal(self):
        values = np.array([0, 0, .1, .1, .2], dtype=float)
        self.assertEqual(data.sorted_summary(values),
                         {"draws": 5, "zero_count": 2, "unique_count": 3, "minimum": 0., "maximum": .2})
        self.assertEqual(data.count_sorted(values, 0)["ge"], 5)
        self.assertEqual(data.count_sorted(values, 0)["gt"], 3)

    def test_unsorted_nonfinite_or_empty_cache_rejected(self):
        for values in ([2., 1.], [np.nan], []):
            with self.subTest(values=values), self.assertRaises(ValueError):
                data.sorted_summary(np.array(values, dtype=float))

    def test_threshold_must_be_finite_not_bool(self):
        for threshold in (True, np.nan, np.inf, -np.inf):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                data.count_sorted(np.array([0., 1.]), threshold)


if __name__ == "__main__":
    unittest.main()
