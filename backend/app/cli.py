"""Command line: ``uv run cnc ingest data/``, ``uv run cnc serve``, ``uv run cnc eval``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.config import get_settings


def _cmd_ingest(args: argparse.Namespace) -> int:
    from app.db.session import make_engine, make_session_factory
    from app.logging_setup import configure_logging
    from app.services.ingest_service import ingest_paths

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    path = Path(args.path or settings.data_dir)
    if not path.exists():
        print(f"error: {path} does not exist", file=sys.stderr)
        return 2
    engine = make_engine(settings.database_url)
    try:
        from app.config import geometry_worker
        from app.services.file_store import FileStore

        outcomes = ingest_paths(
            make_session_factory(engine),
            path,
            FileStore(settings.store_dir),
            settings.pdf_max_pages,
            geometry_worker(settings),
        )
    finally:
        engine.dispose()
    if not outcomes:
        print(f"No .xlsx/.xls/.csv/.pdf/.igs files found under {path}")
        return 1
    for o in outcomes:
        print(f"{o.status:<10} {o.file_name:<32} parts={','.join(o.parts) or '-'}")
        for w in o.warnings:
            print(f"           ! {w}")
    return 1 if any(o.status == "failed" for o in outcomes) else 0


def _cmd_rebuild(_: argparse.Namespace) -> int:
    from app.db.session import make_engine, make_session_factory, session_scope
    from app.repositories.parts import rebuild_all

    settings = get_settings()
    engine = make_engine(settings.database_url)
    try:
        with session_scope(make_session_factory(engine)) as session:
            count = rebuild_all(session)
    finally:
        engine.dispose()
    print(f"Rebuilt {count} part records from stored fragments")
    return 0


def _cmd_reset_drawing(args: argparse.Namespace) -> int:
    """Re-extract a drawing from its file, dropping any vision reading (re-asks for consent)."""
    from app.db.session import make_engine, make_session_factory, session_scope
    from app.ingestion.pdf import ingest_drawing_path
    from app.repositories.parts import replace_drawing

    settings = get_settings()
    path = Path(args.path)
    if not path.is_file():
        print(f"error: {path} is not a file", file=sys.stderr)
        return 2
    result = ingest_drawing_path(path, settings.pdf_max_pages)
    engine = make_engine(settings.database_url)
    try:
        with session_scope(make_session_factory(engine)) as session:
            part = replace_drawing(session, result.file_name, result.slice)
    finally:
        engine.dispose()
    if part is None:
        print(f"error: {result.file_name} is not an ingested drawing; run `cnc ingest` first")
        return 1
    print(f"reset      {result.file_name:<32} part={part} extraction={result.slice.extraction}")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


def _cmd_eval(args: argparse.Namespace) -> int:
    from app.evaluation import rescore, run_eval

    out = Path(args.out) if args.out else None
    if args.rescore:
        return rescore(Path(args.rescore), out)
    delay = args.delay if args.delay is not None else (8.0 if args.provider == "groq" else 0.0)
    return run_eval(args.provider, out, delay)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cnc", description="SPEC'26 CNC part analyzer")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser(
        "ingest", help="Ingest a spreadsheet or PDF drawing, or a directory of them"
    )
    p_ingest.add_argument("path", nargs="?", help="File or directory (default: DATA_DIR)")
    p_ingest.set_defaults(func=_cmd_ingest)

    p_rebuild = sub.add_parser(
        "rebuild", help="Regroup stored fragments into part records (after an upgrade)"
    )
    p_rebuild.set_defaults(func=_cmd_rebuild)

    p_reset = sub.add_parser(
        "reset-drawing",
        help="Re-read a drawing from its PDF, discarding any vision reading of a scan",
    )
    p_reset.add_argument("path", help="The PDF file that was ingested")
    p_reset.set_defaults(func=_cmd_reset_drawing)

    p_serve = sub.add_parser("serve", help="Run the API server")
    p_serve.add_argument("--host", default="127.0.0.1")
    p_serve.add_argument("--port", type=int, default=8000)
    p_serve.add_argument("--reload", action="store_true")
    p_serve.set_defaults(func=_cmd_serve)

    p_eval = sub.add_parser("eval", help="Run the golden-set evaluation through the API")
    p_eval.add_argument(
        "--provider", choices=["fake", "anthropic", "claude_code", "groq"], default="fake"
    )
    p_eval.add_argument("--out", help="Markdown report path, e.g. ../docs/eval-results.md")
    p_eval.add_argument(
        "--delay", type=float, help="Seconds between questions (default 8 for groq free tier)"
    )
    p_eval.add_argument(
        "--rescore", metavar="RUN.json", help="Re-score a saved run offline (no LLM calls)"
    )
    p_eval.set_defaults(func=_cmd_eval)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
