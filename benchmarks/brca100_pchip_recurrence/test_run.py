"""Small deterministic runner contracts; no BRCA100 data or inference execution."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location("pchip_recurrence_run", Path(__file__).with_name("run.py"))
run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run)


class RunnerContracts(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def write(self, path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def test_fixed_engine_inference_and_full_seed_schedule(self):
        self.assertEqual(run.ENGINE_COMMIT, "f512ef3a29c661e7cdd7b3b2c4027285d8d19fa3")
        self.assertEqual(run.INFERENCE_COMMIT, "86f8729087b3a6d22bdce128649b4e49d725fb9e")
        self.assertEqual(run.SEEDS, tuple(range(1, 101)))
        self.assertEqual(run.MODES, ("k6", "legacy_pc"))

    def test_raw_git_export_requires_hash_and_new_destination(self):
        output = self.root / "export/file.py"
        payload = b"# raw LF bytes\n"
        digest = hashlib.sha256(payload).hexdigest()
        with mock.patch.object(run, "git_blob", return_value=payload):
            self.assertEqual(run.export_blob(self.root, "file.py", output, digest),
                             {"bytes": len(payload), "sha256": digest})
            with self.assertRaises(FileExistsError):
                run.export_blob(self.root, "file.py", output, digest)
            other = self.root / "other.py"
            with self.assertRaisesRegex(RuntimeError, "SHA256 mismatch"):
                run.export_blob(self.root, "file.py", other, "0" * 64)
            self.assertFalse(other.exists())
        self.assertEqual(output.read_bytes(), payload)

    def test_manifest_requires_exact_unique_arm_seed_matrix(self):
        rows = [{"driver": driver, "seed": seed} for driver in run.DRIVERS for seed in (1, 2)]
        good = {"complete": True, "completed_seed_jobs": 4, "rows": rows}
        self.assertEqual(len(run.run_rows(good, seeds=(1, 2))), 4)
        for broken in (
                {**good, "complete": False}, {**good, "rows": rows[:-1]},
                {**good, "rows": rows[:-1] + [rows[0]]},
                {**good, "completed_seed_jobs": 3},
                {**good, "rows": rows + [{"driver": "tf", "seed": 3}]}):
            with self.subTest(broken=broken), self.assertRaises(RuntimeError):
                run.run_rows(broken, seeds=(1, 2))

    def test_raw_directory_rejects_missing_or_unexpected_entries(self):
        directory = self.root / "adj"
        directory.mkdir()
        self.write(directory / "TF_run_001.adj", b"> header\n")
        with self.assertRaises(RuntimeError):
            run.exact_adjacency_files(directory, seeds=(1, 2))
        self.write(directory / "TF_run_002.adj", b"> header\n")
        self.assertEqual(len(run.exact_adjacency_files(directory, seeds=(1, 2))), 2)
        self.write(directory / "sidecar.json", b"{}")
        with self.assertRaises(RuntimeError):
            run.exact_adjacency_files(directory, seeds=(1, 2))

    def test_commands_select_only_consensus_no_inference(self):
        python, work = Path("/venv/bin/python"), Path("/work")
        for driver in run.DRIVERS:
            for mode in run.MODES:
                with self.subTest(driver=driver, mode=mode):
                    command = run.consensus_command(python, work, driver, mode)
                    self.assertEqual(command[:3], [str(python), "-m", "SJARACNe.bin.create_consensus_network"])
                    self.assertEqual(run.option(command, "-a"), str(work / "adjacency" / driver))
                    self.assertEqual(run.option(command, "-o"), str(work / "arms" / driver / mode))
                    if mode == "k6":
                        self.assertEqual(run.option(command, "-k"), "6")
                        self.assertNotIn("-p", command)
                    else:
                        self.assertEqual(run.option(command, "-p"), "0.00001")
                        self.assertNotIn("-k", command)
                    self.assertNotIn("sjaracne.exe", " ".join(command))

    def test_environment_binds_source_and_one_numeric_thread(self):
        with mock.patch.dict(run.os.environ, {"PYTHONPATH": "/old/source", "PYTHONHOME": "/old/python"}):
            env = run.bounded_environment(Path("/new/bin/python"), Path("/new/source"), Path("/work"))
        self.assertEqual(env["PYTHONPATH"], str(Path("/new/source")))
        self.assertNotIn("PYTHONHOME", env)
        self.assertEqual(env["PYTHONNOUSERSITE"], "1")
        for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
            self.assertEqual(env[key], "1")

    def test_k6_requires_B100_and_exact_fraction_metadata(self):
        output = self.root / "k6"
        self.write(output / "bootstrap_info_.txt", b"Total edge tested: 7\nConsensus selection: minimum recurrence\n"
                   b"Bootstrap networks: 100\nMinimum recurrence: 6\nMinimum recurrence fraction: 0.06\n")
        self.write(output / "parameter_info_.txt", b">  Bootstrap No: 100\n>  Minimum recurrence 6 of 100\n"
                   b">  Minimum recurrence fraction 0.06\n")
        run.validate_consensus_metadata(output, "k6")
        info = output / "bootstrap_info_.txt"
        info.write_bytes(info.read_bytes().replace(b"fraction: 0.06", b"fraction: 1"))
        with self.assertRaisesRegex(RuntimeError, "K6/B100"):
            run.validate_consensus_metadata(output, "k6")

    def test_legacy_requires_probability_metadata_not_recurrence(self):
        output = self.root / "legacy"
        self.write(output / "bootstrap_info_.txt", b"Total edge tested: 7\nmu: 3.0\nsigma: 1.2\n")
        self.write(output / "parameter_info_.txt", b">  Bootstrap No: 100\n")
        run.validate_consensus_metadata(output, "legacy_pc")
        self.write(output / "parameter_info_.txt", b">  Bootstrap No: 100\n>  Minimum recurrence 6 of 100\n")
        with self.assertRaisesRegex(RuntimeError, "probability path"):
            run.validate_consensus_metadata(output, "legacy_pc")

    def test_legacy_comparison_allows_only_output_provenance_path_change(self):
        original, new = self.root / "original", self.root / "new"
        for name in run.OUTPUT_FILES:
            body = b"source\ttarget\tMI\nA\tB\t0.5000\n" if "network" in name else b"Total edge tested: 1\n"
            if name == "parameter_info_.txt":
                body = b">  Bootstrap No: 100\n>  Output network: OLD\n"
            self.write(original / name, body)
            self.write(new / name, body.replace(b"OLD", b"NEW"))
        baseline = {"path": str(original), "inventory": {name: run.file_record(original / name) for name in run.OUTPUT_FILES}}
        self.assertTrue(run.compare_legacy(new, baseline)["passed"])
        self.write(new / "consensus_network_3col_.txt", b"source\ttarget\tMI\nA\tB\t0.5001\n")
        with self.assertRaisesRegex(RuntimeError, "Frozen file mismatch"):
            run.compare_legacy(new, baseline)

    def test_parameter_normalization_rejects_ambiguous_or_other_changes(self):
        first = self.write(self.root / "first", b">  Bootstrap No: 100\n>  Output network: A\n")
        second = self.write(self.root / "second", b">  Bootstrap No: 99\n>  Output network: B\n")
        self.assertNotEqual(run.normalized_parameters(first), run.normalized_parameters(second))
        self.write(second, b">  Output network: A\n>  Output network: B\n")
        with self.assertRaisesRegex(RuntimeError, "exactly one"):
            run.normalized_parameters(second)

    def test_existing_result_or_started_run_cannot_be_implicitly_resumed(self):
        run.atomic_json(self.root / "run_manifest.json", {"status": "failed", "rows": []})
        with self.assertRaisesRegex(RuntimeError, "implicit resume"):
            run.execute(self.root, {}, {}, 4)
        run.atomic_json(self.root / "run_manifest.json", {"status": "prepared", "rows": []})
        (self.root / "arms/tf/k6").mkdir(parents=True)
        with self.assertRaisesRegex(RuntimeError, "existing consensus"):
            run.execute(self.root, {}, {}, 4)

    def test_memory_preflight_prevents_any_job_submission(self):
        run.atomic_json(self.root / "run_manifest.json", {"status": "prepared", "rows": []})
        with mock.patch.object(run, "available_memory_kib", return_value=1), \
                mock.patch.object(run, "ThreadPoolExecutor") as pool:
            with self.assertRaisesRegex(RuntimeError, "Insufficient available memory"):
                run.execute(self.root, {}, {}, 4)
        pool.assert_not_called()

    def test_worker_limit_is_enforced_before_any_job_or_output(self):
        for workers in (0, 5, True, 1.5):
            with self.subTest(workers=workers), self.assertRaises(ValueError):
                run.execute(self.root, {}, {}, workers)

    def test_prepare_verifies_all_inputs_before_creating_work_or_exporting_code(self):
        work = self.root / "new_work"
        with mock.patch.object(run, "verify_frozen", side_effect=RuntimeError("bad200inputs")), \
                mock.patch.object(run, "stage_engine") as stage:
            with self.assertRaisesRegex(RuntimeError, "bad200inputs"):
                run.prepare(object(), work, self.root / "raw", self.root / "frozen")
        self.assertFalse(work.exists())
        stage.assert_not_called()

    def test_seed_bytes_and_metadata_must_both_match_frozen_row(self):
        raw = self.root / "raw"
        path = raw / "arms/tf/adj/TF_run_001.adj"
        metadata_path = raw / "arms/tf/seed_metadata/TF_run_001.json"
        frozen_metadata = self.root / "frozen/TF_run_001.json"
        design = {"arms": {"tf": {"p_token": "0.001", "mi_cutoff": 0.14783}},
                  "pchip_data_sha256": "a" * 64, "pchip_primary_sha256": "b" * 64}
        headers = [">  MI threshold method experimental PCHIP empirical cutoff",
                   ">  AP-MI actual m 80", ">  AP-MI Npar 40", ">  DPI tolerance   0",
                   ">  Sampling method fixed-size without replacement", ">  Sampling request 80%",
                   ">  Eligible observations 100", ">  Sampled observations 80",
                   ">  AP-MI PCHIP data SHA256 " + "a" * 64,
                   ">  AP-MI PCHIP primary SHA256 " + "b" * 64,
                   ">  MI requested p binary64 0.001", ">  MI threshold binary64 0.14783"]
        data = b"H\tT\t0.5\n"
        body = ("\n".join(headers) + "\n").encode() + data
        self.write(path, body)
        command = ["/frozen/sjaracne.exe", "-S", "1", "-M", "pchip", "-u", "80%", "-N", "40",
                   "-e", "0", "-p", "0.001", "-i", str(raw / "inputs/BRCA100.exp"),
                   "-s", str(raw / "inputs/BRCA100_TF.txt"), "-l", str(raw / "inputs/BRCA100_TF.txt"),
                   "-o", str(path) + ".partial"]
        adjacency = {"bytes": len(body), "full_sha256": hashlib.sha256(body).hexdigest(),
                     "data_sha256": hashlib.sha256(data).hexdigest(), "edges": 1,
                     "header_lines": len(headers), "source_rows": 1}
        metadata = {"driver": "tf", "seed": 1, "adjacency": adjacency,
                    "command": command, "final_output": str(path)}
        metadata_bytes = json.dumps(metadata, sort_keys=True).encode()
        self.write(metadata_path, metadata_bytes)
        self.write(frozen_metadata, metadata_bytes)
        row = {"sha256": adjacency["full_sha256"], "edges": 1,
               "metadata_sha256": hashlib.sha256(metadata_bytes).hexdigest()}
        actual = run.verify_seed(path, metadata_path, frozen_metadata, row, "tf", 1, design)
        self.assertEqual(actual["edges"], 1)
        self.assertEqual(actual["native_cutoff_hex"], float(0.14783).hex())
        self.write(path, body.replace(b"H\tT\t0.5", b"H\tT\t0.6"))
        with self.assertRaisesRegex(RuntimeError, "Adjacency bytes/data/counts"):
            run.verify_seed(path, metadata_path, frozen_metadata, row, "tf", 1, design)
        self.write(path, body)
        self.write(metadata_path, metadata_bytes + b"\n")
        with self.assertRaisesRegex(RuntimeError, "Raw seed metadata differs"):
            run.verify_seed(path, metadata_path, frozen_metadata, row, "tf", 1, design)


if __name__ == "__main__":
    unittest.main()
