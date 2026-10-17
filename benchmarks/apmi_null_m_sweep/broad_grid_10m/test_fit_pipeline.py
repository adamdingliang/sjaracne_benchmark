"""Controller contract tests using synthetic summaries only, never raw draws."""
from argparse import Namespace
import contextlib
import io
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import fit_pipeline as pipe


def development_rows():
    return [{"method": method, "m": m, "p": p, "count": int(10_000_000 * p),
             "n": 10_000_000, "available": True}
            for method in pipe.METHODS for m in pipe.fit_models.DEVELOPMENT_M
            for p in pipe.fit_models.SELECTION_P]


class ControllerTests(unittest.TestCase):
    def test_fixed_groups(self):
        groups = pipe.groups()
        self.assertEqual([len(v) for v in groups.values()], [160, 20, 20])
        self.assertEqual(set(sum(groups.values(), [])), set(range(50, 10001, 50)))
        self.assertFalse(set(groups["training"]) & set(groups["development"]))

    def test_legacy_literal_formula(self):
        row = pipe.legacy_predictions(80, [.001])[0]
        self.assertEqual(row["cutoff"], (1.062 - math.log(.001)) / (48.7 + .634 * 80))
        self.assertEqual(float.fromhex(row["cutoff_hex"]), row["cutoff"])

    def test_full_cell_tie_quadratic(self):
        check = {m: {"eligible": True} for m in pipe.METHODS}
        result = pipe.choose(development_rows(), check)
        self.assertEqual(result["selected_method"], "quadratic")
        self.assertEqual(len(result["candidates"]), 2)

    def test_shape_failure_disqualifies_lower_loss(self):
        check = {"quadratic": {"eligible": False}, "pchip": {"eligible": True}}
        self.assertEqual(pipe.choose(development_rows(), check)["selected_method"], "pchip")

    def test_missing_cell_not_averaged(self):
        check = {m: {"eligible": True} for m in pipe.METHODS}
        rows = development_rows()[1:]
        self.assertEqual(pipe.choose(rows, check)["selected_method"], "pchip")

    def test_no_finite_winner(self):
        check = {m: {"eligible": False} for m in pipe.METHODS}
        self.assertIsNone(pipe.choose(development_rows(), check)["selected_method"])

    def test_all200_function_only_shape_checks(self):
        def predict(model, m, ps):
            return [{"m": m, "p": p, "available": not (m == 350 and p == .001)} for p in ps]
        with patch.object(pipe.fit_models, "predict_surface", side_effect=predict) as call:
            checks = pipe.shape_check({})
        self.assertEqual(call.call_count, 200)
        self.assertFalse(checks["eligible"])
        self.assertEqual(len(checks["moderate_failures"]), 1)

    def test_rare_shape_failure_does_not_poison_body(self):
        def predict(model, m, ps):
            return [{"m": m, "p": p, "available": p >= .0001} for p in ps]
        with patch.object(pipe.fit_models, "predict_surface", side_effect=predict):
            checks = pipe.shape_check({})
        self.assertTrue(checks["eligible"])
        self.assertTrue(checks["rare_failures"])

    def test_refit_extracts49_but_matrix_uses25(self):
        with patch.object(pipe.fit_data, "extract_refit") as extraction:
            pipe.worker(("refit", "plan", 50, "out", "gate"))
        self.assertEqual(extraction.call_args.args[3], pipe.GRID.ALL_P)
        cache = {50: {"quantiles": [{"p": p, "cutoff": p} for p in pipe.GRID.ALL_P]}}
        ms, matrix = pipe.matrix(cache)
        self.assertEqual(ms, [50])
        self.assertEqual(matrix.shape, (1, 25))
        self.assertEqual(matrix.tolist()[0], list(pipe.GRID.DENSE_P))

    def test_lock_detects_tampering(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lock.json"
            pipe.locked_write(path, {"x": 1})
            self.assertEqual(pipe.read_locked(path), {"x": 1})
            path.write_text('{"x":2}')
            with self.assertRaises(ValueError):
                pipe.read_locked(path)

    def test_no_second_run_of_same_request(self):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / "started.json").write_text("{}")
            with patch.object(pipe, "check_request", return_value={"output_dir": directory}):
                with self.assertRaises(FileExistsError):
                    pipe.run(Namespace(request="unused"))

    def test_pipeline_primary_passes_real_frozen_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = {"plan_sha256": "a" * 64}
            pinned = root / "code.txt"
            pinned.write_text("synthetic code only")
            selection = {"format": "apmi-two-surface-selection-v1", "stage": "selected",
                         "plan_sha256": "a" * 64, "analysis_plan_sha256": "b" * 64,
                         "selected_model": "quadratic", "eligible": True, "no_fallback": True}
            selected_record = pipe.locked_write(root / "selection.json", selection)
            ms = sorted(pipe.groups()["training"] + pipe.groups()["development"])
            model = pipe.fit_models.fit_surface(ms, np.full((180, 25), .1), "quadratic")
            primary = pipe.primary_artifact(request, "quadratic", ms, model, selected_record)
            primary_record = pipe.locked_write(root / "primary.json", primary)
            gate = {"format": pipe.fit_data.GATE_SCHEMA, "stage": "frozen", "plan_sha256": "a" * 64,
                    "analysis_plan_sha256": "b" * 64, "pins": {"test": pipe.generate.record(pinned)},
                    "selection_lock": selected_record, "primary_model": primary_record,
                    "primary_eligible": True, "no_fallback": True}
            gate_path = root / "gate.json"
            pipe.locked_write(gate_path, gate)
            self.assertEqual(pipe.fit_data._authorize(gate_path, "frozen", "a" * 64), gate)

    def test_failed_refit_never_opens_final_or_substitutes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            args = Namespace(request=root / "request.json")
            args.request.write_text("{}")
            request = {"output_dir": directory, "plan_sha256": "a" * 64,
                       "groups": {"training": [50, 100, 10000], "development": [450]}}
            pipe.locked_write(root / "access_initial.json", {"pins": {}})
            initial_cache = {m: {"quantiles": [{"p": p, "cutoff": .1} for p in pipe.GRID.ALL_P]}
                             for m in [50, 100, 10000]}
            extraction_phases = []
            def extract(request, phase, ms, gate):
                extraction_phases.append(phase)
                return []
            checks = [{"eligible": True}, {"eligible": True},
                      {"eligible": False}, {"eligible": True}]
            with contextlib.ExitStack() as stack:
                stack.enter_context(patch.object(pipe, "check_request", return_value=request))
                stack.enter_context(patch.object(pipe, "extract_phase", side_effect=extract))
                stack.enter_context(patch.object(pipe, "caches", side_effect=[initial_cache, {}, initial_cache]))
                stack.enter_context(patch.object(pipe.fit_models, "fit_surface", return_value={"synthetic": True}))
                stack.enter_context(patch.object(pipe, "shape_check", side_effect=checks))
                stack.enter_context(patch.object(pipe, "score_cache", side_effect=[[], development_rows()]))
                stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
                with self.assertRaisesRegex(ValueError, "no fallback"):
                    pipe.run(args)
            self.assertEqual(extraction_phases, ["training", "development", "refit"])
            self.assertEqual(pipe.read_locked(root / "selection.json")["selected_model"], "quadratic")
            self.assertFalse((root / "primary.json").exists())
            self.assertFalse((root / "access_final.json").exists())
            self.assertTrue((root / "failure.json").exists())


if __name__ == "__main__":
    unittest.main()
