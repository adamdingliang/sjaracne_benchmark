"""Synthetic sampling-backport protocol tests; never launch native jobs or R.

The tiny expression fixture has the real protocol's 121 observations but only
three genes. All baseline, component and score artifacts are temporary files.
"""

import contextlib
import copy
import importlib.util
import io
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


SPEC = importlib.util.spec_from_file_location(
    "run_sampling_backport", Path(__file__).with_name("run_sampling_backport.py"))
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class SamplingBackportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="sampling-backport-test-")
        self.root = Path(self.tmp.name)
        self.prepared = self.root / "prepared"
        self.prepared.mkdir()
        self.expression = self.prepared / "expression.exp"
        observations = [f"metacell_{number:03d}" for number in range(1, 122)]
        rows = ["probe\tsymbol\t" + "\t".join(observations)]
        for gene, offset in (("A", 0), ("B", 1), ("C", 2)):
            rows.append(gene + "\t" + gene + "\t" + "\t".join(
                str((number + offset) % 7) for number in range(121)))
        self.expression.write_text("\n".join(rows) + "\n", encoding="utf-8")
        self.hubs = self.prepared / "hubs.txt"
        self.hubs.write_text("A\nB\n", encoding="utf-8")
        self.reference = self.prepared / "reference_positive_edges.tsv"
        self.reference.write_text("source\ttarget\teffect\nA\tB\t1\n", encoding="utf-8")
        self.prepare = self.prepared / "prepare_manifest.json"
        self.write(self.prepare, {"status": "complete", "outputs": {
            path.name: module.legacy.record_file(path)
            for path in (self.expression, self.hubs, self.reference)}})
        self.baseline_root = self.root / "legacy"
        self.baseline_root.mkdir()
        self.baseline_source = self.root / "baseline_source"
        self.baseline_source.mkdir()
        self.baseline_binary = self.baseline_source / "native"
        self.baseline_binary.write_bytes(b"pinned baseline native fixture")
        self.consensus = self.baseline_source / "create_consensus_network.py"
        self.consensus.write_text("# unmodified pinned consensus fixture\n", encoding="utf-8")
        self.config = self.baseline_source / "config"
        self.config.mkdir()
        (self.config / "config_threshold.txt").write_text(
            "> bcell_mas5\n1.062\t-48.7\t-0.634\n", encoding="utf-8")
        (self.config / "config_kernel.txt").write_text(
            "> bcell_mas5\n0.52477\t-0.24\n", encoding="utf-8")
        self.baseline_component = self.baseline_source / "build_record.json"
        self.write(self.baseline_component, {
            "source_commit": module.legacy.SOURCE_COMMIT,
            "binary_sha256": module.legacy.digest(self.baseline_binary),
            "consensus_script_sha256": module.legacy.digest(self.consensus),
            "config_sha256": {name: module.legacy.digest(self.config / name)
                              for name in module.legacy.CONFIG_FILES},
            "compiler": "mock", "build_command": "mock", "adaptations": []})
        legacy_args = module.legacy.parser().parse_args([
            "plan", "--expression", str(self.expression), "--hubs", str(self.hubs),
            "--prepare-manifest", str(self.prepare), "--out", str(self.baseline_root),
            "--binary", str(self.baseline_binary), "--config", str(self.config),
            "--consensus-script", str(self.consensus),
            "--component-manifest", str(self.baseline_component)])
        frozen, _, _ = module.legacy.make_frozen(legacy_args)
        self.baseline_run = {"status": "complete", "frozen": frozen,
                             "bootstraps": {}, "consensus": {}}
        (self.baseline_root / "adj").mkdir()
        for seed in range(1, 101):
            adjacency = self.baseline_root / "adj" / f"bootstrap_{seed:03d}.adj"
            adjacency.write_text("A\tB\t0.7\nB\tA\t0.7\n", encoding="utf-8")
            log = self.baseline_root / f"baseline_{seed:03d}.log"
            log.write_text("Array No: 121\n", encoding="utf-8")
            self.baseline_run["bootstraps"][str(seed)] = {
                "seed": seed, "status": "complete", "validation": {"draws": 121},
                "artifacts": {"adjacency": module.legacy.record_file(adjacency),
                              "log": module.legacy.record_file(log)}}
        for p in (0.01, 0.001):
            directory = self.baseline_root / module.legacy.consensus_name(p)
            directory.mkdir()
            network = directory / "edges.tsv"
            network.write_text("source\ttarget\tMI\nA\tB\t0.7000\n", encoding="utf-8")
            self.baseline_run["consensus"][module.legacy.consensus_name(p)] = {
                "p": p, "status": "complete", "artifacts": {
                    "edges.tsv": module.legacy.record_file(network)}}
        self.baseline_manifest = self.baseline_root / "run_manifest.json"
        self.write(self.baseline_manifest, self.baseline_run)
        self.comparison = self.root / "comparison"
        self.comparison.mkdir()
        self.publication = self.root / "publication"
        self.publication.mkdir()
        for name in ("tp.tsv", "epr.tsv", "roc_segment.tsv"):
            (self.publication / name).write_text("synthetic published source points\n", encoding="utf-8")
        self.publication_manifest = self.publication / "manifest.json"
        self.publication_record = {
            "full_ROC_available": False, "published_AUROC_rounded": .75,
            "outputs_sha256": {name: module.legacy.digest(self.publication / name)
                              for name in ("tp.tsv", "epr.tsv", "roc_segment.tsv")}}
        self.write(self.publication_manifest, self.publication_record)
        self.scorer = Path(__file__).with_name("score_author.R")
        self.completion_path = self.comparison / "completion_manifest.json"
        self.completion_context = {
            "scorer": module.legacy.record_file(self.scorer),
            "preparation_manifest": module.legacy.record_file(self.prepare),
            "publication_manifest": module.legacy.record_file(self.publication_manifest),
            "reference_positive_edges.tsv": module.legacy.record_file(self.reference),
            "expression.exp": module.legacy.record_file(self.expression),
            "hubs.txt": module.legacy.record_file(self.hubs),
            **{"publication_" + name: module.legacy.record_file(self.publication / name)
               for name in ("tp.tsv", "epr.tsv", "roc_segment.tsv")}}
        self.write(self.completion_path, {"inputs": self.completion_context})
        self.summary_path = self.comparison / "summary.json"
        self.summary = {"status": "complete", "exact_reproduction_established": False,
                        "native_run": module.legacy.record_file(self.baseline_manifest),
                        "consensus": {}}
        for p in (0.01, 0.001):
            reconstructed_auc = .573906 if p == .01 else .554708
            score = self.comparison / ("score_pc" + module.legacy.consensus_name(p).removeprefix("consensus_pc"))
            score.mkdir()
            curves = score / "ranked_curves.tsv"
            curves.write_text("k\tTP\tRandom_TP\tEPR\n1000\t80\t10\t8\n", encoding="utf-8")
            for name in module.SCORE_OUTPUTS[1:]:
                (score / name).write_bytes(b"tiny synthetic score output\n")
            output_hashes = {name: module.legacy.digest(score / name) for name in module.SCORE_OUTPUTS}
            network = self.baseline_root / module.legacy.consensus_name(p) / "edges.tsv"
            metrics = score / "metrics.json"
            self.write(metrics, {"status": "complete", "exact_reproduction_established": False,
                                 "AUROC": reconstructed_auc, "Random_AUROC": .5,
                                 "reported_edges": 1000, "reference_positive_reported_edges": 80,
                                 "script_sha256": self.completion_context["scorer"]["sha256"],
                                 "input_sha256": {
                                     "run_manifest": module.legacy.digest(self.baseline_manifest),
                                     "prepare_manifest": module.legacy.digest(self.prepare),
                                     "reference": module.legacy.digest(self.reference),
                                     "network": module.legacy.digest(network),
                                     "publication_manifest": module.legacy.digest(self.publication_manifest),
                                     **{"publication_" + name.removesuffix(".tsv"):
                                        module.legacy.digest(self.publication / name)
                                        for name in ("tp.tsv", "epr.tsv", "roc_segment.tsv")}},
                                 "output_sha256": output_hashes})
            self.summary["consensus"][str(p)] = {
                "AUROC": reconstructed_auc, "Random_AUROC": .5,
                "reported_edges": 1000, "reference_positive_reported_edges": 80,
                "metrics": module.legacy.record_file(metrics),
                "output_sha256": output_hashes}
        self.refresh_summary()
        self.source = self.root / "sampling_source"
        self.source.mkdir()
        modified = ["SJARACNe/src/" + name for name in
                    ("main.cpp", "matrix.cpp", "matrix.h", "param.cpp", "param.h")]
        source_records = {}
        for name in modified:
            source = self.source / name
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text("// tiny pinned source fixture: " + name + "\n", encoding="utf-8")
            source_records[name] = module.legacy.digest(source)
        self.binary = self.source / "native"
        self.binary.write_bytes(b"pinned sampling-only backport fixture")
        self.patch_file = self.source / "sampling-only.patch"
        self.patch_file.write_text("synthetic sampling-only patch\n", encoding="utf-8")
        self.validation_artifact = self.source / "validation.json"
        self.write(self.validation_artifact, {"status": "passed"})
        self.components = self.source / "build_record.json"
        self.build_record = {
            "schema_version": 1,
            "source_repository": "https://github.com/adamdingliang/SJARACNe",
            "source_commit": module.BASE_COMMIT,
            "sampling_commit": module.SAMPLING_COMMIT,
            "profile": module.PROFILE,
            "source_root": str(self.source.resolve()),
            "compiler": "mock", "platform": "mock", "build_command": "mock",
            "build_exit_code": 0,
            "validation_status": "passed", "legacy_equivalence_case_count": 16,
            "native_unique_index_case_count": 100,
            "validation_artifact": str(self.validation_artifact.resolve()),
            "validation_artifact_sha256": module.legacy.digest(self.validation_artifact),
            "binary": str(self.binary.resolve()),
            "binary_sha256": module.legacy.digest(self.binary),
            "config": str(self.config.resolve()),
            "config_sha256": {name: module.legacy.digest(self.config / name)
                              for name in module.legacy.CONFIG_FILES},
            "consensus_script": str(self.consensus.resolve()),
            "consensus_script_sha256": module.legacy.digest(self.consensus),
            "source_sha256": source_records, "modified_source_paths": modified,
            "modified_source_files": [
                {"path": name, "base_sha256": "0" * 64, "backport_sha256": source_records[name]}
                for name in modified],
            "patchfile": str(self.patch_file.resolve()),
            "patch_sha256": module.legacy.digest(self.patch_file)}
        self.write(self.components, self.build_record)
        self.gate_path = self.root / "gate.json"
        self.gate = {"schema": 1, "status": "accepted_by_user_or_audit",
                     "baseline_run_manifest_sha256": module.legacy.digest(self.baseline_manifest),
                     "baseline_summary_sha256": module.legacy.digest(self.summary_path),
                     "reason": "Synthetic user decision: proceed with the fixed reconstructed reference "
                               "despite Figure 6a disagreement; not exact reproduction.",
                     "scope": module.PROFILE, "sampling_percent": 80}
        self.write(self.gate_path, self.gate)
        self.out = self.root / "sampling_after"
        self.args = module.parser().parse_args([
            "run", "--expression", str(self.expression), "--hubs", str(self.hubs),
            "--prepare-manifest", str(self.prepare), "--out", str(self.out),
            "--binary", str(self.binary), "--config", str(self.config),
            "--consensus-script", str(self.consensus),
            "--component-manifest", str(self.components),
            "--baseline-run-manifest", str(self.baseline_manifest),
            "--baseline-summary", str(self.summary_path),
            "--gate-decision", str(self.gate_path), "--workers", "1"])
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    @staticmethod
    def write(path, value):
        path.write_text(json.dumps(value), encoding="utf-8")

    def refresh_summary(self):
        self.write(self.summary_path, self.summary)
        report = self.comparison / "REPORT.md"
        report.write_text("Synthetic completed baseline report.\n", encoding="utf-8")
        self.write(self.comparison / "status.json", {
            "status": "complete", "outputs": {
                path.name: module.legacy.record_file(path)
                for path in (self.summary_path, report)}})

    def fake_run(self, command, stdout, stderr, check):
        self.calls.append(list(command))
        self.assertFalse(check)
        if "-u" in command:
            output = Path(command[command.index("-o") + 1])
            cutoff = module.legacy.affine_cutoff(self.config, 97, 1e-7)
            output.write_text(
                f">  MI threshold    {cutoff:.6g}\n>  MI P-value      1e-07\n"
                ">  DPI tolerance   0\n"
                ">  Sampling method fixed-size without replacement\n"
                ">  Sampling request 80%\n"
                ">  Eligible observations 121\n"
                ">  Sampled observations 97\n"
                "A\tB\t0.7\tC\t0.8\nB\tA\t0.7\n", encoding="utf-8")
            stdout.write("Marker No: 3 (3 active), Array No: 97\n"
                         "[SAMPLING] Fixed-size sampling without replacement: "
                         "selected 97 of 121 eligible observations (request: 80%).\n")
        else:
            output = Path(command[command.index("-o") + 1])
            output.mkdir()
            (output / "consensus_network_3col_.txt").write_text(
                "source\ttarget\tMI\nA\tB\t0.7000\nA\tC\t0.8000\n", encoding="utf-8")
            (output / "consensus_network_ncol_.txt").write_text(
                "source\ttarget\tsource.symbol\ttarget.symbol\tMI\tpearson\tspearman\tslope\tp-value\n"
                "A\tB\tA\tB\t0.7000\t0\t0\t0\t1\n"
                "A\tC\tA\tC\t0.8000\t0\t0\t0\t1\n", encoding="utf-8")
            (output / "bootstrap_info_.txt").write_text("Total edge tested: 3\n", encoding="utf-8")
            (output / "parameter_info_.txt").write_text(
                ">  Bootstrap No: 100\n", encoding="utf-8")
            stdout.write("original consensus completed\n")
        return subprocess.CompletedProcess(command, 0)

    def run_mocked(self, runner=None):
        with patch.object(module.legacy, "PLATFORM", "posix"), \
                patch.object(module.subprocess, "run", runner or self.fake_run), \
                contextlib.redirect_stderr(io.StringIO()):
            return module.execute(self.args)

    def assert_preflight_rejected(self, message):
        with self.assertRaisesRegex((ValueError, RuntimeError, FileNotFoundError), message):
            self.run_mocked()
        self.assertFalse(self.calls)
        self.assertFalse(self.out.exists())

    def test_parser_defaults_are_frozen_matched_protocol(self):
        self.assertEqual(self.args.bootstrap_count, 100)
        self.assertEqual(self.args.bootstrap_p, 1e-7)
        self.assertEqual(self.args.consensus_p, [0.01, 0.001])
        self.assertEqual(self.args.npar, 40)
        self.assertEqual(self.args.subsample_percent, 80)

    def test_plan_has100seeds97draws_and_no_pr71_or_recurrence(self):
        self.args.action = "plan"
        state = self.run_mocked()
        commands = state["bootstrap_commands"]
        self.assertEqual(len(commands), 100)
        self.assertEqual(commands[0][commands[0].index("-S") + 1], "1")
        self.assertEqual(commands[-1][commands[-1].index("-S") + 1], "100")
        for command in commands:
            self.assertEqual(command[command.index("-u") + 1], "80%")
            self.assertEqual(command[command.index("-N") + 1], "40")
            self.assertEqual(float(command[command.index("-p") + 1]), 1e-7)
            self.assertEqual(command[command.index("-e") + 1], "0")
            self.assertNotIn("-r", command)
            self.assertNotIn("-t", command)
            self.assertNotIn("-M", command)
        frozen = state["frozen"]
        self.assertEqual(frozen["source_commit"], module.BASE_COMMIT)
        self.assertEqual(frozen["sampling_commit"], module.SAMPLING_COMMIT)
        self.assertEqual(frozen["profile"], module.PROFILE)
        self.assertEqual(frozen["observations"], 121)
        self.assertEqual(frozen["parameters"]["sampling_draws"], 97)
        self.assertEqual(frozen["parameters"]["affine_mi_cutoff"],
                         module.legacy.affine_cutoff(self.config, 97, 1e-7))
        for command in state["consensus_commands"]:
            self.assertEqual(command[1], str(self.consensus.resolve()))
            self.assertIn("-p", command)
            self.assertNotIn("--min-recurrence", command)
        self.assertFalse(self.calls)
        self.assertFalse(self.out.exists())

    def test_matched_parameters_cannot_be_tuned(self):
        for field, value in (("bootstrap_count", 99), ("bootstrap_p", .001),
                             ("consensus_p", [.001]), ("npar", 41),
                             ("subsample_percent", 90), ("workers", 0)):
            with self.subTest(field=field):
                original = getattr(self.args, field)
                setattr(self.args, field, value)
                try:
                    self.assert_preflight_rejected("(protocol|fixed|positive|80|100|parameter)")
                finally:
                    setattr(self.args, field, original)

    def test_missing_gate_never_defaults_to_acceptance(self):
        self.args.gate_decision = None
        self.assert_preflight_rejected("[Gg]ate")

    def test_explicit_gate_accepts_reconstructed_nonreproducing_baseline(self):
        self.assertFalse(self.summary["exact_reproduction_established"])
        for score in self.summary["consensus"].values():
            metrics = module.read_json(Path(score["metrics"]["path"]))
            self.assertFalse(metrics["exact_reproduction_established"])
            self.assertLess(metrics["AUROC"], self.publication_record["published_AUROC_rounded"])
        with patch.object(module.legacy, "PLATFORM", "posix"):
            frozen, _, _ = module.make_frozen(self.args)
        self.assertEqual(frozen["gate_binding"]["status"], "accepted")
        self.assertEqual(frozen["baseline_binding"]["status"], "complete")
        self.assertIn("reconstructed", frozen["label"])
        self.assertIn("not exact Fig. 6a reproduction", frozen["scope"])
        self.assertEqual(frozen["inputs"]["reference_positive_edges"]["sha256"],
                         module.legacy.digest(self.reference))
        self.assertFalse(self.calls)
        self.assertFalse(self.out.exists())

    def test_conditional_rejected_and_absent_acceptance_are_not_accepted(self):
        for status in ("conditional", "rejected", "pending", "", None):
            with self.subTest(status=status):
                gate = dict(self.gate, status=status)
                self.write(self.gate_path, gate)
                self.assert_preflight_rejected("(accepted|[Gg]ate)")

    def test_gate_is_bound_to_exact_baseline_and_scope(self):
        for name, value in (("baseline_run_manifest_sha256", "wrong"),
                            ("baseline_summary_sha256", "wrong"),
                            ("scope", "actual_pr70"), ("sampling_percent", 90),
                            ("reason", ""), ("schema", 2)):
            with self.subTest(field=name):
                self.write(self.gate_path, dict(self.gate, **{name: value}))
                self.assert_preflight_rejected("([Gg]ate|scope|baseline|reason|schema)")

    def test_incomplete_baseline_does_not_launch_after_arm(self):
        self.baseline_run["status"] = "incomplete"
        self.write(self.baseline_manifest, self.baseline_run)
        self.assert_preflight_rejected("(baseline|complete)")

    def test_uncompleted_scoring_does_not_launch_after_arm(self):
        self.summary["status"] = "scoring"
        self.refresh_summary()
        self.assert_preflight_rejected("(baseline|complete|summary)")

    def test_score_output_and_completion_report_are_hash_bound(self):
        records = [self.summary["consensus"]["0.01"]["metrics"],
                   {"path": str(self.comparison / "score_pc1e-02" / "ranked_curves.tsv")},
                   {"path": str(self.comparison / "REPORT.md")}]
        for record in records:
            path = Path(record["path"])
            original = path.read_bytes()
            with self.subTest(path=path.name):
                path.write_bytes(original + b"changed\n")
                try:
                    self.assert_preflight_rejected("(hash|changed|binding|mismatch)")
                finally:
                    path.write_bytes(original)

    def test_completed_baseline_artifact_drift_blocks_after_arm(self):
        for kind in ("adjacency", "log"):
            record = self.baseline_run["bootstraps"]["1"]["artifacts"][kind]
            path = Path(record["path"])
            original = path.read_bytes()
            path.write_bytes(original + b"changed\n")
            try:
                with self.subTest(kind=kind):
                    self.assert_preflight_rejected("(hash|changed|binding|mismatch)")
            finally:
                path.write_bytes(original)

    def test_completion_context_records_cannot_claim_other_hashes(self):
        for name in ("scorer", "preparation_manifest", "publication_tp.tsv"):
            with self.subTest(record=name):
                context = copy.deepcopy(self.completion_context)
                context[name]["sha256"] = "0" * 64
                self.write(self.completion_path, {"inputs": context})
                try:
                    self.assert_preflight_rejected("(hash|mismatch)")
                finally:
                    self.write(self.completion_path, {"inputs": self.completion_context})

    def test_publication_and_shared_reference_artifacts_are_hash_bound(self):
        for path in (self.publication_manifest, self.reference,
                     *(self.publication / name for name in ("tp.tsv", "epr.tsv", "roc_segment.tsv"))):
            original = path.read_bytes()
            with self.subTest(path=path.name):
                path.write_bytes(original + b"changed\n")
                try:
                    self.assert_preflight_rejected("(hash|changed|reference|mismatch)")
                finally:
                    path.write_bytes(original)

    def test_publication_metadata_must_remain_declared_partial_context(self):
        for name, value in (("full_ROC_available", True), ("published_AUROC_rounded", .8)):
            with self.subTest(field=name):
                self.write(self.publication_manifest, dict(self.publication_record, **{name: value}))
                context = copy.deepcopy(self.completion_context)
                context["publication_manifest"] = module.legacy.record_file(self.publication_manifest)
                self.write(self.completion_path, {"inputs": context})
                try:
                    self.assert_preflight_rejected("[Pp]ublication context")
                finally:
                    self.write(self.publication_manifest, self.publication_record)
                    self.write(self.completion_path, {"inputs": self.completion_context})

    def test_component_commit_and_profile_cannot_claim_other_code(self):
        for name, value in (("source_commit", "different_base"),
                            ("sampling_commit", "different_sampler"),
                            ("profile", "actual_pr70"),
                            ("modified_source_paths", ["SJARACNe/src/main.cpp"]),
                            ("build_exit_code", 1), ("validation_status", "failed"),
                            ("legacy_equivalence_case_count", 15),
                            ("native_unique_index_case_count", 99)):
            with self.subTest(field=name):
                self.write(self.components, dict(self.build_record, **{name: value}))
                self.assert_preflight_rejected("(commit|profile|source|build|sampling|backport)")

    def test_component_and_backport_source_hashes_are_checked(self):
        paths = [self.binary, self.consensus, self.patch_file, self.validation_artifact,
                 *(self.config / name for name in module.legacy.CONFIG_FILES),
                 self.source / "SJARACNe/src/matrix.cpp"]
        for path in paths:
            original = path.read_bytes()
            with self.subTest(path=path.name):
                path.write_bytes(original + b"changed\n")
                try:
                    self.assert_preflight_rejected("(hash|changed|source|component|mismatch|patch)")
                finally:
                    path.write_bytes(original)

    def test_failed_native_validation_cannot_be_accepted_by_rehashing(self):
        self.write(self.validation_artifact, {"status": "failed"})
        build_record = dict(self.build_record,
                            validation_artifact_sha256=module.legacy.digest(self.validation_artifact))
        self.write(self.components, build_record)
        self.assert_preflight_rejected("[Vv]alidation.*passed")

    def native_fixture(self):
        with patch.object(module.legacy, "PLATFORM", "posix"):
            frozen, genes, hubs = module.make_frozen(self.args)
            adjacency, log = self.root / "sampled.adj", self.root / "sampled.log"
            command = module.native_command(self.args, 1, adjacency)
            with log.open("w", encoding="utf-8") as stream:
                self.fake_run(command, stream, subprocess.STDOUT, False)
        return frozen, genes, hubs, adjacency, log

    def test_native_header_and_sampling_draw_contract(self):
        frozen, genes, hubs, adjacency, log = self.native_fixture()
        validation = module.validate_adjacency(adjacency, genes, hubs, frozen, log)
        self.assertEqual(validation["edges"], 3)
        self.assertEqual(validation["draws"], 97)

    def test_original121sample_affine_threshold_is_not_after_cutoff(self):
        frozen, genes, hubs, adjacency, log = self.native_fixture()
        text = adjacency.read_text(encoding="utf-8")
        actual = module.legacy.affine_cutoff(self.config, 97, 1e-7)
        wrong = module.legacy.affine_cutoff(self.config, 121, 1e-7)
        adjacency.write_text(text.replace(f"{actual:.6g}", f"{wrong:.6g}"), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "MI threshold"):
            module.validate_adjacency(adjacency, genes, hubs, frozen, log)

    def test_wrong_sampling_headers_and_missing_sampler_log_are_rejected(self):
        frozen, genes, hubs, adjacency, log = self.native_fixture()
        header, native_log = adjacency.read_text(encoding="utf-8"), log.read_text(encoding="utf-8")
        changes = [
            ("header", "Sampling method fixed-size without replacement", "Sampling method replacement"),
            ("header", "Sampling request 80%", "Sampling request 90%"),
            ("header", "Eligible observations 121", "Eligible observations 120"),
            ("header", "Sampled observations 97", "Sampled observations 96"),
            ("log", "Array No: 97", "Array No: 121"),
            ("log", "selected 97 of 121", "selected 96 of 121"),
            ("log", "eligible observations (request: 80%)", "eligible observations (request: 90%)")]
        for kind, old, new in changes:
            with self.subTest(kind=kind, old=old):
                adjacency.write_text(header.replace(old, new) if kind == "header" else header,
                                     encoding="utf-8")
                log.write_text(native_log.replace(old, new) if kind == "log" else native_log,
                               encoding="utf-8")
                with self.assertRaises(ValueError):
                    module.validate_adjacency(adjacency, genes, hubs, frozen, log)
        adjacency.write_text(header, encoding="utf-8")
        log.write_text("Marker No: 3 (3 active), Array No: 97\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            module.validate_adjacency(adjacency, genes, hubs, frozen, log)

    def test_adjacency_body_requires_known_unique_gene_sources_and_targets(self):
        frozen, genes, hubs, adjacency, log = self.native_fixture()
        text = adjacency.read_text(encoding="utf-8")
        header = text[:text.index("A\tB\t0.7")]
        for body in ("C\tA\t0.7\n", "A\tunknown\t0.7\n", "A\tA\t0.7\n",
                     "A\tB\t0.7\tB\t0.8\n", "A\tB\t0.7\nA\tC\t0.8\n",
                     "A\tB\tnan\n", "A\tB\t-0.1\n", "A\tB\n"):
            with self.subTest(body=body):
                adjacency.write_text(header + body, encoding="utf-8")
                with self.assertRaises(ValueError):
                    module.validate_adjacency(adjacency, genes, hubs, frozen, log)

    def test_expression_observation_identifiers_and_body_are_validated(self):
        original = self.expression.read_text(encoding="utf-8")
        for change in (lambda text: text.replace("metacell_002", "metacell_001", 1),
                       lambda text: text.replace("A\tA\t0", "A\tA\tnan", 1),
                       lambda text: text.replace("B\tB", "A\tB", 1)):
            with self.subTest(change=change):
                self.expression.write_text(change(original), encoding="utf-8")
                with self.assertRaises(ValueError):
                    module.legacy.expression_info(self.expression)
        self.expression.write_text(original, encoding="utf-8")

    def test_mocked_full_run_uses_original_consensus_and_preserves_baseline(self):
        baseline_bytes = {path: path.read_bytes() for root in
                          (self.baseline_root, self.baseline_source, self.prepared, self.comparison)
                          for path in root.rglob("*") if path.is_file()}
        helpers = {Path(module.legacy.__file__): Path(module.legacy.__file__).read_bytes()}
        for name in ("run_full_baseline.py", "complete_baseline.py", "score_author.R"):
            path = Path(__file__).with_name(name)
            helpers[path] = path.read_bytes()
        state = self.run_mocked()
        self.assertEqual(state["status"], "complete")
        self.assertEqual(len(state["bootstraps"]), 100)
        self.assertEqual(len(state["consensus"]), 2)
        self.assertEqual(len(self.calls), 102)
        commands = [command for command in self.calls if "-u" not in command]
        self.assertEqual([float(command[command.index("-p") + 1]) for command in commands], [.01, .001])
        self.assertTrue(all(command[1] == str(self.consensus.resolve()) for command in commands))
        for p in (.01, .001):
            directory = self.out / module.legacy.consensus_name(p)
            self.assertEqual((directory / "edges.tsv").read_bytes(),
                             (directory / "consensus_network_3col_.txt").read_bytes())
        self.assertEqual({path: path.read_bytes() for path in baseline_bytes}, baseline_bytes)
        self.assertEqual({path: path.read_bytes() for path in helpers}, helpers)
        self.assertFalse((self.out / ".runner.lock").exists())

    def test_resume_reuses_all_verified_completed_jobs(self):
        self.run_mocked()
        self.args.resume = True
        self.args.workers = 3
        state = self.run_mocked()
        self.assertEqual(state["status"], "complete")
        self.assertEqual(len(self.calls), 102)

    def test_existing_completed_run_requires_explicit_resume(self):
        self.run_mocked()
        with self.assertRaises(FileExistsError):
            self.run_mocked()
        self.assertEqual(len(self.calls), 102)

    def test_completed_after_output_hash_drift_blocks_resume(self):
        self.run_mocked()
        self.args.resume = True
        (self.out / "adj" / "bootstrap_001.adj").write_text("changed\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "(changed|hash|mismatch)"):
            self.run_mocked()
        self.assertEqual(len(self.calls), 102)

    def test_exclusive_publish_never_replaces_existing_file(self):
        temporary, target = self.root / "temporary", self.root / "target"
        temporary.write_text("new", encoding="utf-8")
        target.write_text("old", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            module.legacy.publish_file(temporary, target)
        self.assertEqual(target.read_text(encoding="utf-8"), "old")

    def test_existing_runner_lock_blocks_without_subprocess(self):
        self.out.mkdir()
        self.args.resume = True
        self.write(self.out / "run_manifest.json", {})
        lock = self.out / ".runner.lock"
        lock.write_text("another owner", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            self.run_mocked()
        self.assertFalse(self.calls)
        self.assertEqual(lock.read_text(encoding="utf-8"), "another owner")

    def test_uncheckpointed_adjacency_is_never_adopted_or_overwritten(self):
        (self.out / "adj").mkdir(parents=True)
        path = self.out / "adj" / "bootstrap_001.adj"
        path.write_text("retain this orphan", encoding="utf-8")
        with self.assertRaisesRegex(FileExistsError, "(Uncheckpointed|uncheckpointed|fresh|existing)"):
            self.run_mocked()
        self.assertFalse(self.calls)
        self.assertEqual(path.read_text(encoding="utf-8"), "retain this orphan")


if __name__ == "__main__":
    unittest.main()
