#!/usr/bin/env python3
"""Synthetic-only regression tests for compact evidence publication."""
from __future__ import annotations

from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).with_name("package_dpi_summary_evidence.py")
SPEC = importlib.util.spec_from_file_location("dpi_evidence_packager", SCRIPT)
packager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packager)


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        self.process = self.root / "PROCESS_SOURCE.md"
        self.process.write_text(
            "# Process\n[Counts](source/counts.tsv)\n"
            "[Source README](source/README.md)\n",
            encoding="utf-8",
        )
        self.files = {
            "RESULTS.md": (
                b"# Results\nMI cutoff: 0.123456; observed rate: 0.001.\n"
                b"[Counts](counts.tsv?download=1#rows)\n"
                b"![Figure](figure.svg)\n[Metadata](metadata.json#source)\n"
                b"[Original README](README.md)\n[Raw network](network.adj)\n"
                b"[Full analysis](analysis.json)\n"
                b"[External](https://example.org/report?a=1#part)\n"
                b"[Section](#results)\n"
            ),
            "README.md": b"# Source report\n[Results](RESULTS.md)\n",
            "counts.tsv": b"source\tTP\tFP\nA\t12\t34\n",
            "figure.svg": b'<svg xmlns="http://www.w3.org/2000/svg"><text>12</text></svg>\n',
            "metadata.json": b'{"seed": 7, "cutoff": 0.123456}\n',
            "network.adj": b">A\nB\t0.123456\n",
            "analysis.json": b'{"large_sidecar":"' + b"x" * 1_000_000 + b'"}\n',
            "large.tsv": b"x\n" * 100,
            "per_source_runs.tsv": b"source\tn\nA\t1\n",
        }
        for name, content in self.files.items():
            (self.source / name).write_bytes(content)

    def publish(self, name="published", **kwargs):
        destination = self.root / name
        packager.publish(
            self.source, destination, self.process, "Synthetic test",
            max_table_bytes=64, **kwargs,
        )
        return destination

    def test_numeric_artifacts_are_byte_identical_and_manifest_verifies(self):
        original_hashes = {p.name: packager.sha(p) for p in self.source.iterdir()}
        destination = self.publish()
        self.assertTrue(packager.verify(destination))
        manifest = json.loads((destination / "PUBLICATION.json").read_text(encoding="utf-8"))
        self.assertFalse(manifest["new_scientific_run"])
        records = {item["source_name"]: item for item in manifest["files"]}
        for source_name, published_name in (
            ("counts.tsv", "counts.tsv"),
            ("figure.svg", "figure.svg"),
            ("metadata.json", "original_metadata.json"),
        ):
            with self.subTest(artifact=source_name):
                self.assertEqual((destination / published_name).read_bytes(), self.files[source_name])
                self.assertEqual(records[source_name]["original"], records[source_name]["published"])
                self.assertEqual(records[source_name]["original"]["sha256"], original_hashes[source_name])
        self.assertEqual(original_hashes, {p.name: packager.sha(p) for p in self.source.iterdir()})

    def test_links_distinguish_included_artifacts_from_omitted_sidecars(self):
        destination = self.publish()
        report = (destination / "RESULTS.md").read_text(encoding="utf-8")
        self.assertIn("MI cutoff: 0.123456; observed rate: 0.001.", report)
        self.assertIn("[Counts](counts.tsv?download=1#rows)", report)
        self.assertIn("![Figure](figure.svg)", report)
        self.assertIn("[Metadata](original_metadata.json#source)", report)
        self.assertIn("[Original README](SOURCE_README.md)", report)
        self.assertIn("[Raw network](README.md#local-artifacts)", report)
        self.assertIn("[Full analysis](README.md#local-artifacts)", report)
        self.assertIn("[External](https://example.org/report?a=1#part)", report)
        self.assertIn("[Section](#results)", report)
        process = (destination / "PROCESS.md").read_text(encoding="utf-8")
        self.assertIn("[Counts](counts.tsv)", process)
        self.assertIn("[Source README](SOURCE_README.md)", process)

    def test_raw_and_large_artifacts_are_omitted_but_hashed(self):
        destination = self.publish()
        manifest = json.loads((destination / "PUBLICATION.json").read_text(encoding="utf-8"))
        omitted = {item["name"]: item for item in manifest["omitted_local_artifacts"]}
        for name in ("network.adj", "analysis.json", "large.tsv", "per_source_runs.tsv"):
            with self.subTest(artifact=name):
                self.assertFalse((destination / name).exists())
                self.assertEqual(omitted[name]["sha256"], packager.sha(self.source / name))
                self.assertEqual(omitted[name]["bytes"], len(self.files[name]))

    def test_repeated_cli_include_flags_select_only_requested_source_files(self):
        destination = self.root / "selected"
        arguments = [
            str(SCRIPT), "--source", str(self.source),
            "--destination", str(destination), "--process", str(self.process),
            "--label", "Selected synthetic test", "--include", "RESULTS.md",
            "--include", "counts.tsv", "--include", "RESULTS.md",
        ]
        output = io.StringIO()
        with patch.object(sys, "argv", arguments), redirect_stdout(output):
            packager.main()
        self.assertEqual(json.loads(output.getvalue())["published_files"], 5)
        self.assertEqual(
            {p.name for p in destination.iterdir()},
            {"RESULTS.md", "counts.tsv", "PROCESS.md", "README.md", "PUBLICATION.json"},
        )
        self.assertIn(
            "![Figure](README.md#local-artifacts)",
            (destination / "RESULTS.md").read_text(encoding="utf-8"),
        )
        self.assertTrue(packager.verify(destination))

    def test_verification_detects_tampered_artifact_and_readme(self):
        for index, name in enumerate(("counts.tsv", "RESULTS.md", "README.md")):
            with self.subTest(artifact=name):
                destination = self.publish(f"tampered-{index}")
                with (destination / name).open("ab") as stream:
                    stream.write(b"tampered\n")
                with self.assertRaisesRegex(ValueError, "mismatch"):
                    packager.verify(destination)

    def test_existing_destination_is_rejected_without_overwriting(self):
        destination = self.root / "existing"
        destination.mkdir()
        sentinel = destination / "keep.txt"
        sentinel.write_bytes(b"Do not overwrite.\n")
        with self.assertRaisesRegex(FileExistsError, "already exists"):
            self.publish("existing")
        self.assertEqual({p.name for p in destination.iterdir()}, {"keep.txt"})
        self.assertEqual(sentinel.read_bytes(), b"Do not overwrite.\n")


if __name__ == "__main__":
    unittest.main()
