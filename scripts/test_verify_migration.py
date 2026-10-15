from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from verify_migration import LUAD_RETIREMENT_COMMIT, RETIRED_LUAD_REPLACEMENTS, verify


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

    def retired_fixture(self, root, relative="archive/tcga_luad_gdc/download_luad_star_counts.py"):
        old, manifest_path, sha = self.fixture(root, relative)
        content = old.read_bytes()
        old.unlink()
        replacement_relative = RETIRED_LUAD_REPLACEMENTS.get(
            relative, "benchmarks/tcga_luad_download/download_tcga_luad.py")
        replacement = root / replacement_relative
        replacement.parent.mkdir(parents=True, exist_ok=True)
        replacement.write_bytes(b"canonical acquisition utility\n")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        row = manifest["files"][0]
        row.update(lifecycle="retired", retirement={
            "date": "2026-10-14",
            "reason": "Consolidated LUAD acquisition into one benchmark entry point",
            "replacement": replacement_relative,
            "recovery_commit": LUAD_RETIREMENT_COMMIT,
            "recovery_path": relative,
        })
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return old, replacement, manifest_path, manifest, content, sha

    def test_only_declared_retirements_recover_unchanged_imports(self):
        for relative in RETIRED_LUAD_REPLACEMENTS:
            with self.subTest(relative=relative), tempfile.TemporaryDirectory() as value:
                root = Path(value)
                _, _, manifest_path, _, content, sha = self.retired_fixture(root, relative)
                before = manifest_path.read_bytes()
                with patch("verify_migration.git", return_value=content) as recovered:
                    result = verify(root)
                recovered.assert_called_once_with(root, "show", LUAD_RETIREMENT_COMMIT + ":" + relative)
                self.assertEqual(result["files"], 1)
                self.assertEqual(result["active_files"], 0)
                self.assertEqual(result["retired_files"], 1)
                self.assertEqual(result["active_bytes"], 0)
                self.assertEqual(result["retired_bytes"], len(content))
                self.assertEqual(result["retired_destinations"], [relative])
                self.assertEqual(manifest_path.read_bytes(), before)
                self.assertEqual(json.loads(before)["files"][0]["source_sha256"], sha)

    def test_historical_result_cannot_be_retired(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.retired_fixture(root, "benchmarks/toy/metrics.json")
            with patch("verify_migration.git") as recovered, self.assertRaisesRegex(ValueError, "Undeclared"):
                verify(root, finalize_docs=True)
            recovered.assert_not_called()

    def test_retirement_recovery_metadata_is_pinned(self):
        bad_fields = {
            "date": "2026-10-15",
            "reason": " ",
            "replacement": "../external.py",
            "recovery_commit": "0" * 40,
            "recovery_path": "archive/tcga_luad_gdc/README.md",
        }
        for field, bad in bad_fields.items():
            with self.subTest(field=field), tempfile.TemporaryDirectory() as value:
                root = Path(value)
                _, _, manifest_path, manifest, _, _ = self.retired_fixture(root)
                manifest["files"][0]["retirement"][field] = bad
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                with patch("verify_migration.git") as recovered, self.assertRaises(ValueError):
                    verify(root)
                recovered.assert_not_called()

    def test_retirement_metadata_is_required(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            _, _, manifest_path, manifest, _, _ = self.retired_fixture(root)
            manifest["files"][0].pop("retirement")
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "metadata"):
                verify(root)

    def test_retirement_cannot_rebind_original_or_imported_hashes(self):
        for mutation in ("source", "both", "bytes", "adapted"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as value:
                root = Path(value)
                _, _, manifest_path, manifest, content, _ = self.retired_fixture(root)
                row = manifest["files"][0]
                if mutation in {"source", "both"}:
                    row["source_sha256"] = "0" * 64
                if mutation == "both":
                    row["imported_sha256"] = row["source_sha256"]
                if mutation == "bytes":
                    row["bytes"] += 1
                if mutation == "adapted":
                    row["adapted_for_new_repo"] = True
                manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
                with patch("verify_migration.git", return_value=content), self.assertRaises(ValueError):
                    verify(root, finalize_docs=True)

    def test_retirement_recovery_bytes_are_verified(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.retired_fixture(root)
            with patch("verify_migration.git", return_value=b"modified\n"), self.assertRaisesRegex(
                    ValueError, "immutable recovery"):
                verify(root)

    def test_retired_destination_must_stay_absent(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            old, _, _, _, content, _ = self.retired_fixture(root)
            old.write_bytes(content)
            with self.assertRaisesRegex(ValueError, "still present"):
                verify(root)

    def test_retirement_replacement_must_exist_and_be_a_file(self):
        for as_directory in (False, True):
            with self.subTest(as_directory=as_directory), tempfile.TemporaryDirectory() as value:
                root = Path(value)
                _, replacement, _, _, _, _ = self.retired_fixture(root)
                replacement.unlink()
                if as_directory:
                    replacement.mkdir()
                with self.assertRaises((ValueError, FileNotFoundError)):
                    verify(root)

    def test_retired_source_verification_still_detects_original_change(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value) / "new"
            root.mkdir()
            _, _, _, manifest, content, _ = self.retired_fixture(root)
            workspace = Path(value) / "old"
            row = manifest["files"][0]
            source = workspace / row["source_checkout"] / row["source_relative_path"]
            source.parent.mkdir(parents=True)
            source.write_bytes(content)
            with patch("verify_migration.git", return_value=content):
                self.assertTrue(verify(root, workspace)["originals_verified"])
                source.write_bytes(b"changed\n")
                with self.assertRaisesRegex(ValueError, "Original source changed"):
                    verify(root, workspace)

    def test_retired_destination_must_be_absent_from_git_index(self):
        for staged in (False, True):
            with self.subTest(staged=staged), tempfile.TemporaryDirectory() as value:
                root = Path(value)
                old, _, _, _, content, _ = self.retired_fixture(root)
                relative = old.relative_to(root).as_posix()

                def fake_git(checkout, *args, **kwargs):
                    if args == ("show", LUAD_RETIREMENT_COMMIT + ":" + relative):
                        return content
                    self.assertEqual(args, ("ls-files", "--stage", "--", relative))
                    self.assertEqual(kwargs, {"text": True})
                    return "100644 oldblob 0\t" + relative + "\n" if staged else ""

                with patch("verify_migration.git", side_effect=fake_git):
                    if staged:
                        with self.assertRaisesRegex(ValueError, "still staged"):
                            verify(root, git_index=True)
                    else:
                        self.assertEqual(verify(root, git_index=True)["retired_files"], 1)

    def test_active_import_cannot_carry_retirement_metadata(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            _, manifest_path, _ = self.fixture(root)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"][0]["retirement"] = {}
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Active"):
                verify(root)

    def test_unknown_lifecycle_cannot_bypass_preserved_bytes(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            path, manifest_path, _ = self.fixture(root)
            path.write_bytes(b"modified\n")
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"][0]["lifecycle"] = "omitted"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Unknown"):
                verify(root)


if __name__ == "__main__":
    unittest.main()
