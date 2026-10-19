#!/usr/bin/env python3
"""Check documented CLI contracts without starting inference, CWL, or LSF.

The wrapper really parses the documented arguments and writes its CWL job file;
only its final execution hook is mocked. Manual LSF scripts run against an argv
recording stub, never the installed sjaracne command.
"""

import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile
from unittest import mock


BASELINE = "f512ef3a29c661e7cdd7b3b2c4027285d8d19fa3"
ALLOWED_CHANGES = {
    ".gitattributes",
    "README.md",
    "tests/test_sjaracne_lsf_brca_data.sh",
    "tests/test_sjaracne_lsf_real_data.sh",
}
ATTRIBUTE_APPEND = (
    b"\n# Keep the runnable LSF examples executable under Bash after Windows checkouts.\n"
    b"tests/test_sjaracne_lsf_brca_data.sh text eol=lf\n"
    b"tests/test_sjaracne_lsf_real_data.sh text eol=lf\n"
)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def git_location(engine):
    """Read, never rewrite, Windows-created linked-worktree metadata under WSL."""
    pointer = engine / ".git"
    if sys.platform != "win32" and pointer.is_file():
        declaration = pointer.read_text(encoding="utf-8").strip()
        require(declaration.startswith("gitdir: "), "Malformed linked-worktree Git pointer")
        location = declaration[len("gitdir: "):]
        windows_drive_pointer = bool(re.match(r"^[A-Za-z]:[\\/]", location))
        normalization = []
        if windows_drive_pointer:
            location = "/mnt/" + location[0].lower() + "/" + location[3:].replace("\\", "/")
            # Match Windows Git's checkout normalization on this read-only WSL bridge.
            # These command-local overrides never alter repository/global config.
            normalization = ["-c", "core.autocrlf=true", "-c", "core.fileMode=false"]
        directory = Path(location)
        if not directory.is_absolute():
            directory = engine / directory
        return normalization + ["--git-dir=" + str(directory.resolve()), "--work-tree=" + str(engine)]
    return ["-C", str(engine)]


def git(engine, *args):
    return subprocess.check_output(
        ["git", "-c", "safe.directory=" + str(engine), *git_location(engine), *args],
        text=True,
    ).strip()


def git_blob(engine, revision, path):
    return subprocess.check_output(
        ["git", "-c", "safe.directory=" + str(engine), *git_location(engine),
         "show", revision + ":" + path],
    )


def check_attribute_append(engine, baseline):
    original = git_blob(engine, baseline, ".gitattributes")
    current = git_blob(engine, "HEAD", ".gitattributes")
    require(current == original + ATTRIBUTE_APPEND,
            ".gitattributes must preserve its exact baseline bytes and append only the two LSF LF rules")
    return {"path": ".gitattributes", "scope": "exact baseline bytes preserved; only two manual LSF scripts receive LF rules",
            "baseline_blob_sha256": hashlib.sha256(original).hexdigest(),
            "checked_blob_sha256": hashlib.sha256(current).hexdigest(),
            "exact_permitted_append": ATTRIBUTE_APPEND.decode("ascii")}


def runtime_identity(engine, baseline=BASELINE):
    """Git compares normalized tracked blobs, including uncommitted changes."""
    require(not git(engine, "diff", "--name-only", "HEAD", "--"),
            "Tracked working state must be clean so checked example bytes bind to HEAD")
    baseline_tree = git(engine, "ls-tree", "-r", baseline)
    paths = {line.split("\t", 1)[1] for line in baseline_tree.splitlines()}
    tracked = set(git(engine, "ls-files").splitlines())
    require(paths == tracked, "Tracked path set differs from the regression baseline")
    changed = git(engine, "diff", "--name-only", baseline, "--").splitlines()
    require(set(changed) <= ALLOWED_CHANGES,
            "Unvalidated engine changes: " + repr(sorted(set(changed) - ALLOWED_CHANGES)))
    # Also reject staged path/type changes that --name-only alone could conceal.
    for line in git(engine, "diff", "--name-status", baseline, "--").splitlines():
        require(line.startswith("M\t"), "Only modifications to existing example files are allowed")
    attributes_exception = check_attribute_append(engine, baseline) if ".gitattributes" in changed else None
    runtime_blobs = [line for line in baseline_tree.splitlines()
                     if line.split("\t", 1)[1] not in ALLOWED_CHANGES]
    access = git_location(engine)
    return {
        "baseline_engine_commit": baseline,
        "inspected_head_commit": git(engine, "rev-parse", "HEAD"),
        "changed_tracked_paths": sorted(changed),
        "allowed_documentation_and_manual_script_paths": sorted(ALLOWED_CHANGES),
        "narrow_attributes_exception": attributes_exception,
        "unchanged_runtime_tracked_paths": len(runtime_blobs),
        "runtime_tree_listing_sha256": hashlib.sha256(
            ("\n".join(runtime_blobs) + "\n").encode()).hexdigest(),
        "git_normalization": {
            "windows_drive_pointer_bridge": "core.autocrlf=true" in access,
            "per_command_config": [access[index + 1] for index, value in enumerate(access) if value == "-c"],
            "scope": "per-command only; no repository or global configuration written",
        },
        "status": "all other tracked blobs identical to regression baseline",
    }


