#!/usr/bin/env python3
"""Final-scoring-only recovery after the recorded Windows progress-file error.

Freeze validates and pins existing compact records without opening arrays. Run
rechecks that lock before calling the original frozen scoring implementation.
There are no fit, selection, extraction, simulation, fallback or retry calls.
Original analysis files are never changed; completion status is written once
with exclusive creation, not os.replace or a recurring progress update.
"""
from __future__ import annotations

import argparse
import math
from pathlib import Path
import shutil

try:
    from . import fit_pipeline as pipeline
except ImportError:
    import fit_pipeline as pipeline


data = pipeline.fit_data
gen = pipeline.generate
HERE = Path(__file__).resolve().parent
SCHEMA = "apmi-final-scoring-operational-recovery-v1"
SOURCE_LOCKS = ("request", "access_initial", "initial_models", "selection", "access_selected",
                "refit_models", "primary", "access_final", "training_index", "development_index",
                "refit_index", "validation_index")
PURPOSES = {"validation": "final_validation_score_only", "refit": "selected_procedure_full10M_refit",
            "test_fit": "final_test_fit_diagnostic_only"}


def _not_scored(root):
    if any((Path(root) / name).exists() for name in ("final_scores.csv", "summary.json", "summary.sha256")):
        raise ValueError("existing final statistics prohibit this scoring-only recovery")


def _failure(root):
    value = gen.read_json(Path(root) / "failure.json")
    error = value.get("error", "")
    if not isinstance(error, str) or not error.startswith("PermissionError(13,"):
        raise ValueError("recovery applies only to the recorded PermissionError13 progress-status failure")
    return value


def _quantiles(cache):
    quantiles = cache.get("quantiles")
    expected = list(pipeline.GRID.ALL_P)
    if not isinstance(quantiles, list) or [row.get("p") for row in quantiles] != expected:
        raise ValueError("exact49 frozen probability quantiles required")
    previous = -math.inf
    m = cache["source"]["task"]["m"]
    for row in quantiles:
        if set(row) != {"p", "cutoff", "cutoff_hex"} or isinstance(row["cutoff"], bool):
            raise ValueError("malformed empirical quantile record")
        cutoff = float(row["cutoff"])
        if (not math.isfinite(cutoff) or not 0 <= cutoff <= math.log(m) + data.SUPPORT_TOLERANCE
                or not isinstance(row["cutoff_hex"], str) or cutoff.hex() != row["cutoff_hex"]):
            raise ValueError("invalid literal empirical cutoff/hex/support")
        if cutoff < previous:
            raise ValueError("crossed exact empirical quantiles")
        previous = cutoff


def _source(cache, plan, plan_hash, m, stream):
    """Verify cached lineage against small original generation checkpoints.

    Extraction already verified the unchanged native bytes. This checks the
    pinned checkpoint, metadata and literal raw-record identity without opening
    native distributions again. Scoring separately rehashes its cached arrays.
    """
    identity = cache.get("source", {})
    task = data._find_task(plan, m, stream)
    directory = Path(plan["output_dir"]) / "streams" / task["id"]
    checkpoint = directory / "complete.json"
    expected_checkpoint = gen.record(checkpoint)
    if (identity.get("plan_sha256") != plan_hash or identity.get("task") != task
            or identity.get("checkpoint") != expected_checkpoint
            or identity.get("generator_sha256") != plan["pins"]["generator"]["sha256"]
            or identity.get("engine_commit") != plan["engine_commit"]):
        raise ValueError("cache source generation identity mismatch")
    complete = gen.read_json(checkpoint)
    if (complete.get("status") != "complete" or complete.get("returncode") != 0
            or complete.get("task") != task or complete.get("plan_sha256") != plan_hash):
        raise ValueError("cache source lacks original successful completion")
    if (identity.get("raw") != complete.get("artifacts", {}).get("null.f64")
            or identity.get("metadata") != complete.get("artifacts", {}).get("null.f64.meta")):
        raise ValueError("cache raw/metadata lineage differs from native checkpoint")
    data._check_record(identity["metadata"])
    raw = identity["raw"]
    if (Path(raw["path"]).resolve() != (directory / "null.f64").resolve()
            or raw["bytes"] != data.N_DRAWS * 8):
        raise ValueError("unexpected original raw path or size")
    audit = identity.get("normalization", {})
    count = audit.get("negative_count")
    minimum = audit.get("raw_minimum")
    if (audit.get("policy") != data.NORMALIZATION_POLICY or audit.get("tolerance") != data.SUPPORT_TOLERANCE
            or isinstance(count, bool) or not isinstance(count, int) or not 0 <= count <= data.N_DRAWS
            or audit.get("normalized_to_positive_zero_count") != count
            or isinstance(minimum, bool) or not isinstance(minimum, (int, float)) or not math.isfinite(minimum)
            or minimum < -data.SUPPORT_TOLERANCE or minimum > math.log(m) + data.SUPPORT_TOLERANCE
            or (count == 0 and minimum < 0) or (count > 0 and minimum >= 0)):
        raise ValueError("invalid pinned numerical-zero normalization provenance")


