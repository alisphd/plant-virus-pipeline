from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


class PipelineError(RuntimeError):
    """Raised when the pipeline configuration or execution is invalid."""


@dataclass
class PipelineConfig:
    reads1: Path
    reads2: Path
    output: Path
    host_reference: Path | None = None
    blast_db: str | None = None
    kraken_db: Path | None = None
    threads: int = 4
    dry_run: bool = False
    resume: bool = False
    skip_fastqc: bool = False
    skip_host_removal: bool = False
    skip_assembly: bool = False
    skip_blast: bool = False
    skip_kraken: bool = False
    keep_sam: bool = False

    def serializable(self) -> dict[str, object]:
        data = asdict(self)
        for key, value in list(data.items()):
            if isinstance(value, Path):
                data[key] = str(value)
        return data

    @classmethod
    def from_mapping(cls, payload: dict[str, object]) -> "PipelineConfig":
        return cls(
            reads1=Path(str(payload["reads1"])),
            reads2=Path(str(payload["reads2"])),
            output=Path(str(payload["output"])),
            host_reference=Path(str(payload["host_reference"]))
            if payload.get("host_reference")
            else None,
            blast_db=str(payload["blast_db"]) if payload.get("blast_db") else None,
            kraken_db=Path(str(payload["kraken_db"])) if payload.get("kraken_db") else None,
            threads=int(payload.get("threads", 4)),
            dry_run=bool(payload.get("dry_run", False)),
            resume=bool(payload.get("resume", False)),
            skip_fastqc=bool(payload.get("skip_fastqc", False)),
            skip_host_removal=bool(payload.get("skip_host_removal", False)),
            skip_assembly=bool(payload.get("skip_assembly", False)),
            skip_blast=bool(payload.get("skip_blast", False)),
            skip_kraken=bool(payload.get("skip_kraken", False)),
            keep_sam=bool(payload.get("keep_sam", False)),
        )


def load_config_file(path: Path) -> dict[str, object]:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def ensure_exists(path: Path, label: str) -> None:
    if not path.exists():
        raise PipelineError(f"{label} does not exist: {path}")


def _quote_command(command: Iterable[str]) -> str:
    return subprocess.list2cmdline([str(part) for part in command])


def write_plan(config: PipelineConfig, commands: list[list[str]]) -> Path:
    config.output.mkdir(parents=True, exist_ok=True)
    plan_path = config.output / "pipeline_plan.json"
    payload = config.serializable()
    payload["commands"] = commands
    with plan_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)
    return plan_path


def check_environment(config: PipelineConfig) -> dict[str, list[str]]:
    required = ["fastp", "multiqc"]
    if not config.skip_fastqc:
        required.append("fastqc")
    if config.host_reference and not config.skip_host_removal:
        required.extend(["bowtie2-build", "bowtie2", "samtools"])
    if not config.skip_assembly:
        required.append("megahit")
    if config.blast_db and not config.skip_blast:
        required.append("blastn")
    if config.kraken_db and not config.skip_kraken:
        required.append("kraken2")

    found: list[str] = []
    missing: list[str] = []
    for tool in sorted(set(required)):
        if shutil.which(tool):
            found.append(tool)
        else:
            missing.append(tool)
    return {"found": found, "missing": missing}


def run_command(command: list[str], dry_run: bool = False) -> None:
    printable = _quote_command(command)
    print(f"$ {printable}")
    if dry_run:
        return
    subprocess.run(command, check=True)


