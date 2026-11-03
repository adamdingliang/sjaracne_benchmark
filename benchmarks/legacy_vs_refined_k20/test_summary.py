"""Check published tables, links and figure provenance without scientific runs."""

import csv
import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]


def table_rows(path, header_prefix):
    """Read one simple Markdown table, identified by its exact header prefix."""
    lines = path.read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith(header_prefix))
    rows = []
    for line in lines[start + 2:]:
        if not line.startswith("|"):
            break
        rows.append([cell.strip() for cell in line.strip("|").split("|")])
    return rows


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class SummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = json.loads((ROOT / "evidence/report_data.json").read_text(encoding="utf-8"))
        with (ROOT / "evidence/overall_metrics.tsv").open(encoding="utf-8", newline="") as handle:
            cls.metrics = {(r["comparison"], r["id"]): r
                           for r in csv.DictReader(handle, delimiter="\t")}

    def test_primary_dream_table_matches_counts_and_derived_rates(self):
        rows = table_rows(ROOT / "RESULTS.md", "| Dataset | Workflow / consensus | TP |")
        self.assertEqual(len(rows), 4)
        for cells, record in zip(rows, self.report["primary_dream"]):
            metric = record["metrics"]
            f1 = 2 * metric["TP"] / (2 * metric["TP"] + metric["FP"] + metric["FN"])
            expected = [f'{metric["TP"]:,}', f'{metric["FP"]:,}',
                        f'{metric["precision"]:.2%}', f'{metric["recall"]:.2%}',
                        f'{f1:.4f}', f'{metric["edges_all"]:,}', f'{metric["edges_unlabeled"]:,}']
            self.assertEqual(cells[2:], expected, record["id"])

    def test_matched_dream_table_matches_frozen_evidence(self):
        rows = table_rows(ROOT / "RESULTS.md", "| Dataset | Resample-generation configuration |")
        self.assertEqual(len(rows), 4)
        for cells, record in zip(rows, self.report["matched_dream"]):
            metric = self.metrics[("matched_dream_K20", record["id"])]
            self.assertEqual(cells[2:], [f'{int(metric["TP"]):,}', f'{int(metric["FP"]):,}',
                f'{float(metric["precision"]):.2%}', f'{float(metric["recall"]):.2%}',
                f'{float(metric["F1"]):.4f}'], record["id"])

    def test_primary_bulk_table_matches_frozen_evidence(self):
        rows = table_rows(ROOT / "RESULTS.md", "| Dataset | Network | Workflow / consensus |")
        self.assertEqual(len(rows), 12)
        for cells, record in zip(rows, self.report["primary_bulk"]):
            metric = record["metrics"]
            self.assertEqual(cells[:2], [record["dataset"], record["network"]])
            self.assertEqual(cells[3:], [f'{metric["edges_all"]:,}',
                f'{metric["active_driver_fraction"]:.2%}', f'{metric["median_targets"]:g}',
                f'{metric["median_targets_active_only"]:g}',
                f'{metric["scale_free_adjusted_r2"]:.4f}'], record["id"])

    def test_matched_bulk_table_matches_frozen_evidence(self):
        rows = table_rows(ROOT / "RESULTS.md", "| Dataset | Network | Resamples |")
        self.assertEqual(len(rows), 8)
        for cells in rows:
            version = "legacy" if cells[2].startswith("Legacy") else "current"
            identifier = f"{cells[0]}_{cells[1]}_{version}"
            metric = self.metrics[("matched_bulk_K20", identifier)]
            self.assertEqual(cells[3:], [f'{int(metric["edges_all"]):,}',
                f'{float(metric["median_targets"]):g}',
                f'{float(metric["scale_free_adjusted_r2"]):.4f}'], identifier)

    def test_k6_k20_table_matches_both_recorded_operating_points(self):
        rows = table_rows(ROOT / "RESULTS.md", "| Dataset | Network | K6 edges |")
        old = {r["id"]: r["metrics"] for r in self.report["original_current_K6"]}
        self.assertEqual(len(rows), 4)
        for cells in rows:
            identifier = f"{cells[0]}_{cells[1]}_current"
            before = old[identifier]
            after = self.metrics[("primary_bulk", identifier)]
            self.assertEqual(cells[2:], [f'{before["edges_all"]:,}',
                f'{int(after["edges_all"]):,}', f'{before["median_targets"]:g}',
                f'{float(after["median_targets"]):g}',
                f'{before["scale_free_adjusted_r2"]:.4f}',
                f'{float(after["scale_free_adjusted_r2"]):.4f}'])

    def test_concise_summary_matches_primary_metric_tables(self):
        path = REPO / "docs/benchmark_summaries/legacy_refined_k20.md"
        dream_rows = table_rows(path, "| Dataset | Workflow / consensus | TP |")
        detailed = table_rows(ROOT / "RESULTS.md", "| Dataset | Workflow / consensus | TP |")
        self.assertEqual([r[2:] for r in dream_rows], [r[2:7] for r in detailed])
        bulk_rows = table_rows(path, "| Dataset | Network | Legacy median targets |")
        primary = {r["id"]: r["metrics"] for r in self.report["primary_bulk"]}
        self.assertEqual(len(bulk_rows), 6)
        for cells in bulk_rows:
            prefix = f"{cells[0]}_{cells[1]}_"
            a, b = primary[prefix + "legacy"], primary[prefix + "current"]
            self.assertEqual(cells[2:], [f'{a["median_targets"]:g}', f'{b["median_targets"]:g}',
                f'{a["scale_free_adjusted_r2"]:.4f}', f'{b["scale_free_adjusted_r2"]:.4f}'])

    def test_all_new_document_links_resolve_inside_repository(self):
        documents = list(ROOT.glob("*.md")) + [REPO / "docs/benchmark_summaries/legacy_refined_k20.md"]
        for document in documents:
            for link in re.findall(r"!?\[[^\]]*\]\(([^\s)]+)\)", document.read_text(encoding="utf-8")):
                if "://" in link or link.startswith("#"):
                    continue
                target = (document.parent / link.split("#")[0]).resolve()
                self.assertTrue(target.is_relative_to(REPO.resolve()), str(target))
                self.assertTrue(target.is_file(), f"{document.name}: {link}")

    def test_qc_catalog_covers_every_original_png_once(self):
        catalog = (ROOT / "NETBID2_FIGURES.md").read_text(encoding="utf-8")
        links = re.findall(r"!\[[^\]]*\]\((figures/netbid2/[^)]+)\)", catalog)
        expected = {p.relative_to(ROOT).as_posix() for p in (ROOT / "figures/netbid2").glob("*.png")}
        self.assertEqual(len(links), 24)
        self.assertEqual(set(links), expected)

    def test_overview_figures_and_code_match_recorded_hashes(self):
        provenance = json.loads((ROOT / "figures/overview_manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(digest(ROOT / provenance["source"]), provenance["source_sha256"])
        self.assertEqual(digest(ROOT / provenance["plot_code"]), provenance["plot_code_sha256"])
        for figure in provenance["plots"]:
            self.assertEqual(digest(ROOT / figure["path"]), figure["sha256"])

    def test_default_proposal_is_explicitly_scoped(self):
        results = (ROOT / "RESULTS.md").read_text(encoding="utf-8")
        self.assertIn("default for the standard B=100", results)
        self.assertIn("separate engine PR", results)
        self.assertIn("no BLCA K6 baseline", results)
        self.assertNotIn("\ufffd", results)


if __name__ == "__main__":
    unittest.main()
