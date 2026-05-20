#***********************************************
#      Filename: ingest.py
#   Description: 将本地文档写入 Chroma RAG 库
#***********************************************

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from doc_generation.logging_config import configure_logging
from doc_generation.utils import load_dotenv_if_present
from doc_generation.rag import get_rag_store, is_rag_enabled

load_dotenv_if_present()
from doc_generation.rag.errors import RagConfigError


def main(argv: list[str] | None = None) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(
        description="Ingest text/markdown files into the Chroma RAG knowledge base.",
    )
    parser.add_argument(
        "paths",
        nargs="+",
        help="Files or directories to ingest (directories are scanned recursively).",
    )
    parser.add_argument(
        "--chunk-size",
        type=int,
        default=1000,
        help="Text splitter chunk size (default: 1000).",
    )
    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=200,
        help="Text splitter chunk overlap (default: 200).",
    )
    parser.add_argument(
        "--glob",
        default="*.{txt,md,rst}",
        help="Glob for files when a directory is given (default: *.{txt,md,rst}).",
    )
    args = parser.parse_args(argv)

    if not is_rag_enabled():
        print("RAG is not enabled in config.yml (missing 'rag' block or enabled: false).", file=sys.stderr)
        return 1

    file_paths: list[Path] = []
    for raw in args.paths:
        path = Path(raw)
        if path.is_file():
            file_paths.append(path)
        elif path.is_dir():
            patterns = [p.strip() for p in args.glob.split(",") if p.strip()]
            for pattern in patterns:
                file_paths.extend(sorted(path.rglob(pattern)))
        else:
            print(f"Path not found: {path}", file=sys.stderr)
            return 1

    if not file_paths:
        print("No files to ingest.", file=sys.stderr)
        return 1

    try:
        store = get_rag_store()
        count = store.ingest_paths(
            [str(p) for p in file_paths],
            chunk_size=args.chunk_size,
            chunk_overlap=args.chunk_overlap,
        )
    except RagConfigError as exc:
        print(f"RAG error: {exc}", file=sys.stderr)
        return 1

    print(f"Ingested {count} chunks from {len(file_paths)} file(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
