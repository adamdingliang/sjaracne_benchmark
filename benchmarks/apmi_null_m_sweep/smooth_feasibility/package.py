#!/usr/bin/env python3
"""Copy compact completed feasibility evidence, never raw or sorted payloads."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from analyze import sha256, write_json

FILES = ("request.json", "completion.json", "extraction.json", "predictions.json",
         "evaluation.csv", "summary.csv", "feasibility.png", "feasibility.svg")


def package(run, out):
    run, out = Path(run).resolve(strict=True), Path(out).resolve()
    if out.exists() or out == run or out.is_relative_to(run) or run.is_relative_to(out):
        raise ValueError("package must be a new, nonoverlapping output directory")
    completion = json.loads((run / "completion.json").read_text(encoding="utf-8"))
    request = json.loads((run / "request.json").read_text(encoding="utf-8"))
    if (completion["new_null_draws"] != 0 or request["new_null_draws"] != 0 or
            completion["m_count"] != 19 or completion["evaluation_rows"] != 4864 or
            completion["request_sha256"] != sha256(run / "request.json")):
        raise ValueError("not a complete no-generation nineteen-size feasibility analysis")
    for name, digest in completion["outputs_sha256"].items():
        if name not in FILES or sha256(run / name) != digest:
            raise ValueError("compact output hash mismatch or unsafe output name")
    for name, digest in request["code_sha256"].items():
        if Path(name).name != name or sha256(run / "code" / name) != digest:
            raise ValueError("execution snapshot code hash mismatch")
    out.mkdir(parents=True)
    for name in FILES:
        shutil.copy2(run / name, out / name)
    code = out / "execution_code"
    code.mkdir()
    for name in request["code_sha256"]:
        shutil.copy2(run / "code" / name, code / name)
    write_json(out / "package_sha256.json", {path.relative_to(out).as_posix(): sha256(path)
               for path in sorted(out.rglob("*")) if path.is_file()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    package(args.run, args.out)
