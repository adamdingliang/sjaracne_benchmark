"""Synthetic contract checks; these do not claim an inference reproduction."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location("brca_refresh_run", Path(__file__).with_name("run.py"))
run = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(run)


class ContractTests(unittest.TestCase):
    def test_command_matches_intended_workflow(self):
        build = {"binary": "/engine/sjaracne", "config": "/engine/config"}
        for driver, p in (("tf", "0.001"), ("sig", "0.0005")):
            command = run.seed_command(build, Path("/work"), driver, 17, Path("/out.adj"))
            options = dict(zip(command[1::2], command[2::2]))
            self.assertEqual(options["-M"], "pchip")
            self.assertEqual(options["-p"], p)
            self.assertEqual(options["-u"], "80%")
            self.assertEqual(options["-S"], "17")
            self.assertEqual(options["-N"], "40")
            self.assertEqual(options["-e"], "0")
            self.assertEqual(options["-l"], options["-s"])
            self.assertNotIn("-R", options)

    def test_immutable_manifest_rejects_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "design.json"
            run.immutable_json(path, {"m": 80})
            run.immutable_json(path, {"m": 80})
            with self.assertRaises(RuntimeError):
                run.immutable_json(path, {"m": 90})

    def test_inventory_rejects_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "example"
            path.write_text("first")
            expected = run.inventory(root, [path])
            run.verify_inventory(root, expected)
            path.write_text("other")
            with self.assertRaises(RuntimeError):
                run.verify_inventory(root, expected)

    def test_all_seed_schedule_is_fixed(self):
        self.assertEqual(run.SEEDS, list(range(1, 101)))
        self.assertEqual(run.DRIVERS["tf"][2], "p1e-03")
        self.assertEqual(run.DRIVERS["sig"][2], "p5e-04")

    def test_native_concurrency_is_bounded(self):
        for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
            self.assertEqual(run.bounded_environment()[key], "1")

    def test_header_requires_actual_pchip_not_gpd(self):
        headers = "\n".join(run.required_headers("tf"))
        self.assertIn("experimental PCHIP empirical cutoff", headers)
        self.assertIn(run.DATA_SHA256, headers)
        self.assertIn("Sampled observations 80", headers)
        self.assertNotIn("GPD", headers)

    def test_adjacency_validation_checks_exact_requested_probability(self):
        design = {"arms": {"tf": {"p_token": "0.001", "mi_cutoff": 0.14783}}}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "seed.adj"
            text = "\n".join(run.required_headers("tf"))
            text += "\n>  MI requested p binary64 0.001\n>  MI threshold binary64 0.14783\nH\tT\t0.2\n"
            path.write_text(text)
            stats = run.validate_seed(path, "tf", design, {"H", "T"}, {"H"})
            self.assertEqual(stats["edges"], 1)
            path.write_text(text.replace("binary64 0.001", "binary64 0.0005"))
            with self.assertRaises(RuntimeError):
                run.validate_seed(path, "tf", design, {"H", "T"}, {"H"})

    def test_seed_record_keeps_executed_partial_command_and_final_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            run.core.atomic_json(work / "design.json", {"fixed": True})
            build = {"binary": "/engine/sjaracne", "config": "/engine/config",
                     "source": "/engine"}
            captured = []

            def fake_timed(command, *args, **kwargs):
                captured.append(command)
                Path(command[command.index("-o") + 1]).write_text("validated")
                return {"elapsed_s": 1.0}

            with mock.patch.object(run, "timed", side_effect=fake_timed), \
                    mock.patch.object(run, "validate_seed", return_value={"full_sha256": "test"}):
                record = run.seed_job(build, work, {}, "tf", 1, {"H", "T"}, {"H"})
            self.assertEqual(record["command"], captured[0])
            self.assertTrue(record["command"][record["command"].index("-o") + 1].endswith(".adj.partial"))
            self.assertTrue(record["final_output"].endswith("TF_run_001.adj"))
            self.assertTrue(Path(record["final_output"]).is_file())


if __name__ == "__main__":
    unittest.main()
