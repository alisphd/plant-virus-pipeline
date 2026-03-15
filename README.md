
# Plant Virus Pipeline

Plant Virus Pipeline is a command-line workflow for screening paired-end plant sequencing reads for possible viral content.

The repository now includes:

- a Python CLI entrypoint that orchestrates the workflow end-to-end,
- a lightweight web service for submitting and tracking runs,
- hardened shell helpers for the preprocessing steps,
- tiny demo inputs for smoke testing,
- Markdown and JSON reports that summarize each run,
- Docker and GitHub Actions files for deployment.

## What The Pipeline Does

The intended workflow is:

1. run quality control and adapter trimming,
2. remove reads that map to the host plant genome,
3. assemble the remaining reads into contigs,
4. classify candidate viral material with BLAST and/or Kraken2,
5. write a run summary report.

## Repository Layout

- `plant_virus_pipeline/`: Python package and CLI entrypoint
- `docs/`: deployment notes
- `scripts/`: standalone shell helpers for QC and host removal
- `data/`: tiny demo inputs for smoke tests
- `envs/`: Conda environment definition
- `tests/`: lightweight unit and smoke tests

## Quick Start

### 1. Create The Conda Environment

```bash
conda env create -f envs/plantvirome.yml
conda activate plantvirome
```

### 2. Run A Dry-Run Smoke Test

This works even if the external bioinformatics tools are not installed yet. It generates a pipeline plan and a placeholder summary report.

```bash
python -m plant_virus_pipeline run \
  --reads1 data/demo_R1.fastq \
  --reads2 data/demo_R2.fastq \
  --host-reference data/demo_host_reference.fasta \
  --output results/demo \
  --dry-run
```

### 3. Run The Real Pipeline

For a real run you need the external tools from the Conda environment and at least one classification database.

```bash
python -m plant_virus_pipeline run \
  --reads1 /path/to/sample_R1.fastq.gz \
  --reads2 /path/to/sample_R2.fastq.gz \
  --host-reference /path/to/host_genome.fasta \
  --blast-db /path/to/blast/database_prefix \
  --kraken-db /path/to/kraken_database \
  --output results/sample_01 \
  --threads 8
```

## CLI Commands

### Check Your Environment

```bash
python -m plant_virus_pipeline check \
  --host-reference data/demo_host_reference.fasta
```

### Rebuild A Report From Existing Outputs

```bash
python -m plant_virus_pipeline report --output results/sample_01
```

### Start The Web Service

```bash
python -m plant_virus_pipeline serve --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000`.

## Docker Deployment

Build the container:

```bash
docker build -t plant-virus-pipeline .
```

Run the web service:

```bash
docker run --rm -p 8000:8000 -v $(pwd)/runtime:/data \
  -e PVP_RUNTIME_DIR=/data \
  -e PVP_ALLOW_REAL_RUNS=false \
  plant-virus-pipeline
```

Or use Compose:

```bash
docker compose up --build
```

## Web API

The web layer exposes:

- `GET /healthz`: health check
- `GET /api/environment`: tool availability and runtime settings
- `POST /api/jobs`: submit a pipeline job via file upload
- `GET /api/jobs`: list recent jobs
- `GET /api/jobs/{job_id}`: fetch job status
- `GET /api/jobs/{job_id}/report`: fetch report JSON when available

## CI

GitHub Actions now runs the unit test suite on pushes and pull requests. A separate workflow can publish a container image to GitHub Container Registry on demand or on release.

## Output Structure

Each run creates a directory like:

```text
results/sample_01/
  01_qc/
  02_host_removed/
  03_assembly/
  04_classification/
  05_report/
  pipeline_plan.json
```

The `05_report/` folder contains:

- `summary.json`: machine-readable run summary
- `summary.md`: human-readable run summary

## Notes

- The pipeline is designed for paired-end reads.
- Host removal is optional, but recommended when a host reference is available.
- BLAST and Kraken2 classification are optional independently, but at least one should be supplied for real virus screening.
- Windows users will usually have the smoothest experience through Conda plus a POSIX-compatible shell, WSL, or Docker.
- The bundled web service stores jobs on the local filesystem. For public production deployments, add authentication, object storage, and a separate worker queue.
- Classification databases are not bundled into the repo or image. Mount them at runtime and pass their paths in the web form or CLI.

## Run The Tests

```bash
python -m unittest discover -s tests
```

## Deployment Notes

Deployment details and platform considerations are in `docs/DEPLOYMENT.md`.

