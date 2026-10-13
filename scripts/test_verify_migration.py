from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from verify_migration import verify


class ImportVerificationTests(unittest.TestCase):
    def fixture(self, root, relative="benchmarks/toy/metrics.json"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"original\n")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest = {"files": [{"destination": relative, "source_checkout": "engine",
                               "source_relative_path": relative, "source_sha256": sha,
                               "imported_sha256": sha, "bytes": path.stat().st_size,
                               "adapted_for_new_repo": False}]}
        manifest_path = root / "provenance/import_manifest.json"
        manifest_path.parent.mkdir()
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return path, manifest_path, sha

    def test_preserved_artifact_then_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            path, _, _ = self.fixture(root)
            self.assertEqual(verify(root)["files"], 1)
            path.write_bytes(b"changed\n")
            with self.assertRaises(ValueError):
                verify(root)

    def test_only_navigation_adaptation_can_be_finalized(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            path, manifest_path, sha = self.fixture(root, "benchmarks/thp1_perturbseq/README.md")
            path.write_bytes(b"updated navigation\n")
            with self.assertRaises(ValueError):
                verify(root)
            result = verify(root, finalize_docs=True)
            self.assertEqual(len(result["adapted_navigation_documents"]), 1)
            row = json.loads(manifest_path.read_text())["files"][0]
            self.assertEqual(row["source_sha256"], sha)
            self.assertNotEqual(row["source_sha256"], row["imported_sha256"])
            self.assertEqual(verify(root)["status"], "pass")

    def test_historical_result_cannot_be_rebound_as_adapted(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            path, manifest_path, _ = self.fixture(root)
            before = manifest_path.read_bytes()
            path.write_bytes(b"changed\n")
            with self.assertRaises(ValueError):
                verify(root, finalize_docs=True)
            self.assertEqual(manifest_path.read_bytes(), before)

    def test_source_verification_detects_original_change(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value) / "new"
            root.mkdir()
            _, _, _ = self.fixture(root)
            workspace = Path(value) / "old"
            source = workspace / "engine/benchmarks/toy/metrics.json"
            source.parent.mkdir(parents=True)
            source.write_bytes(b"original\n")
            self.assertTrue(verify(root, workspace)["originals_verified"])
            source.write_bytes(b"changed\n")
            with self.assertRaises(ValueError):
                verify(root, workspace)


if __name__ == "__main__":
    unittest.main()