def bash_commands(markdown):
    commands = []
    in_bash = False
    block = []
    for line in markdown.splitlines():
        if not in_bash and re.fullmatch(r"```(?:bash|sh)\s*", line):
            in_bash, block = True, []
        elif in_bash and line.strip() == "```":
            logical = "\n".join(block).replace("\\\n", "")
            for command in logical.splitlines():
                argv = shlex.split(command, comments=True, posix=True)
                if argv:
                    commands.append(argv)
            in_bash = False
        elif in_bash:
            block.append(line)
    require(not in_bash, "Unclosed bash fence")
    return commands


def replace_output_paths(argv, output, temporary):
    argv = list(argv)
    for aliases, replacement in (({"-o", "--output-dir"}, output),
                                  ({"-tmp", "--tmpdir-prefix"}, temporary)):
        positions = [i for i, value in enumerate(argv) if value in aliases]
        require(len(positions) == 1, "Expected exactly one output/tmp option")
        position = positions[0]
        require(position + 1 < len(argv), "Missing output/tmp value")
        argv[position + 1] = str(replacement) + ("/" if aliases == {"-tmp", "--tmpdir-prefix"} else "")
    return argv


def read_job(path):
    """Read the wrapper's small fixed YAML vocabulary without extra packages."""
    job, current = {}, None
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        key, separator, value = line.strip().partition(":")
        require(bool(separator), "Malformed generated job line")
        value = value.strip()
        if value:
            try:
                scalar = json.loads(value)
            except ValueError:
                scalar = value
        else:
            scalar = {}
        if line.startswith("  "):
            require(current is not None and isinstance(job[current], dict), "Invalid nested job key")
            require(key not in job[current], "Duplicate nested job key")
            job[current][key] = scalar
        else:
            require(key not in job, "Duplicate job key")
            job[key] = scalar
            current = key
    return job


