# CLAUDE.md

## Project Overview

Local OpenMemory setup for Neo's (OpenClaw agent) Mem0 memory system. This repo contains the tooling, configuration docs, and utilities for a fully self-hosted AI memory pipeline: auto-capture facts from conversations, store as vectors in Qdrant, and auto-recall relevant memories before each agent turn.

**This is the UI/utility layer** — the actual memory system runs as an OpenClaw plugin (`@mem0/openclaw-mem0`).

## Architecture

```
OpenClaw Gateway
  └─ @mem0/openclaw-mem0 plugin (v0.3.3, open-source mode)
       ├─ Extraction LLM: GPT-4o-mini via OpenRouter (~$0.001/call)
       ├─ Embeddings: Ollama bge-m3 (1024 dims, local, free)
       └─ Vector DB: Qdrant v1.14.0 (Docker, port 6333)
```

- **Auto-recall:** Before each turn, plugin searches Qdrant and injects `<relevant-memories>` into context
- **Auto-capture:** After each turn, GPT-4o-mini extracts facts → embedded via Ollama → stored in Qdrant
- **Agent tools:** `memory_store`, `memory_search`, `memory_list`, `memory_get`, `memory_forget`
- **QMD layer** also exists (BM25 + vector search over raw markdown files) — separate from this repo

## Key Technical Details

### Qdrant Version Pinning
**Must use Qdrant v1.14.x.** The Mem0 JS client (used by OpenClaw plugin) requires ≤1.14. Running `latest` (1.17+) causes version mismatch errors.

### JS vs Python Field Names (The #1 Trap)
OpenClaw uses the **JS** Mem0 library. Config must use camelCase:
- ✅ `apiKey`, `baseURL` (JS)
- ❌ `api_key`, `openai_base_url` (Python — don't use these)

### Embedding Model
- **bge-m3** via Ollama — 1024 dimensions
- Alternative: `nomic-embed-text` (768 dims) — update `embedding_model_dims` if switching
- Changing models requires deleting and recreating the Qdrant collection:
  ```bash
  curl -X DELETE http://localhost:6333/collections/openmemory
  # Restart OpenClaw — plugin auto-creates the collection
  ```

### Local LLMs for Extraction Don't Work
`llama3.2` fails ~40% of the time with malformed JSON. GPT-4o-mini via OpenRouter is the reliable choice.

## Repo Structure

| File | Purpose |
|------|---------|
| `README.md` | Full setup guide, architecture, gotchas, lessons learned |
| `current-setup.md` | Detailed technical overview of the 3-layer memory architecture |
| `dashboard.html` | Standalone memory browser — opens in any browser, talks to Qdrant + Ollama directly |
| `migrate.py` | Bulk import markdown files → Qdrant (used for initial migration of ~39 files → ~300 memories) |
| `mem0-cleanup.py` | Periodic junk memory cleanup with regex patterns, backs up before deleting |
| `docker-compose.yml` | Qdrant + search-proxy + OpenMemory stack (OpenMemory services blocked by upstream bugs) |
| `search-proxy/` | CORS-safe proxy: local Ollama + NAS Qdrant (Dockerfile + FastAPI server) |
| `default_config.json` | Config for Docker OpenMemory stack (not needed for plugin mode) |
| `.env.example` | Environment variables template |
| `requirements.txt` | Python deps: `qdrant-client`, `requests` |
| `venv/` | Python virtualenv (gitignored) |

## Current Status

- ✅ Mem0 memory system is operational (plugin mode)
- ✅ Dashboard (standalone HTML) works
- ✅ Cleanup script works and runs on cron
- ⛔ OpenMemory Docker dashboard blocked by upstream bugs:
  - [#3238](https://github.com/mem0ai/mem0/issues/3238) — No `vector_store` config API route
  - [#3439](https://github.com/mem0ai/mem0/issues/3439) — `OPENAI_API_KEY` required even with Ollama
  - [#3447](https://github.com/mem0ai/mem0/issues/3447) — UI has no vector store settings

## Memory Hygiene (Important)

Auto-capture generates **a lot of junk** (timestamps, heartbeat statuses, message metadata). Mitigations:
1. **Restrictive `customPrompt`** in OpenClaw config — explicit DO NOT extract list
2. **`searchThreshold: 0.6`** (default 0.5 pulls too much noise)
3. **Periodic cleanup** via `mem0-cleanup.py` (regex-based, backs up first)

First cleanup deleted 751/3412 memories (22% junk). See README.md "Memory Hygiene" section for full details.

## Docker Compose Profiles

```bash
docker compose up -d                    # Just Qdrant
docker compose --profile search up -d   # Qdrant + search proxy
docker compose --profile openmemory up -d  # Full stack (blocked)
```

Search proxy runs on port 6380, queries Qdrant on NAS (10.0.0.116:6333) + local Ollama.

## Development

```bash
cd ~/git/openmemory-local
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run cleanup (dry run)
python3 mem0-cleanup.py --dry-run -v

# Run migration
python3 migrate.py --workspace ~/.openclaw/workspace \
  --qdrant-url http://localhost:6333 \
  --collection openmemory \
  --ollama-url http://localhost:11434 \
  --ollama-model bge-m3 \
  --openrouter-key $OPENROUTER_API_KEY \
  --user-id pranav
```

## Remotes

- **GitHub:** https://github.com/pranavprem/openmemory-local
- **Related:** [qdrant-nas](https://github.com/pranavprem/qdrant-nas) — run Qdrant on NAS instead of locally

## Owner

Pranav Prem (pranavprem93@gmail.com)