def build_commands(config: PipelineConfig) -> list[list[str]]:
    reads1 = config.reads1
    reads2 = config.reads2

    qc_dir = config.output / "01_qc"
    trimmed_dir = qc_dir / "trimmed"
    host_dir = config.output / "02_host_removed"
    assembly_dir = config.output / "03_assembly"
    classification_dir = config.output / "04_classification"

    commands: list[list[str]] = []

    trimmed_r1 = trimmed_dir / "trimmed_R1.fastq.gz"
    trimmed_r2 = trimmed_dir / "trimmed_R2.fastq.gz"

    if not config.skip_fastqc:
        commands.append(
            [
                "fastqc",
                "-t",
                str(config.threads),
                str(reads1),
                str(reads2),
                "-o",
                str(qc_dir / "qc"),
            ]
        )

    commands.append(
        [
            "fastp",
            "-w",
            str(config.threads),
            "-i",
            str(reads1),
            "-I",
            str(reads2),
            "-o",
            str(trimmed_r1),
            "-O",
            str(trimmed_r2),
            "-j",
            str(trimmed_dir / "fastp.json"),
            "-h",
            str(trimmed_dir / "fastp.html"),
        ]
    )

    commands.append(
        [
            "multiqc",
            str(qc_dir),
            "-o",
            str(qc_dir),
        ]
    )

    current_r1 = trimmed_r1
    current_r2 = trimmed_r2

    if config.host_reference and not config.skip_host_removal:
        host_index = host_dir / "host_index"
        host_sam = host_dir / "host_align.sam"
        host_bam = host_dir / "host_align.bam"
        unmapped_bam = host_dir / "unmapped.bam"
        current_r1 = host_dir / "unmapped_R1.fastq.gz"
        current_r2 = host_dir / "unmapped_R2.fastq.gz"

        commands.extend(
            [
                ["bowtie2-build", str(config.host_reference), str(host_index)],
                [
                    "bowtie2",
                    "-x",
                    str(host_index),
                    "-1",
                    str(trimmed_r1),
                    "-2",
                    str(trimmed_r2),
                    "-S",
                    str(host_sam),
                    "--very-sensitive",
                    "-p",
                    str(config.threads),
                ],
                [
                    "samtools",
                    "view",
                    "-bS",
                    str(host_sam),
                    "-o",
                    str(host_bam),
                ],
                [
                    "samtools",
                    "view",
                    "-b",
                    "-f",
                    "12",
                    "-F",
                    "256",
                    str(host_bam),
                    "-o",
                    str(unmapped_bam),
                ],
                [
                    "samtools",
                    "fastq",
                    "-1",
                    str(current_r1),
                    "-2",
                    str(current_r2),
                    str(unmapped_bam),
                ],
            ]
        )

    contigs = assembly_dir / "final.contigs.fa"

    if not config.skip_assembly:
        commands.append(
            [
                "megahit",
                "-1",
                str(current_r1),
                "-2",
                str(current_r2),
                "-o",
                str(assembly_dir),
                "-t",
                str(config.threads),
            ]
        )

    if config.blast_db and not config.skip_blast:
        commands.append(
            [
                "blastn",
                "-query",
                str(contigs),
                "-db",
                str(config.blast_db),
                "-out",
                str(classification_dir / "blast_hits.tsv"),
                "-outfmt",
                "6 qseqid sseqid pident length bitscore evalue stitle",
                "-max_target_seqs",
                "5",
                "-num_threads",
                str(config.threads),
            ]
        )

    if config.kraken_db and not config.skip_kraken:
        commands.append(
            [
                "kraken2",
                "--db",
                str(config.kraken_db),
                "--paired",
                str(current_r1),
                str(current_r2),
                "--threads",
                str(config.threads),
                "--use-names",
                "--report",
                str(classification_dir / "kraken_report.tsv"),
                "--output",
                str(classification_dir / "kraken_output.tsv"),
            ]
        )

    return commands


def prepare_directories(config: PipelineConfig) -> None:
    for path in [
        config.output,
        config.output / "01_qc" / "qc",
        config.output / "01_qc" / "trimmed",
        config.output / "02_host_removed",
        config.output / "03_assembly",
        config.output / "04_classification",
        config.output / "05_report",
    ]:
        path.mkdir(parents=True, exist_ok=True)


def validate_config(config: PipelineConfig) -> None:
    ensure_exists(config.reads1, "Reads 1")
    ensure_exists(config.reads2, "Reads 2")

    if config.host_reference:
        ensure_exists(config.host_reference, "Host reference")
    if config.kraken_db:
        ensure_exists(config.kraken_db, "Kraken2 database")

    if config.threads < 1:
        raise PipelineError("threads must be at least 1")


def run_pipeline(config: PipelineConfig) -> Path:
    validate_config(config)
    prepare_directories(config)

    environment = check_environment(config)
    if environment["missing"] and not config.dry_run:
        raise PipelineError(
            "Missing required tools: " + ", ".join(environment["missing"])
        )

    commands = build_commands(config)
    plan_path = write_plan(config, commands)

    for command in commands:
        run_command(command, dry_run=config.dry_run)

    if not config.keep_sam and not config.dry_run:
        host_sam = config.output / "02_host_removed" / "host_align.sam"
        if host_sam.exists():
            host_sam.unlink()

    return plan_path
