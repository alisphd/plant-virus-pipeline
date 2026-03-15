#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: bash scripts/remove_host.sh <host_genome.fasta> <trimmed_R1.fastq.gz> <trimmed_R2.fastq.gz> <output_dir> [threads]" >&2
}

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

if [[ $# -lt 4 || $# -gt 5 ]]; then
  usage
  exit 1
fi

HOST_REF=$1
TRIM_R1=$2
TRIM_R2=$3
OUTDIR=$4
THREADS=${5:-4}

for path in "$HOST_REF" "$TRIM_R1" "$TRIM_R2"; do
  if [[ ! -f "$path" ]]; then
    echo "Input file not found: $path" >&2
    exit 1
  fi
done

require_cmd bowtie2-build
require_cmd bowtie2
require_cmd samtools

mkdir -p "$OUTDIR"

echo "Step 1: Building Bowtie2 index for host genome..."
bowtie2-build "$HOST_REF" "$OUTDIR/host_index"

echo "Step 2: Mapping trimmed reads to host genome..."
bowtie2 -x "$OUTDIR/host_index" -1 "$TRIM_R1" -2 "$TRIM_R2" \
  -S "$OUTDIR/host_align.sam" --very-sensitive -p "$THREADS"

echo "Step 3: Converting SAM to BAM..."
samtools view -bS "$OUTDIR/host_align.sam" -o "$OUTDIR/host_align.bam"

echo "Step 4: Extracting unmapped reads..."
samtools view -b -f 12 -F 256 "$OUTDIR/host_align.bam" -o "$OUTDIR/unmapped.bam"
samtools fastq \
  -1 "$OUTDIR/unmapped_R1.fastq.gz" \
  -2 "$OUTDIR/unmapped_R2.fastq.gz" \
  "$OUTDIR/unmapped.bam"

echo "Host genome removal complete!"
echo "Unmapped reads saved to:"
echo " - $OUTDIR/unmapped_R1.fastq.gz"
echo " - $OUTDIR/unmapped_R2.fastq.gz"
