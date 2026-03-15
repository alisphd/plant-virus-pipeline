#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: bash scripts/qc_and_trim.sh <reads_R1.fastq.gz> <reads_R2.fastq.gz> <output_dir> [threads]" >&2
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

if [[ $# -lt 3 || $# -gt 4 ]]; then
  usage
  exit 1
fi

R1=$1
R2=$2
OUTDIR=$3
THREADS=${4:-4}

if [[ ! -f "$R1" ]]; then
  echo "Input file not found: $R1" >&2
  exit 1
fi

if [[ ! -f "$R2" ]]; then
  echo "Input file not found: $R2" >&2
  exit 1
fi

require_cmd fastqc
require_cmd fastp
require_cmd multiqc

mkdir -p "$OUTDIR/qc" "$OUTDIR/trimmed"

echo "Running FastQC on raw reads..."
fastqc -t "$THREADS" "$R1" "$R2" -o "$OUTDIR/qc"

echo "Trimming with fastp..."
fastp \
  -w "$THREADS" \
  -i "$R1" -I "$R2" \
  -o "$OUTDIR/trimmed/trimmed_R1.fastq.gz" \
  -O "$OUTDIR/trimmed/trimmed_R2.fastq.gz" \
  -j "$OUTDIR/trimmed/fastp.json" \
  -h "$OUTDIR/trimmed/fastp.html"

echo "Running MultiQC..."
multiqc "$OUTDIR" -o "$OUTDIR"

echo "QC and trimming complete!"
