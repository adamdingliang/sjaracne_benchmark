"""Offline frozen-cohort tests added during downloader consolidation.

The original 26 imported tests remain unchanged in test_download_tcga_luad.py.
Only tiny synthetic API responses and temporary directories are used here.
"""

import copy
import json
from pathlib import Path
import tempfile
import unittest

import download_tcga_luad as downloader
import test_download_tcga_luad as fixtures


class QuerySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.outdir = Path(self.directory.name)
        self.snapshot_path = self.outdir / "query_snapshot.json"

    def fresh_session(self, before="synthetic-release-1", after="synthetic-release-1", hit=None):
        return fixtures.FakeSession([
            fixtures.FakeResponse({"data_release": before}),
            fixtures.FakeResponse(fixtures.page([fixtures.raw_hit() if hit is None else hit])),
            fixtures.FakeResponse({"data_release": after}),
        ])

    def freeze(self):
        return downloader.load_or_query(self.fresh_session(), self.outdir, page_size=10)

    def write_snapshot(self, snapshot):
        downloader.save_json(self.snapshot_path, snapshot)

    def test_fresh_query_freezes_protocol_metadata_and_release(self):
        session = self.fresh_session()
        snapshot, records = downloader.load_or_query(session, self.outdir, page_size=10)
        self.assertEqual(json.loads(self.snapshot_path.read_text(encoding="utf-8")), snapshot)
        self.assertEqual(records, [downloader.normalize_hit(fixtures.raw_hit())])
        self.assertEqual(snapshot["schema_version"], 1)
        self.assertEqual(snapshot["api"], downloader.API)
        self.assertEqual(snapshot["filters"], downloader.build_filters())
        self.assertEqual(snapshot["file_count"], 1)
        self.assertEqual(snapshot["files_sha256"], downloader.json_digest(snapshot["files"]))
        self.assertEqual(snapshot["gdc_status_before"]["data_release"], "synthetic-release-1")
        self.assertEqual(snapshot["gdc_status_after"], snapshot["gdc_status_before"])
        self.assertEqual([url for url, _ in session.calls], [
            downloader.API + "/status", downloader.API + "/files", downloader.API + "/status"])
        self.assertFalse((self.outdir / "files").exists())

    def test_existing_snapshot_reused_without_requery_or_rewrite(self):
        original_snapshot, original_records = self.freeze()
        original_bytes = self.snapshot_path.read_bytes()
        no_network = fixtures.FakeSession([])
        snapshot, records = downloader.load_or_query(no_network, self.outdir, page_size=1)
        self.assertEqual((snapshot, records), (original_snapshot, original_records))
        self.assertEqual(no_network.calls, [])
        self.assertEqual(self.snapshot_path.read_bytes(), original_bytes)

    def test_existing_snapshot_can_be_loaded_offline(self):
        original = self.freeze()
        original_bytes = self.snapshot_path.read_bytes()
        no_network = fixtures.FakeSession([])
        loaded = downloader.load_or_query(no_network, self.outdir, page_size=10, offline=True)
        self.assertEqual(loaded, original)
        self.assertEqual(no_network.calls, [])
        self.assertEqual(self.snapshot_path.read_bytes(), original_bytes)

    def test_offline_without_snapshot_fails_without_network_or_new_files(self):
        no_network = fixtures.FakeSession([])
        with self.assertRaisesRegex(ValueError, "requires an existing query_snapshot"):
            downloader.load_or_query(no_network, self.outdir, page_size=10, offline=True)
        self.assertEqual(no_network.calls, [])
        self.assertEqual(list(self.outdir.iterdir()), [])

    def test_legacy_layout_is_not_implicitly_imported_in_offline_mode(self):
        # Old query.json + metadata.tsv are not the current snapshot schema.
        # Their directories must be preserved; acquisition should use a fresh directory.
        legacy_files = {"query.json": b'{"sample_type": "Primary Tumor"}\n',
                        "metadata.tsv": b"file_id\tfile_name\tfile_size\n"}
        for name, content in legacy_files.items():
            (self.outdir / name).write_bytes(content)
        no_network = fixtures.FakeSession([])
        with self.assertRaisesRegex(ValueError, "requires an existing query_snapshot"):
            downloader.load_or_query(no_network, self.outdir, page_size=10, offline=True)
        self.assertEqual(no_network.calls, [])
        self.assertFalse(self.snapshot_path.exists())
        for name, content in legacy_files.items():
            self.assertEqual((self.outdir / name).read_bytes(), content)

    def test_tampered_file_metadata_fails_stored_digest_check(self):
        snapshot, _ = self.freeze()
        snapshot["files"][0]["file_size"] += 1
        self.write_snapshot(snapshot)
        original_bytes = self.snapshot_path.read_bytes()
        no_network = fixtures.FakeSession([])
        with self.assertRaisesRegex(ValueError, "Invalid or incompatible"):
            downloader.load_or_query(no_network, self.outdir, page_size=10, offline=True)
        self.assertEqual(no_network.calls, [])
        self.assertEqual(self.snapshot_path.read_bytes(), original_bytes)

    def test_incompatible_snapshot_protocol_is_rejected_without_network(self):
        original, _ = self.freeze()
        changes = {
            "schema_version": 999,
            "api": "https://example.invalid/other-api",
            "filters": {"op": "and", "content": []},
            "file_count": 999,
        }
        for key, value in changes.items():
            with self.subTest(field=key):
                snapshot = copy.deepcopy(original)
                snapshot[key] = value
                self.write_snapshot(snapshot)
                no_network = fixtures.FakeSession([])
                with self.assertRaisesRegex(ValueError, "Invalid or incompatible"):
                    downloader.load_or_query(no_network, self.outdir, page_size=10, offline=True)
                self.assertEqual(no_network.calls, [])

    def test_reused_snapshot_metadata_is_revalidated_even_with_matching_digest(self):
        snapshot, _ = self.freeze()
        snapshot["files"][0]["access"] = "controlled"
        snapshot["files_sha256"] = downloader.json_digest(snapshot["files"])
        self.write_snapshot(snapshot)
        no_network = fixtures.FakeSession([])
        with self.assertRaisesRegex(ValueError, "access must be"):
            downloader.load_or_query(no_network, self.outdir, page_size=10, offline=True)
        self.assertEqual(no_network.calls, [])

    def test_duplicate_files_in_reused_snapshot_are_rejected(self):
        snapshot, _ = self.freeze()
        snapshot["files"].append(copy.deepcopy(snapshot["files"][0]))
        snapshot["file_count"] = len(snapshot["files"])
        snapshot["files_sha256"] = downloader.json_digest(snapshot["files"])
        self.write_snapshot(snapshot)
        no_network = fixtures.FakeSession([])
        with self.assertRaisesRegex(ValueError, "duplicate file UUIDs"):
            downloader.load_or_query(no_network, self.outdir, page_size=10, offline=True)
        self.assertEqual(no_network.calls, [])

    def test_changed_or_missing_release_does_not_publish_snapshot(self):
        for before, after in [("release-1", "release-2"), (None, None), ("release-1", None)]:
            with self.subTest(before=before, after=after):
                session = self.fresh_session(before=before, after=after)
                with self.assertRaisesRegex(ValueError, "release changed or is missing"):
                    downloader.load_or_query(session, self.outdir, page_size=10)
                self.assertFalse(self.snapshot_path.exists())
                self.assertEqual(len(session.calls), 3)

    def test_invalid_fresh_association_does_not_publish_snapshot(self):
        hit = fixtures.raw_hit()
        hit["associated_entities"][0]["entity_id"] = fixtures.OTHER_ALIQUOT_ID
        session = self.fresh_session(hit=hit)
        with self.assertRaisesRegex(ValueError, "missing or ambiguous aliquot-to-sample link"):
            downloader.load_or_query(session, self.outdir, page_size=10)
        self.assertFalse(self.snapshot_path.exists())


if __name__ == "__main__":
    unittest.main()
