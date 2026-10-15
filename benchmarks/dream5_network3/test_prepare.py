"""Offline synthetic preparation tests, with no inference or network access."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import prepare as module


class PreparationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.contents = {
            module.EXPRESSION: b"G1\tG2\tG3\n1.00\t-2e-3\t0\n3.14159\t4\t5\n",
            module.TFS: b"G1\t\n",
            module.GOLD: b"G1\tG2\t1\nG1\tG3\t0\n",
            module.CHIP: b"#Experiment\tPerturbations\tPerturbationLevels\tTreatment\tDeletedGenes\tOverexpressedGenes\tTime\tRepeat\n1\tNA\tNA\tNA\tNA\tNA\tNA\t1\n1\tNA\tNA\tNA\tNA\tNA\tNA\t2\n",
            module.ANONYMIZATION: b"#ID\tName\nG1\tgeneA\nG2\tgeneB\nG3\tgeneC\n",
        }
        self.contents[module.TFS] = b"G1\nG2\n"

    def tearDown(self):
        self.temp.cleanup()

    def test_bundled_source_manifest_and_all_original_bytes(self):
        manifest = json.loads((module.HERE / "data/provenance.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["source"]["archive_md5"], module.ARCHIVE_MD5)
        rows = {row["path"]: row for row in manifest["files"]}
        self.assertEqual(set(rows), set(module.FILES) | {
            "SOURCE_CHALLENGE_README.txt", "gold standard/SOURCE_GOLD_STANDARD_README.txt"})
        for name, row in rows.items():
            with self.subTest(name=name):
                path = module.DEFAULT_DATA_ROOT / name
                self.assertEqual(path.stat().st_size, row["bytes"])
                self.assertEqual(module.digest(path), row["sha256"])
                if name in module.FILES:
                    self.assertEqual(module.FILES[name], {key: row[key] for key in ("sha256", "bytes")})

    def manifest(self, contents=None):
        contents = self.contents if contents is None else contents
        return {name: {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)} for name, data in contents.items()}

    def test_expression_tokens_preserved_and_all_genes_retained(self):
        genes, profiles, tfs, counts = module.validate_bundle(self.contents)
        self.assertEqual(genes, ("G1", "G2", "G3"))
        self.assertEqual(profiles[0], ("1.00", "-2e-3", "0"))
        self.assertEqual(tfs, ("G1", "G2"))
        self.assertEqual(counts["full_TF_nonself_pairs"], 4)
        self.assertEqual(counts["unlabelled_pairs"], 2)
        out = self.root / "prepared"
        result = module.write_prepared(out, genes, profiles, tfs, {"counts": counts})
        expression = (out / "dream5_net3.exp").read_bytes()
        self.assertEqual(expression, b"isoformId\tgeneSymbol\tS1\tS2\nG1\tG1\t1.00\t3.14159\nG2\tG2\t-2e-3\t4\nG3\tG3\t0\t5\n")
        self.assertEqual((out / "all334_tfs.txt").read_bytes(), b"G1\nG2\n")
        self.assertFalse(result["inference_performed"])
        self.assertEqual(json.loads((out / "provenance.json").read_text())["outputs"], result["outputs"])
        with self.assertRaises(FileExistsError):
            module.write_prepared(out, genes, profiles, tfs, {})

    def test_expression_rejects_duplicate_empty_dimensions_and_nonfinite(self):
        for text in ("G1\tG1\n1\t2\n", "G1\t\n1\t2\n", "G1\tG2\n1\n", "G1\n", "G1\nNaN\n", "G1\ninf\n", "G1\nnot-a-number\n", "G1\n 1\n", "G1\n\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                module.parse_expression(text)

    def test_tf_validation(self):
        for text in ("G1\nG1\n", "G4\n", "G1\tG2\n", "\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                module.parse_tfs(text, ("G1", "G2"))

    def test_gold_rejects_unknown_nontf_self_duplicates_and_nonbinary(self):
        valid = "G1\tG2\t1\nG1\tG3\t0\n"
        self.assertEqual(module.parse_gold(valid, ("G1", "G2", "G3"), ("G1",)), [("G1", "G2", 1), ("G1", "G3", 0)])
        for text in (valid + "G1\tG2\t1\n", valid + "G1\tG1\t0\n", valid + "G1\tG4\t0\n", valid + "G2\tG1\t0\n", valid.replace("\t0", "\t0.0"), "G1\tG2\t1\n", "G1\tG2\n"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                module.parse_gold(text, ("G1", "G2", "G3"), ("G1",))

    def test_metadata_checks_profile_count_and_gene_order(self):
        chip = self.contents[module.CHIP].decode()
        mapping = self.contents[module.ANONYMIZATION].decode()
        module.validate_metadata(chip, mapping, ("G1", "G2", "G3"), 2)
        with self.assertRaises(ValueError):
            module.validate_metadata(chip, mapping, ("G1", "G2", "G3"), 3)
        with self.assertRaises(ValueError):
            module.validate_metadata(chip, mapping, ("G2", "G1", "G3"), 2)
        with self.assertRaises(ValueError):
            module.validate_metadata(chip, mapping.replace("G2\t", "G1\t"), ("G1", "G2", "G3"), 2)

    def test_file_hashes_and_content_tamper_fail_closed(self):
        source = self.root / "source"
        for name, data in self.contents.items():
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        with patch.object(module, "FILES", self.manifest()):
            loaded, provenance = module.load_originals(data_root=source)
            self.assertEqual(loaded, self.contents)
            self.assertEqual(provenance["origin"]["kind"], "bundled_original_files")
            (source / module.EXPRESSION).write_bytes(b"changed\n")
            with self.assertRaisesRegex(ValueError, "SHA256"):
                module.load_originals(data_root=source)

    def test_archive_md5_and_exact_members_without_extraction(self):
        archive = self.root / "source.zip"
        with zipfile.ZipFile(archive, "w") as stream:
            for name, data in self.contents.items():
                stream.writestr(module.ARCHIVE_PREFIX + name, data)
            stream.writestr("../do-not-extract", "unrelated member")
        with patch.object(module, "FILES", self.manifest()), patch.object(module, "ARCHIVE_MD5", module.digest(archive, "md5")):
            contents, provenance = module.load_originals(archive=archive)
            self.assertEqual(contents, self.contents)
            self.assertEqual(provenance["origin"]["kind"], "verified_archive")
            self.assertEqual(sorted(path.name for path in self.root.iterdir()), ["source.zip"])
        with self.assertRaisesRegex(ValueError, "MD5"):
            module.load_originals(archive=archive)

    def test_fixed_real_dimensions_are_enforced_and_invalid_input_leaves_no_output(self):
        out = self.root / "prepared"
        with patch.object(module, "load_originals", return_value=(self.contents, {})):
            with self.assertRaisesRegex(ValueError, "dimensions"):
                module.prepare(out)
        self.assertFalse(out.exists())
        with self.assertRaises(ValueError):
            module.load_originals(data_root=self.root, archive=self.root / "missing.zip")


if __name__ == "__main__":
    unittest.main()
