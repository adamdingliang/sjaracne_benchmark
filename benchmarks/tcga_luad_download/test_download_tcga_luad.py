"""Offline contract tests for the public TCGA-LUAD downloader.

Run with ``python -m unittest discover -s benchmarks/tcga_luad_download -v``.
The synthetic records and tiny STAR files contain no real patient data.
"""

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

import download_tcga_luad as downloader


FILE_ID = "11111111-1111-4111-8111-111111111111"
SECOND_FILE_ID = "22222222-2222-4222-8222-222222222222"
CASE_ID = "33333333-3333-4333-8333-333333333333"
SAMPLE_ID = "44444444-4444-4444-8444-444444444444"
ALIQUOT_ID = "55555555-5555-4555-8555-555555555555"
OTHER_ALIQUOT_ID = "66666666-6666-4666-8666-666666666666"

STAR_HEADER = (
    "gene_id\tgene_name\tgene_type\tunstranded\tstranded_first\t"
    "stranded_second\ttpm_unstranded\tfpkm_unstranded\tfpkm_uq_unstranded"
)
STAR_LINES = [
    "# gene-model: GENCODE v36",
    STAR_HEADER,
    "N_unmapped\t\t\t10\t10\t10\t\t\t",
    "N_multimapping\t\t\t20\t20\t20\t\t\t",
    "N_noFeature\t\t\t30\t30\t30\t\t\t",
    "N_ambiguous\t\t\t40\t40\t40\t\t\t",
    "ENSG00000141510.18\tTP53\tprotein_coding\t42\t20\t22\t1.25\t0.5\t0.7",
    "ENSG00000012048.23\tBRCA1\tprotein_coding\t0\t0\t0\t0\t0\t0",
]


def star_bytes(lines=None):
    return ("\n".join(STAR_LINES if lines is None else lines) + "\n").encode("utf-8")


def raw_hit(file_id=FILE_ID, content=None):
    content = star_bytes() if content is None else content
    return {
        "id": file_id,
        "file_id": file_id,
        "file_name": "example.rna_seq.augmented_star_gene_counts.tsv",
        "file_size": len(content),
        "md5sum": hashlib.md5(content).hexdigest(),
        "access": "open",
        "state": "released",
        "data_format": "TSV",
        "experimental_strategy": "RNA-Seq",
        "data_category": "Transcriptome Profiling",
        "data_type": "Gene Expression Quantification",
        "analysis": {"workflow_type": "STAR - Counts"},
        "associated_entities": [
            {
                "entity_id": ALIQUOT_ID,
                "entity_submitter_id": "TCGA-XX-0001-01A-01R-0000-00",
                "entity_type": "aliquot",
            }
        ],
        "cases": [
            {
                "case_id": CASE_ID,
                "submitter_id": "TCGA-XX-0001",
                "project": {"project_id": "TCGA-LUAD"},
                "samples": [
                    {
                        "sample_id": SAMPLE_ID,
                        "submitter_id": "TCGA-XX-0001-01A",
                        "sample_type": "Primary Tumor",
                        "portions": [
                            {
                                "analytes": [
                                    {
                                        "aliquots": [
                                            {
                                                "aliquot_id": ALIQUOT_ID,
                                                "submitter_id": "TCGA-XX-0001-01A-01R-0000-00",
                                            }
                                        ]
                                    }
                                ]
                            }
                        ],
                    }
                ],
            }
        ],
    }


class FakeResponse:
    def __init__(self, payload=None, content=b"", stream_error=None):
        self.payload = payload
        self.content = content
        self.stream_error = stream_error
        self.headers = {"Content-Length": str(len(content))}
        self.status_code = 200

    def raise_for_status(self):
        return None

    def json(self):
        return copy.deepcopy(self.payload)

    def iter_content(self, chunk_size=8192):
        if self.stream_error is not None:
            raise self.stream_error
        for offset in range(0, len(self.content), chunk_size):
            yield self.content[offset : offset + chunk_size]

    def close(self):
        return None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


class FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected extra HTTP request")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def page(hits, offset=0, total=None, count=None):
    total = len(hits) if total is None else total
    count = len(hits) if count is None else count
    return {
        "data": {
            "hits": hits,
            "pagination": {
                "from": offset,
                "count": count,
                "total": total,
                "size": len(hits),
            },
        },
        "warnings": {},
    }


class NormalizeHitTests(unittest.TestCase):
    def test_accepts_linked_primary_tumor_record(self):
        result = downloader.normalize_hit(raw_hit())
        self.assertEqual(result["file_id"], FILE_ID)
        self.assertEqual(result["case_id"], CASE_ID)
        self.assertEqual(result["sample_id"], SAMPLE_ID)
        self.assertEqual(result["sample_type"], "Primary Tumor")
        self.assertEqual(result["aliquot_id"], ALIQUOT_ID)

    def test_uses_associated_aliquot_not_first_sample(self):
        hit = raw_hit()
        unrelated = copy.deepcopy(hit["cases"][0]["samples"][0])
        unrelated["sample_id"] = "77777777-7777-4777-8777-777777777777"
        unrelated["sample_type"] = "Solid Tissue Normal"
        unrelated["portions"][0]["analytes"][0]["aliquots"][0]["aliquot_id"] = OTHER_ALIQUOT_ID
        hit["cases"][0]["samples"].insert(0, unrelated)
        self.assertEqual(downloader.normalize_hit(hit)["sample_id"], SAMPLE_ID)

    def test_rejects_wrong_file_metadata(self):
        for field, value in [
            ("access", "controlled"),
            ("state", "submitted"),
            ("data_format", "BAM"),
            ("experimental_strategy", "WXS"),
            ("data_category", "Sequencing Reads"),
            ("data_type", "Aligned Reads"),
            ("file_id", "not-a-uuid"),
            ("file_size", 0),
            ("md5sum", "not-an-md5"),
        ]:
            with self.subTest(field=field):
                hit = raw_hit()
                hit[field] = value
                with self.assertRaises(ValueError):
                    downloader.normalize_hit(hit)

    def test_rejects_wrong_workflow_project_or_sample(self):
        hit = raw_hit()
        hit["analysis"]["workflow_type"] = "HTSeq - Counts"
        with self.assertRaises(ValueError):
            downloader.normalize_hit(hit)
        hit = raw_hit()
        hit["cases"][0]["project"]["project_id"] = "TCGA-BRCA"
        with self.assertRaises(ValueError):
            downloader.normalize_hit(hit)
        hit = raw_hit()
        hit["cases"][0]["samples"][0]["sample_type"] = "Solid Tissue Normal"
        with self.assertRaises(ValueError):
            downloader.normalize_hit(hit)

    def test_rejects_unsafe_filenames(self):
        for name in ["../bad.tsv", "..\\bad.tsv", "/bad.tsv", "D:\\bad.tsv", "", ".."]:
            with self.subTest(name=name):
                hit = raw_hit()
                hit["file_name"] = name
                with self.assertRaises(ValueError):
                    downloader.normalize_hit(hit)

    def test_rejects_missing_or_ambiguous_association(self):
        for entities in [[], raw_hit()["associated_entities"] * 2]:
            with self.subTest(entities=entities):
                hit = raw_hit()
                hit["associated_entities"] = entities
                with self.assertRaises(ValueError):
                    downloader.normalize_hit(hit)

    def test_rejects_unmatched_associated_aliquot(self):
        hit = raw_hit()
        hit["associated_entities"][0]["entity_id"] = OTHER_ALIQUOT_ID
        with self.assertRaises(ValueError):
            downloader.normalize_hit(hit)

    def test_rejects_ambiguous_nested_aliquot(self):
        hit = raw_hit()
        hit["cases"][0]["samples"].append(copy.deepcopy(hit["cases"][0]["samples"][0]))
        with self.assertRaises(ValueError):
            downloader.normalize_hit(hit)


class StarValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "counts.tsv"

    def write(self, content):
        self.path.write_bytes(content)
        return self.path

    def test_valid_star_has_reproducible_gene_fingerprints(self):
        summary = downloader.validate_star(self.write(star_bytes()))
        self.assertEqual(summary["gene_rows"], 2)
        self.assertIn("GENCODE", summary["gene_model"])
        for key in ["gene_id_sha256", "gene_annotation_sha256"]:
            self.assertRegex(summary[key], r"^[0-9a-f]{64}$")
        changed = star_bytes().replace(b"42\t20\t22\t1.25", b"43\t20\t23\t1.50")
        other = downloader.validate_star(self.write(changed))
        self.assertEqual(summary["gene_id_sha256"], other["gene_id_sha256"])
        self.assertEqual(summary["gene_annotation_sha256"], other["gene_annotation_sha256"])

    def test_annotation_change_changes_annotation_fingerprint(self):
        original = downloader.validate_star(self.write(star_bytes()))
        changed = downloader.validate_star(self.write(star_bytes().replace(b"\tTP53\t", b"\tOTHER\t")))
        self.assertEqual(original["gene_id_sha256"], changed["gene_id_sha256"])
        self.assertNotEqual(original["gene_annotation_sha256"], changed["gene_annotation_sha256"])

    def test_rejects_non_tsv_or_wrong_header(self):
        for content in [b"<html>service unavailable</html>\n", star_bytes().replace(b"tpm_unstranded", b"tpm")]:
            with self.subTest(content=content[:40]):
                with self.assertRaises(ValueError):
                    downloader.validate_star(self.write(content))

    def test_requires_gene_model_and_all_summary_rows(self):
        for removed_index in [0, 2, 3, 4, 5]:
            lines = STAR_LINES[:removed_index] + STAR_LINES[removed_index + 1 :]
            with self.subTest(removed_index=removed_index):
                with self.assertRaises(ValueError):
                    downloader.validate_star(self.write(star_bytes(lines)))

    def test_rejects_duplicate_gene_or_invalid_gene_id(self):
        for lines in [STAR_LINES + [STAR_LINES[-1]], STAR_LINES[:-1] + [STAR_LINES[-1].replace("ENSG00000012048.23", "not-a-gene")]]:
            with self.subTest(last_line=lines[-1]):
                with self.assertRaises(ValueError):
                    downloader.validate_star(self.write(star_bytes(lines)))

    def test_rejects_negative_fractional_or_nonfinite_measurements(self):
        for column, value in [(3, "-1"), (3, "1.5"), (4, "nan"), (6, "-0.1"), (6, "nan"), (7, "inf"), (8, "-inf"), (6, "")]:
            with self.subTest(column=column, value=value):
                lines = list(STAR_LINES)
                fields = lines[-1].split("\t")
                fields[column] = value
                lines[-1] = "\t".join(fields)
                with self.assertRaises(ValueError):
                    downloader.validate_star(self.write(star_bytes(lines)))

    def test_rejects_missing_or_extra_fields(self):
        for row in [STAR_LINES[-1].rsplit("\t", 1)[0], STAR_LINES[-1] + "\textra"]:
            with self.subTest(row=row):
                with self.assertRaises(ValueError):
                    downloader.validate_star(self.write(star_bytes(STAR_LINES[:-1] + [row])))

    def test_rejects_file_without_gene_rows(self):
        with self.assertRaises(ValueError):
            downloader.validate_star(self.write(star_bytes(STAR_LINES[:6])))

    def test_verify_file_checks_size_md5_and_star_schema(self):
        content = star_bytes()
        record = downloader.normalize_hit(raw_hit())
        result = downloader.verify_file(self.write(content), record)
        self.assertEqual(result["sha256"], hashlib.sha256(content).hexdigest())
        self.assertEqual(result["gene_rows"], 2)
        for field, value in [("file_size", len(content) + 1), ("md5sum", "0" * 32)]:
            with self.subTest(field=field):
                bad = dict(record)
                bad[field] = value
                with self.assertRaises(ValueError):
                    downloader.verify_file(self.path, bad)


