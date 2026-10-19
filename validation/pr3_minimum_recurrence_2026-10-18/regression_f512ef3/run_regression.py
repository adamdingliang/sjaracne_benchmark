#!/usr/bin/env python3
"""Fresh, revision-bound PR3 regression run; never edits the source worktree."""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import unittest

COMMIT = None
RESOURCE_ROOT = Path("/home/adam/sjaracne-regression/pr1-86f8729-20261018-r2")
REPO = Path("/mnt/d/GitHub/SJARACNe")
DEPENDENCY_PYTHON = Path("/mnt/d/GitHub/SJARACNe-pr67-develop/SJARACNe/build/pchip-test-env/bin/python")
EVIDENCE = Path(__file__).resolve().parent


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def sha(path):
    value = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def write_json(path, value):
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def clean_environment(work):
    allowed = {"PATH", "LANG", "LC_ALL", "USER", "LOGNAME", "SHELL", "TERM", "TZ"}
    env = {key: value for key, value in os.environ.items() if key in allowed}
    env.update({
        "PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1",
        "PIP_NO_INDEX": "1", "PIP_NO_INPUT": "1",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1", "PIP_CONFIG_FILE": "/dev/null",
        "PIP_CACHE_DIR": str(work / "pip-cache"), "XDG_CACHE_HOME": str(work / "cache"),
        "TMPDIR": str(work / "tmp"), "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
        "http_proxy": "http://127.0.0.1:9", "https_proxy": "http://127.0.0.1:9",
        "all_proxy": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9", "ALL_PROXY": "http://127.0.0.1:9",
    })
    return env


def flatten(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from flatten(item)
        else:
            yield item


def suite_phase(work):
    source = work / "source"
    os.chdir(source)
    sys.path.insert(0, str(source))
    loader = unittest.TestLoader()
    suite = loader.discover(str(source / "tests"), pattern="test_*.py")
    identities = [test.id() for test in flatten(suite)]
    if not identities or len(identities) != len(set(identities)) or loader.errors:
        raise RuntimeError("Empty/duplicate/error-containing discovery: " + repr(loader.errors))
    print("PINNED_COMMIT=" + COMMIT, flush=True)
    print("DISCOVERED_TESTS=" + str(len(identities)), flush=True)
    started = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2, stream=sys.stdout).run(suite)
    record = {
        "commit": COMMIT, "discovered": len(identities), "tests_run": result.testsRun,
        "test_ids": identities, "failures": [{"test": test.id(), "detail": detail} for test, detail in result.failures],
        "errors": [{"test": test.id(), "detail": detail} for test, detail in result.errors],
        "skipped": [{"test": test.id(), "reason": reason} for test, reason in result.skipped],
        "expected_failures": [test.id() for test, _ in result.expectedFailures],
        "unexpected_successes": [test.id() for test in result.unexpectedSuccesses],
        "duration_seconds": time.monotonic() - started, "finished_at_utc": now(),
        "python": sys.version, "executable": sys.executable,
        "native_sha256": sha(os.environ["SJARACNE_TEST_EXE"]),
        "generator_sha256": sha(os.environ["SJARACNE_APMI_NULL_EXE"]),
    }
    record["passed"] = bool(result.wasSuccessful() and not result.skipped
                            and not result.expectedFailures and result.testsRun == len(identities))
    write_json(EVIDENCE / "python_tests.json", record)
    return 0 if record["passed"] else 1


