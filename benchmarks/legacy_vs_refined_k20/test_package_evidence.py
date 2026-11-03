"""Synthetic checks for portable frozen-evidence import and validation."""

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location("package_evidence", Path(__file__).with_name("package_evidence.py"))
PACKAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PACKAGE)


class EvidenceTests(unittest.TestCase):
    def test_safe_relative_path(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(PACKAGE.safe_path(directory, "evidence/example.json"),
                             Path(directory).resolve() / "evidence/example.json")

    def test_rejects_escaping_and_nonportable_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ("../escape.json", "/absolute.json", "C:/absolute.json", "evidence\\file.json"):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    PACKAGE.safe_path(directory, name)

    def test_copy_hash_and_idempotence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, target = root / "source.json", root / "nested/target.json"
            source.write_bytes(b'{"small":true}\n')
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            self.assertEqual(PACKAGE.copy_immutable(source, target, digest), digest)
            self.assertEqual(PACKAGE.copy_immutable(source, target, digest), digest)
            self.assertEqual(source.read_bytes(), target.read_bytes())

    def test_copy_refuses_bad_source_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.write_bytes(b"original")
            with self.assertRaises(ValueError):
                PACKAGE.copy_immutable(source, Path(directory) / "target", "0" * 64)

    def test_copy_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            source, target = Path(directory) / "source", Path(directory) / "target"
            source.write_bytes(b"new")
            target.write_bytes(b"old")
            with self.assertRaises(ValueError):
                PACKAGE.copy_immutable(source, target)
            self.assertEqual(target.read_bytes(), b"old")

    def publication(self, root):
        wanted = ("OVERALL.html", "OVERALL.md", "report_data.json", "overall_metrics.tsv")
        hashes = {}
        for name in wanted:
            (root / name).write_text(name, encoding="utf-8")
            hashes[name] = PACKAGE.sha256(root / name)
        marker = {"state": "complete", "dataset": "BLCA406", "published_sha256": hashes}
        (root / "LATEST_OVERALL.json").write_text(json.dumps(marker), encoding="utf-8")
        return marker

    def test_verify_complete_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = self.publication(root)
            self.assertEqual(PACKAGE.verify_publication(root), expected)

    def test_verify_rejects_incomplete_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = self.publication(root)
            marker["state"] = "running"
            (root / "LATEST_OVERALL.json").write_text(json.dumps(marker), encoding="utf-8")
            with self.assertRaises(ValueError):
                PACKAGE.verify_publication(root)

    def test_verify_rejects_changed_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.publication(root)
            (root / "OVERALL.md").write_text("changed", encoding="utf-8")
            with self.assertRaises(ValueError):
                PACKAGE.verify_publication(root)

    def test_verify_requires_full_hash_set(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = self.publication(root)
            del marker["published_sha256"]["OVERALL.html"]
            (root / "LATEST_OVERALL.json").write_text(json.dumps(marker), encoding="utf-8")
            with self.assertRaises(ValueError):
                PACKAGE.verify_publication(root)

    def test_validate_checks_repository_evidence(self):
        result = PACKAGE.validate(Path(__file__).parent)
        self.assertEqual(result["files"], 38)
        self.assertEqual(result["dream_K_cases"], 400)
        self.assertEqual(result["primary_bulk_rows"], 12)


if __name__ == "__main__":
    unittest.main()