class PaginationTests(unittest.TestCase):
    def test_fetches_all_pages_and_preserves_pagination(self):
        first, second = raw_hit(), raw_hit(SECOND_FILE_ID)
        session = FakeSession([
            FakeResponse(page([first], offset=0, total=2)),
            FakeResponse(page([second], offset=1, total=2)),
        ])
        result = downloader.query_files(session, page_size=1)
        self.assertEqual([hit["file_id"] for hit in result["files"]], [FILE_ID, SECOND_FILE_ID])
        self.assertEqual(len(result["pages"]), 2)
        self.assertEqual([call[1]["params"]["from"] for call in session.calls], [0, 1])

    def test_rejects_duplicate_files_across_pages(self):
        session = FakeSession([
            FakeResponse(page([raw_hit()], offset=0, total=2)),
            FakeResponse(page([raw_hit()], offset=1, total=2)),
        ])
        with self.assertRaises(ValueError):
            downloader.query_files(session, page_size=1)

    def test_rejects_empty_result(self):
        with self.assertRaises(ValueError):
            downloader.query_files(FakeSession([FakeResponse(page([]))]), page_size=10)

    def test_rejects_inconsistent_pagination(self):
        for payload in [page([raw_hit()], offset=1), page([raw_hit()], count=2), page([raw_hit()], total=0)]:
            with self.subTest(payload=payload["data"]["pagination"]):
                with self.assertRaises(ValueError):
                    downloader.query_files(FakeSession([FakeResponse(payload)]), page_size=10)

    def test_rejects_changed_total_between_pages(self):
        session = FakeSession([
            FakeResponse(page([raw_hit()], offset=0, total=2)),
            FakeResponse(page([raw_hit(SECOND_FILE_ID)], offset=1, total=3)),
        ])
        with self.assertRaises(ValueError):
            downloader.query_files(session, page_size=1)

    def test_rejects_api_warnings(self):
        payload = page([raw_hit()])
        payload["warnings"] = {"fields": ["Requested field does not exist"]}
        with self.assertRaises(ValueError):
            downloader.query_files(FakeSession([FakeResponse(payload)]), page_size=10)


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.outdir = Path(self.directory.name)
        self.record = downloader.normalize_hit(raw_hit())
        self.destination = self.outdir / "files" / FILE_ID / self.record["file_name"]

    def test_downloads_verified_file_and_reuses_it_without_network(self):
        session = FakeSession([FakeResponse(content=star_bytes())])
        result = downloader.download_file(session, self.record, self.outdir, attempts=1)
        self.assertEqual(result["status"], "downloaded")
        self.assertEqual(self.destination.read_bytes(), star_bytes())
        empty_session = FakeSession([])
        reused = downloader.download_file(empty_session, self.record, self.outdir, attempts=1)
        self.assertEqual(reused["status"], "already_valid")
        self.assertEqual(empty_session.calls, [])

    def test_failed_replacement_preserves_existing_corrupt_file(self):
        self.destination.parent.mkdir(parents=True)
        self.destination.write_bytes(b"old incomplete download")
        with self.assertRaises((ValueError, RuntimeError)):
            downloader.download_file(FakeSession([FakeResponse(content=b"bad replacement")]), self.record, self.outdir, attempts=1)
        self.assertEqual(self.destination.read_bytes(), b"old incomplete download")

    def test_verified_replacement_overwrites_corrupt_file(self):
        self.destination.parent.mkdir(parents=True)
        self.destination.write_bytes(b"old incomplete download")
        result = downloader.download_file(FakeSession([FakeResponse(content=star_bytes())]), self.record, self.outdir, attempts=1)
        self.assertEqual(result["status"], "downloaded")
        self.assertEqual(self.destination.read_bytes(), star_bytes())


if __name__ == "__main__":
    unittest.main()