def validate_cache(record, m, phase, root, plan, plan_hash):
    """Validate metadata/lineage only; never call np.load or load_array."""
    expected = Path(root) / "cache" / phase / f"m{m:05d}" / "cache.json"
    if Path(record["path"]).resolve() != expected.resolve():
        raise ValueError("cache record is outside the expected original phase directory")
    data._check_record(record)
    cache = gen.read_json(record["path"])
    if cache.get("format") != data.SCHEMA or cache.get("purpose") != PURPOSES[phase]:
        raise ValueError("cache schema or purpose mismatch")
    gate = "access_selected.json" if phase == "refit" else "access_final.json"
    if cache.get("phase_lock") != gen.record(Path(root) / gate):
        raise ValueError("cache phase-lock mismatch")
    _source(cache, plan, plan_hash, m, "validation" if phase == "validation" else "fit")
    arrays = cache.get("arrays")
    if phase == "validation":
        if not isinstance(arrays, dict) or set(arrays) != {"score"} or cache.get("quantiles") != []:
            raise ValueError("validation cache must be score-only")
        score = arrays["score"]
        artifact = score.get("artifact", {})
        if (score.get("draws") != data.N_DRAWS or score.get("dtype") != "float64" or score.get("sorted") is not True
                or set(artifact) != {"path", "bytes", "sha256"}
                or Path(artifact["path"]).resolve() != expected.with_name("score.npy").resolve()
                or not isinstance(artifact["bytes"], int) or artifact["bytes"] <= data.N_DRAWS * 8
                or not isinstance(artifact["sha256"], str) or len(artifact["sha256"]) != 64):
            raise ValueError("invalid cached scoring-array metadata")
        # Existence and byte size are operational checks, not array reads.
        data._reject_links(artifact["path"])
        if not Path(artifact["path"]).is_file() or Path(artifact["path"]).stat().st_size != artifact["bytes"]:
            raise ValueError("cached scoring array missing or changed size")
        summary = score.get("summary", {})
        if (summary.get("draws") != data.N_DRAWS or not 0 <= summary.get("zero_count", -1) <= data.N_DRAWS
                or not 1 <= summary.get("unique_count", 0) <= data.N_DRAWS
                or not isinstance(summary.get("minimum"), (int, float))
                or not isinstance(summary.get("maximum"), (int, float))
                or not 0 <= summary["minimum"] <= summary["maximum"] <= math.log(m) + data.SUPPORT_TOLERANCE):
            raise ValueError("invalid cached scoring-array summary")
    else:
        if arrays != {}:
            raise ValueError("exact-m diagnostic cache must not contain arrays")
        _quantiles(cache)
    return cache


def indexed(root, phase, expected, plan, plan_hash):
    index = pipeline.read_locked(Path(root) / (phase + "_index.json"))
    records = index.get("records", [])
    if index.get("phase") != phase or [row.get("m") for row in records] != list(expected):
        raise ValueError("missing, duplicate or unexpected indexed cache sizes")
    return {row["m"]: validate_cache(row["cache"], row["m"], phase, root, plan, plan_hash) for row in records}, records