def main_phase(work):
    work = work.resolve()
    if not work.is_relative_to(Path("/home/adam/sjaracne-regression")) or work.exists():
        raise RuntimeError("A new isolated WSL regression directory is required: " + str(work))
    work.mkdir(parents=True)
    source = work / "source"
    source.mkdir()
    (work / "tmp").mkdir()
    env = clean_environment(work)
    manifest = {
        "schema": "sjaracne-pr3-pinned-regression-v1", "run_variant": "setup.py-compliant-scipy-1.7.3", "commit": COMMIT,
        "repository": "https://github.com/adamdingliang/SJARACNe", "started_at_utc": now(),
        "work_root": str(work), "source_root": str(source), "evidence_root": str(EVIDENCE),
        "controller_sha256": sha(__file__), "platform": platform.platform(),
        "libc": platform.libc_ver(), "steps": [], "complete": False,
        "scope": "Linux/WSL build, Python unittest, CWL validation, four Bats tests, isolated wheel import",
    }

    def persist():
        write_json(EVIDENCE / "manifest.json", manifest)

    def command(name, args, cwd=source, check=True, command_env=None):
        log = EVIDENCE / (name + ".log")
        started = time.monotonic()
        entry = {"name": name, "argv": [str(x) for x in args], "cwd": str(cwd),
                 "started_at_utc": now(), "status": "running", "log": log.name}
        manifest["steps"].append(entry)
        persist()
        print(now(), "START", name, flush=True)
        with log.open("xb") as handle:
            handle.write((json.dumps(entry, sort_keys=True) + "\n").encode())
            handle.flush()
            proc = subprocess.run(entry["argv"], cwd=cwd, env=command_env or env,
                                  stdout=handle, stderr=subprocess.STDOUT)
        entry.update({"returncode": proc.returncode, "duration_seconds": time.monotonic() - started,
                      "finished_at_utc": now(), "log_sha256": sha(log),
                      "status": "passed" if proc.returncode == 0 else "failed"})
        persist()
        print(now(), entry["status"].upper(), name, "rc=" + str(proc.returncode), flush=True)
        if check and proc.returncode:
            raise RuntimeError(name + " failed; inspect " + str(log))
        return proc.returncode

    try:
        git = ["git", "-c", "safe.directory=" + str(REPO), "-C", str(REPO)]
        actual = subprocess.check_output(git + ["rev-parse", COMMIT + "^{commit}"], env=env, text=True).strip()
        if actual != COMMIT:
            raise RuntimeError("Git revision does not match requested PR3 head")
        archive = work / "source.tar"
        with archive.open("xb") as handle:
            subprocess.run(git + ["archive", "--format=tar", COMMIT], env=env, stdout=handle, check=True)
        manifest["source_archive_sha256"] = sha(archive)
        with tarfile.open(archive) as handle:
            members = handle.getmembers()
            tracked = [member.name for member in members if member.isfile()]
            handle.extractall(source, filter="data")
        original = {name: sha(source / name) for name in tracked}
        write_json(EVIDENCE / "tracked_source_sha256.json", original)
        binary = source / "SJARACNe/bin/sjaracne.exe"
        generator = source / "SJARACNe/bin/apmi_null_generator.exe"
        if binary.exists() or generator.exists():
            raise RuntimeError("Export unexpectedly contains prebuilt native binaries")
        persist()

        dependency_code = (
            "import sys,json,importlib.metadata; "
            "print(json.dumps({'python':sys.version,'executable':sys.executable,"
            "'paths':[p for p in sys.path if p.endswith(('site-packages','dist-packages'))],"
            "'versions':{p:importlib.metadata.version(p) for p in "
            "['numpy','scipy','pandas','cwltool','pip','setuptools','wheel']}}))"
        )
        dependency = json.loads(subprocess.check_output([str(DEPENDENCY_PYTHON), "-c", dependency_code],
                                                       cwd=work, env=env, text=True))
        manifest["dependency_environment"] = dependency
        command("create_venv", [DEPENDENCY_PYTHON, "-m", "venv", "--without-pip", work / "venv"], cwd=work)
        python = work / "venv/bin/python"
        site = Path(subprocess.check_output([str(python), "-c", "import sysconfig;print(sysconfig.get_path('purelib'))"],
                                           cwd=work, env=env, text=True).strip())
        (site / "regression_dependencies.pth").write_text("\n".join(dependency["paths"]) + "\n", encoding="utf-8")
        env["PATH"] = str(work / "venv/bin") + ":" + str(binary.parent) + ":" + env.get("PATH", "/usr/bin:/bin")
        env["SJARACNE_TEST_EXE"] = str(binary)
        env["SJARACNE_APMI_NULL_EXE"] = str(generator)
        # Satisfy the stronger setup.py lower bound, without changing old environments.
        scipy_dir = work / "scipy-wheel"
        scipy_dir.mkdir()
        cached_scipy = RESOURCE_ROOT / "scipy-wheel/scipy-1.7.3-cp39-cp39-manylinux_2_17_x86_64.manylinux2014_x86_64.whl"
        if sha(cached_scipy) != "5d1cc2c19afe3b5a546ede7e6a44ce1ff52e443d12b231823268019f608b9b12":
            raise RuntimeError("Pinned cached SciPy wheel hash mismatch")
        shutil.copy2(cached_scipy, scipy_dir / cached_scipy.name)
        manifest["cached_scipy_source"] = str(cached_scipy)
        scipy_wheels = list(scipy_dir.glob("scipy-1.7.3-*.whl"))
        if len(scipy_wheels) != 1:
            raise RuntimeError("Expected one pinned SciPy 1.7.3 wheel")
        manifest["isolated_scipy_wheel"] = {"path": str(scipy_wheels[0]), "sha256": sha(scipy_wheels[0])}
        command("scipy_wheel_install", [python, "-m", "pip", "install", "--ignore-installed",
                "--no-index", "--no-deps", "--no-compile", scipy_wheels[0]], cwd=work)
        command("compiler_version", ["g++", "--version"], cwd=work)
        command("build", ["make", "-C", source / "SJARACNe", "-j", "12", "all"])
        manifest["binaries_before_tests"] = {"sjaracne": sha(binary), "null_generator": sha(generator)}
        command("binary_format", ["file", binary, generator], cwd=work)
        wheel_dir = work / "wheel"
        wheel_dir.mkdir()
        command("wheel_build", [python, "-m", "pip", "wheel", "--no-index", "--no-deps", "--no-build-isolation",
                                "--wheel-dir", wheel_dir, source])
        wheels = list(wheel_dir.glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("Expected exactly one freshly built wheel")
        manifest["wheel"] = {"path": str(wheels[0]), "sha256": sha(wheels[0])}
        command("wheel_install", [python, "-m", "pip", "install", "--ignore-installed", "--no-index", "--no-deps",
                                  "--no-compile", wheels[0]], cwd=work)
        launcher = work / "venv/bin/cwltool"
        launcher.write_text("#!" + str(python) + "\nimport importlib.metadata,sys\n"
                            "entry=next(e for e in importlib.metadata.distribution('cwltool').entry_points "
                            "if e.group=='console_scripts' and e.name=='cwltool')\n"
                            "sys.exit(entry.load()())\n", encoding="utf-8")
        launcher.chmod(0o755)
        command("cwltool_version", [launcher, "--version"], cwd=work)
        package_code = (
            "import sys,json,hashlib,importlib.metadata;from pathlib import Path;import SJARACNe; "
            "p=Path(SJARACNe.__file__).resolve(); "
            "assert str(p).startswith(sys.prefix+'/'),str(p); "
            "files=['__init__.py','sjaracne.py','apmi_cutoff.py','config/apmi_pchip.json',"
            "'bin/create_consensus_network.py','bin/sjaracne.exe','bin/apmi_null_generator.exe',"
            "'cwl/sjaracne.cwl','cwl/sjaracne_workflow.cwl','cwl/create_consensus_network.cwl']; "
            "pairs={f:(hashlib.sha256((p.parent/f).read_bytes()).hexdigest(),"
            "hashlib.sha256((Path(sys.argv[1])/'SJARACNe'/f).read_bytes()).hexdigest()) for f in files}; "
            "assert all(a==b for a,b in pairs.values()),pairs; "
            "print(json.dumps({'module':str(p),'executable':sys.executable,'prefix':sys.prefix,'hash_pairs':pairs,"
            "'versions':{x:importlib.metadata.version(x) for x in ['numpy','scipy','pandas','cwltool']}}))"
        )
        command("installed_package_identity", [python, "-c", package_code, source], cwd=work)
        package_records = [json.loads(line) for line in (EVIDENCE / "installed_package_identity.log").read_text().splitlines()
                           if line.startswith("{")]
        manifest["installed_test_environment"] = next(item for item in package_records if "hash_pairs" in item)
        requirements_code = (
            "import importlib.metadata as m,json;from packaging.requirements import Requirement; "
            "items=[Requirement(x) for x in m.requires('SJARACNe')]; "
            "assert all(r.specifier.contains(m.version(r.name),prereleases=True) for r in items "
            "if r.marker is None or r.marker.evaluate()),[(str(r),m.version(r.name)) for r in items]; "
            "print(json.dumps({r.name:m.version(r.name) for r in items}))"
        )
        command("declared_dependency_contract", [python, "-c", requirements_code], cwd=work)


        for cwl in sorted((source / "SJARACNe/cwl").glob("*.cwl")):
            command("validate_" + cwl.stem, [launcher, "--validate", cwl], cwd=work, check=False)
        command("python_tests", [python, __file__, "--phase", "suite", "--work-root", work, "--commit", COMMIT], check=False)

        # Reuse the verified pinned Ubuntu package; do not download or install globally.
        deps = work / "deps"
        deps.mkdir()
        cached_bats = RESOURCE_ROOT / "deps/bats_1.10.0-1_all.deb"
        if sha(cached_bats) != "11304638193dddce946021d665a275a6c80a0c7188eb5ba38d82661ded1e8f18":
            raise RuntimeError("Pinned cached Bats package hash mismatch")
        shutil.copy2(cached_bats, deps / cached_bats.name)
        manifest["cached_bats_source"] = str(cached_bats)
        command("bats_package_metadata", ["apt-cache", "show", "bats=1.10.0-1"], cwd=deps)
        debs = list(deps.glob("bats_*.deb"))
        if len(debs) == 1:
            expected_lines = (EVIDENCE / "bats_package_metadata.log").read_text().splitlines()
            expected = next(line.split(": ", 1)[1] for line in expected_lines if line.startswith("SHA256: "))
            actual = sha(debs[0])
            if actual != expected:
                raise RuntimeError("Cached Bats package hash mismatch")
            manifest["bats_package"] = {"path": str(debs[0]), "sha256": actual, "expected_sha256": expected}
            command("bats_package_extract", ["dpkg-deb", "--extract", debs[0], deps / "bats"], cwd=deps)
            bats = deps / "bats/usr/bin/bats"
            command("bats_version", [bats, "--version"], cwd=source)
            command("bats_tests", [bats, "--formatter", "tap", "tests"], check=False)
            tap_lines = (EVIDENCE / "bats_tests.log").read_text().splitlines()
            manifest["bats_test_summary"] = {
                "expected": 4, "passed": sum(line.startswith("ok ") for line in tap_lines),
                "failed": sum(line.startswith("not ok ") for line in tap_lines),
                "skipped": sum("# skip" in line.lower() for line in tap_lines),
            }
        else:
            manifest["bats_unavailable"] = "Pinned Bats cache did not produce exactly one package"

        after = {name: sha(source / name) if (source / name).is_file() else None for name in tracked}
        manifest["tracked_source_mutations"] = [name for name in tracked if original[name] != after[name]]
        manifest["binaries_after_tests"] = {"sjaracne": sha(binary), "null_generator": sha(generator)}
        if manifest["binaries_before_tests"] != manifest["binaries_after_tests"]:
            raise RuntimeError("Native binaries changed during package/test execution")
        tests = json.loads((EVIDENCE / "python_tests.json").read_text())
        manifest["python_test_summary"] = {key: tests[key] for key in
            ("discovered", "tests_run", "passed", "failures", "errors", "skipped", "duration_seconds")}
        matrix_lines = (EVIDENCE / "python_tests.log").read_text().splitlines()
        matrix_records = [json.loads(line.split("RECURRENCE_MATRIX_PASS=", 1)[1])
                          for line in matrix_lines if "RECURRENCE_MATRIX_PASS=" in line]
        manifest["integration_matrix"] = matrix_records
        expected_matrix = {(model, mode) for model in ("affine", "pchip")
                           for mode in ("default_k6", "legacy_pc")}
        matrix_ok = (len(matrix_records) == 4 and
                     {(item["model"], item["consensus"]) for item in matrix_records} == expected_matrix)
        manifest["integration_matrix_passed"] = matrix_ok
        manifest["complete"] = True
        manifest["passed"] = bool(all(step["returncode"] == 0 for step in manifest["steps"])
                                  and tests["passed"] and not manifest.get("bats_unavailable")
                                  and manifest.get("bats_test_summary") == {"expected": 4, "passed": 4, "failed": 0, "skipped": 0}
                                  and not manifest["tracked_source_mutations"] and matrix_ok)
        manifest["finished_at_utc"] = now()
        persist()
        lines = ["# PR #3 pinned regression result", "", "- Commit: `" + COMMIT + "`",
                 "- Platform: Linux/WSL; " + manifest["platform"],
                 "- Python tests discovered/run: %s/%s" % (tests["discovered"], tests["tests_run"]),
                 "- Failures/errors/skips: %d/%d/%d" % (len(tests["failures"]), len(tests["errors"]), len(tests["skipped"])),
                 "- Additional shell/CWL tests: " + json.dumps(manifest.get("bats_test_summary")),
                 "- CWL documents validated: " + str(sum(step["name"].startswith("validate_") for step in manifest["steps"])),
                 "- Four-way real CWL integration matrix passed: " + str(matrix_ok),
                 "- Active dependency versions: " + json.dumps(manifest["installed_test_environment"]["versions"], sort_keys=True),
                 "- Overall pass: " + str(manifest["passed"]),
                 "- Native binary SHA256: `" + manifest["binaries_after_tests"]["sjaracne"] + "`",
                 "- Null generator SHA256: `" + manifest["binaries_after_tests"]["null_generator"] + "`",
                 "- Source archive SHA256: `" + manifest["source_archive_sha256"] + "`",
                 "- WSL workspace: `" + str(work) + "`", "",
                 "See manifest.json, python_tests.json and individual logs for commands, identities and results.",
                 "The regression controller did not modify source branches, remote PRs, existing environments or software defaults.", ""]
        (EVIDENCE / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
        inventory = {}
        for path in sorted(EVIDENCE.iterdir()):
            if path.is_file() and path.name != "SHA256SUMS":
                inventory[path.name] = sha(path)
        (EVIDENCE / "SHA256SUMS").write_text("".join(value + "  " + name + "\n" for name, value in inventory.items()), encoding="utf-8")
        print(now(), "COMPLETE", json.dumps(manifest["python_test_summary"]), "overall=" + str(manifest["passed"]), flush=True)
        return 0 if manifest["passed"] else 1
    except BaseException as exc:
        manifest["exception"] = {"type": type(exc).__name__, "message": str(exc)}
        manifest["finished_at_utc"] = now()
        manifest["passed"] = False
        persist()
        print(now(), "FAILED", repr(exc), flush=True)
        raise


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", choices=["all", "suite"], default="all")
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    options = parser.parse_args()
    COMMIT = options.commit
    sys.exit(suite_phase(options.work_root) if options.phase == "suite" else main_phase(options.work_root))






