#!/usr/bin/env python3
"""Download public TCGA-LUAD STAR gene counts with file-level provenance."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


API_ROOT = "https://api.gdc.cancer.gov"
PROJECT = "TCGA-LUAD"
WORKFLOW = "STAR - Counts"
PAGE_SIZE = 500
FIELDS = (
    "file_id", "file_name", "file_size", "md5sum", "access",
    "experimental_strategy", "data_category", "data_type",
    "analysis.workflow_type", "cases.case_id", "cases.submitter_id",
    "cases.samples.sample_id", "cases.samples.submitter_id",
    "cases.samples.sample_type",
)
METADATA_COLUMNS = (
    "file_id", "file_name", "file_size", "md5sum", "case_uuid",
    "case_id", "sample_uuid", "sample_id", "sample_type", "relative_path",
)
FILTERS = {
    "op": "and",
    "content": [
        {"op": "in", "content": {"field": field, "value": [value]}}
        for field, value in (
            ("cases.project.project_id", PROJECT),
            ("experimental_strategy", "RNA-Seq"),
            ("data_category", "Transcriptome Profiling"),
            ("data_type", "Gene Expression Quantification"),
            ("analysis.workflow_type", WORKFLOW),
            ("access", "open"),
        )
    ],
}


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=4,
        backoff_factor=1,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = "SJARACNe-TCGA-LUAD-benchmark-downloader/1"
    return session


def checked_uuid(value: object, label: str) -> str:
    try:
        result = str(uuid.UUID(str(value)))
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"Invalid {label}: {value!r}") from exc
    return result


def validate_record(hit: dict, sample_type: str) -> dict | None:
    """Select by the sample actually linked to this file, not by case alone."""
    if hit.get("access") != "open":
        raise ValueError(f"Non-public file in GDC response: {hit.get('file_id')}")
    expected = {
        "experimental_strategy": "RNA-Seq",
        "data_category": "Transcriptome Profiling",
        "data_type": "Gene Expression Quantification",
    }
    for field, value in expected.items():
        if hit.get(field) != value:
            raise ValueError(f"Unexpected {field} for {hit.get('file_id')}: {hit.get(field)!r}")
    if hit.get("analysis", {}).get("workflow_type") != WORKFLOW:
        raise ValueError(f"Unexpected workflow for {hit.get('file_id')}")

    cases = hit.get("cases", [])
    if len(cases) != 1 or len(cases[0].get("samples", [])) != 1:
        raise ValueError(f"Ambiguous case/sample linkage for {hit.get('file_id')}")
    case = cases[0]
    sample = case["samples"][0]
    if sample.get("sample_type") != sample_type:
        return None

    file_id = checked_uuid(hit.get("file_id"), "file_id")
    name = hit.get("file_name")
    if (
        not isinstance(name, str) or not name or name in (".", "..")
        or PurePosixPath(name).name != name
        or PureWindowsPath(name).name != name
        or not name.endswith(".tsv")
    ):
        raise ValueError(f"Unsafe or unexpected GDC file name: {name!r}")
    size = hit.get("file_size")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0:
        raise ValueError(f"Invalid file_size for {file_id}: {size!r}")
    digest = hit.get("md5sum")
    if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", digest):
        raise ValueError(f"Missing or invalid MD5 for {file_id}")

    case_id = case.get("submitter_id")
    sample_id = sample.get("submitter_id")
    if not case_id or not sample_id or not sample_id.startswith(case_id + "-"):
        raise ValueError(f"Invalid case/sample barcode for {file_id}")
    return {
        "file_id": file_id,
        "file_name": name,
        "file_size": size,
        "md5sum": digest.lower(),
        "case_uuid": checked_uuid(case.get("case_id"), "case_id"),
        "case_id": case_id,
        "sample_uuid": checked_uuid(sample.get("sample_id"), "sample_id"),
        "sample_id": sample_id,
        "sample_type": sample_type,
        "relative_path": f"files/{file_id}/{name}",
    }


def query_files(session: requests.Session, sample_type: str) -> tuple[list[dict], int]:
    records = []
    seen = set()
    offset = 0
    total = None
    while total is None or offset < total:
        params = {
            "filters": json.dumps(FILTERS, separators=(",", ":")),
            "fields": ",".join(FIELDS),
            "format": "JSON",
            "size": PAGE_SIZE,
            "from": offset,
            "sort": "file_id:asc",
        }
        response = session.get(f"{API_ROOT}/files", params=params, timeout=(30, 120))
        response.raise_for_status()
        data = response.json()["data"]
        hits = data["hits"]
        page = data["pagination"]
        current_total = page["total"]
        if not isinstance(current_total, int) or current_total < 1:
            raise ValueError("GDC query returned no files")
        if total is None:
            total = current_total
        if current_total != total or page["from"] != offset or page["count"] != len(hits):
            raise ValueError("GDC pagination changed or was incomplete; retry the query")
        expected_count = min(PAGE_SIZE, total - offset)
        if len(hits) != expected_count:
            raise ValueError("GDC returned an incomplete page; retry the query")
        for hit in hits:
            file_id = checked_uuid(hit.get("file_id"), "file_id")
            if file_id in seen:
                raise ValueError(f"Repeated file ID across GDC pages: {file_id}")
            seen.add(file_id)
            record = validate_record(hit, sample_type)
            if record is not None:
                records.append(record)
        offset += len(hits)
    if not records:
        raise ValueError(f"No {sample_type} files found")
    records.sort(key=lambda row: row["file_id"])
    return records, total


def metadata_bytes(records: list[dict]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output, fieldnames=METADATA_COLUMNS, delimiter="\t", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(records)
    return output.getvalue().encode("utf-8")


def save_snapshot(outdir: Path, records: list[dict], total: int, sample_type: str) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
    metadata = outdir / "metadata.tsv"
    content = metadata_bytes(records)
    if metadata.exists():
        if metadata.read_bytes() != content:
            raise RuntimeError(
                f"GDC selection differs from the existing {metadata}; use a new output "
                "directory to keep benchmark provenance unambiguous"
            )
    else:
        temporary = outdir / "metadata.tsv.tmp"
        temporary.write_bytes(content)
        os.replace(temporary, metadata)

    provenance = outdir / "query.json"
    if not provenance.exists():
        details = {
            "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
            "api_root": API_ROOT,
            "project": PROJECT,
            "filters": FILTERS,
            "sample_type": sample_type,
            "sort": "file_id:asc",
            "query_file_count": total,
            "selected_file_count": len(records),
            "metadata_file": "metadata.tsv",
        }
        temporary = outdir / "query.json.tmp"
        temporary.write_text(json.dumps(details, indent=2) + "\n", encoding="utf-8")
        os.replace(temporary, provenance)


def check_file(path: Path, expected_size: int, expected_md5: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    size = path.stat().st_size
    if size != expected_size:
        raise ValueError(f"Size mismatch for {path}: expected {expected_size}, got {size}")
    digest = hashlib.md5()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != expected_md5:
        raise ValueError(f"MD5 mismatch for {path}: expected {expected_md5}, got {digest.hexdigest()}")


def download_one(session: requests.Session, outdir: Path, row: dict) -> bool:
    destination = outdir / row["relative_path"]
    if destination.exists():
        check_file(destination, row["file_size"], row["md5sum"])
        return False

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    url = f"{API_ROOT}/data/{row['file_id']}"
    with session.get(url, stream=True, timeout=(30, 120)) as response:
        response.raise_for_status()
        with partial.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    handle.write(chunk)
    check_file(partial, row["file_size"], row["md5sum"])
    os.replace(partial, destination)
    return True


def read_snapshot(outdir: Path) -> list[dict]:
    with (outdir / "metadata.tsv").open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if tuple(reader.fieldnames or ()) != METADATA_COLUMNS:
            raise ValueError("Unexpected metadata.tsv columns")
        rows = list(reader)
    if not rows:
        raise ValueError("Empty metadata.tsv")
    for row in rows:
        file_id = checked_uuid(row["file_id"], "file_id")
        name = row["file_name"]
        if (
            not name or name in (".", "..")
            or PurePosixPath(name).name != name
            or PureWindowsPath(name).name != name
            or row["relative_path"] != f"files/{file_id}/{name}"
        ):
            raise ValueError(f"Invalid metadata path for {file_id}")
        row["file_size"] = int(row["file_size"])
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--outdir", type=Path, default=Path("downloads/TCGA_LUAD_STAR_Counts"),
        help="Destination directory (default: downloads/TCGA_LUAD_STAR_Counts)",
    )
    parser.add_argument("--sample-type", default="Primary Tumor", help="GDC sample type")
    parser.add_argument("--metadata-only", action="store_true", help="Query and save metadata only")
    parser.add_argument("--verify-only", action="store_true", help="Verify all files in saved metadata")
    parser.add_argument("--max-files", type=int, help="Download first N file IDs for a smoke test")
    args = parser.parse_args()
    if args.metadata_only and args.verify_only:
        parser.error("--metadata-only and --verify-only are mutually exclusive")
    if args.verify_only and args.max_files is not None:
        parser.error("--verify-only cannot be combined with --max-files")
    if args.max_files is not None and args.max_files < 1:
        parser.error("--max-files must be positive")

    if args.verify_only:
        records = read_snapshot(args.outdir)
        for index, row in enumerate(records, 1):
            check_file(args.outdir / row["relative_path"], row["file_size"], row["md5sum"])
            print(f"[{index}/{len(records)}] verified {row['file_id']}")
        print(f"Verified all {len(records)} files in {args.outdir.resolve()}")
        return

    with make_session() as session:
        records, total = query_files(session, args.sample_type)
        save_snapshot(args.outdir, records, total, args.sample_type)
        print(f"GDC returned {total} matching files; selected {len(records)} {args.sample_type} files")
        print(f"Metadata: {(args.outdir / 'metadata.tsv').resolve()}")
        if args.metadata_only:
            return
        selected = records[: args.max_files] if args.max_files else records
        downloaded = 0
        for index, row in enumerate(selected, 1):
            is_new = download_one(session, args.outdir, row)
            downloaded += is_new
            action = "downloaded" if is_new else "verified existing"
            print(f"[{index}/{len(selected)}] {action}: {row['sample_id']} / {row['file_id']}", flush=True)
        print(
            f"Finished {len(selected)}/{len(records)} selected files "
            f"({downloaded} downloaded this run). Output: {args.outdir.resolve()}"
        )
        if args.max_files:
            print("Smoke-test limit was used; the full selection remains in metadata.tsv")


if __name__ == "__main__":
    main()
