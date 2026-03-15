"""
migrate.py — Migrate OpenClaw workspace markdown files into Qdrant via mem0ai.

Usage:
    python migrate.py                  # migrate all files
    python migrate.py --dry-run        # preview what would be migrated
    python migrate.py --file MEMORY.md # migrate a single file
    python migrate.py --file memory/   # migrate all daily logs

Requires:
    pip install -r requirements.txt
    Qdrant running on localhost:6333
    Ollama running on localhost:11434 with nomic-embed-text
    OPENROUTER_API_KEY env var (or key in ~/.openclaw/openclaw.json)
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

from mem0 import Memory

WORKSPACE = Path.home() / ".openclaw" / "workspace"
USER_ID = "pranav"

# Files in priority order
PRIORITY_FILES = [
    "MEMORY.md",
    "USER.md",
    "TOOLS.md",
    "IDENTITY.md",
    "SOUL.md",
    "contacts.md",
    "calendar.md",
    "tasks.md",
]


def get_openrouter_api_key() -> str:
    """Get OpenRouter API key from env var or openclaw.json config."""
    key = os.environ.get("OPENROUTER_API_KEY")
    if key:
        return key

    config_path = Path.home() / ".openclaw" / "openclaw.json"
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
            # Navigate the nested config to find the apiKey near openai/gpt-4o-mini
            models = (
                config.get("agents", {})
                .get("defaults", {})
                .get("models", {})
            )
            for model_key, model_conf in models.items():
                if "gpt-4o-mini" in model_key or "openrouter" in json.dumps(model_conf):
                    api_key = model_conf.get("apiKey")
                    if api_key:
                        return api_key
            # Also check nested provider configs
            providers = config.get("agents", {}).get("defaults", {}).get("providers", {})
            for _, prov_conf in providers.items():
                if isinstance(prov_conf, dict):
                    for _, model_conf in prov_conf.items():
                        if isinstance(model_conf, dict) and model_conf.get("apiKey"):
                            return model_conf["apiKey"]
        except (json.JSONDecodeError, KeyError):
            pass

    print("ERROR: No OpenRouter API key found.")
    print("Set OPENROUTER_API_KEY env var or ensure it's in ~/.openclaw/openclaw.json")
    sys.exit(1)


def init_memory(api_key: str) -> Memory:
    """Initialize mem0 Memory with Qdrant + Ollama + OpenRouter."""
    config = {
        "vector_store": {
            "provider": "qdrant",
            "config": {
                "host": "localhost",
                "port": 6333,
                "collection_name": "memories",
                "embedding_model_dims": 768,
            },
        },
        "embedder": {
            "provider": "ollama",
            "config": {
                "model": "nomic-embed-text",
                "ollama_base_url": "http://localhost:11434",
            },
        },
        "llm": {
            "provider": "openai",
            "config": {
                "model": "openai/gpt-4o-mini",
                "api_key": api_key,
                "openai_base_url": "https://openrouter.ai/api/v1",
            },
        },
    }
    return Memory.from_config(config)


def split_into_chunks(content: str, max_chars: int = 2000) -> list[str]:
    """Split markdown content into chunks by ## headers, respecting max size."""
    # Split on ## headers (keep the header with its section)
    sections = re.split(r'(?=^## )', content, flags=re.MULTILINE)
    sections = [s.strip() for s in sections if s.strip()]

    chunks = []
    for section in sections:
        if len(section) <= max_chars:
            chunks.append(section)
        else:
            # Split large sections into paragraphs, then group up to max_chars
            paragraphs = re.split(r'\n\n+', section)
            current = ""
            for para in paragraphs:
                if current and len(current) + len(para) + 2 > max_chars:
                    chunks.append(current.strip())
                    current = para
                else:
                    current = current + "\n\n" + para if current else para
            if current.strip():
                chunks.append(current.strip())

    return chunks if chunks else [content.strip()]


def collect_files(single_file: str | None) -> list[Path]:
    """Build the ordered list of files to migrate."""
    if single_file:
        target = WORKSPACE / single_file
        if target.is_dir():
            # Migrate all .md files in the directory
            return sorted(target.glob("*.md"))
        elif target.exists():
            return [target]
        else:
            print(f"ERROR: File not found: {target}")
            sys.exit(1)

    files = []

    # Priority files first
    for name in PRIORITY_FILES:
        path = WORKSPACE / name
        if path.exists():
            files.append(path)

    # Daily logs (sorted chronologically)
    memory_dir = WORKSPACE / "memory"
    if memory_dir.exists():
        daily_logs = sorted(
            p for p in memory_dir.glob("*.md")
            if p.name != "oracle-traffic-light-strategy.md"
        )
        files.extend(daily_logs)
        # Trading strategy last
        strategy = memory_dir / "oracle-traffic-light-strategy.md"
        if strategy.exists():
            files.append(strategy)

    return files


def migrate(args):
    api_key = get_openrouter_api_key()

    if not args.dry_run:
        print("Initializing mem0 Memory...")
        mem = init_memory(api_key)
    else:
        mem = None
        print("DRY RUN — no data will be stored\n")

    files = collect_files(args.file)
    if not files:
        print("No files found to migrate.")
        return

    print(f"Found {len(files)} file(s) to migrate\n")

    total_memories = 0
    total_errors = 0
    files_processed = 0

    for filepath in files:
        rel = filepath.relative_to(WORKSPACE)
        print(f"{'─' * 60}")
        print(f"Processing: {rel}")

        try:
            content = filepath.read_text(encoding="utf-8")
        except Exception as e:
            print(f"  ERROR reading file: {e}")
            total_errors += 1
            continue

        if not content.strip():
            print("  Skipped (empty file)")
            continue

        chunks = split_into_chunks(content)
        print(f"  Split into {len(chunks)} chunk(s)")

        file_memories = 0
        for i, chunk in enumerate(chunks, 1):
            preview = chunk[:80].replace("\n", " ")
            print(f"  [{i}/{len(chunks)}] {preview}...")

            if args.dry_run:
                file_memories += 1
                continue

            try:
                result = mem.add(
                    chunk,
                    user_id=USER_ID,
                    metadata={"source": str(rel), "type": "migration"},
                )
                # mem0 returns a dict with 'results' containing extracted memories
                added = len(result.get("results", []))
                file_memories += added
                if added:
                    for r in result["results"]:
                        event = r.get("event", "unknown")
                        mem_text = r.get("memory", "")[:100]
                        print(f"       → {event}: {mem_text}")
                # Small delay to avoid overwhelming the LLM API
                time.sleep(0.5)
            except Exception as e:
                print(f"       ERROR: {e}")
                total_errors += 1

        total_memories += file_memories
        files_processed += 1
        print(f"  → {file_memories} memories from {rel}")

    # Summary
    print(f"\n{'═' * 60}")
    print("MIGRATION SUMMARY")
    print(f"{'═' * 60}")
    print(f"  Files processed: {files_processed}/{len(files)}")
    print(f"  Memories added:  {total_memories}")
    print(f"  Errors:          {total_errors}")
    if args.dry_run:
        print("  (dry run — nothing was stored)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Migrate OpenClaw workspace markdown into Qdrant via mem0"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be migrated without storing anything",
    )
    parser.add_argument(
        "--file",
        type=str,
        default=None,
        help="Migrate a single file (relative to workspace), e.g. MEMORY.md or memory/",
    )
    args = parser.parse_args()
    migrate(args)
