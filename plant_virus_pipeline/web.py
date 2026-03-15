from __future__ import annotations

import json
import os
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse

from .pipeline import PipelineConfig, check_environment, run_pipeline
from .reporting import collect_summary, write_report


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, runtime_dir: Path) -> None:
        self.runtime_dir = runtime_dir
        self.jobs_dir = runtime_dir / "jobs"
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()

    def job_dir(self, job_id: str) -> Path:
        return self.jobs_dir / job_id

    def job_file(self, job_id: str) -> Path:
        return self.job_dir(job_id) / "job.json"

    def write(self, record: dict[str, Any]) -> None:
        job_id = str(record["job_id"])
        job_path = self.job_file(job_id)
        job_path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            with job_path.open("w", encoding="utf-8") as handle:
                json.dump(record, handle, indent=2)

    def read(self, job_id: str) -> dict[str, Any]:
        job_path = self.job_file(job_id)
        if not job_path.exists():
            raise HTTPException(status_code=404, detail=f"Unknown job: {job_id}")
        with job_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def list(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in self.jobs_dir.glob("*/job.json"):
            with path.open("r", encoding="utf-8") as handle:
                records.append(json.load(handle))
        return sorted(records, key=lambda item: item.get("created_at", ""), reverse=True)


async def _save_upload(upload: UploadFile, destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as handle:
        while True:
            chunk = await upload.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    await upload.close()
    return destination


def _job_record(
    job_id: str,
    config: PipelineConfig,
    inputs: dict[str, str | None],
    allow_real_runs: bool,
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "status": "queued",
        "created_at": _utcnow(),
        "started_at": None,
        "finished_at": None,
        "allow_real_runs": allow_real_runs,
        "config": config.serializable(),
        "inputs": inputs,
        "output_dir": str(config.output),
        "summary_json": None,
        "summary_md": None,
        "summary": None,
        "error": None,
    }


def _render_home(runtime_dir: Path, allow_real_runs: bool) -> str:
    checked = "" if allow_real_runs else "checked"
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Plant Virus Pipeline</title>
  <style>
    :root {{
      --bg: #f5f1e8;
      --card: #fffdf8;
      --ink: #23313a;
      --accent: #1d6b52;
      --muted: #5f6d76;
      --line: #d8d1c4;
    }}
    body {{
      margin: 0;
      font-family: "Trebuchet MS", "Segoe UI", sans-serif;
      background:
        radial-gradient(circle at top left, #f2dcc2 0, transparent 32%),
        radial-gradient(circle at top right, #d6eadf 0, transparent 28%),
        var(--bg);
      color: var(--ink);
    }}
    .shell {{
      max-width: 1040px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }}
    .hero {{
      display: grid;
      gap: 18px;
      margin-bottom: 24px;
    }}
    .hero h1 {{
      margin: 0;
      font-size: clamp(2rem, 5vw, 3.8rem);
      line-height: 0.95;
      letter-spacing: -0.04em;
    }}
    .hero p {{
      margin: 0;
      max-width: 780px;
      color: var(--muted);
      font-size: 1.05rem;
    }}
    .badge-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .badge {{
      border: 1px solid var(--line);
      background: rgba(255,255,255,0.75);
      padding: 8px 12px;
      border-radius: 999px;
      font-size: 0.95rem;
    }}
    .grid {{
      display: grid;
      gap: 18px;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      box-shadow: 0 12px 40px rgba(20, 36, 32, 0.06);
    }}
    h2 {{
      margin-top: 0;
      margin-bottom: 12px;
      font-size: 1.2rem;
    }}
    label {{
      display: block;
      font-size: 0.95rem;
      margin-bottom: 6px;
    }}
    input, button {{
      width: 100%;
      box-sizing: border-box;
      border-radius: 12px;
      border: 1px solid var(--line);
      padding: 11px 12px;
      font: inherit;
    }}
    .checkbox {{
      display: flex;
      align-items: center;
      gap: 10px;
      margin-top: 10px;
    }}
    .checkbox input {{
      width: auto;
    }}
    button {{
      margin-top: 14px;
      background: var(--accent);
      color: white;
      border: none;
      cursor: pointer;
      font-weight: 600;
    }}
    button:hover {{
      filter: brightness(1.05);
    }}
    .jobs {{
      display: grid;
      gap: 12px;
    }}
    .job {{
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px;
      background: white;
    }}
    .muted {{
      color: var(--muted);
      font-size: 0.95rem;
    }}
    code {{
      background: #eef3ef;
      padding: 2px 6px;
      border-radius: 6px;
    }}
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <div class="badge-row">
        <div class="badge">Runtime: <code>{runtime_dir}</code></div>
        <div class="badge">Real runs enabled: <code>{str(allow_real_runs).lower()}</code></div>
      </div>
      <h1>Plant Virus Pipeline</h1>
      <p>Upload paired-end reads, create a job, and track the output of the pipeline from your browser. This deployment stores uploads and reports on the local filesystem.</p>
    </section>

    <section class="grid">
      <div class="card">
        <h2>Submit Job</h2>
        <form id="job-form">
          <label for="reads1">Reads R1</label>
          <input id="reads1" name="reads1" type="file" required>

          <label for="reads2">Reads R2</label>
          <input id="reads2" name="reads2" type="file" required>

          <label for="host_reference">Host Reference (optional)</label>
          <input id="host_reference" name="host_reference" type="file">

          <label for="blast_db">BLAST Database Prefix (optional server path)</label>
          <input id="blast_db" name="blast_db" type="text" placeholder="/db/blast/viral">

          <label for="kraken_db">Kraken2 Database Path (optional server path)</label>
          <input id="kraken_db" name="kraken_db" type="text" placeholder="/db/kraken">

          <label for="threads">Threads</label>
          <input id="threads" name="threads" type="number" value="4" min="1">

          <label class="checkbox"><input name="dry_run" type="checkbox" value="true" {checked}>Dry run</label>
          <button type="submit">Create Job</button>
        </form>
        <p id="submit-status" class="muted"></p>
      </div>

      <div class="card">
        <h2>Recent Jobs</h2>
        <div id="jobs" class="jobs">
          <div class="muted">Loading jobs...</div>
        </div>
      </div>
    </section>
  </div>

  <script>
    const form = document.getElementById("job-form");
    const status = document.getElementById("submit-status");
    const jobsEl = document.getElementById("jobs");

    async function loadJobs() {{
      const response = await fetch("/api/jobs");
      const jobs = await response.json();
      if (!jobs.length) {{
        jobsEl.innerHTML = '<div class="muted">No jobs yet.</div>';
        return;
      }}
      jobsEl.innerHTML = jobs.map(job => {{
        const reportLink = job.summary_json ? `<div><a href="/api/jobs/${{job.job_id}}/report" target="_blank">Open report JSON</a></div>` : "";
        const error = job.error ? `<div class="muted">Error: ${{job.error}}</div>` : "";
        return `
          <div class="job">
            <strong>${{job.job_id}}</strong>
            <div>Status: <code>${{job.status}}</code></div>
            <div class="muted">Created: ${{job.created_at}}</div>
            ${{reportLink}}
            ${{error}}
          </div>
        `;
      }}).join("");
    }}

    form.addEventListener("submit", async (event) => {{
      event.preventDefault();
      status.textContent = "Submitting job...";
      const data = new FormData(form);
      data.set("dry_run", data.get("dry_run") ? "true" : "false");
      const response = await fetch("/api/jobs", {{
        method: "POST",
        body: data
      }});

      const payload = await response.json();
      if (!response.ok) {{
        status.textContent = payload.detail || "Job submission failed.";
        return;
      }}

      status.textContent = `Created job ${{payload.job_id}}`;
      form.reset();
      await loadJobs();
    }});

    loadJobs();
    setInterval(loadJobs, 4000);
  </script>
</body>
</html>
"""


def create_app(
    runtime_dir: Path | None = None, allow_real_runs: bool | None = None
) -> FastAPI:
    resolved_runtime = (runtime_dir or Path(os.getenv("PVP_RUNTIME_DIR", "runtime"))).resolve()
    resolved_allow_real_runs = (
        allow_real_runs
        if allow_real_runs is not None
        else os.getenv("PVP_ALLOW_REAL_RUNS", "false").lower() in {"1", "true", "yes"}
    )
    store = JobStore(resolved_runtime)

    app = FastAPI(
        title="Plant Virus Pipeline",
        version="0.2.0",
        description="Web service wrapper for the Plant Virus Pipeline.",
    )

    def process_job(job_id: str) -> None:
        record = store.read(job_id)
        record["status"] = "running"
        record["started_at"] = _utcnow()
        store.write(record)

        try:
            config = PipelineConfig.from_mapping(record["config"])
            run_pipeline(config)
            summary_json, summary_md = write_report(config.output)
            record["status"] = "succeeded"
            record["summary_json"] = str(summary_json)
            record["summary_md"] = str(summary_md)
            record["summary"] = collect_summary(config.output)
        except Exception as exc:  # noqa: BLE001 - surfacing job failures to clients
            record["status"] = "failed"
            record["error"] = str(exc)
            record["traceback"] = traceback.format_exc()
        finally:
            record["finished_at"] = _utcnow()
            store.write(record)

    @app.get("/", response_class=HTMLResponse)
    async def home() -> str:
        return _render_home(resolved_runtime, resolved_allow_real_runs)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/environment")
    async def environment() -> dict[str, Any]:
        config = PipelineConfig(
            reads1=Path("data/demo_R1.fastq"),
            reads2=Path("data/demo_R2.fastq"),
            output=resolved_runtime / "check",
        )
        environment_info = check_environment(config)
        return {
            "runtime_dir": str(resolved_runtime),
            "allow_real_runs": resolved_allow_real_runs,
            "environment": environment_info,
        }

    @app.get("/api/jobs")
    async def list_jobs() -> list[dict[str, Any]]:
        return store.list()

    @app.get("/api/jobs/{job_id}")
    async def get_job(job_id: str) -> dict[str, Any]:
        return store.read(job_id)

    @app.get("/api/jobs/{job_id}/report")
    async def get_job_report(job_id: str) -> JSONResponse:
        record = store.read(job_id)
        summary_json = record.get("summary_json")
        if not summary_json:
            raise HTTPException(status_code=404, detail="Report not available yet.")
        with Path(summary_json).open("r", encoding="utf-8") as handle:
            return JSONResponse(json.load(handle))

    @app.get("/api/jobs/{job_id}/report.md")
    async def get_job_report_markdown(job_id: str) -> PlainTextResponse:
        record = store.read(job_id)
        summary_md = record.get("summary_md")
        if not summary_md:
            raise HTTPException(status_code=404, detail="Markdown report not available yet.")
        return PlainTextResponse(Path(summary_md).read_text(encoding="utf-8"))

    @app.post("/api/jobs")
    async def create_job(
        background_tasks: BackgroundTasks,
        reads1: UploadFile = File(...),
        reads2: UploadFile = File(...),
        host_reference: UploadFile | None = File(default=None),
        blast_db: str | None = Form(default=None),
        kraken_db: str | None = Form(default=None),
        threads: int = Form(default=4),
        dry_run: bool = Form(default=True),
        skip_fastqc: bool = Form(default=False),
        skip_host_removal: bool = Form(default=False),
        skip_assembly: bool = Form(default=False),
        skip_blast: bool = Form(default=False),
        skip_kraken: bool = Form(default=False),
    ) -> dict[str, Any]:
        if not resolved_allow_real_runs and not dry_run:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Real pipeline runs are disabled on this deployment. "
                    "Set PVP_ALLOW_REAL_RUNS=true or submit a dry run."
                ),
            )

        job_id = uuid.uuid4().hex[:12]
        job_dir = store.job_dir(job_id)
        inputs_dir = job_dir / "inputs"
        output_dir = job_dir / "output"

        reads1_name = Path(reads1.filename or "reads_R1.fastq").name
        reads2_name = Path(reads2.filename or "reads_R2.fastq").name
        reads1_path = await _save_upload(reads1, inputs_dir / reads1_name)
        reads2_path = await _save_upload(reads2, inputs_dir / reads2_name)

        host_reference_path: Path | None = None
        if host_reference and host_reference.filename:
            host_name = Path(host_reference.filename).name
            host_reference_path = await _save_upload(host_reference, inputs_dir / host_name)

        config = PipelineConfig(
            reads1=reads1_path,
            reads2=reads2_path,
            output=output_dir,
            host_reference=host_reference_path,
            blast_db=blast_db or None,
            kraken_db=Path(kraken_db) if kraken_db else None,
            threads=threads,
            dry_run=dry_run,
            skip_fastqc=skip_fastqc,
            skip_host_removal=skip_host_removal,
            skip_assembly=skip_assembly,
            skip_blast=skip_blast,
            skip_kraken=skip_kraken,
        )

        record = _job_record(
            job_id=job_id,
            config=config,
            inputs={
                "reads1": str(reads1_path),
                "reads2": str(reads2_path),
                "host_reference": str(host_reference_path) if host_reference_path else None,
            },
            allow_real_runs=resolved_allow_real_runs,
        )
        store.write(record)
        background_tasks.add_task(process_job, job_id)
        return record

    return app


app = create_app()


def main() -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise RuntimeError(
            "uvicorn is required to run the web service. Install the project dependencies first."
        ) from exc

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
