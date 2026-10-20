#!/usr/bin/env python3
"""Additional fixed correlated-hub inference cases using the frozen harness.

This adds inferred nonzero-pruning coverage without changing probabilities,
epsilon values, seeds, sampling, estimator, or the original differential report.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True
import check_diagnostics as core


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True, type=Path)
    parser.add_argument("--candidate", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--config-dir", required=True, type=Path)
    parser.add_argument("--timeout", type=float, default=30.)
    args = parser.parse_args()
    for key in ("baseline", "candidate", "output_dir", "config_dir"):
        setattr(args, key, getattr(args, key).resolve())
    for binary in (args.baseline, args.candidate):
        if not binary.is_file():
            parser.error("binary not found: " + str(binary))
    if not (args.config_dir / "config_threshold.txt").is_file():
        parser.error("--config-dir must contain config_threshold.txt")
    if args.output_dir.exists():
        parser.error("--output-dir already exists; use a fresh directory")
    args.output_dir.mkdir(parents=True)
    cases = core.inference_cases()
    for case in cases:
        case.selected = [0, 3, 6]
        case.name = "correlated_" + case.name
    runner = core.Runner(args)
    report = dict(
        scope="additional lightweight correlated-hub inference diagnostic differential",
        fixture_change="fixed selected source indices [0,3,6]; all other inputs unchanged",
        baseline=str(args.baseline), baseline_sha256=core.sha256(args.baseline),
        candidate=str(args.candidate), candidate_sha256=core.sha256(args.candidate),
        harness_sha256=core.sha256(Path(core.__file__).resolve()),
        supplementary_script_sha256=core.sha256(Path(__file__).resolve()),
        affine_config_sha256=core.sha256(args.config_dir / "config_threshold.txt"),
        total_cases=len(cases), cases=[])
    started = time.perf_counter()
    for index, case in enumerate(cases):
        try:
            result = runner.check_case(case, args.output_dir / ("%03d_" % index + case.name))
        except Exception as error:
            result = dict(name=case.name, passed=False,
                          error=type(error).__name__ + ": " + str(error))
        result["model"] = case.model or ("explicit" if case.threshold else "legacy")
        report["cases"].append(result)
        print("[%d/%d] %s %s" % (index + 1, len(cases),
                                 "PASS" if result["passed"] else "FAIL", case.name), flush=True)
        if not result["passed"]:
            print("  " + result["error"], flush=True)
        report.update(
            passed=sum(row["passed"] for row in report["cases"]),
            failed=sum(not row["passed"] for row in report["cases"]),
            binary_invocations=runner.invocations,
            elapsed_seconds=time.perf_counter() - started)
        (args.output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n",
                                                    encoding="utf-8")
    report["nonzero_pruning_cases"] = [row["name"] for row in report["cases"]
                                       if row["passed"] and row["statistics"]["pruned_edges"] > 0]
    report["nonzero_pchip_pruning_cases"] = [row["name"] for row in report["cases"]
                                             if row["passed"] and row["model"] == "pchip" and
                                             row["statistics"]["pruned_edges"] > 0]
    report["required_nonzero_pchip_pruning_observed"] = bool(report["nonzero_pchip_pruning_cases"])
    if not report["required_nonzero_pchip_pruning_observed"]:
        report["qualification_error"] = "No nonzero PCHIP pruning observed; integration coverage incomplete"
    (args.output_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n",
                                                encoding="utf-8")
    print(json.dumps({key: report[key] for key in
                      ("passed", "failed", "binary_invocations", "elapsed_seconds",
                       "required_nonzero_pchip_pruning_observed", "nonzero_pchip_pruning_cases")}))
    return 1 if report["failed"] or not report["required_nonzero_pchip_pruning_observed"] else 0


if __name__ == "__main__":
    sys.exit(main())
