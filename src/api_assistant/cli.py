"""Small CLI for inspecting each part of the demo."""

import argparse
import json
import sys

from api_assistant.assistant import IntegrationAssistant, render_markdown
from api_assistant.config import Settings
from api_assistant.knowledge import load_sources
from api_assistant.store import ingest


def main() -> int:
    parser = argparse.ArgumentParser(description="Fictional API integration assistant")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("validate", help="Parse and check sources without calling a model")
    commands.add_parser("ingest", help="Parse sources and build the real vector index")
    ask = commands.add_parser("ask", help="Retrieve and explain a workflow")
    ask.add_argument("question")
    ask.add_argument("--json", action="store_true", help="Print the complete answer and trace")
    ask.add_argument("--trace", action="store_true", help="Print retrieval details after the guide")
    args = parser.parse_args()
    settings = Settings.from_env()
    try:
        if args.command == "validate":
            records = load_sources(settings.source_dir)
            print(json.dumps({name: len(value) for name, value in records.items()}, indent=2))
        elif args.command == "ingest":
            print(json.dumps(ingest(settings), indent=2))
        else:
            answer = IntegrationAssistant(settings).invoke(args.question)
            print(answer.model_dump_json(indent=2) if args.json else render_markdown(answer))
            if args.trace and not args.json:
                print("\nRetrieval and lookup trace:\n" + json.dumps(answer.trace, indent=2))
            return 1 if answer.status in {"data_error", "model_error"} else 0
    except Exception as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
