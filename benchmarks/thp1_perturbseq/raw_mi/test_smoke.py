"""Offline unit tests; native smoke is an explicit separate command."""

import tempfile
from pathlib import Path
import unittest

import smoke


class SmokeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def adjacency(self, body="A\tB\t0.123456\n"):
        path = self.root / "test.adj"
        path.write_text(">  MI threshold    0\n>  MI P-value      1\n>  DPI tolerance   1\n" + body)
        return path

    def test_implicit_zeros_are_not_lost_from_comparison_universe(self):
        scores, _ = smoke.parse_adj(self.adjacency(), {"A"}, {"A", "B", "C"})
        result = smoke.compare_scores(scores, scores, ["A"], ["A", "B", "C"])
        self.assertEqual(result["candidate_pairs"], 2)
        self.assertEqual(result["implicit_zero_pairs"], 1)

    def test_all_zero_source_may_be_omitted(self):
        scores, _ = smoke.parse_adj(self.adjacency(""), {"A"}, {"A", "B"})
        self.assertEqual(smoke.compare_scores(scores, scores, ["A"], ["A", "B"])["implicit_zero_pairs"], 1)

    def test_changed_value_and_zero_pattern_are_rejected(self):
        reference = {("A", "B"): "0.1"}
        for alternative in ({}, {("A", "B"): "0.2"}, {("A", "C"): "0.1"}):
            with self.subTest(alternative=alternative), self.assertRaises(ValueError):
                smoke.compare_scores(reference, alternative, ["A"], ["A", "B", "C"])

    def test_unrelated_sources_do_not_affect_shared_pair_comparison(self):
        reference = {("A", "B"): "0.1"}
        other = {**reference, ("C", "B"): "0.9"}
        self.assertTrue(smoke.compare_scores(reference, other, ["A"], ["A", "B", "C"])["exact_serialized_mi_equality"])

    def test_malformed_pairs_rejected(self):
        for body in ("A\tB\t0.1\tB\t0.2\n", "A\tA\t0.1\n", "A\tX\t0.1\n",
                     "A\tB\t0\n", "A\tB\t-0.1\n", "A\tB\tnan\n", "A\tB\tinf\n",
                     "A\tB\n", "A\tB\t0.1\nA\tB\t0.2\n", "X\tB\t0.1\n"):
            with self.subTest(body=body), self.assertRaises(ValueError):
                smoke.parse_adj(self.adjacency(body), {"A"}, {"A", "B", "C"})

    def test_filter_headers_rejected(self):
        path = self.adjacency()
        path.write_text(path.read_text().replace("MI threshold    0", "MI threshold    0.1"))
        with self.assertRaises(ValueError):
            smoke.parse_adj(path, {"A"}, {"A", "B"})

    def test_before_and_after_log_counts(self):
        before = "Marker No: 17971 (17971 active), Array No: 121\n"
        after = ("[SAMPLING] Fixed-size sampling without replacement: selected 97 of 121 "
                 "eligible observations (request: 80%).\nMarker No: 17971 (17971 active), Array No: 97\n")
        self.assertEqual(smoke.audit_log(before, genes=17971, observations=121, arm="before")["draws"], 121)
        self.assertEqual(smoke.audit_log(after, genes=17971, observations=121, arm="after")["draws"], 97)
        for text, arm in ((before, "after"), (before + "Applying DPI", "before"),
                          (before + "MI threshold determined", "before"),
                          (before + "Cannot find probe: _A\r ... ignored.", "before"),
                          (before.replace("17971 active", "17000 active"), "before")):
            with self.subTest(text=text), self.assertRaises(ValueError):
                smoke.audit_log(text, genes=17971, observations=121, arm=arm)

    def test_scopes_selected_in_full_sig_order_not_response_scores(self):
        full = [f"G{i}" for i in range(12)]
        scopes = smoke.source_scopes(full, {"G2", "G5", "G8", "G10"})
        self.assertEqual(scopes["subset"], ["G2", "G8", "G10"])
        self.assertEqual(scopes["reordered"], ["G10", "G8", "G2"])
        self.assertEqual(len(scopes["expanded"]), 7)

    def test_commands_disable_threshold_and_dpi(self):
        paths = [self.root / name for name in ("binary", "expression", "annotation", "sources", "config", "out")]
        for arm, flag in (("before", "-r"), ("after", "-u")):
            command = smoke.native_command(*paths, 2, arm)
            for option, expected in (("-p", "1"), ("-t", "0"), ("-e", "1"), ("-N", "40"), ("-n", "0")):
                self.assertEqual(command[command.index(option) + 1], expected)
            self.assertIn(flag, command)
            self.assertNotIn("-c", command)
            self.assertNotIn("-m", command)

    def test_tiny_expression_is_unique_and_sixteen_by_sixteen(self):
        expression, annotation, scopes = smoke.make_tiny(self.root)
        info = smoke.expression_info(expression)
        self.assertEqual(len(info["genes"]), 16)
        self.assertEqual(info["observations"], 16)
        self.assertEqual(len(scopes["expanded"]), 8)
        self.assertNotIn(b"\r", expression.read_bytes())
        self.assertNotIn(b"\r", annotation.read_bytes())

    def test_file_pin_detects_tamper(self):
        path = self.root / "pinned"
        path.write_text("original")
        digest = smoke.sha256(path)
        self.assertEqual(smoke.file_record(path, digest)["bytes"], 8)
        path.write_text("changed")
        with self.assertRaises(ValueError):
            smoke.file_record(path, digest)


if __name__ == "__main__":
    unittest.main()
