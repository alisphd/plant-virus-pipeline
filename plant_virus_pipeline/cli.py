from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import (
    PipelineConfig,
    PipelineError,
    check_environment,
    load_config_file,
    run_pipeline,
)
from .reporting import write_report


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="plant-virus-pipeline",
        description="Run the Plant Virus Pipeline from raw reads to summary report.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the pipeline.")
    _add_common_arguments(run_parser)
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write the pipeline plan without running external tools.",
    )
    run_parser.add_argument(
        "--resume",
        action="store_true",
        help="Reserved for future resume behavior.",
    )
    run_parser.add_argument(
        "--skip-fastqc",
        action="store_true",
        help="Skip FastQC and only run trimming.",
    )
    run_parser.add_argument(
        "--skip-host-removal",
        action="store_true",
        help="Skip host read removal even if a host reference is provided.",
    )
    run_parser.add_argument("--skip-assembly", action="store_true", help="Skip assembly.")
    run_parser.add_argument(
        "--skip-blast",
        action="store_true",
        help="Skip BLAST classification.",
    )
    run_parser.add_argument(
        "--skip-kraken",
        action="store_true",
        help="Skip Kraken2 classification.",
    )
    run_parser.add_argument(
        "--keep-sam",
        action="store_true",
        help="Keep the intermediate host alignment SAM file.",
    )

    check_parser = subparsers.add_parser(
        "check",
        help="Check whether required external tools are available.",
    )
    _add_common_arguments(check_parser, include_inputs=False)
    check_parser.add_argument(
        "--json",
        action="store_true",
        help="Print the environment check as JSON.",
    )
    check_parser.add_argument("--skip-fastqc", action="store_true")
    check_parser.add_argument("--skip-host-removal", action="store_true")
    check_parser.add_argument("--skip-assembly", action="store_true")
    check_parser.add_argument("--skip-blast", action="store_true")
    check_parser.add_argument("--skip-kraken", action="store_true")

    report_parser = subparsers.add_parser(
        "report",
        help="Generate a report from an existing output directory.",
    )
    report_parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Pipeline output directory.",
    )

    serve_parser = subparsers.add_parser("serve", help="Run the web service.")
    serve_parser.add_argument("--host", default="127.0.0.1", help="Host interface to bind.")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port to bind.")
    serve_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for local development.",
    )

    return parser


def _add_common_arguments(
    parser: argparse.ArgumentParser, include_inputs: bool = True
) -> None:
    parser.add_argument("--config", type=Path, help="Optional JSON config file.")
    if include_inputs:
        parser.add_argument("--reads1", type=Path, help="Path to read 1 FASTQ/FASTQ.GZ.")
        parser.add_argument("--reads2", type=Path, help="Path to read 2 FASTQ/FASTQ.GZ.")
    parser.add_argument("--host-reference", type=Path, help="Optional host reference FASTA.")
    parser.add_argument("--blast-db", help="Optional BLAST database prefix.")
    parser.add_argument("--kraken-db", type=Path, help="Optional Kraken2 database directory.")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("results/default_run"),
        help="Output directory.",
    )
    parser.add_argument("--threads", type=int, default=4, help="Number of worker threads.")


def _merge_args_with_config(
    args: argparse.Namespace, require_inputs: bool = True
) -> PipelineConfig:
    payload: dict[str, object] = {}
    if args.config:
        payload.update(load_config_file(args.config))

    cli_values = {
        "reads1": getattr(args, "reads1", None),
        "reads2": getattr(args, "reads2", None),
        "output": getattr(args, "output", None),
        "host_reference": getattr(args, "host_reference", None),
        "blast_db": getattr(args, "blast_db", None),
        "kraken_db": getattr(args, "kraken_db", None),
        "threads": getattr(args, "threads", None),
        "dry_run": getattr(args, "dry_run", False),
        "resume": getattr(args, "resume", False),
        "skip_fastqc": getattr(args, "skip_fastqc", False),
        "skip_host_removal": getattr(args, "skip_host_removal", False),
        "skip_assembly": getattr(args, "skip_assembly", False),
        "skip_blast": getattr(args, "skip_blast", False),
        "skip_kraken": getattr(args, "skip_kraken", False),
        "keep_sam": getattr(args, "keep_sam", False),
    }

    for key, value in cli_values.items():
        if value is not None:
            payload[key] = value

    if require_inputs and ("reads1" not in payload or "reads2" not in payload):
        raise PipelineError("Both --reads1 and --reads2 are required.")

    reads1 = Path(payload["reads1"]) if payload.get("reads1") else Path("data/demo_R1.fastq")
    reads2 = Path(payload["reads2"]) if payload.get("reads2") else Path("data/demo_R2.fastq")

    return PipelineConfig(
        reads1=reads1,
        reads2=reads2,
        output=Path(payload.get("output", Path("results/default_run"))),
        host_reference=Path(payload["host_reference"])
        if payload.get("host_reference")
        else None,
        blast_db=str(payload["blast_db"]) if payload.get("blast_db") else None,
        kraken_db=Path(payload["kraken_db"]) if payload.get("kraken_db") else None,
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


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "serve":
            try:
                import uvicorn
            except ImportError as exc:
                raise PipelineError(
                    "uvicorn is required for the web service. Install the project dependencies first."
                ) from exc

            uvicorn.run(
                "plant_virus_pipeline.web:app",
                host=args.host,
                port=args.port,
                reload=args.reload,
            )
            return 0

        if args.command == "report":
            summary_json, summary_md = write_report(args.output)
            print(f"Wrote {summary_json}")
            print(f"Wrote {summary_md}")
            return 0

        if args.command == "check":
            config = _merge_args_with_config(args, require_inputs=False)
            environment = check_environment(config)
            if args.json:
                print(json.dumps(environment, indent=2))
            else:
                print("Found tools:")
                for tool in environment["found"]:
                    print(f"  - {tool}")
                print("Missing tools:")
                for tool in environment["missing"]:
                    print(f"  - {tool}")
            return 0 if not environment["missing"] else 1

        config = _merge_args_with_config(args)
        run_pipeline(config)
        summary_json, summary_md = write_report(config.output)
        print(f"Wrote {summary_json}")
        print(f"Wrote {summary_md}")
        return 0
    except PipelineError as exc:
        print(f"Error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
