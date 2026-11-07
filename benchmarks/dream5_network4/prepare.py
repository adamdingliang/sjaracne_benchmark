"""Verify DREAM5 Network 4 originals and prepare value-preserving SJARACNe input.

Original source files remain external. No downloads, inference, preprocessing, reference-based gene selection, DPI,
consensus or scoring are performed. Only explicit binary gold-standard labels
are assessed labels; the remaining source-target pairs are unlabelled.
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


HERE = Path(__file__).resolve().parent
ARCHIVE_MD5 = "fabfb9cbba5761d29d681e752a45df75"
ARCHIVE_PREFIX = "DREAM5_network_inference_challenge/Network4/"
EXPRESSION = "input data/net4_expression_data.tsv"
TFS = "input data/net4_transcription_factors.tsv"
GOLD = "gold standard/DREAM5_NetworkInference_GoldStandard_Network4.tsv"
CHIP = "input data/net4_chip_features.tsv"
ANONYMIZATION = "anonymization/net4_gene_ids.tsv"
FILES = {'input data/net4_expression_data.tsv': {'sha256': 'cdfdc5c4a73dce55195f5c1d91779e9d85653c6246712cfe31afd929efeecb27', 'bytes': 33355847}, 'input data/net4_transcription_factors.tsv': {'sha256': '5f5f488db34dee0e895b3eba31ee73d8aa7c0c37c297bcd2331270407196523d', 'bytes': 1557}, 'gold standard/DREAM5_NetworkInference_GoldStandard_Network4.tsv': {'sha256': '8a2dfa1278c062e73b6b4511d0d84b055f3982e467e92a48467b05574ea9a0a0', 'bytes': 2834256}, 'input data/net4_chip_features.tsv': {'sha256': 'a95a2363428140da033694a5912853d2767d83a29bbd274ee01182c2bf7096cc', 'bytes': 13881}, 'anonymization/net4_gene_ids.tsv': {'sha256': 'd1dc1164385c1d5c23d0292dd87348a4b820fe460304bcc6fe620daf586236b1', 'bytes': 82929}}
EXPECTED = {'genes': 5950, 'profiles': 536, 'TFs': 333, 'labelled_pairs': 227202, 'positive_pairs': 3940, 'negative_pairs': 223262, 'scored_sources': 114, 'scored_targets': 1994, 'full_TF_nonself_pairs': 1981017, 'unlabelled_pairs': 1753815}


def digest(path, algorithm="sha256"):
    value = hashlib.new(algorithm)
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _rows(text):
    return list(csv.reader(io.StringIO(text), delimiter="\t"))


def _identifiers(values, name):
    values = tuple(values)
    if not values or any(not value or value.strip() != value or any(c.isspace() for c in value) for value in values):
        raise ValueError(f"Empty or whitespace-containing {name}")
    if len(set(values)) != len(values):
        raise ValueError(f"Duplicate {name}")
    return values


def parse_expression(text):
    """Return gene IDs and profile rows of the original numeric token strings."""
    rows = _rows(text)
    if len(rows) < 2:
        raise ValueError("Expression requires a header and at least one profile")
    genes = _identifiers(rows[0], "expression gene IDs")
    profiles = []
    for number, values in enumerate(rows[1:], 2):
        if len(values) != len(genes):
            raise ValueError(f"Expression row {number} has inconsistent gene count")
        for value in values:
            try:
                numeric = float(value)
            except ValueError as exc:
                raise ValueError(f"Nonnumeric expression in row {number}") from exc
            if not value or value.strip() != value or not math.isfinite(numeric):
                raise ValueError(f"Empty, whitespace or nonfinite expression in row {number}")
        profiles.append(tuple(values))
    return genes, profiles


def parse_tfs(text, genes):
    rows = _rows(text)
    if any(len(row) != 1 for row in rows):
        raise ValueError("TF list requires one identifier per row")
    tfs = _identifiers((row[0] for row in rows), "TF identifiers")
    if not set(tfs) <= set(genes):
        raise ValueError("TF identifier absent from expression genes")
    return tfs


def parse_gold(text, genes, tfs):
    """Read only explicitly labelled directed pairs; never add implicit negatives."""
    genes, tfs = set(genes), set(tfs)
    pairs, seen = [], set()
    for number, row in enumerate(_rows(text), 1):
        if len(row) != 3:
            raise ValueError(f"Gold row {number} requires source, target and binary label")
        source, target, label = row
        if source not in genes or target not in genes or source not in tfs:
            raise ValueError("Gold pair contains unknown gene or a non-TF source")
        if source == target:
            raise ValueError("Gold self-pair is not allowed")
        if label not in ("0", "1"):
            raise ValueError("Gold label must be literal 0 or 1")
        if (source, target) in seen:
            raise ValueError("Duplicate directed gold pair")
        seen.add((source, target))
        pairs.append((source, target, int(label)))
    if not pairs or not 0 < sum(label for _, _, label in pairs) < len(pairs):
        raise ValueError("Gold requires at least one positive and one explicit negative")
    return pairs


def validate_metadata(chip_text, gene_ids_text, genes, profile_count):
    chip = _rows(chip_text)
    expected_header = ["#Experiment", "Perturbations", "PerturbationLevels", "Treatment",
                       "DeletedGenes", "OverexpressedGenes", "Time", "Repeat"]
    if not chip or chip[0] != expected_header or len(chip) - 1 != profile_count:
        raise ValueError("Chip metadata header/profile count differs from expression")
    if any(len(row) != len(expected_header) for row in chip[1:]):
        raise ValueError("Malformed chip metadata row")
    # Experiment IDs repeat for time-series/replicate groups; do not require unique IDs.
    if any(not row[0] for row in chip[1:]):
        raise ValueError("Missing chip experiment identifier")
    mapping = _rows(gene_ids_text)
    if not mapping or mapping[0] != ["#ID", "Name"] or any(len(row) != 2 for row in mapping[1:]):
        raise ValueError("Malformed anonymization mapping")
    identifiers = _identifiers((row[0] for row in mapping[1:]), "anonymization IDs")
    if identifiers != tuple(genes) or any(not row[1] for row in mapping[1:]):
        raise ValueError("Anonymization gene IDs/order differ from expression")


def load_originals(*, data_root=None, archive=None):
    """Read exactly five pinned originals; ZIP contents are never extracted."""
    if (data_root is None) == (archive is None):
        raise ValueError("Choose exactly one of data_root or archive")
    contents, records = {}, {}
    if archive is not None:
        archive = Path(archive).resolve(strict=True)
        if digest(archive, "md5") != ARCHIVE_MD5:
            raise ValueError("Archive MD5 differs from the published DREAM5 archive")
        with zipfile.ZipFile(archive) as source:
            names = source.namelist()
            for name in FILES:
                member = ARCHIVE_PREFIX + name
                if names.count(member) != 1:
                    raise ValueError("Missing or duplicate exact Network4 ZIP member")
                contents[name] = source.read(member)
                records[name] = {"archive": str(archive), "member": member}
        origin = {"kind": "verified_archive", "path": str(archive), "md5": ARCHIVE_MD5,
                  "sha256": digest(archive), "bytes": archive.stat().st_size}
    else:
        data_root = Path(data_root).resolve(strict=True)
        for name in FILES:
            path = (data_root / name).resolve(strict=True)
            if not path.is_relative_to(data_root):
                raise ValueError("Source file resolves outside selected data root")
            contents[name] = path.read_bytes()
            records[name] = {"path": str(path)}
        origin = {"kind": "external_original_files", "path": str(data_root)}
    for name, data in contents.items():
        expected = FILES[name]
        actual = {"sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}
        if actual != expected:
            raise ValueError("Pinned original SHA256/size mismatch: " + name)
        if b"\r" in data or not data.endswith(b"\n"):
            raise ValueError("Pinned originals must retain their literal LF endings")
        records[name].update(actual)
    return contents, {"origin": origin, "source_files": records}


def validate_bundle(contents, *, expected_counts=None):
    genes, profiles = parse_expression(contents[EXPRESSION].decode("utf-8"))
    tfs = parse_tfs(contents[TFS].decode("utf-8"), genes)
    gold = parse_gold(contents[GOLD].decode("utf-8"), genes, tfs)
    validate_metadata(contents[CHIP].decode("utf-8"), contents[ANONYMIZATION].decode("utf-8"), genes, len(profiles))
    labelled = len(gold)
    positive = sum(label for _, _, label in gold)
    full_pairs = len(tfs) * (len(genes) - 1)
    counts = {"genes": len(genes), "profiles": len(profiles), "TFs": len(tfs),
              "labelled_pairs": labelled, "positive_pairs": positive, "negative_pairs": labelled - positive,
              "scored_sources": len({source for source, _, _ in gold}),
              "scored_targets": len({target for _, target, _ in gold}),
              "full_TF_nonself_pairs": full_pairs, "unlabelled_pairs": full_pairs - labelled}
    if expected_counts is not None and counts != expected_counts:
        raise ValueError("Dataset dimensions/explicit-label counts differ from pinned Network4")
    return genes, profiles, tfs, counts


def verify(*, data_root=None, archive=None):
    contents, provenance = load_originals(data_root=data_root, archive=archive)
    _, _, _, counts = validate_bundle(contents, expected_counts=EXPECTED)
    return {"status": "verified", "dataset": "DREAM5 Network 4 (S. cerevisiae)", "counts": counts,
            **provenance, "inference_performed": False}


def write_prepared(out, genes, profiles, tfs, provenance):
    """Write a fresh output only after all source validation has succeeded."""
    out = Path(out).resolve()
    if out.exists():
        raise FileExistsError("Refusing to overwrite an existing preparation directory")
    out.mkdir(parents=True)
    expression = out / "dream5_net4.exp"
    with expression.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\t".join(["isoformId", "geneSymbol"] + [f"S{i+1}" for i in range(len(profiles))]) + "\n")
        for column, gene in enumerate(genes):
            stream.write("\t".join([gene, gene] + [row[column] for row in profiles]) + "\n")
    hubs = out / "all333_tfs.txt"
    with hubs.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write("\n".join(tfs) + "\n")
    outputs = {path.name: {"sha256": digest(path), "bytes": path.stat().st_size}
               for path in (expression, hubs)}
    result = {"schema": 1, "status": "prepared", "dataset": "DREAM5 Network 4 (S. cerevisiae)",
              "created_utc": datetime.now(timezone.utc).isoformat(),
              **provenance, "outputs": outputs, "preparation_script_sha256": digest(__file__),
              "transformation": "Value-preserving transpose only: original numeric tokens retained; all expression genes, profiles and TFs retained in original order",
              "reference_policy": "Only explicit 0/1 labelled directed pairs are assessed; unlabelled pairs are not negatives; reference labels do not select inference genes/hubs",
              "inference_performed": False}
    with (out / "provenance.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return result


def prepare(out, *, data_root=None, archive=None):
    if Path(out).exists():
        raise FileExistsError("Preparation output must be new")
    contents, provenance = load_originals(data_root=data_root, archive=archive)
    genes, profiles, tfs, counts = validate_bundle(contents, expected_counts=EXPECTED)
    provenance["counts"] = counts
    return write_prepared(out, genes, profiles, tfs, provenance)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("verify", "prepare"):
        sub = commands.add_parser(name)
        source = sub.add_mutually_exclusive_group(required=True)
        source.add_argument("--data-root", type=Path, default=None, help="External original Network4 root containing input data/, gold standard/ and anonymization/")
        source.add_argument("--archive", type=Path, help="Original DREAM5 ZIP, verified by published MD5 and exact member SHA256")
        if name == "prepare":
            sub.add_argument("--out", required=True, type=Path, help="Fresh output under the repository's ignored runs/ directory")
    args = parser.parse_args()
    if args.command == "verify":
        result = verify(data_root=args.data_root, archive=args.archive)
    else:
        run_root = HERE.parents[1] / "runs"
        if not args.out.resolve().is_relative_to(run_root.resolve()) or args.out.resolve() == run_root.resolve():
            parser.error("--out must be a fresh child directory under the repository's ignored runs/ directory")
        result = prepare(args.out, data_root=args.data_root, archive=args.archive)
    print(json.dumps(result, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
