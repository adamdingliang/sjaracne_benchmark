"""Synthetic-only compact-packaging safety tests."""
import json
from pathlib import Path
import tempfile
import unittest

import package
from analyze import sha256


class PackageTests(unittest.TestCase):
    def source(self, root):
        run = root / "run"
        run.mkdir()
        for name in package.FILES:
            (run/name).write_text("synthetic",encoding="utf-8")
        code = run / "code"
        code.mkdir()
        (code/"PLAN.md").write_text("synthetic plan",encoding="utf-8")
        request = {"new_null_draws":0,"code_sha256":{"PLAN.md":sha256(code/"PLAN.md")}}
        (run/"request.json").write_text(json.dumps(request),encoding="utf-8")
        completion = {"new_null_draws":0,"m_count":19,"evaluation_rows":4864,
                      "request_sha256":sha256(run/"request.json"),
                      "outputs_sha256":{name:sha256(run/name) for name in package.FILES
                                        if name not in ("request.json","completion.json")}}
        (run/"completion.json").write_text(json.dumps(completion),encoding="utf-8")
        (run/"do_not_copy.f64").write_bytes(b"raw")
        (run/"fit_sorted.npy").write_bytes(b"sorted")
        return run

    def test_compact_only_hashes_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run = self.source(root)
            out = root/"package"
            package.package(run,out)
            self.assertFalse((out/"do_not_copy.f64").exists())
            self.assertFalse((out/"fit_sorted.npy").exists())
            manifest=json.loads((out/"package_sha256.json").read_text())
            self.assertEqual(len(manifest),len(package.FILES)+1)
            for name,digest in manifest.items():
                self.assertEqual(sha256(out/name),digest)
            with self.assertRaises(ValueError):
                package.package(run,out)

    def test_tampering_fails_before_output_creation(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            run=self.source(root)
            (run/"summary.csv").write_text("changed",encoding="utf-8")
            out=root/"package"
            with self.assertRaises(ValueError):
                package.package(run,out)
            self.assertFalse(out.exists())

    def test_overlap_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            run=self.source(Path(temp))
            with self.assertRaises(ValueError):
                package.package(run,run/"inside")


if __name__ == "__main__":
    unittest.main()
