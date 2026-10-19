import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location("check_examples", Path(__file__).with_name("check_examples.py"))
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class TestCheckExamples(unittest.TestCase):
    def test_extracts_continuations_comments_and_quoted_paths(self):
        text = "```bash\n# comment\nsjaracne local \\\n -e 'input file.exp' -g hubs.txt # trailing comment\n```\n"
        self.assertEqual(CHECK.bash_commands(text), [["sjaracne", "local", "-e", "input file.exp", "-g", "hubs.txt"]])

    def test_non_bash_ignored_and_unclosed_rejected(self):
        self.assertEqual(CHECK.bash_commands("```python\nsjaracne local\n```"), [])
        with self.assertRaisesRegex(ValueError, "Unclosed"):
            CHECK.bash_commands("```bash\nsjaracne local")

    def test_output_rewrite_preserves_other_arguments(self):
        original = ["sjaracne", "local", "-n", "100", "-M", "pchip", "-pb", ".001", "-k", "6", "-o", "old", "-tmp", "oldtmp"]
        result = CHECK.replace_output_paths(original, Path("new"), Path("newtmp"))
        self.assertEqual(result[:-4], original[:-4])
        self.assertEqual(result[-4:], ["-o", "new", "-tmp", "newtmp/"])
        self.assertEqual(original[-3], "old")

    def test_missing_or_duplicate_output_rejected(self):
        for argv in (["sjaracne", "local", "-o", "x"],
                     ["sjaracne", "local", "-o", "x", "--output-dir", "y", "-tmp", "z"]):
            with self.subTest(argv=argv), self.assertRaises(ValueError):
                CHECK.replace_output_paths(argv, Path("out"), Path("tmp"))

    def test_generated_job_scalar_types_and_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "job.yml"
            path.write_text('exp_file:\n  class: File\n  path: /x\nmin_recurrence: 6\nsubsample_spec: "80%"\np_value_bootstrap: 1e-7\n')
            job = CHECK.read_job(path)
            self.assertEqual(job["exp_file"], {"class": "File", "path": "/x"})
            self.assertEqual(job["min_recurrence"], 6)
            self.assertEqual(job["subsample_spec"], "80%")
            self.assertEqual(job["p_value_bootstrap"], 1e-7)
            path.write_text("min_recurrence: 6\nmin_recurrence: 1\n")
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                CHECK.read_job(path)

    def test_runtime_identity_rejects_runtime_or_tracked_path_changes(self):
        baseline = "100644 blob abc\tREADME.md\n100644 blob def\tSJARACNe/sjaracne.py"
        def output(engine, *args):
            if args[:3] == ("diff", "--name-only", "HEAD"):
                return ""
            if args[0] == "ls-tree":
                return baseline
            if args[0] == "ls-files":
                return "README.md\nSJARACNe/sjaracne.py"
            if args[:2] == ("diff", "--name-only"):
                return "SJARACNe/sjaracne.py"
            self.fail(args)
        with mock.patch.object(CHECK, "git", side_effect=output), self.assertRaisesRegex(ValueError, "Unvalidated"):
            CHECK.runtime_identity(Path("engine"))
        with mock.patch.object(CHECK, "git", side_effect=["", baseline, "README.md"]), self.assertRaisesRegex(ValueError, "path set"):
            CHECK.runtime_identity(Path("engine"))

    def test_runtime_identity_allows_only_example_modifications(self):
        values = ["", "100644 blob abc\tREADME.md\n100644 blob def\tSJARACNe/sjaracne.py",
                  "README.md\nSJARACNe/sjaracne.py", "README.md", "M\tREADME.md", "head"]
        with mock.patch.object(CHECK, "git", side_effect=values):
            result = CHECK.runtime_identity(Path("engine"))
        self.assertEqual(result["changed_tracked_paths"], ["README.md"])
        self.assertEqual(result["unchanged_runtime_tracked_paths"], 1)

    def test_wsl_maps_windows_linked_worktree_pointer_read_only(self):
        with mock.patch.object(CHECK.sys, "platform", "linux"), \
                mock.patch.object(Path, "is_file", return_value=True), \
                mock.patch.object(Path, "read_text", return_value="gitdir: D:/GitHub/SJARACNe/.git/worktrees/pr3\n"), \
                mock.patch.object(Path, "resolve", lambda value: value):
            actual = [value.replace("\\", "/") for value in CHECK.git_location(Path("/mnt/d/GitHub/pr3"))]
            self.assertEqual(actual, [
                "-c", "core.autocrlf=true", "-c", "core.fileMode=false",
                "--git-dir=/mnt/d/GitHub/SJARACNe/.git/worktrees/pr3",
                "--work-tree=/mnt/d/GitHub/pr3"])

    def test_dirty_tracked_working_state_rejected(self):
        with mock.patch.object(CHECK, "git", return_value="README.md"), \
                self.assertRaisesRegex(ValueError, "must be clean"):
            CHECK.runtime_identity(Path("engine"))

    def test_attributes_exception_requires_exact_baseline_plus_narrow_append(self):
        original = b"SJARACNe/config/apmi_pchip.json -text\n"
        with mock.patch.object(CHECK, "git_blob", side_effect=[original, original + CHECK.ATTRIBUTE_APPEND]):
            result = CHECK.check_attribute_append(Path("engine"), "baseline")
            self.assertEqual(result["path"], ".gitattributes")
        for current in (original + CHECK.ATTRIBUTE_APPEND + b"*.json text\n",
                        original.replace(b"-text", b"text") + CHECK.ATTRIBUTE_APPEND):
            with mock.patch.object(CHECK, "git_blob", side_effect=[original, current]), \
                    self.assertRaisesRegex(ValueError, "exact baseline bytes"):
                CHECK.check_attribute_append(Path("engine"), "baseline")

    def test_expected_contracts_are_distinct_and_cover_all_five_cases(self):
        self.assertEqual(len(CHECK.EXPECTED), 5)
        self.assertEqual(set(CHECK.EXPECTED.values()), {"local_smoke", "local_tf_pchip", "local_sig_pchip", "lsf_tf_pchip", "explicit_legacy_consensus"})
        self.assertIn(("local", 100, "80", "pchip", .001, ("pc", 1e-5), "BRCA100_TF.txt"), CHECK.EXPECTED)


if __name__ == "__main__":
    unittest.main()
