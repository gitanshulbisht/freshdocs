"""FreshDocs CLI: refresh, heal, status, create-collector helpers."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from .heal import heal_and_approve
from .pipeline import Pipeline, collect_source, load_registry
from .rag import Rag, RagError
from .schemas import HealthCheckFailure

load_dotenv()

REGISTRY_PATH = Path("collectors/collectors.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("freshdocs.cli")


def cmd_refresh(args: argparse.Namespace) -> int:
    registry = load_registry(REGISTRY_PATH)
    try:
        rag = Rag(data_dir=Path(args.data_dir))
    except RagError as exc:
        rag = None
        log.warning("RAG disabled: %s", exc)

    pipeline = Pipeline(data_dir=Path(args.data_dir), rag=rag)

    sources = [s for s in registry.sources if s.sitemap_url.startswith("http")]
    if args.source:
        sources = [s for s in sources if s.key == args.source]
        if not sources:
            log.error("unknown source %s", args.source)
            return 2

    failed = False
    for source in sources:
        log.info("=== %s (%s) ===", source.key, source.sitemap_url)
        try:
            rows = collect_source(pipeline.client, source)
        except Exception as exc:  # noqa: BLE001 — report and continue with next source
            log.error("%s: collection failed: %s", source.key, exc)
            failed = True
            continue
        outcome = pipeline.refresh_source(source, rows, embed=rag is not None, dry_run=args.dry_run)
        if not outcome.ok:
            failed = True
            for failure in outcome.failures:
                print(f"\nHEALTH FAILURE [{source.key}] -> {failure.symptom}\n", file=sys.stderr)
                if args.heal and failure.collector_id and not args.dry_run:
                    log.info("auto-healing %s ...", source.key)
                    try:
                        log_text = heal_and_approve(failure.collector_id, failure.symptom)
                        pipeline.index.record_heal(source.key, failure.collector_id,
                                                   failure.symptom, result="ok")
                        log.info("%s", log_text)
                    except Exception as exc:  # noqa: BLE001
                        log.error("heal failed: %s", exc)
                        pipeline.index.record_heal(source.key, failure.collector_id,
                                                   failure.symptom, result=f"failed: {exc}")
        print(f"{source.key}: rows={outcome.rows} ok={outcome.ok} {outcome.notes}")
    return 1 if failed else 0


def cmd_heal(args: argparse.Namespace) -> int:
    log_text = heal_and_approve(args.collector_id, args.symptom, auto_approve=not args.manual)
    print(log_text)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    try:
        rag = Rag(data_dir=Path(args.data_dir))
    except RagError:
        rag = None
    pipeline = Pipeline(data_dir=Path(args.data_dir), rag=rag)
    print(json.dumps(pipeline.status(), indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="freshdocs", description="FreshDocs pipeline CLI")
    parser.add_argument("--data-dir", default="data")
    sub = parser.add_subparsers(dest="command", required=True)

    refresh = sub.add_parser("refresh", help="scrape, validate, diff, embed")
    refresh.add_argument("--source", help="only refresh this source key")
    refresh.add_argument("--dry-run", action="store_true", help="scrape + diff, write nothing")
    refresh.add_argument("--heal", action="store_true", help="on health failure, run bdata scraper heal + approve")
    refresh.set_defaults(func=cmd_refresh)

    heal = sub.add_parser("heal", help="heal a collector and approve the fix")
    heal.add_argument("collector_id")
    heal.add_argument("symptom")
    heal.add_argument("--manual", action="store_true", help="propose fix but do not auto-approve")
    heal.set_defaults(func=cmd_heal)

    status = sub.add_parser("status", help="print index + run + heal status as JSON")
    status.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
