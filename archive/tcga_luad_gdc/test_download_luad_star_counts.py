"""Focused validation for the public GDC LUAD downloader."""

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import download_luad_star_counts as downloader


def hit(number, sample_type="Primary Tumor", content=b"gene_id\tunstranded\n"):
    file_id = f"00000000-0000-4000-8000-{number:012d}"
    return {
        "file_id": file_id,
        "file_name": f"{file_id}.tsv",
        "file_size": len(content),
        "md5sum": hashlib.md5(content).hexdigest(),
        "access": "open",
        "experimental_strategy": "RNA-Seq",
        "data_category": "Transcriptome Profiling",
        "data_type": "Gene Expression Quantification",
        "analysis": {"workflow_type": "STAR - Counts"},
        "cases": [{
            "case_id": "11111111-1111-4111-8111-111111111111",
            "submitter_id": "TCGA-00-0000",
            "samples": [{
                "sample_id": f"22222222-2222-4222-8222-{number:012d}",
                "submitter_id": f"TCGA-00-0000-01{number:01d}",
                "sample_type": sample_type,
            }],
        }],
    }


class FakeResponse:
    def __init__(self, payload=None, chunks=()):
        self.payload = payload
        self.chunks = chunks

    def raise_for_status(self):
        pass

    def json(self):
        return self.payload

    def iter_content(self, chunk_size):
        return iter(self.chunks)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        pass


class FakeQuerySession:
    def __init__(self, pages):
        self.pages = pages

    def get(self, url, params, timeout):
        offset = params["from"]
        page = self.pages[offset]
        return FakeResponse({
            "data": {
                "hits": page,
                "pagination": {
                    "from": offset,
                    "count": len(page),
                    "total": sum(len(p) for p in self.pages.values()),
                },
            },
        })


class DownloaderTests(unittest.TestCase):
    def test_file_linked_sample_selection_and_ambiguous_linkage(self):
        normal = hit(1, sample_type="Solid Tissue Normal")
        self.assertIsNone(downloader.validate_record(normal, "Primary Tumor"))
        ambiguous = hit(2)
        ambiguous["cases"][0]["samples"].append(normal["cases"][0]["samples"][0])
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            downloader.validate_record(ambiguous, "Primary Tumor")

    def test_all_pages_and_incomplete_page(self):
        pages = {0: [hit(1), hit(2, "Solid Tissue Normal")], 2: [hit(3)]}
        with patch.object(downloader, "PAGE_SIZE", 2):
            records, total = downloader.query_files(FakeQuerySession(pages), "Primary Tumor")
            self.assertEqual(total, 3)
            self.assertEqual([row["file_id"] for row in records], [hit(1)["file_id"], hit(3)["file_id"]])
            with self.assertRaisesRegex(ValueError, "incomplete page"):
                downloader.query_files(FakeQuerySession({0: [hit(1)], 2: [hit(2), hit(3)]}), "Primary Tumor")

    def test_download_checksum_resume_and_corrupt_existing_file(self):
        data = b"gene_id\tunstranded\nENSG0001\t17\n"
        row = downloader.validate_record(hit(1, content=data), "Primary Tumor")

        class DataSession:
            calls = 0

            def get(self, url, stream, timeout):
                self.calls += 1
                return FakeResponse(chunks=(data[:5], data[5:]))

        session = DataSession()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / row["relative_path"]
            destination.parent.mkdir(parents=True)
            partial = destination.with_name(destination.name + ".part")
            partial.write_bytes(b"incomplete prior attempt")
            self.assertTrue(downloader.download_one(session, root, row))
            self.assertEqual(destination.read_bytes(), data)
            self.assertFalse(partial.exists())
            self.assertFalse(downloader.download_one(session, root, row))
            self.assertEqual(session.calls, 1)
            destination.write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "Size mismatch"):
                downloader.download_one(session, root, row)
            self.assertEqual(destination.read_bytes(), b"corrupt")
            destination.write_bytes(b"x" * len(data))
            with self.assertRaisesRegex(ValueError, "MD5 mismatch"):
                downloader.download_one(session, root, row)
            self.assertEqual(session.calls, 1)

    def test_manifest_is_tsv_and_snapshot_drift_fails(self):
        row = downloader.validate_record(hit(1), "Primary Tumor")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            downloader.save_snapshot(root, [row], total=3, sample_type="Primary Tumor")
            first = (root / "metadata.tsv").read_bytes()
            self.assertIn(b"file_id\tfile_name\tfile_size", first)
            self.assertEqual(downloader.read_snapshot(root)[0]["file_size"], row["file_size"])
            changed = dict(row, md5sum="0" * 32)
            with self.assertRaisesRegex(RuntimeError, "differs"):
                downloader.save_snapshot(root, [changed], total=3, sample_type="Primary Tumor")
            self.assertEqual((root / "metadata.tsv").read_bytes(), first)


if __name__ == "__main__":
    unittest.main()
