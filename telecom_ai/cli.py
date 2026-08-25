from __future__ import annotations

import argparse
import json
from pathlib import Path

from .database import connect
from .ingest import ingest_archives
from .query import ask
from .server import serve


DEFAULT_DATABASE = Path("data/telecom.db")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Local evidence-grounded telecom data query MVP")
    parser.add_argument("--database", default=str(DEFAULT_DATABASE), help="SQLite database path")
    subcommands = parser.add_subparsers(dest="command", required=True)

    ingest_parser = subcommands.add_parser("ingest", help="Ingest Excel archives into SQLite")
    ingest_parser.add_argument("archives", nargs="+", help="ZIP archives containing operator workbooks")

    ask_parser = subcommands.add_parser("ask", help="Ask a governed natural-language question")
    ask_parser.add_argument("question", help="Question about the ingested data")
    ask_parser.add_argument("--json", action="store_true", dest="as_json", help="Print full JSON response")

    subcommands.add_parser("stats", help="Show database counts")
    subcommands.add_parser("quality", help="Show quality issue summary")

    serve_parser = subcommands.add_parser("serve", help="Run the local JSON API")
    serve_parser.add_argument("--host", default="127.0.0.1")
    serve_parser.add_argument("--port", default=8765, type=int)
    return parser


def _print_answer(response: dict) -> None:
    print(response["answer"])
    if response["evidence"]:
        print("\nEvidence:")
        for index, item in enumerate(response["evidence"], 1):
            print(f"  {index}. {item['operator']} {item['period']} - {item['displayed_value']} - {item['source']}")
    governance = response["governance"]
    print(
        f"\nGovernance: {governance['release_class']} / {governance['uncertainty_class']} / "
        f"{governance['release_decision']}; human authority remains final."
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    database = Path(args.database)
    if args.command == "ingest":
        result = ingest_archives(database, args.archives)
        print(json.dumps(result, indent=2))
        return 0
    if args.command == "serve":
        serve(database, args.host, args.port)
        return 0
    if not database.exists():
        raise SystemExit(f"Database not found: {database}. Run the ingest command first.")
    with connect(database) as connection:
        if args.command == "ask":
            response = ask(connection, args.question)
            if args.as_json:
                print(json.dumps(response, indent=2, ensure_ascii=False))
            else:
                _print_answer(response)
        elif args.command == "quality":
            _print_answer(ask(connection, "Show data quality issues"))
        elif args.command == "stats":
            stats = {
                "workbooks": connection.execute("SELECT COUNT(*) FROM source_workbooks").fetchone()[0],
                "metrics": connection.execute("SELECT COUNT(*) FROM metrics").fetchone()[0],
                "observations": connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0],
                "numeric_observations": connection.execute(
                    "SELECT COUNT(*) FROM observations WHERE value_status = 'numeric'"
                ).fetchone()[0],
                "quality_issues": connection.execute("SELECT COUNT(*) FROM quality_issues").fetchone()[0],
                "audited_queries": connection.execute("SELECT COUNT(*) FROM query_audit").fetchone()[0],
            }
            print(json.dumps(stats, indent=2))
    return 0
