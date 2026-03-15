from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from plant_virus_pipeline.reporting import collect_summary, render_markdown, write_report


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_TMP_ROOT = REPO_ROOT / ".tmp-tests"


class ReportingTests(unittest.TestCase):
    def test_report_collects_available_outputs(self) -> None:
        TEST_TMP_ROOT.mkdir(exist_ok=True)
        output_dir = TEST_TMP_ROOT / "reporting_smoke"
        if output_dir.exists():
            shutil.rmtree(output_dir)

        try:
            (output_dir / "01_qc" / "trimmed").mkdir(parents=True)
            (output_dir / "03_assembly").mkdir(parents=True)
            (output_dir / "04_classification").mkdir(parents=True)

            with (output_dir / "pipeline_plan.json").open("w", encoding="utf-8") as handle:
                json.dump({"dry_run": False, "threads": 8, "host_reference": "/tmp/host.fa"}, handle)

            with (output_dir / "01_qc" / "trimmed" / "fastp.json").open("w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "summary": {
                            "before_filtering": {"total_reads": 100, "total_bases": 10000},
                            "after_filtering": {"total_reads": 80, "total_bases": 7600},
                        }
                    },
                    handle,
                )

            with (output_dir / "03_assembly" / "final.contigs.fa").open("w", encoding="utf-8") as handle:
                handle.write(">contig_1\nACGTACGT\n>contig_2\nTTTTCCCCAAAA\n")

            with (output_dir / "04_classification" / "blast_hits.tsv").open("w", encoding="utf-8") as handle:
                handle.write(
                    "contig_1\tvirus_1\t98.5\t120\t210.0\t1e-30\tTomato mosaic virus isolate\n"
                )

            with (output_dir / "04_classification" / "kraken_report.tsv").open("w", encoding="utf-8") as handle:
                handle.write("12.50\t10\t10\tS\t12345\tTomato mosaic virus\n")

            summary = collect_summary(output_dir)

            self.assertEqual(summary["assembly"]["contig_count"], 2)
            self.assertEqual(summary["assembly"]["total_bases"], 20)
            self.assertEqual(summary["blast_top_hits"][0]["query"], "contig_1")
            self.assertEqual(summary["kraken_top_hits"][0]["name"], "Tomato mosaic virus")

            markdown = render_markdown(summary)
            self.assertIn("Tomato mosaic virus", markdown)

            summary_json, summary_md = write_report(output_dir)
            self.assertTrue(summary_json.exists())
            self.assertTrue(summary_md.exists())
        finally:
            if output_dir.exists():
                shutil.rmtree(output_dir)


if __name__ == "__main__":
    unittest.main()
