# Deployment Guide

This repository can now be deployed as a small web service that accepts paired-end reads, creates pipeline jobs, and stores job artifacts on disk.

## What Is Included

- `Dockerfile`: builds a container with the Conda toolchain and web service
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

## Production Considerations

This repo is now deployment-ready for an internal or low-volume service, but public production hosting should add:

- authentication and authorization
- request size limits
- object storage for uploaded FASTQ files
- a job queue and separate worker processes
- monitoring and alerts
- cleanup policies for old runs

## Suggested Hosting Options

- Docker on a Linux VM
- Render or Railway using the Dockerfile
- Kubernetes for larger internal deployments

## Environment Variables

- `PVP_RUNTIME_DIR`: where job data and reports are stored, defaults to `runtime`
- `PVP_ALLOW_REAL_RUNS`: set to `true` to permit real pipeline execution from the web service
- `PORT`: port used by the container entrypoint, defaults to `8000`
