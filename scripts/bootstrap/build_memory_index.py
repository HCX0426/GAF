"""build_memory_index.py — C1 治本机制: .ai-memory/ 语义索引构建

Build a ChromaDB collection from .ai-memory/ 4 directories for semantic
search fallback when fuzzy keyword matching returns 0 results.

Reuses FastembedMultilingualEF from backend/gaf_ai/rag.py (no new deps).
Uses mtime-based incremental update (only re-index changed files).

Usage:
    python scripts/bootstrap/build_memory_index.py           # build/update
    python scripts/bootstrap/build_memory_index.py --rebuild  # full rebuild
    python scripts/bootstrap/build_memory_index.py --stats    # show stats

治本机制 (C1, 2026-07-16):
- 旧机制: B3 fuzzy 4 源覆盖精确关键词, 但自然语言查询有盲区
- 新机制: fuzzy 优先 + embedding 补位, 复用现有 RAG 基础设施
- 不引入新依赖: chromadb + fastembed 已在 pyproject.toml
"""
from __future__ import annotations

# Bootstrap: make scripts/ importable + add backend/ for rag.py import.
import sys as _sys
from pathlib import Path as _Path
_SCRIPTS_DIR = _Path(__file__).resolve().parents[1]
_BACKEND_DIR = _Path(__file__).resolve().parents[2] / "backend"
for _p in (str(_SCRIPTS_DIR), str(_BACKEND_DIR)):
    if _p not in _sys.path:
        _sys.path.insert(0, _p)

import argparse
import datetime as _dt
import hashlib
import json
import logging
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

REPO_ROOT = _Path(__file__).resolve().parents[2]
AI_MEMORY = REPO_ROOT / ".ai-memory"
PERSIST_DIR = REPO_ROOT / ".cache" / "chroma_memory"
STATE_FILE = REPO_ROOT / ".cache" / "chroma_memory_state.json"
COLLECTION_NAME = "gaf_memory"

# 4 source directories (same as B3 query_all_sources)
SCAN_DIRS: List[Tuple[str, Path]] = [
    ("lessons", AI_MEMORY / "lessons"),
    ("failure-modes", AI_MEMORY / "meta" / "failure-modes.md"),
    ("yn-matrices", AI_MEMORY / "meta" / "yn-matrices"),
    ("summaries", AI_MEMORY / "summaries"),
]


def _load_embedding_fn():
    """Load FastembedMultilingualEF from backend/gaf_ai/rag.py."""
    try:
        from gaf_ai.rag import FastembedMultilingualEF  # type: ignore
        return FastembedMultilingualEF()
    except Exception as e:
        logger.warning("FastembedMultilingualEF init failed: %s", e)
        return None


def _init_chroma():
    """Init ChromaDB PersistentClient + collection. Returns (client, collection) or (None, None)."""
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings
    except ImportError:
        logger.warning("chromadb not installed, semantic index unavailable")
        return None, None
    PERSIST_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(
        path=str(PERSIST_DIR),
        settings=ChromaSettings(anonymized_telemetry=False),
    )
    ef = _load_embedding_fn()
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
        embedding_function=ef,
    )
    return client, collection


