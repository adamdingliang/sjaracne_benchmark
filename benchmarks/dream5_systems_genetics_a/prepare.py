"""Verify SysGenA originals and prepare expression-only SJARACNe inputs.

Original expression/genotype bytes remain external. No downloads, inference,
normalization, gold-based regulator selection, DPI, consensus or scoring occur.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile

import verify_gold


HERE = Path(__file__).resolve().parent
GROUPS = ("A100", "A300", "A999")
KINDS = ("expression", "genotype")
GOLD_ARCHIVE = "DREAM5_SysGenA_GoldStandard.zip"


def digest(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _checked_bytes(data, record):
    if len(data) != record["bytes"] or hashlib.sha256(data).hexdigest() != record["sha256"]:
        raise ValueError("Source size/SHA256 mismatch: " + record["path"])


def _inside(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Unsafe source path")
    path = (root / relative).resolve(strict=True)
    if not path.is_relative_to(root):
        raise ValueError("Source resolves outside the selected root")
    return path


def _input_catalog(metadata):
    records = metadata["files"]
    slots = {(row["group"], row["network"], row["kind"]) for row in records}
    expected = {(group, n, kind) for group in GROUPS for n in range(1, 6) for kind in KINDS}
    if len(records) != 30 or slots != expected:
        raise ValueError("Input manifest must contain exactly fifteen expression/genotype pairs")
    archives = {row["group"]: row for row in metadata["source_archives"]}
    if len(metadata["source_archives"]) != 3 or set(archives) != set(GROUPS):
        raise ValueError("Input manifest must contain the three original group archives")
    for row in records:
        group = archives[row["group"]]
        if (row["expected_profiles"] != group["profiles"] or row["expected_genes"] != group["genes"]
                or row["archive_filename"] != group["filename"]):
            raise ValueError("Input member dimensions/archive differ from its group")
        if row["id"] != "DREAM5_SysGen%s_Network%d" % (row["group"], row["network"]):
            raise ValueError("Input member ID differs from its group/network")
    return records, archives


def parse_matrix(data, *, kind, expected_genes, expected_profiles):
    """Parse the exact source schema, preserving numeric token strings.

    Each source record has one required empty terminal CSV field. Only that
    field is discarded; missing, additional or internal empty fields fail.
    Constant genes and duplicate rows are reported, never silently filtered.
    """
    if kind not in KINDS:
        raise ValueError("Unknown input matrix kind")
    if b"\r" in data or not data.endswith(b"\n"):
        raise ValueError("Source matrix must preserve its literal LF endings")
    reader = csv.reader(io.StringIO(data.decode("utf-8")), delimiter="\t")
    try:
        header = next(reader)
    except StopIteration as error:
        raise ValueError("Source matrix is empty") from error
    if len(header) != expected_genes + 1 or header[-1] != "":
        raise ValueError("Header requires exactly one empty terminal field")
    genes = tuple(header[:-1])
    if len(set(genes)) != len(genes) or set(genes) != {"G%d" % i for i in range(1, expected_genes + 1)}:
        raise ValueError("Header has duplicate, missing or unexpected gene IDs")
    profiles, minimum, maximum = [], math.inf, -math.inf
    column_min, column_max = [math.inf] * expected_genes, [-math.inf] * expected_genes
    zero_cells, genotype_counts = 0, {"0": 0, "1": 0}
    for line, row in enumerate(reader, 2):
        if len(row) != expected_genes + 1 or row[-1] != "":
            raise ValueError("Row %d requires exactly one empty terminal field" % line)
        values = tuple(row[:-1])
        for j, token in enumerate(values):
            if not token or token != token.strip():
                raise ValueError("Empty or whitespace-bearing numeric token in row %d" % line)
            try:
                numeric = float(token)
            except ValueError as error:
                raise ValueError("Nonnumeric matrix value in row %d" % line) from error
            if not math.isfinite(numeric):
                raise ValueError("Nonfinite matrix value in row %d" % line)
            if kind == "genotype":
                if token not in ("0", "1"):
                    raise ValueError("Genotype values must be literal binary 0 or 1")
                genotype_counts[token] += 1
            zero_cells += numeric == 0
            minimum, maximum = min(minimum, numeric), max(maximum, numeric)
            column_min[j], column_max[j] = min(column_min[j], numeric), max(column_max[j], numeric)
        profiles.append(values)
    if len(profiles) != expected_profiles or not profiles:
        raise ValueError("Matrix profile count differs from its pinned group")
    constants = [gene for i, gene in enumerate(genes) if column_min[i] == column_max[i]]
    stats = {"genes": len(genes), "profiles": len(profiles), "empty_terminal_field_removed": True,
             "constant_gene_count": len(constants), "constant_genes": constants,
             "duplicate_profile_rows": len(profiles) - len(set(profiles)),
             "zero_cells": zero_cells, "minimum": minimum, "maximum": maximum}
    if kind == "genotype":
        stats["binary_counts"] = genotype_counts
    return genes, profiles, stats


def validate_pair(expression, genotype, *, expected_genes, expected_profiles):
    """Check paired gene order and positional row alignment without inventing IDs."""
    genes, _, expression_stats = parse_matrix(expression, kind="expression", expected_genes=expected_genes,
                                               expected_profiles=expected_profiles)
    genotype_genes, _, genotype_stats = parse_matrix(genotype, kind="genotype", expected_genes=expected_genes,
                                                     expected_profiles=expected_profiles)
    if genes != genotype_genes:
        raise ValueError("Expression/genotype gene order differs")
    return genes, {"expression": expression_stats, "genotype": genotype_stats,
                   "row_alignment": "Original positional order; no source sample IDs supplied"}


def _verified_bundle(*, archives_root=None, data_root=None, input_manifest=None, gold_manifest=None):
    if (archives_root is None) == (data_root is None):
        raise ValueError("Choose exactly one of archives_root or data_root")
    if input_manifest is None:
        metadata_file = HERE / "data/input_provenance.json"
        metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
        metadata_sha = digest(metadata_file)
    else:
        metadata = input_manifest
        metadata_sha = hashlib.sha256(json.dumps(metadata, sort_keys=True).encode()).hexdigest()
    records, archives = _input_catalog(metadata)
    contents, source_files = {}, {}
    if archives_root is not None:
        root = Path(archives_root).resolve(strict=True)
        for group in GROUPS:
            archive_record = archives[group]
            path = _inside(root, archive_record["filename"])
            if path.stat().st_size != archive_record["bytes"] or digest(path) != archive_record["sha256"]:
                raise ValueError("Input archive size/SHA256 mismatch: " + path.name)
            with zipfile.ZipFile(path) as source:
                names = source.namelist()
                for row in (r for r in records if r["group"] == group):
                    if names.count(row["archive_member"]) != 1:
                        raise ValueError("Missing or duplicate exact input ZIP member")
                    data = source.read(row["archive_member"])
                    _checked_bytes(data, row)
                    contents[row["id"], row["kind"]] = data
                    source_files[row["path"]] = {"archive": str(path), "member": row["archive_member"],
                                                  "bytes": row["bytes"], "sha256": row["sha256"]}
        gold = verify_gold.verify(archive=root / GOLD_ARCHIVE, manifest=gold_manifest)
        origin = {"kind": "verified_source_archives", "root": str(root)}
    else:
        root = Path(data_root).resolve(strict=True)
        for row in records:
            path = _inside(root, row["path"])
            data = path.read_bytes()
            _checked_bytes(data, row)
            contents[row["id"], row["kind"]] = data
            source_files[row["path"]] = {"path": str(path), "bytes": row["bytes"], "sha256": row["sha256"]}
        gold = verify_gold.verify(data_root=root, manifest=gold_manifest)
        origin = {"kind": "external_original_files", "root": str(root)}
    if gold.get("gold_status") != "verified":
        raise ValueError("Gold source verification did not pass")
    gold_by_id = {row["id"]: row for row in gold["networks"]}
    networks = []
    for row in (r for r in records if r["kind"] == "expression"):
        identifier = row["id"]
        if identifier not in gold_by_id:
            raise ValueError("Input network is missing its corresponding gold source")
        genes, stats = validate_pair(contents[identifier, "expression"], contents[identifier, "genotype"],
                                    expected_genes=row["expected_genes"], expected_profiles=row["expected_profiles"])
        reference = gold_by_id[identifier]
        if reference["full_directed_nonself_pairs"] != len(genes) * (len(genes) - 1):
            raise ValueError("Input and gold gene universes differ")
        networks.append({"id": identifier, "group": row["group"], "network": row["network"],
                         "candidate_sources": len(genes), "input_statistics": stats, "gold": reference})
    report = {"schema_version": 1, "dataset": metadata["dataset"], "status": "INPUTS_AND_GOLD_VERIFIED",
              "input_manifest_sha256": metadata_sha, "origin": origin, "source_files": source_files,
              "networks": networks, "genotype_use": "Validated and retained as source metadata; not used for expression-only inference",
              "row_identity": "Synthetic sample IDs map only to original row ordinals, not measured source identifiers",
              "inference_performed": False}
    return report, contents


def verify(*, archives_root=None, data_root=None, input_manifest=None, gold_manifest=None):
    """Return an integrity and schema report without writing or running inference."""
    report, _ = _verified_bundle(archives_root=archives_root, data_root=data_root,
                                 input_manifest=input_manifest, gold_manifest=gold_manifest)
    return report


def _file_record(path):
    return {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": digest(path)}


def write_prepared(out, report, contents):
    """Write a fresh complete bundle after every input/reference passed validation."""
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError("Preparation output must be new")
    out.mkdir(parents=True)
    manifests = []
    for network in report["networks"]:
        identifier = network["id"]
        stats = network["input_statistics"]["expression"]
        genes, profiles, _ = parse_matrix(contents[identifier, "expression"], kind="expression",
                                          expected_genes=stats["genes"], expected_profiles=stats["profiles"])
        folder = out / network["group"] / ("Network%d" % network["network"])
        folder.mkdir(parents=True)
        sample_ids = ["sample_%03d" % (i + 1) for i in range(len(profiles))]
        expression = folder / "expression.exp"
        with expression.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write("\t".join(["isoformId", "geneSymbol"] + sample_ids) + "\n")
            for column, gene in enumerate(genes):
                stream.write("\t".join([gene, gene] + [row[column] for row in profiles]) + "\n")
        hubs = folder / "all1000_sources.txt"
        hubs.write_text("\n".join(genes) + "\n", encoding="utf-8", newline="\n")
        samples = folder / "sample_manifest.tsv"
        with samples.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write("generated_profile_id\tsource_data_row_1based\tsource_file_line_1based\tsource_sample_id\n")
            for i, sample in enumerate(sample_ids, 1):
                stream.write("%s\t%d\t%d\tnot_provided\n" % (sample, i, i + 1))
        result = {"schema_version": 1, **network, "status": "PREPARED_NO_INFERENCE",
                  "source_input_manifest_sha256": report["input_manifest_sha256"],
                  "source_files": {key: value for key, value in report["source_files"].items()
                                   if key.startswith(network["group"] + "/Network%d/" % network["network"])},
                  "outputs": {p.name: _file_record(p) for p in (expression, hubs, samples)},
                  "transformation": "CSV parse of required empty terminal field, then value-preserving expression transpose; no normalization/filtering/rounding",
                  "source_selection": "Every expression-header gene in original order; no gold-derived regulator selection",
                  "genotype_use": report["genotype_use"], "row_identity": report["row_identity"],
                  "inference_performed": False}
        (folder / "provenance.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
        manifests.append({"id": identifier, "manifest": _file_record(folder / "provenance.json"),
                          "expression": result["outputs"]["expression.exp"],
                          "sources": result["outputs"]["all1000_sources.txt"]})
    completed = {**report, "status": "PREPARED_NO_INFERENCE", "created_utc": datetime.now(timezone.utc).isoformat(),
                 "preparation_script_sha256": digest(__file__), "prepared_networks": manifests}
    (out / "provenance.json").write_text(json.dumps(completed, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")
    return completed


def prepare(out, *, archives_root=None, data_root=None, input_manifest=None, gold_manifest=None):
    """Validate all sources and create new inputs, including at external output paths.

    The callable permits explicitly selected external outputs. The CLI restricts
    output to a fresh child of this repository's ignored runs directory.
    """
    if Path(out).exists():
        raise FileExistsError("Preparation output must be new")
    report, contents = _verified_bundle(archives_root=archives_root, data_root=data_root,
                                         input_manifest=input_manifest, gold_manifest=gold_manifest)
    return write_prepared(out, report, contents)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("verify", "prepare"):
        sub = commands.add_parser(name)
        source = sub.add_mutually_exclusive_group(required=True)
        source.add_argument("--archives-root", type=Path, help="Directory containing the three pinned input ZIPs and original gold ZIP")
        source.add_argument("--data-root", type=Path, help="External raw data directory containing A100/, A300/, A999/ and the gold README")
        if name == "prepare":
            sub.add_argument("--out", type=Path, required=True, help="Fresh child under this repository's ignored runs/")
    args = parser.parse_args()
    if args.command == "prepare":
        run_root = HERE.parents[1] / "runs"
        if args.out.resolve() == run_root.resolve() or not args.out.resolve().is_relative_to(run_root.resolve()):
            parser.error("--out must be a fresh child under the repository's ignored runs/ directory")
        result = prepare(args.out, archives_root=args.archives_root, data_root=args.data_root)
    else:
        result = verify(archives_root=args.archives_root, data_root=args.data_root)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
