"""Command line: ``lexmind serve`` runs the web app, ``lexmind search "question"`` searches the library."""
from __future__ import annotations

import argparse

from .library import default_library


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="lexmind")
    sub = parser.add_subparsers(dest="cmd", required=True)
    serve = sub.add_parser("serve", help="run the web app")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    search = sub.add_parser("search", help="search the Constitution")
    search.add_argument("query")
    args = parser.parse_args(argv)
    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("lexmind.api:create_app", factory=True, host=args.host, port=args.port)
    else:
        for section, score in default_library().search(args.query):
            print(f"Article {section.article} ({score}): {section.title}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