def _load_state() -> Dict[str, Dict[str, Any]]:
    """Load mtime state: {file_path: {mtime, hash, doc_ids}}."""
    if not STATE_FILE.exists():
        return {}
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(state: Dict[str, Dict[str, Any]]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def _file_hash(path: Path) -> str:
    """MD5 hash of file content (for change detection beyond mtime)."""
    try:
        return hashlib.md5(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def _collect_files() -> List[Tuple[str, Path]]:
    """Collect all .md files from 4 source directories.

    Returns list of (source_label, file_path).
    """
    files: List[Tuple[str, Path]] = []
    for label, path in SCAN_DIRS:
        if path.is_file() and path.suffix == ".md":
            files.append((label, path))
        elif path.is_dir():
            for f in sorted(path.rglob("*.md")):
                files.append((label, f))
    return files


def _split_markdown_sections(text: str) -> List[Tuple[str, str]]:
    """Split markdown by '## ' headers. Returns list of (section_title, content).

    Falls back to [('full', text)] if no ## headers.
    """
    lines = text.split("\n")
    sections: List[Tuple[str, str]] = []
    current_title: Optional[str] = None
    current_lines: List[str] = []

    for line in lines:
        if line.startswith("## "):
            if current_title is not None:
                sections.append((current_title, "\n".join(current_lines)))
            current_title = line[3:].strip()
            current_lines = [line]
        elif current_title is not None:
            current_lines.append(line)

    if current_title is not None:
        sections.append((current_title, "\n".join(current_lines)))

    if not sections:
        return [("full", text)]
    return sections


def _doc_id(file_path: Path, section_slug: str) -> str:
    """Build stable doc_id from file path + section slug."""
    rel = str(file_path.relative_to(REPO_ROOT)).replace("\\", "/")
    return f"{rel}::{section_slug}"


def _build_or_update(rebuild: bool = False) -> Dict[str, int]:
    """Build or incrementally update the ChromaDB collection.

    Returns stats dict: {total_files, indexed_files, skipped_files, total_chunks, errors}.
    """
    client, collection = _init_chroma()
    if collection is None:
        return {"total_files": 0, "indexed_files": 0, "skipped_files": 0, "total_chunks": 0, "errors": 1}

    state = {} if rebuild else _load_state()
    new_state: Dict[str, Dict[str, Any]] = {}
    files = _collect_files()

    stats = {"total_files": len(files), "indexed_files": 0, "skipped_files": 0, "total_chunks": 0, "errors": 0}

    for label, file_path in files:
        try:
            rel = str(file_path.relative_to(REPO_ROOT))
            mtime = file_path.stat().st_mtime
            content_hash = _file_hash(file_path)

            # Check if unchanged (skip)
            prev = state.get(rel)
            if prev and prev.get("hash") == content_hash:
                new_state[rel] = prev
                stats["skipped_files"] += 1
                continue

            # Delete old doc_ids for this file
            if prev and prev.get("doc_ids"):
                try:
                    collection.delete(ids=prev["doc_ids"])
                except Exception as e:
                    logger.warning("Failed to delete old docs for %s: %s", rel, e)

            # Read + split into sections
            text = file_path.read_text(encoding="utf-8")
            sections = _split_markdown_sections(text)

            doc_ids: List[str] = []
            for title, section_content in sections:
                slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "untitled"
                doc_id = _doc_id(file_path, slug)
                # Skip near-empty sections (pollute cosine search)
                if len(section_content.strip()) < 20:
                    continue
                try:
                    collection.add(
                        documents=[section_content],
                        ids=[doc_id],
                        metadatas=[{
                            "filepath": rel,
                            "filename": file_path.name,
                            "source": label,
                            "section": title,
                        }],
                    )
                    doc_ids.append(doc_id)
                    stats["total_chunks"] += 1
                except Exception as e:
                    logger.warning("Failed to index section %s: %s", doc_id, e)
                    stats["errors"] += 1

            new_state[rel] = {
                "mtime": mtime,
                "hash": content_hash,
                "doc_ids": doc_ids,
                "indexed_at": _dt.datetime.now().isoformat(timespec="seconds"),
            }
            stats["indexed_files"] += 1

        except Exception as e:
            logger.warning("Failed to process %s: %s", file_path, e)
            stats["errors"] += 1

    _save_state(new_state)
    return stats


def _show_stats() -> int:
    """Print collection stats."""
    client, collection = _init_chroma()
    if collection is None:
        print("❌ chromadb 不可用")
        return 1
    try:
        count = collection.count()
    except Exception as e:
        print(f"❌ 获取 count 失败: {e}")
        return 1
    state = _load_state()
    print(f"# C1 语义索引统计")
    print(f"  Collection: {COLLECTION_NAME}")
    print(f"  Persist dir: {PERSIST_DIR.relative_to(REPO_ROOT)}")
    print(f"  Chunks: {count}")
    print(f"  Files in state: {len(state)}")
    print(f"  State file: {STATE_FILE.relative_to(REPO_ROOT)}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="C1 治本机制: .ai-memory/ 语义索引构建")
    parser.add_argument("--rebuild", action="store_true", help="Full rebuild (ignore mtime state)")
    parser.add_argument("--stats", action="store_true", help="Show collection stats only")
    args = parser.parse_args(argv)

    if args.stats:
        return _show_stats()

    print(f"🚀 C1 语义索引构建 ({'rebuild' if args.rebuild else 'incremental'})")
    stats = _build_or_update(rebuild=args.rebuild)
    print(f"✅ 索引完成:")
    print(f"  总文件: {stats['total_files']}")
    print(f"  新索引: {stats['indexed_files']}")
    print(f"  跳过 (未变): {stats['skipped_files']}")
    print(f"  总 chunks: {stats['total_chunks']}")
    if stats["errors"]:
        print(f"  ⚠️ 错误: {stats['errors']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