def collect(source):
    """Read only frozen model/selection/cache metadata, never score arrays."""
    source = Path(source).resolve(strict=True)
    data._reject_links(source)
    boundary = (gen.repo_root() / "runs").resolve(strict=True)
    if source == boundary or not source.is_relative_to(boundary):
        raise ValueError("source must be an existing ignored analysis run")
    _not_scored(source)
    _failure(source)
    request = pipeline.check_request(source / "request.json")
    if Path(request["output_dir"]).resolve() != source:
        raise ValueError("source analysis directory differs from its original request")
    plan, plan_hash = gen.load_plan(request["generation_plan"]["path"])
    if plan_hash != request["plan_sha256"] or plan_hash != pipeline.GENERATION_HASH:
        raise ValueError("source generation-plan hash mismatch")
    data._authorize(source / "access_final.json", "frozen", plan_hash)
    values = {name: pipeline.read_locked(source / (name + ".json")) for name in SOURCE_LOCKS}
    selection, primary, refits = values["selection"], values["primary"], values["refit_models"]
    if (selection.get("selected_model") != "pchip" or selection.get("selected_method") != "pchip"
            or selection.get("eligible") is not True or selection.get("no_fallback") is not True
            or primary.get("selected_model") != "pchip"
            or set(refits.get("models", {})) != set(pipeline.METHODS)
            or primary.get("surface", {}).get("fit_models") != refits["models"]["pchip"]
            or refits.get("shape_checks", {}).get("pchip", {}).get("eligible") is not True):
        raise ValueError("frozen PCHIP primary, comparator or no-fallback identity mismatch")
    expected_refit = sorted(request["groups"]["training"] + request["groups"]["development"])
    if primary.get("training_m") != expected_refit:
        raise ValueError("frozen primary refit coverage changed")
    validation, validation_records = indexed(source, "validation", list(gen.GRID), plan, plan_hash)
    refit, refit_records = indexed(source, "refit", expected_refit, plan, plan_hash)
    tests, test_records = {}, []
    for m in request["groups"]["final_interpolation_test"]:
        path = source / "cache" / "test_fit" / f"m{m:05d}" / "cache.json"
        if not path.is_file():
            raise ValueError("missing completed test-fitting cache; extraction is not authorized by recovery")
        record = gen.record(path)
        tests[m] = validate_cache(record, m, "test_fit", source, plan, plan_hash)
        test_records.append({"m": m, "cache": record})
    if (source / "test_fit_index.json").exists():
        previous = pipeline.read_locked(source / "test_fit_index.json")
        if previous != {"phase": "test_fit", "records": test_records}:
            raise ValueError("existing test-fitting index differs from completed caches")
    return {"source": source, "request": request, "values": values, "validation": validation,
            "refit": refit, "test_fit": tests,
            "records": {"validation": validation_records, "refit": refit_records, "test_fit": test_records}}


def _fresh_out(out, source):
    out = Path(out).absolute()
    data._reject_links(out)
    boundary = (gen.repo_root() / "runs").resolve(strict=True)
    target = out.resolve()
    if (out.exists() or target == boundary or not target.is_relative_to(boundary)
            or target != Path(str(source) + "_final_recovery")
            or target == source or target.is_relative_to(source) or source.is_relative_to(target)):
        raise ValueError("recovery output must be a fresh separate child of ignored runs/")
    return out


def freeze(args):
    evidence = collect(args.analysis)
    source = evidence["source"]
    out = _fresh_out(args.out, source)
    pins = {name: gen.record(HERE / name) for name in
            ("fit_finish.py", "test_fit_finish.py", "CORRECTION_STATUS_IO_2026-10-17.md")}
    for stem in SOURCE_LOCKS:
        for suffix in (".json", ".sha256"):
            name = stem + suffix
            pins["original_" + name] = gen.record(source / name)
    pins["source_failure"] = gen.record(source / "failure.json")
    for phase, records in evidence["records"].items():
        for row in records:
            pins[f"cache_{phase}_{row['m']}"] = row["cache"]
    for name in ("internal_scores.csv", "development_scores.csv"):
        if (source / name).is_file():
            pins["original_" + name] = gen.record(source / name)
    if (source / "test_fit_index.json").exists():
        pins["original_test_fit_index.json"] = gen.record(source / "test_fit_index.json")
        pins["original_test_fit_index.sha256"] = gen.record(source / "test_fit_index.sha256")
    request = {"format": SCHEMA, "created_utc": gen.utc_now(), "source_analysis": str(source),
               "output_dir": str(out), "pins": pins, "primary": "pchip", "no_fallback": True,
               "frozen_original_request_sha256": gen.sha256(source / "request.json"),
               "generation_plan_sha256": evidence["request"]["plan_sha256"],
               "records": evidence["records"],
               "only_final_scoring": True, "new_fitting_selection_extraction_or_draws": False,
               "no_final_counts_before_this_lock": True,
               "status_policy": "exclusive one-time completion write; no progress-file replacement"}
    out.mkdir(parents=True, exist_ok=False)
    pipeline.locked_write(out / "recovery_request.json", request)
    print({"recovery_request": str(out / "recovery_request.json"), "sha256": gen.sha256(out / "recovery_request.json")}, flush=True)


