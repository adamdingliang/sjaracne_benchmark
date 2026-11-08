"""Offline checks for exact-source validation and value-preserving preparation."""
import copy
import csv
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

import prepare as module


EXPRESSION = b'"G1"\t"G2"\t"G3"\t\n0.1000\t2e-3\t4.0\t\n3.14159\t0.000\t4.0\t\n'
GENOTYPE = b'"G1"\t"G2"\t"G3"\t\n0\t1\t0\t\n1\t0\t0\t\n'


def source_record(path, data, member):
    return {"path": path, "archive_member": member, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.raw = self.root / "data"
        self.archives = self.root / "archives"
        self.archives.mkdir()
        self.metadata = {"dataset": "synthetic", "source_archives": [], "files": []}
        self.gold_manifest = {"dataset": "synthetic", "files": [], "source": {}}
        gold = b'G1\tG2\t1\n'  # G3 is isolated: source selection must not use gold.
        gold_zip = self.archives / module.GOLD_ARCHIVE
        with zipfile.ZipFile(gold_zip, "w") as gold_source:
            for group in module.GROUPS:
                filename = "DREAM5_SysGen%s.zip" % group
                archive = self.archives / filename
                with zipfile.ZipFile(archive, "w") as source:
                    for network in range(1, 6):
                        identifier = "DREAM5_SysGen%s_Network%d" % (group, network)
                        for kind, data in (("expression", EXPRESSION), ("genotype", GENOTYPE)):
                            basename = "%s_%s.tsv" % (identifier, kind.title())
                            path = "%s/Network%d/input data/%s" % (group, network, basename)
                            member = "DREAM5_SysGen%s/%s" % (group, basename)
                            row = source_record(path, data, member)
                            row.update(id=identifier, group=group, network=network, kind=kind,
                                       expected_profiles=2, expected_genes=3, archive_filename=filename)
                            self.metadata["files"].append(row)
                            self.write_raw(path, data)
                            source.writestr(member, data)
                        path = "%s/Network%d/gold standard/edges.tsv" % (group, network)
                        row = source_record(path, gold, "gold/" + path)
                        row.update(id=identifier, expected_genes=3, **module.verify_gold.parse_gold(gold.decode(), 3))
                        self.gold_manifest["files"].append(row)
                        self.write_raw(path, gold)
                        gold_source.writestr(row["archive_member"], gold)
                self.metadata["source_archives"].append({"group": group, "filename": filename,
                    "profiles": 2, "genes": 3, "bytes": archive.stat().st_size,
                    "sha256": module.digest(archive)})
            notice = b"Missing non-self directed edges are negatives.\n"
            row = source_record("SOURCE_GOLD_STANDARD_README.txt", notice, "gold/README.txt")
            self.gold_manifest["source_notice"] = row
            self.write_raw(row["path"], notice)
            gold_source.writestr(row["archive_member"], notice)
        self.gold_manifest["source"]["gold_archive"] = {
            "bytes": gold_zip.stat().st_size, "sha256": module.digest(gold_zip)}

    def tearDown(self):
        self.temp.cleanup()

    def write_raw(self, path, data):
        target = self.raw / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    def kwargs(self, **options):
        return {"input_manifest": self.metadata, "gold_manifest": self.gold_manifest, **options}

    def test_source_metrics_report_constants_and_duplicate_rows_without_filtering(self):
        genes, profiles, stats = module.parse_matrix(EXPRESSION, kind="expression", expected_genes=3, expected_profiles=2)
        self.assertEqual(genes, ("G1", "G2", "G3"))
        self.assertEqual(profiles[0], ("0.1000", "2e-3", "4.0"))
        self.assertEqual(stats["constant_genes"], ["G3"])
        self.assertEqual(stats["zero_cells"], 1)
        duplicate = EXPRESSION.splitlines(keepends=True)[0] + EXPRESSION.splitlines(keepends=True)[1] * 2
        _, rows, stats = module.parse_matrix(duplicate, kind="expression", expected_genes=3, expected_profiles=2)
        self.assertEqual(len(rows), 2)
        self.assertEqual(stats["duplicate_profile_rows"], 1)
        self.assertEqual(stats["constant_gene_count"], 3)

    def test_terminal_field_schema_is_exact_and_never_silently_stripped(self):
        invalid = (EXPRESSION.replace(b'"G3"\t\n', b'"G3"\n'),
                   EXPRESSION.replace(b'4.0\t\n', b'4.0\n', 1),
                   EXPRESSION.replace(b'4.0\t\n', b'4.0\t\t\n', 1),
                   EXPRESSION.replace(b'2e-3', b''), EXPRESSION.replace(b'2e-3', b' 2e-3'),
                   EXPRESSION.replace(b'\n', b'\r\n'), EXPRESSION[:-1],
                   EXPRESSION.replace(b'"G3"', b'"G2"'),
                   EXPRESSION.replace(b'"G3"', b'"G4"'))
        for data in invalid:
            with self.subTest(data=data), self.assertRaises(ValueError):
                module.parse_matrix(data, kind="expression", expected_genes=3, expected_profiles=2)

    def test_nonfinite_and_nonnumeric_expression_or_nonbinary_genotype_fail(self):
        for token in (b"NaN", b"inf", b"-inf", b"1e10000", b"text"):
            with self.subTest(token=token), self.assertRaises(ValueError):
                module.parse_matrix(EXPRESSION.replace(b"2e-3", token), kind="expression", expected_genes=3, expected_profiles=2)
        for token in (b"2", b"0.0", b"-1"):
            with self.subTest(token=token), self.assertRaisesRegex(ValueError, "binary"):
                module.parse_matrix(GENOTYPE.replace(b"0\t1\t0", token + b"\t1\t0", 1),
                                    kind="genotype", expected_genes=3, expected_profiles=2)

    def test_pair_alignment_requires_same_gene_order_and_profile_count(self):
        swapped = GENOTYPE.replace(b'"G1"\t"G2"', b'"G2"\t"G1"')
        with self.assertRaisesRegex(ValueError, "gene order"):
            module.validate_pair(EXPRESSION, swapped, expected_genes=3, expected_profiles=2)
        with self.assertRaisesRegex(ValueError, "profile count"):
            module.validate_pair(EXPRESSION, GENOTYPE, expected_genes=3, expected_profiles=3)

    def test_full_preparation_preserves_tokens_ordinals_and_all_sources(self):
        output = self.root / "prepared"
        report = module.prepare(output, **self.kwargs(data_root=self.raw))
        self.assertEqual(report["status"], "PREPARED_NO_INFERENCE")
        self.assertFalse(report["inference_performed"])
        self.assertEqual(len(report["prepared_networks"]), 15)
        for item in report["prepared_networks"]:
            expression = Path(item["expression"]["path"])
            rows = list(csv.reader(io.StringIO(expression.read_text()), delimiter="\t"))
            self.assertEqual(rows, [["isoformId", "geneSymbol", "sample_001", "sample_002"],
                                   ["G1", "G1", "0.1000", "3.14159"],
                                   ["G2", "G2", "2e-3", "0.000"], ["G3", "G3", "4.0", "4.0"]])
            self.assertNotIn(b"\r", expression.read_bytes())
            self.assertEqual(item["expression"]["sha256"], module.digest(expression))
            self.assertEqual(Path(item["sources"]["path"]).read_text(), "G1\nG2\nG3\n")
            samples = (expression.parent / "sample_manifest.tsv").read_text().splitlines()
            self.assertEqual(samples[1:], ["sample_001\t1\t2\tnot_provided", "sample_002\t2\t3\tnot_provided"])
            manifest = json.loads(Path(item["manifest"]["path"]).read_text())
            self.assertEqual(manifest["candidate_sources"], 3)
            self.assertEqual(manifest["gold"]["reference_source_genes"], 1)
            self.assertEqual(len(manifest["source_files"]), 2)
            self.assertEqual(set(manifest["outputs"]), {"expression.exp", "all1000_sources.txt", "sample_manifest.tsv"})
        with self.assertRaises(FileExistsError):
            module.prepare(output, **self.kwargs(data_root=self.raw))

    def test_source_tampering_missing_pairs_and_path_escape_fail_before_output(self):
        output = self.root / "never_created"
        original = self.metadata["files"][0]
        self.write_raw(original["path"], EXPRESSION.replace(b"0.1000", b"0.1001"))
        with self.assertRaisesRegex(ValueError, "SHA256"):
            module.prepare(output, **self.kwargs(data_root=self.raw))
        self.assertFalse(output.exists())
        self.write_raw(original["path"], EXPRESSION)
        changed = copy.deepcopy(self.metadata)
        changed["files"].pop()
        with self.assertRaisesRegex(ValueError, "fifteen"):
            module.verify(data_root=self.raw, input_manifest=changed, gold_manifest=self.gold_manifest)
        changed = copy.deepcopy(self.metadata)
        changed["files"][0]["path"] = "../outside.tsv"
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            module.verify(data_root=self.raw, input_manifest=changed, gold_manifest=self.gold_manifest)

    def test_both_routes_verify_same_sources_and_pin_whole_archives(self):
        archive_report = module.verify(**self.kwargs(archives_root=self.archives))
        raw_report = module.verify(**self.kwargs(data_root=self.raw))
        self.assertEqual(archive_report["status"], "INPUTS_AND_GOLD_VERIFIED")
        self.assertEqual(archive_report["networks"], raw_report["networks"])
        self.assertFalse((self.root / "prepared").exists())
        first = self.archives / self.metadata["source_archives"][0]["filename"]
        with first.open("ab") as stream:
            stream.write(b"tampered")
        with self.assertRaisesRegex(ValueError, "archive size/SHA256"):
            module.verify(**self.kwargs(archives_root=self.archives))

    def test_source_choice_and_cli_external_output_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            module.verify(**self.kwargs())
        with self.assertRaisesRegex(ValueError, "exactly one"):
            module.verify(**self.kwargs(data_root=self.raw, archives_root=self.archives))
        output = self.root / "outside_repo_runs"
        result = subprocess.run([sys.executable, str(module.HERE / "prepare.py"), "prepare",
                                 "--data-root", str(self.raw), "--out", str(output)],
                                capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 2)
        self.assertIn("fresh child", result.stderr)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
