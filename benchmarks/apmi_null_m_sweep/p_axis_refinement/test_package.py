"""Synthetic-only checks of the compact refinement packager."""
import json
from pathlib import Path
import tempfile
import unittest

import package


class PackageTests(unittest.TestCase):
    def write_json(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def source(self, root):
        run = root / "run"
        run.mkdir()
        for name in package.OUTPUT_FILES:
            (run / name).write_text("synthetic compact output", encoding="utf-8")
        snapshots = {
            "benchmarks/apmi_null_m_sweep/p_axis_refinement/PLAN.md": "synthetic plan",
            "benchmarks/apmi_null_m_sweep/p_axis_refinement/run.py": "synthetic run code",
            "benchmarks/apmi_null_m_sweep/smooth_feasibility/models.py": "synthetic older helper",
        }
        for name, content in snapshots.items():
            target = run / "execution_code" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
        request = {"format": package.FORMAT, "new_null_draws": 0, "new_large_copies": 0,
                   "code_sha256": {name: package.sha256(run / "execution_code" / name)
                                   for name in snapshots}}
        self.write_json(run / "request.json", request)
        completion = {"format": package.FORMAT, "new_null_draws": 0, "new_large_copies": 0,
                      "m_count": 19, "query_probability_count": 49,
                      "evaluation_rows": 16758, "prediction_count": 8379,
                      "request_sha256": package.sha256(run / "request.json"),
                      "outputs_sha256": {name: package.sha256(run / name)
                                         for name in package.OUTPUT_FILES}}
        self.write_json(run / "completion.json", completion)
        (run / "do_not_copy.f64").write_bytes(b"raw")
        (run / "fit_sorted.npy").write_bytes(b"sorted")
        return run

    def mutate_request(self, run, change):
        request = json.loads((run / "request.json").read_text())
        change(request)
        self.write_json(run / "request.json", request)
        completion = json.loads((run / "completion.json").read_text())
        completion["request_sha256"] = package.sha256(run / "request.json")
        self.write_json(run / "completion.json", completion)

    def test_compact_only_preserves_snapshot_structure_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = self.source(root)
            out = root / "package"
            returned = package.package(run, out)
            self.assertFalse((out / "do_not_copy.f64").exists())
            self.assertFalse((out / "fit_sorted.npy").exists())
            manifest = json.loads((out / "package_sha256.json").read_text())
            self.assertEqual(returned, manifest)
            self.assertEqual(len(manifest), len(package.FILES) + 3)
            for name, digest in manifest.items():
                self.assertEqual(package.sha256(out / name), digest)
            self.assertTrue((out / "execution_code/benchmarks/apmi_null_m_sweep/p_axis_refinement/PLAN.md").is_file())
            with self.assertRaises(ValueError):
                package.package(run, out)

    def test_tampered_output_fails_before_output_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = self.source(root)
            (run / "summary.csv").write_text("changed", encoding="utf-8")
            with self.assertRaises(ValueError):
                package.package(run, root / "package")
            self.assertFalse((root / "package").exists())

    def test_tampered_request_fails_before_output_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = self.source(root)
            request = json.loads((run / "request.json").read_text())
            request["extra"] = "unhashed edit"
            self.write_json(run / "request.json", request)
            with self.assertRaises(ValueError):
                package.package(run, root / "package")
            self.assertFalse((root / "package").exists())

    def test_tampered_code_fails_before_output_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = self.source(root)
            (run / "execution_code/benchmarks/apmi_null_m_sweep/p_axis_refinement/run.py").write_text("changed")
            with self.assertRaises(ValueError):
                package.package(run, root / "package")
            self.assertFalse((root / "package").exists())

    def test_missing_or_extra_output_hash_rejected(self):
        for mutation in ("missing", "extra"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                run = self.source(root)
                completion = json.loads((run / "completion.json").read_text())
                if mutation == "missing":
                    del completion["outputs_sha256"]["summary.csv"]
                else:
                    completion["outputs_sha256"]["do_not_copy.f64"] = package.sha256(run / "do_not_copy.f64")
                self.write_json(run / "completion.json", completion)
                with self.assertRaises(ValueError):
                    package.package(run, root / "package")
                self.assertFalse((root / "package").exists())

    def test_unsafe_snapshot_names_rejected(self):
        for name in ("../escape.py", "/absolute.py", "C:/drive.py", "bad\\path.py",
                     "same//path.py", "same/./path.py", "raw.f64", ".", ""):
            with self.subTest(name=name), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                run = self.source(root)
                self.mutate_request(run, lambda request: request.update(code_sha256={name: "0" * 64}))
                with self.assertRaises(ValueError):
                    package.package(run, root / "package")
                self.assertFalse((root / "package").exists())

    def test_metadata_format_counts_and_generation_requirements(self):
        changes = {"format": "other", "m_count": 18, "query_probability_count": 48,
                   "evaluation_rows": 1, "prediction_count": 1, "new_null_draws": 1,
                   "new_large_copies": 1}
        for key, value in changes.items():
            with self.subTest(key=key), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                run = self.source(root)
                completion = json.loads((run / "completion.json").read_text())
                completion[key] = value
                self.write_json(run / "completion.json", completion)
                with self.assertRaises(ValueError):
                    package.package(run, root / "package")
                self.assertFalse((root / "package").exists())

    def test_request_generation_metadata_rejected_even_when_rehashed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = self.source(root)
            self.mutate_request(run, lambda request: request.update(new_null_draws=1))
            with self.assertRaises(ValueError):
                package.package(run, root / "package")
            self.assertFalse((root / "package").exists())

    def test_snapshot_links_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = self.source(root)
            snapshot = run / "execution_code/benchmarks/apmi_null_m_sweep/p_axis_refinement/run.py"
            snapshot.unlink()
            outside = root / "outside.py"
            outside.write_text("synthetic run code")
            try:
                snapshot.symlink_to(outside)
            except OSError:
                self.skipTest("symlink creation unavailable")
            with self.assertRaises(ValueError):
                package.package(run, root / "package")
            self.assertFalse((root / "package").exists())

    def test_overlap_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = self.source(root)
            for out in (run, run / "inside", root):
                with self.subTest(out=out), self.assertRaises(ValueError):
                    package.package(run, out)


if __name__ == "__main__":
    unittest.main()
