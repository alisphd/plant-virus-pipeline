from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_TMP_ROOT = REPO_ROOT / ".tmp-tests"


class CliSmokeTests(unittest.TestCase):
    def test_dry_run_creates_plan_and_report(self) -> None:
        TEST_TMP_ROOT.mkdir(exist_ok=True)
        output_dir = TEST_TMP_ROOT / "cli_smoke"
        if output_dir.exists():
            shutil.rmtree(output_dir)

        command = [
            sys.executable,
            "-m",
            "plant_virus_pipeline",
            "run",
            "--reads1",
            str(REPO_ROOT / "data" / "demo_R1.fastq"),
            "--reads2",
            str(REPO_ROOT / "data" / "demo_R2.fastq"),
            "--host-reference",
            str(REPO_ROOT / "data" / "demo_host_reference.fasta"),
            "--output",
            str(output_dir),
            "--dry-run",
        ]

        try:
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(completed.returncode, 0, completed.stderr or completed.stdout)
            self.assertTrue((output_dir / "pipeline_plan.json").exists())
            self.assertTrue((output_dir / "05_report" / "summary.json").exists())
            self.assertTrue((output_dir / "05_report" / "summary.md").exists())

            with (output_dir / "pipeline_plan.json").open("r", encoding="utf-8") as handle:
                plan = json.load(handle)

            self.assertTrue(plan["dry_run"])
            self.assertGreaterEqual(len(plan["commands"]), 4)
        finally:
            if output_dir.exists():
                shutil.rmtree(output_dir)


if __name__ == "__main__":
    unittest.main()