@contextlib.contextmanager
def working_directory(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def load_wrapper(engine):
    spec = importlib.util.spec_from_file_location(
        "example_checked_wrapper", engine / "SJARACNe/sjaracne.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def invoke_wrapper(module, engine, argv, temporary):
    output, scratch = temporary / "output", temporary / "scratch"
    rewritten = replace_output_paths(argv, output, scratch)
    messages = []
    with working_directory(engine), mock.patch.object(sys, "argv", rewritten), \
            mock.patch.dict(os.environ, {"PATH": os.environ.get("PATH", "")}), \
            mock.patch.object(module.logging, "basicConfig"), \
            mock.patch.object(module.logging, "info", side_effect=lambda value: messages.append(str(value))), \
            mock.patch.object(module, "run_shell_command_call") as execution:
        module.main()
    execution.assert_called_once()
    dispatch = shlex.split(execution.call_args[0][0])
    require(dispatch[0] == ("cwltool" if argv[1] == "local" else "cwlexec"),
            "Unexpected wrapper dispatch")
    require(str(engine / "SJARACNe/cwl/sjaracne_workflow.cwl") in dispatch,
            "Wrapper did not select its bundled workflow")
    if argv[1] == "lsf":
        config = Path(argv[argv.index("-j") + 1])
        require((engine / config).resolve() == (engine / "SJARACNe/config/config_cwlexec.json").resolve(),
                "Unexpected LSF scheduler configuration")
    return {"documented_argv": argv, "tested_argv": rewritten,
            "job": read_job(output / "sjaracne_workflow.yml"),
            "mocked_dispatch_argv": dispatch, "wrapper_messages": messages}


def signature(record, engine):
    job = record["job"]
    require(job["exp_file"] == {"class": "File", "path": str(engine / "tests/inputs/BRCA100.exp")},
            "Unexpected expression input")
    require(job["aracne_config_dir"] == {"class": "Directory", "path": str(engine / "SJARACNe/config")},
            "Unexpected bundled configuration")
    hub = Path(job["probe_file"]["path"])
    require(job["probe_file"]["class"] == "File" and hub.is_file(), "Missing hub input")
    require(hub.parent == engine / "tests/inputs", "Unexpected hub input directory")
    require(job["depth"] == 40, "Unexpected AP-MI depth")
    require(("min_recurrence" in job) != ("p_value_consensus" in job),
            "Consensus job must select exactly one mode")
    selection = ("K", job["min_recurrence"]) if "min_recurrence" in job else ("pc", job["p_value_consensus"])
    return (record["documented_argv"][1], job["bootstrap_num"], job["subsample_spec"],
            job.get("apmi_null_model", "affine"), float(job["p_value_bootstrap"]),
            selection, hub.name)


EXPECTED = {
    ("local", 2, "80%", "affine", 1e-7, ("K", 1), "BRCA100_TF.txt"): "local_smoke",
    ("local", 100, "80", "pchip", .001, ("K", 6), "BRCA100_TF.txt"): "local_tf_pchip",
    ("local", 100, "80", "pchip", .0005, ("K", 6), "BRCA100_SIG.txt"): "local_sig_pchip",
    ("lsf", 100, "80", "pchip", .001, ("K", 6), "BRCA100_TF.txt"): "lsf_tf_pchip",
    ("local", 100, "80", "pchip", .001, ("pc", 1e-5), "BRCA100_TF.txt"): "explicit_legacy_consensus",
}


def check_readme(engine, module, temporary):
    commands = bash_commands((engine / "README.md").read_text(encoding="utf-8"))
    workflows = [argv for argv in commands if argv[0] == "sjaracne" and argv[1:2] in (["local"], ["lsf"])]
    require(len(workflows) == 5, "README must contain exactly five workflow examples")
    records, seen = [], set()
    for index, argv in enumerate(workflows):
        record = invoke_wrapper(module, engine, argv, temporary / str(index))
        case = signature(record, engine)
        require(case in EXPECTED, "Unexpected README workflow contract: " + repr(case))
        require(case not in seen, "Duplicate README workflow contract")
        seen.add(case)
        record["case"] = EXPECTED[case]
        records.append(record)
    require(seen == set(EXPECTED), "Missing README workflow contract")
    native = [argv for argv in commands if argv[0] == "./SJARACNe/bin/sjaracne.exe"]
    require(len(native) == 1, "Expected one native example")
    argv = native[0]
    for option, value in {"-i": "./tests/inputs/BRCA100.exp", "-s": "./tests/inputs/BRCA100_TF.txt",
                          "-l": "./tests/inputs/BRCA100_TF.txt", "-N": "40", "-e": "0",
                          "-u": "80", "-M": "pchip", "-p": "0.001", "-o": "brca100_tf_run.adj"}.items():
        require(argv.count(option) == 1 and argv[argv.index(option) + 1] == value,
                "Native example contract differs at " + option)
    return records, {"argv": argv, "check": "static argument contract only; native binary not executed"}


def check_manual_scripts(engine, module, temporary):
    stub_dir = temporary / "stub"
    stub_dir.mkdir(parents=True)
    stub = stub_dir / "sjaracne"
    stub.write_text("#!" + sys.executable + "\nimport json, os, sys\n"
                    "with open(os.environ['SJARACNE_STUB_CAPTURE'], 'w') as f: json.dump(sys.argv[1:], f)\n")
    stub.chmod(0o755)
    environment = dict(os.environ)
    for name in ("SJARACNE_EXPRESSION_FILE", "SJARACNE_HUB_FILE", "SJARACNE_OUTPUT_DIR", "SJARACNE_TMP_DIR"):
        environment.pop(name, None)
    environment["PATH"] = str(stub_dir) + os.pathsep + environment.get("PATH", "")
    records = []
    for index, name in enumerate(("test_sjaracne_lsf_brca_data.sh", "test_sjaracne_lsf_real_data.sh")):
        script = engine / "tests" / name
        subprocess.run(["bash", "-n", str(script)], check=True, capture_output=True, text=True)
        capture = temporary / (name + ".argv.json")
        environment["SJARACNE_STUB_CAPTURE"] = str(capture)
        missing_inputs = []
        if "real_data" in name:
            # Both missing-expression and missing-hub guards must stop before the stub.
            for only_expression in (False, True):
                guarded = dict(environment)
                if only_expression:
                    guarded["SJARACNE_EXPRESSION_FILE"] = str(engine / "tests/inputs/BRCA100.exp")
                result = subprocess.run(["bash", str(script)], cwd=engine, env=guarded,
                                        capture_output=True, text=True)
                require(result.returncode != 0 and not capture.exists(), "Missing required inputs reached sjaracne")
                missing_inputs.append({"provided_expression_only": only_expression,
                                       "exit_code": result.returncode, "stderr": result.stderr})
        supplied = dict(environment)
        supplied["SJARACNE_EXPRESSION_FILE"] = str(engine / "tests/inputs/BRCA100.exp")
        supplied["SJARACNE_HUB_FILE"] = str(engine / "tests/inputs/BRCA100_TF.txt")
        result = subprocess.run(["bash", str(script)], cwd=engine, env=supplied,
                                check=True, capture_output=True, text=True)
        require(capture.is_file(), "Manual LSF script did not reach argv stub")
        argv = ["sjaracne"] + json.loads(capture.read_text())
        record = invoke_wrapper(module, engine, argv, temporary / ("wrapper_" + str(index)))
        expected = ("lsf", 100 if "real_data" in name else 5, "80%", "affine", 1e-7,
                    ("K", 6 if "real_data" in name else 1), "BRCA100_TF.txt")
        require(signature(record, engine) == expected, "Manual LSF script contract differs")
        record.update({"script": str(script.relative_to(engine)), "bash_n": "passed",
                       "stub_execution": "passed; no CWL or scheduler execution",
                       "missing_input_guards": missing_inputs,
                       "stdout": result.stdout, "stderr": result.stderr})
        records.append(record)
    return records


def run(engine):
    engine = engine.resolve()
    identity = runtime_identity(engine)
    module = load_wrapper(engine)
    with tempfile.TemporaryDirectory(prefix="sjaracne-example-check-") as temp:
        temporary = Path(temp)
        readme, native = check_readme(engine, module, temporary / "readme")
        scripts = check_manual_scripts(engine, module, temporary / "scripts")
    return {"status": "passed", "scope": "argument/job construction only; no inference, CWL, LSF or network QC",
            "runtime_identity": identity, "readme_workflows": readme, "native_example": native,
            "manual_lsf_scripts": scripts,
            "python": {"executable": sys.executable, "version": sys.version},
            "source_hashes": {str(path.relative_to(engine)): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in [engine / value for value in sorted(ALLOWED_CHANGES)]}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, help="Fresh directory for JSON and concise text evidence")
    args = parser.parse_args()
    if args.output_dir is not None:
        require(not args.output_dir.exists(), "Refusing to overwrite an existing evidence directory")
    result = run(args.engine)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=False)
        (args.output_dir / "check_examples.json").write_text(encoded)
        (args.output_dir / "check_examples.log").write_text(
            "PASS: five README workflows parsed by the real wrapper with execution mocked.\n"
            "PASS: two manual LSF scripts passed bash -n and argv-stub/wrapper checks.\n"
            "PASS: both real-data input guards stopped before dispatch.\n"
            "PASS: all runtime tracked engine blobs match " + BASELINE + "; only examples and the exact checked LSF attributes append differ.\n"
            "No inference, CWL, scheduler, or NetBID2 execution occurred.\n")
    print(encoded, end="")


if __name__ == "__main__":
    main()
