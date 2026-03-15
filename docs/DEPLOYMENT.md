# Deployment Guide

This repository can now be deployed as a small web service that accepts paired-end reads, creates pipeline jobs, and stores job artifacts on disk.

## What Is Included

- `Dockerfile`: builds a lightweight web-service container for Railway and similar hosts
- `compose.yml`: local container orchestration for the web service
- `.github/workflows/ci.yml`: Python test workflow
- `.github/workflows/publish-container.yml`: optional container publish workflow for GHCR

## Local Deployment With Docker

Build:

```bash
docker build -t plant-virus-pipeline .
```

Run:

```bash
docker run --rm -p 8000:8000 \
  -v $(pwd)/runtime:/data \
  -e PVP_RUNTIME_DIR=/data \
  -e PVP_ALLOW_REAL_RUNS=false \
  plant-virus-pipeline
```

The service will be available at `http://localhost:8000`.

## Real Pipeline Runs

To allow non-dry-run execution:

1. set `PVP_ALLOW_REAL_RUNS=true`
2. ensure the image or host contains the required bioinformatics tools
3. mount or provision BLAST and Kraken2 databases if you plan to use them
4. mount persistent storage for `/data`

The default hosted Docker image in this repo does not bundle the full bioinformatics stack. It is optimized for getting the web service online successfully on Railway. For real analysis runs, use a heavier compute image or a separate worker environment.

## Production Considerations

This repo is now deployment-ready for an internal or low-volume service, but public production hosting should add:

- authentication and authorization
- request size limits
- object storage for uploaded FASTQ files
- a job queue and separate worker processes
- monitoring and alerts
- cleanup policies for old runs

## Suggested Hosting Options

- Railway for the quickest first hosted version
- Docker on a Linux VM for maximum control
- Kubernetes for larger internal deployments

## Environment Variables

- `PVP_RUNTIME_DIR`: where job data and reports are stored, defaults to `runtime`
- `PVP_ALLOW_REAL_RUNS`: set to `true` to permit real pipeline execution from the web service
- `PORT`: port used by the container entrypoint, defaults to `8000`
- `RAILWAY_VOLUME_MOUNT_PATH`: used automatically by the app when present on Railway

## Railway Quick Start

1. Create a new project on Railway and connect this GitHub repository.
2. Railway will detect the repo Dockerfile automatically.
3. In Railway, add a volume and mount it at `/data`.
4. Add environment variables:
   - `PVP_ALLOW_REAL_RUNS=false`
   - `PVP_RUNTIME_DIR=/data`
5. Deploy the service.
6. Verify:
   - `/healthz`
   - `/api/environment`

For the first public deploy, keep `PVP_ALLOW_REAL_RUNS=false`. Turn on real runs only after your databases and compute/storage limits are ready.
