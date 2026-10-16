"""Synthetic tests only: no native generator or scientific stream is launched."""
from __future__ import annotations

from array import array
import argparse
import importlib.util
import json
import math
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

SPEC = importlib.util.spec_from_file_location("broad_generate", Path(__file__).with_name("generate.py"))
gen = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gen)


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def write_raw(self, values=(0.0, 0.1, 0.2), m=50):
        task = {"id": "fixture", "m": m, "seed": 123, "draws": len(values), "stream": "fit"}
        raw = self.root / "fixture.f64"
        numbers = array("d", values)
        if gen.sys.byteorder != "little":
            numbers.byteswap()
        raw.write_bytes(numbers.tobytes())
        metadata = {"format": "sjaracne-apmi-null-binary-v1", "kernel_schema": "sjaracne-apmi-v1",
                    "estimator": "sjaracne-adaptive-partitioning", "rng": "mt19937-rejection-fisher-yates-v1",
                    "m": str(m), "draws": str(len(values)), "npar_limit": "40", "seed": "123",
                    "dtype": "float64", "byte_order": "little", "record_bytes": "8"}
        Path(str(raw) + ".meta").write_text("\n".join(k + "=" + v for k, v in metadata.items()) + "\n")
        return raw, task

    def small_plan(self, count=2):
        (self.root / "streams").mkdir()
        (self.root / "invocations").mkdir()
        tasks = [{"id": "task%03d" % n, "m": 50, "stream": "fit", "seed": 100 + n, "draws": 2,
                  "command": ["never-executed"]} for n in range(count)]
        plan = {"output_dir": str(self.root), "tasks": tasks, "engine_root": str(self.root),
                "engine_commit": gen.EXPECTED_ENGINE, "pins": {"generator": {"sha256": gen.EXPECTED_GENERATOR}},
                "execution": {"distro": ""}}
        return plan

    def test_grid_roles_counts_order_and_seeds(self):
        tasks = gen.task_list()
        self.assertEqual(len(tasks), 400)
        self.assertEqual(tasks[0]["m"], 10000)
        self.assertEqual(tasks[-1]["m"], 50)
        self.assertEqual(len({t["seed"] for t in tasks}), 400)
        self.assertEqual(sum(t["m_group"] == "training" for t in tasks), 320)
        self.assertEqual(sum(t["m_group"] == "development" for t in tasks), 40)
        self.assertEqual(sum(t["m_group"] == "final_interpolation_test" for t in tasks), 40)
        self.assertEqual(tasks[-2]["seed"], 20261019 + 50)
        self.assertEqual(tasks[-1]["seed"], 20261020 + 1_000_000_000 + 50)

    def test_seed_overlap_rejected(self):
        task = gen.task_list()[0]
        old = {"m": [task["m"]], "config": {"fit_seed": gen.CONFIG["fit_seed"], "validation_seed": 1}}
        with self.assertRaisesRegex(ValueError, "overlap"):
            gen.verify_seeds([task], [old])

    def test_published_seeds_disjoint(self):
        check = gen.verify_seeds(gen.task_list(), [gen.read_json(path) for path in gen.prior_plan_paths()])
        self.assertEqual(check["new_unique_seeds"], 400)
        self.assertEqual(check["overlap"], 0)

    def test_worker_limits(self):
        for value in (1, 12):
            gen.validate_workers(value)
        for value in (0, 13, True, 1.5, "12"):
            with self.assertRaises(ValueError):
                gen.validate_workers(value)

    def test_cli_defaults_twelve(self):
        with patch.object(gen, "run_generation", return_value={"status": "selected_complete"}) as run:
            self.assertEqual(gen.main(["run", "--plan", str(self.root / "plan.json")]), 0)
            self.assertEqual(run.call_args.args[1], 12)

    def test_raw_integrity_good(self):
        raw, task = self.write_raw()
        self.assertEqual(gen.verify_raw(raw, task)["m"], "50")

    def test_raw_bad_length(self):
        raw, task = self.write_raw()
        raw.write_bytes(raw.read_bytes()[:-1])
        with self.assertRaisesRegex(ValueError, "length"):
            gen.verify_raw(raw, task)

    def test_raw_nonfinite_negative_or_outside_support(self):
        for value in (float("nan"), float("inf"), -1.0, math.log(50) + 0.01):
            raw, task = self.write_raw((value,))
            with self.assertRaisesRegex(ValueError, "support"):
                gen.verify_raw(raw, task)

    def test_raw_duplicate_metadata(self):
        raw, task = self.write_raw()
        metadata = Path(str(raw) + ".meta")
        metadata.write_text(metadata.read_text() + "m=50\n")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            gen.verify_raw(raw, task)

    def test_raw_wrong_seed(self):
        raw, task = self.write_raw()
        task["seed"] += 1
        with self.assertRaisesRegex(ValueError, "metadata"):
            gen.verify_raw(raw, task)

    def test_lock_is_exclusive(self):
        with gen.output_lock(self.root):
            with self.assertRaisesRegex(ValueError, "another controller"):
                with gen.output_lock(self.root):
                    pass
        with gen.output_lock(self.root):
            pass

    def test_exclusive_evidence_creation(self):
        path = self.root / "evidence.json"
        gen.write_new(path, {"value": 1})
        with self.assertRaises(FileExistsError):
            gen.write_new(path, {"value": 2})
        self.assertEqual(gen.read_json(path), {"value": 1})

    def test_atomic_status_replaces_only_status(self):
        path = self.root / "status.json"
        gen.atomic_status(path, {"value": 1})
        gen.atomic_status(path, {"value": 2})
        self.assertEqual(gen.read_json(path), {"value": 2})
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_command_is_argv_env_threads_and_pinned_stream(self):
        task = gen.task_list()[-2]
        plan = {"execution": {"distro": "Ubuntu"}, "generator_native": "/mnt/d/frozen/generator"}
        command = gen.command_for(plan, task, Path("D:/GitHub/runs/task"))
        self.assertEqual(command[:5], ["wsl.exe", "--distribution", "Ubuntu", "--exec", "/usr/bin/env"])
        self.assertIn("OMP_NUM_THREADS=1", command)
        self.assertIn("10000000", command)
        self.assertEqual(command[command.index("--seed") + 1], str(task["seed"]))
        self.assertEqual(command[-1], "/mnt/d/GitHub/runs/task/null.f64")

    def test_resume_requires_explicit_option(self):
        plan = self.small_plan()
        (self.root / "streams" / plan["tasks"][0]["id"]).mkdir()
        with patch.object(gen, "load_plan", return_value=(plan, "abc")):
            with self.assertRaisesRegex(ValueError, "explicit --resume"):
                gen.run_generation(self.root / "plan.json")

    def test_incomplete_resume_never_retries(self):
        plan = self.small_plan()
        (self.root / "streams" / plan["tasks"][0]["id"]).mkdir()
        with patch.object(gen, "load_plan", return_value=(plan, "abc")), patch.object(gen, "run_stream") as worker:
            with self.assertRaisesRegex(ValueError, "no automatic retry"):
                gen.run_generation(self.root / "plan.json", resume=True)
            worker.assert_not_called()

    def test_invalid_complete_blocks_resume(self):
        plan = self.small_plan()
        directory = self.root / "streams" / plan["tasks"][0]["id"]
        directory.mkdir()
        gen.write_new(directory / "complete.json", {"status": "complete", "returncode": 1})
        with patch.object(gen, "load_plan", return_value=(plan, "abc")), patch.object(gen, "run_stream") as worker:
            with self.assertRaisesRegex(ValueError, "identity or exit"):
                gen.run_generation(self.root / "plan.json", resume=True)
            worker.assert_not_called()

    def test_unexpected_stream_directory_rejected(self):
        plan = self.small_plan()
        (self.root / "streams" / "unexpected").mkdir()
        with patch.object(gen, "load_plan", return_value=(plan, "abc")):
            with self.assertRaisesRegex(ValueError, "unexpected stream"):
                gen.run_generation(self.root / "plan.json", resume=True)

    def test_status_is_readonly_and_explicit_unverified(self):
        plan = self.small_plan()
        before = sorted(str(p) for p in self.root.rglob("*"))
        with patch.object(gen, "load_plan", return_value=(plan, "abc")):
            value = gen.status(self.root / "plan.json")
        self.assertEqual(value["checkpoint_count_unverified"], 0)
        self.assertEqual(before, sorted(str(p) for p in self.root.rglob("*")))

    def test_stop_idempotent_preserves_request(self):
        plan = self.small_plan()
        with patch.object(gen, "load_plan", return_value=(plan, "abc")):
            gen.stop(self.root / "plan.json")
            before = (self.root / "STOP.json").read_bytes()
            gen.stop(self.root / "plan.json")
        self.assertEqual(before, (self.root / "STOP.json").read_bytes())

    def test_twelve_concurrency_ceiling(self):
        plan = self.small_plan(25)
        active = peak = 0
        mutex = threading.Lock()
        def fake_stream(path, plan, digest, task, registry, registry_lock, abort):
            nonlocal active, peak
            with mutex:
                active += 1
                peak = max(peak, active)
            time.sleep(0.015)
            with mutex:
                active -= 1
            return {"id": task["id"], "status": "complete"}
        with patch.object(gen, "load_plan", return_value=(plan, "abc")), patch.object(gen, "run_stream", side_effect=fake_stream):
            result = gen.run_generation(self.root / "plan.json", workers=12)
        self.assertLessEqual(peak, 12)
        self.assertGreater(peak, 1)
        self.assertEqual(result["completed"], 25)

    def test_first_failure_stops_new_launches(self):
        plan = self.small_plan(20)
        calls = []
        def fake_stream(path, plan, digest, task, registry, registry_lock, abort):
            calls.append(task["id"])
            abort.set()
            return {"id": task["id"], "status": "failed", "error": "synthetic failure"}
        with patch.object(gen, "load_plan", return_value=(plan, "abc")), patch.object(gen, "run_stream", side_effect=fake_stream):
            result = gen.run_generation(self.root / "plan.json", workers=2)
        self.assertLessEqual(len(calls), 2)
        self.assertEqual(result["status"], "failed")
        self.assertTrue(result["failures"])

    def test_nonzero_native_exit_is_failure_and_no_checkpoint(self):
        plan = self.small_plan()
        child = MagicMock(pid=999)
        child.wait.return_value = 7
        child.poll.return_value = 7
        abort = threading.Event()
        with patch.object(gen, "load_plan", return_value=(plan, "abc")), patch.object(gen.subprocess, "Popen", return_value=child):
            result = gen.run_stream(self.root / "plan.json", plan, "abc", plan["tasks"][0], {}, threading.Lock(), abort)
        directory = self.root / "streams" / plan["tasks"][0]["id"]
        self.assertEqual(result["status"], "failed")
        self.assertTrue(abort.is_set())
        self.assertFalse((directory / "complete.json").exists())
        self.assertEqual(gen.read_json(directory / "failure.json")["returncode"], 7)

    def test_only_m_selection_keeps_full_plan_scope(self):
        plan = self.small_plan(3)
        plan["tasks"][2]["m"] = 100
        with patch.object(gen, "load_plan", return_value=(plan, "abc")), patch.object(gen, "run_stream", side_effect=lambda *args: {"id": args[3]["id"], "status": "complete"}) as worker:
            result = gen.run_generation(self.root / "plan.json", only_m=[50])
        self.assertEqual(worker.call_count, 2)
        self.assertEqual(result["scope_streams"], 400)
        self.assertEqual(len(plan["tasks"]), 3)

    def successful_fixture(self):
        plan = self.small_plan(1)
        raw, fixture = self.write_raw()
        task = plan["tasks"][0]
        task.update({"m": fixture["m"], "seed": fixture["seed"], "draws": fixture["draws"]})
        child = MagicMock(pid=999)
        child.poll.return_value = 0
        def finish_native():
            directory = self.root / "streams" / task["id"]
            (directory / "null.f64").write_bytes(raw.read_bytes())
            (directory / "null.f64.meta").write_bytes(Path(str(raw) + ".meta").read_bytes())
            (directory / "time.tsv").write_text("0.01\t0.01\t0.00\t100\n", encoding="ascii")
            return 0
        child.wait.side_effect = finish_native
        with patch.object(gen, "load_plan", return_value=(plan, "abc")), patch.object(gen.subprocess, "Popen", return_value=child):
            result = gen.run_stream(self.root / "plan.json", plan, "abc", task, {}, threading.Lock(), threading.Event())
        self.assertEqual(result["status"], "complete")
        return plan, task, self.root / "streams" / task["id"]

    def test_successful_checkpoint_revalidates_all_evidence(self):
        plan, task, directory = self.successful_fixture()
        result = gen.verify_complete(plan, "abc", task, directory)
        self.assertEqual(result["returncode"], 0)
        self.assertEqual(result["peak_rss_kib"], 100)
        self.assertIn("stdout.log", result["artifacts"])
        self.assertIn("stderr.log", result["artifacts"])
        self.assertIn("null.f64", result["artifacts"])
        self.assertNotIn("complete.json", result["artifacts"])

    def test_complete_raw_hash_tamper_rejected(self):
        plan, task, directory = self.successful_fixture()
        raw = directory / "null.f64"
        changed = bytearray(raw.read_bytes())
        changed[10] ^= 1
        raw.write_bytes(changed)
        with self.assertRaisesRegex(ValueError, "artifacts changed"):
            gen.verify_complete(plan, "abc", task, directory)

    def test_complete_command_tamper_rejected(self):
        plan, task, directory = self.successful_fixture()
        changed = dict(task, command=["different-generator"])
        with self.assertRaisesRegex(ValueError, "identity"):
            gen.verify_complete(plan, "abc", changed, directory)

    def test_valid_completed_stream_skipped_on_resume(self):
        plan, task, directory = self.successful_fixture()
        with patch.object(gen, "load_plan", return_value=(plan, "abc")), patch.object(gen, "run_stream") as worker:
            result = gen.run_generation(self.root / "plan.json", resume=True)
        worker.assert_not_called()
        self.assertEqual(result["completed"], 1)

    def test_stop_blocks_new_run_and_explicit_resume_preserves_stop(self):
        plan = self.small_plan(0)
        gen.write_new(self.root / "STOP.json", {"original": "request"})
        with patch.object(gen, "load_plan", return_value=(plan, "abc")):
            with self.assertRaisesRegex(ValueError, "explicit --resume"):
                gen.run_generation(self.root / "plan.json")
            gen.run_generation(self.root / "plan.json", resume=True)
        self.assertFalse((self.root / "STOP.json").exists())
        preserved = list((self.root / "invocations").glob("observed_stop_*.json"))
        self.assertEqual(len(preserved), 1)
        self.assertEqual(gen.read_json(preserved[0]), {"original": "request"})

    def test_invalid_only_m_and_workers_cannot_start(self):
        for workers, only_m in ((13, None), (12, [51]), (12, [50, 50])):
            with patch.object(gen, "load_plan") as load:
                with self.assertRaises(ValueError):
                    gen.run_generation(self.root / "plan.json", workers=workers, only_m=only_m)
                load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
