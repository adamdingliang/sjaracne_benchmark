#!/usr/bin/env python3
"""Download and validate open TCGA-LUAD primary-tumor STAR Counts (Python 3.9+).

Requires requests. No token, matrix transformation, or patient deduplication.
See README.md alongside this file for use and provenance semantics.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from uuid import UUID

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


API = "https://api.gdc.cancer.gov"
PROJECT = "TCGA-LUAD"
TIMEOUT = (20, 120)
EXPECTED = {
    "access": "open",
    "state": "released",
    "data_format": "TSV",
    "experimental_strategy": "RNA-Seq",
    "data_category": "Transcriptome Profiling",
    "data_type": "Gene Expression Quantification",
}
FIELDS = list(EXPECTED) + [
    "file_id", "file_name", "file_size", "md5sum", "analysis.workflow_type",
    "associated_entities.entity_id", "associated_entities.entity_type",
    "associated_entities.entity_submitter_id", "associated_entities.case_id",
    "cases.case_id", "cases.submitter_id", "cases.project.project_id",
    "cases.samples.sample_id", "cases.samples.submitter_id",
    "cases.samples.sample_type",
    "cases.samples.portions.analytes.aliquots.aliquot_id",
    "cases.samples.portions.analytes.aliquots.submitter_id",
]
COLUMNS = [
    "gene_id", "gene_name", "gene_type", "unstranded", "stranded_first",
    "stranded_second", "tpm_unstranded", "fpkm_unstranded", "fpkm_uq_unstranded",
]
SUMMARY_IDS = {"N_unmapped", "N_multimapping", "N_noFeature", "N_ambiguous"}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def json_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def build_filters():
    terms = dict(EXPECTED)
    terms.update({"cases.project.project_id": PROJECT,
                  "analysis.workflow_type": "STAR - Counts",
                  "cases.samples.sample_type": "Primary Tumor"})
    return {"op": "and", "content": [
        {"op": "in", "content": {"field": key, "value": [value]}}
        for key, value in terms.items()
    ]}


def uuid_string(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ValueError(f"Invalid canonical UUID: {value!r}")
    return value


def normalize_hit(hit):
    """Validate a file and resolve its ONE associated aliquot, not array order."""
    file_id = uuid_string(hit["file_id"])
    for key, expected in EXPECTED.items():
        if hit.get(key) != expected:
            raise ValueError(f"{file_id}: {key} must be {expected!r}")
    if hit.get("analysis", {}).get("workflow_type") != "STAR - Counts":
        raise ValueError(f"{file_id}: unexpected workflow")
    name = hit["file_name"]
    if (not isinstance(name, str) or not name.endswith(".tsv")
            or re.search(r'[<>:"/\\|?*\x00-\x1f]', name)
            or name.startswith(".") or name.endswith((".", " "))
            or name.split(".")[0].upper() in
            {"CON", "PRN", "AUX", "NUL", *[f"COM{i}" for i in range(1, 10)],
             *[f"LPT{i}" for i in range(1, 10)]}):
        raise ValueError(f"{file_id}: unsafe or unexpected TSV filename")
    size, md5 = hit["file_size"], hit["md5sum"]
    if type(size) is not int or size <= 0:
        raise ValueError(f"{file_id}: missing/invalid expected byte size")
    if not isinstance(md5, str) or not re.fullmatch(r"[0-9a-fA-F]{32}", md5):
        raise ValueError(f"{file_id}: missing/invalid expected MD5")

    entities = hit.get("associated_entities", [])
    if len(entities) != 1 or entities[0].get("entity_type") != "aliquot":
        raise ValueError(f"{file_id}: expected exactly one associated aliquot")
    entity = entities[0]
    aliquot_id = uuid_string(entity["entity_id"])
    matches = []
    for case in hit.get("cases", []):
        for sample in case.get("samples", []):
            for portion in sample.get("portions", []):
                for analyte in portion.get("analytes", []):
                    for aliquot in analyte.get("aliquots", []):
                        if aliquot.get("aliquot_id") == aliquot_id:
                            matches.append((case, sample, aliquot))
    if len(matches) != 1:
        raise ValueError(f"{file_id}: missing or ambiguous aliquot-to-sample link")
    case, sample, aliquot = matches[0]
    if case.get("project", {}).get("project_id") != PROJECT:
        raise ValueError(f"{file_id}: associated sample is not {PROJECT}")
    if sample.get("sample_type") != "Primary Tumor":
        raise ValueError(f"{file_id}: associated sample is not Primary Tumor")
    if entity.get("case_id") and entity["case_id"] != case["case_id"]:
        raise ValueError(f"{file_id}: associated case UUID mismatch")
    if entity.get("entity_submitter_id") != aliquot.get("submitter_id"):
        raise ValueError(f"{file_id}: associated aliquot barcode mismatch")
    for item in (case, sample, aliquot):
        if not item.get("submitter_id"):
            raise ValueError(f"{file_id}: missing case/sample/aliquot barcode")
    return {
        "file_id": file_id, "file_name": name, "file_size": size,
        "md5sum": md5.lower(), "state": hit["state"],
        "case_id": uuid_string(case["case_id"]),
        "case_submitter_id": case["submitter_id"],
        "sample_id": uuid_string(sample["sample_id"]),
        "sample_submitter_id": sample["submitter_id"],
        "sample_type": sample["sample_type"], "aliquot_id": aliquot_id,
        "aliquot_submitter_id": aliquot["submitter_id"],
        "relative_path": f"files/{file_id}/{name}",
    }


def make_session():
    session = requests.Session()
    session.headers.update({"User-Agent": "SJARACNe-LUAD-benchmark-downloader/1"})
    retry = Retry(total=3, backoff_factor=1, allowed_methods={"GET"},
                  status_forcelist=[429, 500, 502, 503, 504],
                  respect_retry_after_header=True)
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def get_json(session, endpoint, **kwargs):
    with session.get(API + endpoint, timeout=TIMEOUT, **kwargs) as response:
        response.raise_for_status()
        payload = response.json()
    if payload.get("warnings"):
        raise ValueError(f"GDC returned warnings: {payload['warnings']}")
    return payload


def query_files(session, page_size):
    hits, pages, seen = [], [], set()
    total = None
    while total is None or len(hits) < total:
        payload = get_json(session, "/files", params={
            "filters": json.dumps(build_filters()), "fields": ",".join(FIELDS),
            "format": "JSON", "size": page_size, "from": len(hits),
            "sort": "file_id:asc",
        })
        page = payload["data"]["hits"]
        pagination = payload["data"]["pagination"]
        if total is None:
            total = pagination["total"]
            if type(total) is not int or total <= 0:
                raise ValueError("GDC returned no matching files or an invalid total")
        if (pagination["total"] != total or pagination["from"] != len(hits)
                or pagination["count"] != len(page) or not page
                or len(hits) + len(page) > total):
            raise ValueError("Inconsistent/empty GDC page; refuse a partial cohort")
        for hit in page:
            file_id = uuid_string(hit["file_id"])
            if file_id in seen or (hits and file_id <= hits[-1]["file_id"]):
                raise ValueError("Duplicate or unsorted UUID in GDC pagination")
            seen.add(file_id)
            hits.append(hit)
        pages.append(pagination)
        print(f"Metadata: {len(hits)}/{total} files", flush=True)
    return {"files": hits, "pages": pages}


def atomic_text(path, content):
    """Publish this tool's metadata only after the complete write succeeds."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="",
                                         dir=path.parent, delete=False) as handle:
            temp = Path(handle.name)
            handle.write(content)
        os.replace(temp, path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


def save_json(path, value):
    atomic_text(path, json.dumps(value, indent=2, sort_keys=True) + "\n")


def save_tsv(path, fields, records):
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=fields, delimiter="\t",
                            lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(records)
    atomic_text(path, output.getvalue())


def load_or_query(session, outdir, page_size, offline=False):
    path = outdir / "query_snapshot.json"
    if path.exists():
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        if (snapshot.get("schema_version") != 1 or snapshot.get("api") != API
                or snapshot.get("filters") != build_filters()
                or snapshot.get("files_sha256") != json_digest(snapshot["files"])
                or snapshot.get("file_count") != len(snapshot["files"])):
            raise ValueError("Invalid or incompatible frozen query snapshot")
        print(f"Reusing frozen query from {snapshot['queried_at_utc']}")
    else:
        if offline:
            raise ValueError("--verify-only requires an existing query_snapshot.json")
        before = get_json(session, "/status")
        result = query_files(session, page_size)
        after = get_json(session, "/status")
        if not before.get("data_release") or before.get("data_release") != after.get("data_release"):
            raise ValueError("GDC release changed or is missing; repeat in a fresh directory")
        snapshot = {
            "schema_version": 1, "api": API, "project": PROJECT,
            "queried_at_utc": utc_now(), "filters": build_filters(), "fields": FIELDS,
            "sort": "file_id:asc", "page_size": page_size,
            "gdc_status_before": before, "gdc_status_after": after,
            "file_count": len(result["files"]), "files": result["files"],
            "files_sha256": json_digest(result["files"]), "pages": result["pages"],
        }
        # Validate every association before publishing the frozen cohort.
        [normalize_hit(hit) for hit in snapshot["files"]]
        save_json(path, snapshot)
    records = [normalize_hit(hit) for hit in snapshot["files"]]
    if not records or len({r["file_id"] for r in records}) != len(records):
        raise ValueError("Frozen cohort is empty or contains duplicate file UUIDs")
    return snapshot, records


def validate_star(path):
    """Check every row; N_* STAR summaries are not expression genes."""
    genes, summaries, comments = set(), set(), []
    gene_hash, annotation_hash = hashlib.sha256(), hashlib.sha256()
    with path.open(encoding="utf-8", newline="") as handle:
        first = handle.readline()
        while first.startswith("#"):
            comments.append(first.strip())
            first = handle.readline()
        header = next(csv.reader([first], delimiter="\t"))
        if header != COLUMNS:
            raise ValueError(f"{path.name}: unexpected augmented STAR Counts header")
        for line_number, row in enumerate(csv.reader(handle, delimiter="\t"), start=2 + len(comments)):
            if len(row) != len(COLUMNS):
                raise ValueError(f"{path.name}:{line_number}: malformed TSV row")
            gene = row[0]
            for value in row[3:6]:
                if not re.fullmatch(r"[0-9]+", value):
                    raise ValueError(f"{gene}: count must be a nonnegative integer")
            if gene in SUMMARY_IDS:
                if gene in summaries:
                    raise ValueError(f"Duplicate STAR summary row: {gene}")
                summaries.add(gene)
                continue
            if not re.fullmatch(r"ENSG[0-9]+(?:\.[0-9]+)?(?:_PAR_Y)?", gene):
                raise ValueError(f"Unexpected gene identifier: {gene!r}")
            if gene in genes:
                raise ValueError(f"Duplicate gene ID: {gene}")
            if not row[1] or not row[2]:
                raise ValueError(f"Missing gene name/type: {gene}")
            for value in row[6:9]:
                numeric = float(value)
                if not math.isfinite(numeric) or numeric < 0:
                    raise ValueError(f"{gene}: normalized values must be finite and nonnegative")
            genes.add(gene)
            gene_hash.update((gene + "\n").encode("utf-8"))
            annotation_hash.update(("\t".join(row[:3]) + "\n").encode("utf-8"))
    if not genes or summaries != SUMMARY_IDS:
        raise ValueError(f"{path.name}: no genes or incomplete STAR summary rows")
    return {"gene_rows": len(genes), "gene_id_sha256": gene_hash.hexdigest(),
            "gene_annotation_sha256": annotation_hash.hexdigest(),
            "gene_model": "; ".join(comments)}


def verify_file(path, record):
    if path.stat().st_size != record["file_size"]:
        raise ValueError(f"{path.name}: byte-size mismatch")
    md5, sha256 = hashlib.md5(), hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            md5.update(chunk)
            sha256.update(chunk)
    if md5.hexdigest() != record["md5sum"]:
        raise ValueError(f"{path.name}: MD5 mismatch")
    return {"file_size": path.stat().st_size, "observed_md5": md5.hexdigest(),
            "sha256": sha256.hexdigest(), **validate_star(path)}


def download_file(session, record, outdir, attempts):
    path = outdir / "files" / record["file_id"] / record["file_name"]
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            return {"status": "already_valid", **verify_file(path, record)}
        except ValueError as exc:
            print(f"  Existing file failed validation; downloading replacement: {exc}")
    for attempt in range(1, attempts + 1):
        temp = None
        try:
            with tempfile.NamedTemporaryFile(mode="wb", dir=path.parent,
                                             suffix=".part", delete=False) as handle:
                temp = Path(handle.name)
                with session.get(API + "/data/" + record["file_id"], stream=True,
                                 timeout=TIMEOUT) as response:
                    response.raise_for_status()
                    size = 0
                    for chunk in response.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            size += len(chunk)
                            if size > record["file_size"]:
                                raise ValueError("Download exceeds expected byte size")
                            handle.write(chunk)
            validation = verify_file(temp, record)
            os.replace(temp, path)
            return {"status": "downloaded", **validation}
        except (requests.RequestException, ValueError) as exc:
            # A retry re-downloads this file; it never resumes unchecked bytes.
            if attempt == attempts:
                raise
            print(f"  Attempt {attempt}/{attempts} failed: {exc}; retrying", flush=True)
            time.sleep(min(2 ** (attempt - 1), 30))
        finally:
            if temp is not None and temp.exists():
                temp.unlink()


def duplicate_groups(records, key):
    groups = defaultdict(list)
    for record in records:
        groups[record[key]].append(record["file_id"])
    return {key: values for key, values in sorted(groups.items()) if len(values) > 1}


def positive_int(value):
    value = int(value)
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outdir", type=Path, default=Path("downloads/TCGA_LUAD_STAR_Counts"))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--metadata-only", action="store_true", help="Freeze/query metadata; download no expression files")
    mode.add_argument("--verify-only", action="store_true", help="Offline validation of files against the frozen query")
    parser.add_argument("--max-files", type=positive_int, help="Process only first N UUIDs for a smoke test; not cohort selection")
    parser.add_argument("--page-size", type=positive_int, default=100)
    parser.add_argument("--attempts", type=positive_int, default=3, help="Maximum whole-file download attempts")
    args = parser.parse_args(argv)
    outdir = args.outdir.resolve()
    outdir.mkdir(parents=True, exist_ok=True)
    with make_session() as session:
        snapshot, records = load_or_query(session, outdir, args.page_size, args.verify_only)
        save_tsv(outdir / "metadata.tsv", list(records[0]), records)
        save_tsv(outdir / "gdc_manifest.tsv", ["id", "filename", "md5", "size", "state"], [
            {"id": r["file_id"], "filename": r["file_name"], "md5": r["md5sum"],
             "size": r["file_size"], "state": r["state"]} for r in records])
        summary = {
            "file_count": len(records), "expected_bytes": sum(r["file_size"] for r in records),
            "unique_cases": len({r["case_id"] for r in records}),
            "unique_samples": len({r["sample_id"] for r in records}),
            "duplicate_cases": duplicate_groups(records, "case_submitter_id"),
            "duplicate_samples": duplicate_groups(records, "sample_submitter_id"),
            "duplicate_aliquots": duplicate_groups(records, "aliquot_submitter_id"),
            "selection_policy": "All matching files retained; no patient/sample deduplication.",
            "gdc_data_release": snapshot["gdc_status_before"]["data_release"],
        }
        save_json(outdir / "cohort_summary.json", summary)
        print(f"{len(records)} files; {summary['unique_cases']} patients; "
              f"{summary['unique_samples']} samples; {summary['expected_bytes'] / 2**30:.2f} GiB")
        if summary["duplicate_cases"]:
            print("WARNING: repeated patients/files; see cohort_summary.json before selecting benchmark samples.")
        if args.metadata_only:
            print(f"Metadata only; expression files have NOT been validated. Output: {outdir}")
            return 0

        selected = records[:args.max_files] if args.max_files else records
        report = {
            "started_at_utc": utc_now(), "status": "in_progress", "complete_cohort": False,
            "cohort_file_count": len(records), "requested_file_count": len(selected),
            "mode": "verify_only" if args.verify_only else "download",
            "max_files": args.max_files, "files_metadata_sha256": snapshot["files_sha256"],
            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "python_version": sys.version, "requests_version": requests.__version__, "files": [],
        }
        report_path = outdir / "validation_report.json"
        save_json(report_path, report)
        reference_annotation = None
        for index, record in enumerate(selected, 1):
            print(f"[{index}/{len(selected)}] {record['file_id']} {record['sample_submitter_id']}", flush=True)
            try:
                if args.verify_only:
                    result = {"status": "verified", **verify_file(outdir / record["relative_path"], record)}
                else:
                    result = download_file(session, record, outdir, args.attempts)
                fingerprint = (result["gene_model"], result["gene_annotation_sha256"])
                if reference_annotation is None:
                    reference_annotation = fingerprint
                if fingerprint != reference_annotation:
                    raise ValueError("Gene annotation/order/model differs from the first validated file")
            except (OSError, ValueError, requests.RequestException) as exc:
                result = {"status": "failed", "error": str(exc)}
                print(f"  FAILED: {exc}", file=sys.stderr)
            report["files"].append({"file_id": record["file_id"], **result})
        counts = Counter(r["status"] for r in report["files"])
        report.update({"finished_at_utc": utc_now(), "status_counts": dict(counts),
                       "status": "failed" if counts["failed"] else "passed",
                       "complete_cohort": not counts["failed"] and len(selected) == len(records)})
        save_json(report_path, report)
        print(f"Validation: {report['status']}; complete cohort: {report['complete_cohort']}. Output: {outdir}")
        return 1 if counts["failed"] else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, requests.RequestException) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("Interrupted; rerun to revalidate and skip completed files.", file=sys.stderr)
        sys.exit(130)
