from __future__ import annotations

import importlib.util
import shutil
import unittest
from pathlib import Path


FASTAPI_AVAILABLE = bool(importlib.util.find_spec("fastapi")) and bool(
    importlib.util.find_spec("httpx")
)

if FASTAPI_AVAILABLE:
    from fastapi.testclient import TestClient

    from plant_virus_pipeline.web import create_app


REPO_ROOT = Path(__file__).resolve().parents[1]
TEST_TMP_ROOT = REPO_ROOT / ".tmp-tests"


@unittest.skipUnless(FASTAPI_AVAILABLE, "fastapi/httpx not installed")
class WebTests(unittest.TestCase):
    def test_healthz_and_environment_routes(self) -> None:
        TEST_TMP_ROOT.mkdir(exist_ok=True)
        runtime_dir = TEST_TMP_ROOT / "web_smoke"
        if runtime_dir.exists():
            shutil.rmtree(runtime_dir)

        try:
            app = create_app(runtime_dir=runtime_dir, allow_real_runs=False)
            client = TestClient(app)

            health = client.get("/healthz")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["status"], "ok")

            environment = client.get("/api/environment")
            self.assertEqual(environment.status_code, 200)
            payload = environment.json()
            self.assertFalse(payload["allow_real_runs"])
            self.assertIn("environment", payload)

            home = client.get("/")
            self.assertEqual(home.status_code, 200)
            self.assertIn("Plant Virus Pipeline", home.text)
            self.assertIn("Demo mode", home.text)
            self.assertIn("What This Is Not", home.text)
        finally:
            if runtime_dir.exists():
                shutil.rmtree(runtime_dir)

    def test_job_submission_creates_report(self) -> None:
        TEST_TMP_ROOT.mkdir(exist_ok=True)
        runtime_dir = TEST_TMP_ROOT / "web_job_smoke"
        if runtime_dir.exists():
            shutil.rmtree(runtime_dir)

        try:
            app = create_app(runtime_dir=runtime_dir, allow_real_runs=False)
            client = TestClient(app)

            with (REPO_ROOT / "data" / "demo_R1.fastq").open("rb") as reads1_handle:
                with (REPO_ROOT / "data" / "demo_R2.fastq").open("rb") as reads2_handle:
                    with (REPO_ROOT / "data" / "demo_host_reference.fasta").open("rb") as host_handle:
                        response = client.post(
                            "/api/jobs",
                            data={"threads": "2", "dry_run": "true"},
                            files={
                                "reads1": ("demo_R1.fastq", reads1_handle, "text/plain"),
                                "reads2": ("demo_R2.fastq", reads2_handle, "text/plain"),
                                "host_reference": (
                                    "demo_host_reference.fasta",
                                    host_handle,
                                    "text/plain",
                                ),
                            },
                        )

            self.assertEqual(response.status_code, 200, response.text)
            payload = response.json()
            self.assertEqual(payload["status"], "queued")

            job_id = payload["job_id"]
            job = client.get(f"/api/jobs/{job_id}")
            self.assertEqual(job.status_code, 200)
            job_payload = job.json()
            self.assertEqual(job_payload["status"], "succeeded")

            report = client.get(f"/api/jobs/{job_id}/report")
            self.assertEqual(report.status_code, 200)
            report_payload = report.json()
            self.assertIn("plan", report_payload)
        finally:
            if runtime_dir.exists():
                shutil.rmtree(runtime_dir)


if __name__ == "__main__":
    unittest.main()
