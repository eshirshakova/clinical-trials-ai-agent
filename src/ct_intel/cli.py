"""Command line entry points."""

from __future__ import annotations

import argparse
import json

from ct_intel.config import load_settings
from ct_intel.ingest.bronze import ingest
from ct_intel.silver.normalize import normalize


def _add_ingest_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--max-pages", type=int, default=5, help="Pages to pull. Ignored with --full.")
    parser.add_argument("--page-size", type=int, default=100)
    parser.add_argument("--full", action="store_true", help="Page until nextPageToken is absent.")
    parser.add_argument("--force", action="store_true", help="Download even if dataTimestamp is unchanged.")
    parser.add_argument("--query-cond", default=None, help="ClinicalTrials.gov query.cond filter.")
    parser.add_argument("--overall-status", default=None, help="filter.overallStatus value, such as RECRUITING.")


def _ingest_kwargs(args: argparse.Namespace) -> dict:
    if args.page_size < 1 or args.page_size > 1000:
        raise SystemExit("--page-size must be between 1 and 1000.")
    max_pages = None if args.full else args.max_pages
    if max_pages is not None and max_pages < 1:
        raise SystemExit("--max-pages must be at least 1.")
    return {
        "page_size": args.page_size,
        "max_pages": max_pages,
        "query_cond": args.query_cond,
        "overall_status": args.overall_status,
        "force": args.force,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ct_intel", description="Clinical Trial Intelligence pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest_parser = sub.add_parser("ingest", help="Pull raw study pages into Bronze.")
    _add_ingest_args(ingest_parser)

    sub.add_parser("normalize", help="Flatten the latest Bronze snapshot into Silver, delta, and Gold.")

    ask_parser = sub.add_parser("ask", help="Ask a natural-language question against Gold views.")
    ask_parser.add_argument("question")

    run_parser = sub.add_parser("run", help="Ingest, then normalize.")
    _add_ingest_args(run_parser)

    args = parser.parse_args(argv)
    settings = load_settings()

    if args.command == "ingest":
        result = ingest(settings, **_ingest_kwargs(args))
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "normalize":
        result = normalize(settings)
        print(json.dumps(result, indent=2))
        return 0

    if args.command == "ask":
        from ct_intel.agent.agent import ask

        result = ask(settings, args.question)
        if result["sql"]:
            print("SQL:")
            for statement in result["sql"]:
                print(statement)
            print()
        print("Answer:")
        print(result["answer"])
        return 0

    if args.command == "run":
        ingested = ingest(settings, **_ingest_kwargs(args))
        print(json.dumps({"ingest": ingested}, indent=2))
        normalized = normalize(settings)
        print(json.dumps({"normalize": normalized}, indent=2))
        return 0

    parser.error(f"Unknown command {args.command}")
    return 2
