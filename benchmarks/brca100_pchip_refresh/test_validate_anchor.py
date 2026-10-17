"""Synthetic anchor tests; no inference jobs or historical data are opened."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("brca_anchor", Path(__file__).with_name("validate_anchor.py"))
anchor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(anchor)


def fake_design():
    return {"commit": anchor.OLD_COMMIT,
            "fixed_parameters": {"m": 80, "npar": 40, "dpi_epsilon": 0,
                                 "seeds": list(range(1, 101))},
            "all_points": [{"key": "p1e-03", "p_value": 0.001,
                            "mi_cutoff": 0.14732247558240297,
                            "mi_cutoff_header": "0.147322"}]}


class AnchorTests(unittest.TestCase):
    def test_cutoff_is_full_precision_not_header(self):
        value = anchor.historical_cutoff(fake_design())
        self.assertEqual(value, 0.14732247558240297)
        self.assertNotEqual(value, float("0.147322"))

    def test_cutoff_rejects_wrong_source_or_design(self):
        for key, value in (("m", 90), ("npar", 20), ("dpi_epsilon", 0.1)):
            design = fake_design()
            design["fixed_parameters"][key] = value
            with self.assertRaises(RuntimeError):
                anchor.historical_cutoff(design)
        design = fake_design()
        design["commit"] = "wrong"
        with self.assertRaises(RuntimeError):
            anchor.historical_cutoff(design)

    def test_cutoff_rejects_missing_or_duplicate_point(self):
        for points in ([], fake_design()["all_points"] * 2):
            design = fake_design()
            design["all_points"] = points
            with self.assertRaises(RuntimeError):
                anchor.historical_cutoff(design)

    def test_command_bypasses_models_and_preserves_sampling_dpi(self):
        cutoff = anchor.historical_cutoff(fake_design())
        command = anchor.anchor_command({"binary": "/binary", "config": "/config"},
                                        Path("/work"), Path("/validation/anchor.adj"), cutoff)
        options = dict(zip(command[1::2], command[2::2]))
        self.assertEqual(float(options["-t"]), cutoff)
        self.assertEqual(options["-S"], "1")
        self.assertEqual(options["-N"], "40")
        self.assertEqual(options["-e"], "0")
        self.assertEqual(options["-u"], "80%")
        self.assertEqual(options["-l"], options["-s"])
        self.assertNotIn("-M", options)
        self.assertNotIn("-p", options)


if __name__ == "__main__":
    unittest.main()
