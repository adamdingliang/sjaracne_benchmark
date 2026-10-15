from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import verify_engine_archive as archive


class EngineArchiveVerificationTests(unittest.TestCase):
    def fixture(self, root):
        records = []
        for source in sorted(archive.EXPECTED_SOURCES) + [archive.SOURCE_TEST]:
            destination = (archive.TEST_DESTINATION if source == archive.SOURCE_TEST else
                           archive.ARCHIVE + "/" + source.removeprefix("benchmarks/"))
            content = (source + "\r\nunchanged bytes\x00\n").encode("utf-8")
            path = root / destination
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            records.append({"source_path": source, "destination": destination,
                            "git_mode": "100644", "git_blob": archive.git_blob(content),
                            "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
        manifest = {"schema": 1, "migration_date": archive.MIGRATION_DATE,
                    "source_repository": archive.SOURCE_REPOSITORY,
                    "source_commit": archive.SOURCE_COMMIT,
                    "files": records[:-1], "source_tests": records[-1:],
                    "notes": "Optional descriptive metadata is permitted."}
        manifest_path = root / archive.MANIFEST
        manifest_path.parent.mkdir(parents=True)
        self.write_manifest(manifest_path, manifest)
        return manifest, manifest_path

    def write_manifest(self, path, manifest):
        path.write_text(json.dumps(manifest), encoding="utf-8")

    def run_git(self, root, *arguments):
        return subprocess.check_output(
            ["git", "-c", "safe.directory=" + root.as_posix(), "-C", str(root), *arguments],
            stderr=subprocess.STDOUT,
        )

    def stage_fixture(self, root):
        self.run_git(root, "init", "-q")
        self.run_git(root, "config", "core.autocrlf", "false")
        self.run_git(root, "add", ".")

    def test_preserved_sixty_files_and_original_test_pass(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            manifest, _ = self.fixture(root)
            (root / archive.ARCHIVE / "README.md").write_text("New navigation", encoding="utf-8")
            (root / archive.ARCHIVE / "tests").mkdir()
            (root / archive.ARCHIVE / "tests/test_adapter.py").write_text("# authored", encoding="utf-8")
            result = archive.verify(root)
            self.assertEqual((result["status"], result["files"], result["folders"], result["source_tests"]),
                             ("pass", 60, 9, 1))
            self.assertEqual(result["bytes"], sum(row["bytes"] for row in manifest["files"]))
            self.assertFalse(result["source_verified"])
            self.assertFalse(result["git_index_verified"])

    def test_manifest_source_pin_and_schema_are_immutable(self):
        for key, value in [("source_commit", "0" * 40), ("source_repository", "https://example.com"),
                           ("migration_date", "2026-10-15"), ("schema", 2), ("schema", True)]:
            with self.subTest(key=key, value=value), tempfile.TemporaryDirectory() as location:
                root = Path(location)
                manifest, path = self.fixture(root)
                manifest[key] = value
                self.write_manifest(path, manifest)
                with self.assertRaisesRegex(ValueError, "schema.*pin differs"):
                    archive.verify(root)

    def test_missing_record_or_original_test_snapshot_fails(self):
        for key in ("files", "source_tests"):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as value:
                root = Path(value)
                manifest, path = self.fixture(root)
                manifest[key].pop()
                self.write_manifest(path, manifest)
                with self.assertRaisesRegex(ValueError, "exactly 60"):
                    archive.verify(root)

    def test_tampered_or_missing_archive_bytes_fail(self):
        for change in ("tamper", "missing"):
            with self.subTest(change=change), tempfile.TemporaryDirectory() as value:
                root = Path(value)
                manifest, _ = self.fixture(root)
                target = root / manifest["files"][0]["destination"]
                if change == "tamper":
                    target.write_bytes(b"replacement")
                else:
                    target.unlink()
                with self.assertRaises(ValueError):
                    archive.verify(root)

    def test_git_blob_requires_git_object_header(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            manifest, path = self.fixture(root)
            row = manifest["files"][0]
            row["git_blob"] = hashlib.sha1((root / row["destination"]).read_bytes()).hexdigest()
            self.write_manifest(path, manifest)
            with self.assertRaisesRegex(ValueError, "Git blob differ"):
                archive.verify(root)

    def test_duplicate_source_or_destination_rejected(self):
        for field in ("source_path", "destination"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as value:
                root = Path(value)
                manifest, path = self.fixture(root)
                manifest["files"][1][field] = manifest["files"][0][field]
                self.write_manifest(path, manifest)
                with self.assertRaisesRegex(ValueError, "Duplicate"):
                    archive.verify(root)

    def test_paths_cannot_escape_or_use_windows_aliases(self):
        for field in ("source_path", "destination"):
            for path_value in ("../outside", "/absolute", "C:/outside", "engine_performance/../outside",
                               "engine_performance\\rank_cache\\fixture", "engine_performance//x"):
                with self.subTest(field=field, path=path_value), tempfile.TemporaryDirectory() as value:
                    root = Path(value)
                    manifest, path = self.fixture(root)
                    manifest["files"][0][field] = path_value
                    self.write_manifest(path, manifest)
                    with self.assertRaisesRegex(ValueError, "Noncanonical or escaping"):
                        archive.verify(root)

    def test_manifest_modes_sizes_and_digests_are_strict(self):
        for field, value in (("git_mode", "100755"), ("git_mode", "120000"), ("bytes", True),
                             ("bytes", -1), ("sha256", "a" * 63), ("git_blob", "Z" * 40)):
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as location:
                root = Path(location)
                manifest, path = self.fixture(root)
                manifest["files"][0][field] = value
                self.write_manifest(path, manifest)
                with self.assertRaisesRegex(ValueError, "Invalid archive"):
                    archive.verify(root)

    def test_extra_archive_files_and_unknown_folders_rejected(self):
        for relative in ("rank_cache/unrecorded.txt", "unrecorded/report.txt"):
            with self.subTest(path=relative), tempfile.TemporaryDirectory() as value:
                root = Path(value)
                self.fixture(root)
                target = root / archive.ARCHIVE / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(b"extra")
                with self.assertRaisesRegex(ValueError, "Unexpected|unmanifested"):
                    archive.verify(root)

    def test_other_source_path_cannot_replace_original(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            manifest, path = self.fixture(root)
            manifest["files"][0]["source_path"] = "benchmarks/adjacency_lookup/other.py"
            manifest["files"][0]["destination"] = "engine_performance/adjacency_lookup/other.py"
            self.write_manifest(path, manifest)
            with self.assertRaisesRegex(ValueError, "Undeclared archive"):
                archive.verify(root)

    def test_symlink_to_even_identical_internal_bytes_rejected(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            manifest, _ = self.fixture(root)
            target = root / manifest["files"][0]["destination"]
            internal = root / "identical.bin"
            internal.write_bytes(target.read_bytes())
            target.unlink()
            try:
                target.symlink_to(internal)
            except OSError as error:
                self.skipTest(f"Symlink creation is unavailable: {error}")
            with self.assertRaisesRegex(ValueError, "symlink or junction"):
                archive.verify(root)

    def test_pinned_source_objects_are_checked_not_worktree_bytes(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            manifest, _ = self.fixture(root)
            rows = manifest["files"] + manifest["source_tests"]
            contents = {row["git_blob"]: (root / row["destination"]).read_bytes() for row in rows}

            def fake_git(checkout, *arguments, input=None):
                self.assertEqual(checkout, root / "external_engine")
                if arguments[0] == "ls-tree":
                    self.assertIn(archive.SOURCE_COMMIT, arguments)
                    return b"".join((f"100644 blob {row['git_blob']}\t{row['source_path']}\0").encode()
                                    for row in rows)
                self.assertEqual(arguments, ("cat-file", "--batch"))
                return b"".join(identifier + b" blob " + str(len(contents[identifier.decode()])).encode()
                                + b"\n" + contents[identifier.decode()] + b"\n"
                                for identifier in input.splitlines())

            with patch.object(archive, "_git", side_effect=fake_git):
                self.assertTrue(archive.verify(root, engine_repo=root / "external_engine")["source_verified"])

    def test_missing_pinned_source_or_different_mode_fails(self):
        for mutation in ("missing", "mode"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as value:
                root = Path(value)
                manifest, _ = self.fixture(root)
                rows = manifest["files"] + manifest["source_tests"]
                modified = rows[1:] if mutation == "missing" else rows
                tree = b"".join((f"{'100755' if mutation == 'mode' else '100644'} blob "
                                 f"{row['git_blob']}\t{row['source_path']}\0").encode()
                                for row in modified)
                with patch.object(archive, "_git", return_value=tree), patch.object(archive, "_blobs", return_value={}):
                    with self.assertRaises(ValueError):
                        archive.verify(root, engine_repo=root / "external_engine")

    def test_staged_bytes_and_modes_must_equal_archive(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            manifest, _ = self.fixture(root)
            self.stage_fixture(root)
            self.assertTrue(archive.verify(root, git_index=True)["git_index_verified"])
            row = manifest["files"][0]
            target = root / row["destination"]
            original = target.read_bytes()
            target.write_bytes(b"wrong staged version")
            self.run_git(root, "add", row["destination"])
            target.write_bytes(original)
            with self.assertRaisesRegex(ValueError, "Staged archive bytes or mode"):
                archive.verify(root, git_index=True)
            self.run_git(root, "add", row["destination"])
            self.run_git(root, "update-index", "--chmod=+x", row["destination"])
            with self.assertRaisesRegex(ValueError, "Staged archive bytes or mode"):
                archive.verify(root, git_index=True)

    def test_index_only_unmanifested_archive_file_rejected(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            self.fixture(root)
            extra = root / archive.ARCHIVE / "rank_cache/extra.txt"
            extra.write_bytes(b"extra")
            self.stage_fixture(root)
            extra.unlink()
            with self.assertRaisesRegex(ValueError, "Unmanifested archive file remains in Git index"):
                archive.verify(root, git_index=True)

    def test_staged_manifest_must_match_verified_working_manifest(self):
        with tempfile.TemporaryDirectory() as value:
            root = Path(value)
            manifest, path = self.fixture(root)
            self.stage_fixture(root)
            manifest["notes"] = "An unstaged change must not silently pass an index audit."
            self.write_manifest(path, manifest)
            with self.assertRaisesRegex(ValueError, "Staged archive manifest differs"):
                archive.verify(root, git_index=True)


if __name__ == "__main__":
    unittest.main()
