from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def _safe_read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _count_fasta(path: Path) -> dict[str, int] | None:
    if not path.exists():
        return None

    contig_count = 0
    total_bases = 0

    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            if line.startswith(">"):
                contig_count += 1
                continue
            total_bases += len(line)

    return {"contig_count": contig_count, "total_bases": total_bases}


def _top_blast_hits(path: Path, limit: int = 5) -> list[dict[str, str | float | int]]:
    if not path.exists():
        return []

    hits: list[dict[str, str | float | int]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 7:
                continue
            hits.append(
                {
                    "query": parts[0],
                    "subject": parts[1],
                    "percent_identity": float(parts[2]),
                    "alignment_length": int(parts[3]),
                    "bitscore": float(parts[4]),
                    "evalue": parts[5],
                    "title": parts[6],
                }
            )
            if len(hits) >= limit:
                break
    return hits


def _top_kraken_hits(path: Path, limit: int = 5) -> list[dict[str, str]]:
    if not path.exists():
        return []

    hits: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 6:
                continue

            percent = parts[0].strip()
            name = parts[5].strip()
            if name.lower() == "unclassified":
                continue

            hits.append(
                {
                    "percent": percent,
                    "reads_clade": parts[1].strip(),
                    "reads_direct": parts[2].strip(),
                    "rank": parts[3].strip(),
                    "taxonomy_id": parts[4].strip(),
                    "name": name,
                }
            )
            if len(hits) >= limit:
                break
    return hits


def collect_summary(output_dir: Path) -> dict[str, Any]:
    qc_dir = output_dir / "01_qc"
    host_dir = output_dir / "02_host_removed"
    assembly_dir = output_dir / "03_assembly"
    classification_dir = output_dir / "04_classification"

    fastp_json = qc_dir / "trimmed" / "fastp.json"
    contigs_fasta = assembly_dir / "final.contigs.fa"
    blast_hits = classification_dir / "blast_hits.tsv"
    kraken_report = classification_dir / "kraken_report.tsv"
    plan_path = output_dir / "pipeline_plan.json"

    fastp = _safe_read_json(fastp_json)
    assembly = _count_fasta(contigs_fasta)
    plan = _safe_read_json(plan_path)

    summary: dict[str, Any] = {
        "output_dir": str(output_dir.resolve()),
        "plan": plan or {},
        "artifacts": {
            "fastp_json": str(fastp_json) if fastp_json.exists() else None,
            "unmapped_reads_r1": str(host_dir / "unmapped_R1.fastq.gz")
            if (host_dir / "unmapped_R1.fastq.gz").exists()
            else None,
            "unmapped_reads_r2": str(host_dir / "unmapped_R2.fastq.gz")
            if (host_dir / "unmapped_R2.fastq.gz").exists()
            else None,
            "contigs_fasta": str(contigs_fasta) if contigs_fasta.exists() else None,
            "blast_hits": str(blast_hits) if blast_hits.exists() else None,
            "kraken_report": str(kraken_report) if kraken_report.exists() else None,
        },
        "qc": {},
        "assembly": assembly or {},
        "blast_top_hits": _top_blast_hits(blast_hits),
        "kraken_top_hits": _top_kraken_hits(kraken_report),
    }

    if fastp:
        summary["qc"] = {
            "before_filtering": fastp.get("summary", {}).get("before_filtering", {}),
            "after_filtering": fastp.get("summary", {}).get("after_filtering", {}),
        }

    return summary


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Plant Virus Pipeline Report",
        "",
        f"Output directory: `{summary.get('output_dir', 'unknown')}`",
        "",
    ]

    plan = summary.get("plan", {})
    if plan:
        host_removal_enabled = bool(plan.get("host_reference")) and not bool(
            plan.get("skip_host_removal", False)
        )
        blast_enabled = bool(plan.get("blast_db")) and not bool(
            plan.get("skip_blast", False)
        )
        kraken_enabled = bool(plan.get("kraken_db")) and not bool(
            plan.get("skip_kraken", False)
        )
        lines.extend(
            [
                "## Run Configuration",
                "",
                f"- Dry run: `{plan.get('dry_run', False)}`",
                f"- Threads: `{plan.get('threads', 'n/a')}`",
                f"- Host removal enabled: `{host_removal_enabled}`",
                f"- BLAST enabled: `{blast_enabled}`",
                f"- Kraken2 enabled: `{kraken_enabled}`",
                "",
            ]
        )

    qc = summary.get("qc", {})
    if qc:
        before = qc.get("before_filtering", {})
        after = qc.get("after_filtering", {})
        lines.extend(
            [
                "## QC Summary",
                "",
                f"- Reads before filtering: `{before.get('total_reads', 'n/a')}`",
                f"- Bases before filtering: `{before.get('total_bases', 'n/a')}`",
                f"- Reads after filtering: `{after.get('total_reads', 'n/a')}`",
                f"- Bases after filtering: `{after.get('total_bases', 'n/a')}`",
                "",
            ]
        )

    assembly = summary.get("assembly", {})
    if assembly:
        lines.extend(
            [
                "## Assembly Summary",
                "",
                f"- Contigs: `{assembly.get('contig_count', 'n/a')}`",
                f"- Total assembled bases: `{assembly.get('total_bases', 'n/a')}`",
                "",
            ]
        )

    blast_hits = summary.get("blast_top_hits", [])
    lines.extend(["## BLAST Top Hits", ""])
    if blast_hits:
        for hit in blast_hits:
            lines.append(
                f"- `{hit['query']}` -> {hit['title']} (identity `{hit['percent_identity']}`%, bitscore `{hit['bitscore']}`)"
            )
    else:
        lines.append("- No BLAST hits were found or BLAST was not run.")
    lines.append("")

    kraken_hits = summary.get("kraken_top_hits", [])
    lines.extend(["## Kraken2 Top Hits", ""])
    if kraken_hits:
        for hit in kraken_hits:
            lines.append(
                f"- {hit['name']} ({hit['percent']}% of reads in clade, taxid `{hit['taxonomy_id']}`)"
            )
    else:
        lines.append("- No Kraken2 hits were found or Kraken2 was not run.")
    lines.append("")

    artifacts = summary.get("artifacts", {})
    lines.extend(["## Key Artifacts", ""])
    for key, value in artifacts.items():
        lines.append(f"- {key}: `{value or 'not generated'}`")
    lines.append("")

    return "\n".join(lines)


def write_report(output_dir: Path) -> tuple[Path, Path]:
    report_dir = output_dir / "05_report"
    report_dir.mkdir(parents=True, exist_ok=True)

    summary = collect_summary(output_dir)
    summary_json = report_dir / "summary.json"
    summary_md = report_dir / "summary.md"

    with summary_json.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2)

    with summary_md.open("w", encoding="utf-8") as handle:
        handle.write(render_markdown(summary))
        handle.write("\n")

    return summary_json, summary_md