def _copy(record, target):
    data._check_record(record)
    target = Path(target)
    if target.exists():
        raise ValueError("refuse to overwrite compact recovery artifact")
    shutil.copy2(record["path"], target)
    if gen.sha256(target) != record["sha256"] or gen.record(record["path"]) != record:
        raise ValueError("compact source changed during recovery copy")


def run(args):
    lock = Path(args.request).resolve(strict=True)
    request = pipeline.read_locked(lock)
    out = Path(request["output_dir"]).resolve(strict=True)
    if (request.get("format") != SCHEMA or lock != out / "recovery_request.json"
            or request.get("primary") != "pchip" or request.get("no_fallback") is not True
            or request.get("only_final_scoring") is not True
            or request.get("new_fitting_selection_extraction_or_draws") is not False):
        raise ValueError("invalid final-scoring-only recovery lock")
    _not_scored(out)
    if (out / "failure.json").exists() or (out / "started.json").exists():
        raise ValueError("recovery is one-shot; no statistical retry is permitted")
    for record in request["pins"].values():
        data._check_record(record)
    source = Path(request["source_analysis"]).resolve(strict=True)
    if out != Path(str(source) + "_final_recovery"):
        raise ValueError("recovery must use the one fixed original-analysis sibling")
    evidence = collect(source)
    if (request["records"] != evidence["records"]
            or request["frozen_original_request_sha256"] != gen.sha256(source / "request.json")
            or request["generation_plan_sha256"] != evidence["request"]["plan_sha256"]):
        raise ValueError("frozen recovery inputs changed")
    gen.write_new(out / "started.json", {"utc": gen.utc_now(), "recovery_request_sha256": gen.sha256(lock)})
    try:
        for name, record in request["pins"].items():
            if name.startswith("original_"):
                _copy(record, out / name.removeprefix("original_"))
        _copy(request["pins"]["source_failure"], out / "source_failure.json")
        if not (out / "test_fit_index.json").exists():
            pipeline.locked_write(out / "test_fit_index.json", {"phase": "test_fit", "records": evidence["records"]["test_fit"]})
        empirical = {}
        for m, cache in {**evidence["refit"], **evidence["test_fit"]}.items():
            empirical[m] = [dict(row, m=m, available=0 < row["cutoff"] <= math.log(m), reason=None,
                                 source="exact_m_empirical") for row in cache["quantiles"]]
        # The sole array/count opening begins here, after the recovery hash lock.
        # This is the unmodified original function, not a replacement scorer.
        rows = pipeline.score_cache(evidence["validation"], evidence["values"]["refit_models"]["models"],
                                    "final_validation", "pchip", legacy=True, empirical=empirical)
        pipeline.write_csv(out / "final_scores.csv", rows)
        pipeline.locked_write(out / "summary.json", {
            "selection": evidence["values"]["selection"], "primary": evidence["values"]["primary"],
            "final_summary": pipeline.fit_report.summarize(rows), "completed_utc": gen.utc_now(),
            "operational_recovery": {"request": gen.record(lock), "source_failure": request["pins"]["source_failure"],
                                     "no_reselection_or_refitting": True}})
        gen.write_new(out / "status.json", {"phase": "complete", "primary": "pchip", "updated_utc": gen.utc_now(),
                                             "operational_recovery": True})
        print({"complete": str(out), "primary": "pchip"}, flush=True)
    except BaseException as error:
        gen.write_new(out / "failure.json", {"utc": gen.utc_now(), "error": repr(error), "no_automatic_retry": True})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    frozen = sub.add_parser("freeze")
    frozen.add_argument("--analysis", required=True, type=Path)
    frozen.add_argument("--out", required=True, type=Path)
    scoring = sub.add_parser("run")
    scoring.add_argument("--request", required=True, type=Path)
    args = parser.parse_args()
    freeze(args) if args.command == "freeze" else run(args)


if __name__ == "__main__":
    main()
