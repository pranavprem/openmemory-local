# OpenMemory Local — Self-Hosted AI Memory for OpenClaw

> Give your OpenClaw agent persistent, semantic memory using [Mem0](https://github.com/mem0ai/mem0) + [Qdrant](https://qdrant.tech/) + [Ollama](https://ollama.com), running entirely on your own hardware.

> **Running on a Mac mini or low-storage device?** See [qdrant-nas](https://github.com/pranavprem/qdrant-nas) to run Qdrant on a NAS instead of locally.

**Last updated:** 2026-03-20

## What This Does

Your OpenClaw agent wakes up fresh every session. This setup gives it long-term memory:

- **Auto-capture:** After each conversation turn, important facts are automatically extracted and stored
- **Auto-recall:** Before each turn, relevant memories are retrieved and injected into context
- **Agent tools:** The agent can explicitly `memory_store`, `memory_search`, `memory_list`, `memory_get`, and `memory_forget`
- **Semantic search:** Memories are embedded as vectors — the agent finds relevant context even with different wording
- **100% local:** Embeddings run on Ollama, vectors stored in Qdrant on your machine. Only the extraction LLM can optionally use a cloud API.

## Architecture

```
┌──────────────────────────────────────────────────┐
│                OpenClaw Gateway                   │
│  ┌─────────────────────────────────────────────┐  │
│  │  @mem0/openclaw-mem0 plugin (v0.3.3+)       │  │
│  │  - Auto-recall (before each turn)           │  │
│  │  - Auto-capture (after each turn)           │  │
│  │  - 5 agent tools (search/store/get/forget)  │  │
│  └────────┬───────────────────┬────────────────┘  │
│           │                   │                   │
│  ┌────────▼─────────┐  ┌─────▼───────────────┐   │
│  │  Extraction LLM   │  │  Ollama (local)     │   │
│  │  GPT-4o-mini via  │  │  bge-m3 embeddings  │   │
│  │  OpenRouter       │  │  (1024 dims)        │   │
│  │  (~$0.001/call)   │  │  FREE               │   │
│  └──────────────────┘  └─────────────────────┘   │
└──────────────────────┬───────────────────────────┘
                       │
              ┌────────▼────────┐
              │  Qdrant (:6333) │
              │  Docker v1.14.0 │
              │  persistent vol │
              └─────────────────┘
```

### Component Roles

| Component | What it does | Where it runs | Cost |
|-----------|-------------|---------------|------|
| **Qdrant** | Stores memory vectors + metadata | Docker container, port 6333 | Free |
| **Ollama + bge-m3** | Generates 1024-dim embeddings for memories | Local, port 11434 | Free |
| **GPT-4o-mini** | Extracts structured facts from conversation | OpenRouter API | ~$0.001/call |
| **@mem0/openclaw-mem0** | OpenClaw plugin that wires it all together | Inside OpenClaw process | Free |

> **Why not run extraction locally too?** Small local LLMs (llama3.2, etc.) don't reliably output the structured JSON that Mem0 expects. GPT-4o-mini via OpenRouter costs fractions of a penny per extraction and works perfectly. You can try local extraction, but expect failures.

## Prerequisites

- **Docker** — for Qdrant
- **Ollama** installed and running — [ollama.com](https://ollama.com)
- **OpenRouter API key** — [openrouter.ai](https://openrouter.ai) (~$5 credit lasts months)
- **OpenClaw** — with plugin support

## Setup Guide (Step by Step)

### 1. Start Qdrant

```bash
docker run -d --name qdrant \
  -p 6333:6333 \
  -v qdrant_data:/qdrant/storage \
  --restart unless-stopped \
  qdrant/qdrant:v1.14.0
```

Verify it's running:
```bash
curl -s http://localhost:6333/healthz
# Should return: {"title":"qdrant - vectorass engine","version":"1.14.0",...}
```

> **⚠️ Use Qdrant v1.14.x specifically.** The Mem0 JS client (used by the OpenClaw plugin) requires Qdrant ≤1.14. Running `latest` (1.17+) causes version mismatch errors.

### 2. Pull the embedding model

```bash
ollama pull bge-m3
```

This downloads the BGE-M3 model (~1.2GB). It produces 1024-dimensional embeddings.

> **Alternative:** You can use `nomic-embed-text` (768 dims) instead — just update the `embedding_model_dims` to 768 in the config below. bge-m3 is recommended for better multilingual and retrieval quality.

### 3. Install the OpenClaw plugin

```bash
openclaw plugins install @mem0/openclaw-mem0
```

### 4. Configure in `openclaw.json`

Add the following under `plugins.entries`:

```jsonc
"openclaw-mem0": {
  "enabled": true,
  "config": {
    "mode": "open-source",
    "userId": "your-username",      // identifies whose memories these are
    "autoRecall": true,             // inject relevant memories before each turn
    "autoCapture": true,            // extract + store memories after each turn
    "topK": 5,                      // number of memories to recall per turn
    "oss": {
      "embedder": {
        "provider": "ollama",
        "config": {
          "model": "bge-m3",
          "ollama_base_url": "http://localhost:11434"
        }
      },
      "vectorStore": {
        "provider": "qdrant",
        "config": {
          "host": "localhost",
          "port": 6333,
          "collection_name": "openmemory",
          "embedding_model_dims": 1024
        }
      },
      "llm": {
        "provider": "openai",
        "config": {
          "model": "openai/gpt-4o-mini",
          "apiKey": "YOUR_OPENROUTER_API_KEY",
          "baseURL": "https://openrouter.ai/api/v1",
          "temperature": 0,
          "max_tokens": 2000
        }
      }
    }
  }
}
```

### 5. Restart the gateway

```bash
openclaw gateway restart
```

### 6. Verify it works

In chat with your agent:
```
Store a test memory: "The sky is blue"
```
Then:
```
Search your memory for sky color
```

The agent should find it. You can also ask it to run `memory_list` to see all stored memories.

## Migrating Existing Memories

If you already have markdown memory files (like `memory/YYYY-MM-DD.md`, `MEMORY.md`, etc.), the included `migrate.py` script can bulk-import them into Qdrant.

```bash
cd ~/git/openmemory-local
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run migration (reads all .md files from your workspace)
python3 migrate.py \
  --workspace ~/.openclaw/workspace \
  --qdrant-url http://localhost:6333 \
  --collection openmemory \
  --ollama-url http://localhost:11434 \
  --ollama-model bge-m3 \
  --openrouter-key YOUR_OPENROUTER_API_KEY \
  --user-id your-username
```

This will:
1. Read all `.md` files in your workspace
2. Chunk them by section headers
3. Use GPT-4o-mini to extract structured facts from each chunk
4. Embed with bge-m3 via Ollama
5. Store in Qdrant

Our migration of ~39 files produced ~300 memories and cost about $0.50 in OpenRouter tokens.

## Dashboard

`dashboard.html` is a standalone HTML file that talks directly to Qdrant + Ollama. No server needed.

```bash
open dashboard.html
# or just open it in any browser
```

**Features:**
- Dark mode UI
- Total memory count + Qdrant health status
- Browse all stored memories with user, date, and metadata
- **Semantic search** — embeds your query via Ollama and searches by vector similarity
- Delete individual memories
- Zero dependencies — just a browser

## Memory Hygiene: Auto-Capture Generates Junk

**This is the biggest lesson from running Mem0 in production.** The default `customPrompt` and auto-capture settings will flood your Qdrant collection with low-value memories. In our case: **3,412 memories after just 5 weeks**, most of which were useless noise like timestamps, heartbeat statuses, photo observations, and message metadata.

### The Problem

Auto-capture stores **everything the extraction LLM considers a "fact"** — which includes:
- "The current time is Friday, March 20th, 2026"
- "HEARTBEAT_OK status was returned"
- "The sender's ID is 404340348194652160"
- "The plastic sheeting was sealed with blue tape"
- Entire blocks from workspace files (TOOLS.md, MEMORY.md) re-stored as memories

These then get auto-recalled in completely wrong contexts (e.g., home renovation details surfacing in a trading strategy discussion), causing the agent to blurt out irrelevant information.

### The Fix: Restrictive customPrompt

Replace the default extraction prompt with one that has an explicit **DO NOT extract** list:

```jsonc
"customPrompt": "Extract ONLY information that would be useful weeks or months from now. Focus on:\n- User preferences, opinions, and explicit decisions\n- Important relationships between people\n- Project outcomes and status changes (not intermediate steps)\n- Lessons learned from mistakes\n- Configuration details that are hard to re-derive\n- Recurring patterns or schedules\n\nDO NOT extract:\n- Timestamps, current dates, or 'the current time is X'\n- Transient status ('inbox is clean', 'HEARTBEAT_OK', '/tmp is clean')\n- Step-by-step procedure details\n- Message metadata (sender IDs, message IDs, channel names)\n- Observations about photos or images\n- Todo list snapshots or task sync reports\n- Code snippets, file paths, or CLI commands\n- Duplicate information already in workspace files\n- Conversation flow details ('user asked about X')\n- Generic facts from web searches\n\nBe extremely selective. 1-3 high-value memories per conversation is ideal. Zero is fine if nothing worth remembering happened."
```

### The Fix: Raise searchThreshold

Default `searchThreshold` is 0.5, which pulls in a lot of tangentially related noise. We raised it to **0.6** for better precision:

```jsonc
"searchThreshold": 0.6
```

### The Fix: Periodic Cleanup Cron

Even with a better prompt, some junk still gets through. The included `mem0-cleanup.py` script uses regex patterns to find and delete common junk categories:

```bash
# Dry run first
python3 mem0-cleanup.py --dry-run

# Actually delete (backs up to memory/mem0-backups/ first)
python3 mem0-cleanup.py

# Verbose mode to see what's being kept/junked
python3 mem0-cleanup.py --dry-run -v
```

We run this on a cron schedule (twice a week). In our first cleanup, it deleted **751 junk memories** out of 3,412 (22% of all stored memories were pure noise).

### Results

| Metric | Before | After |
|--------|--------|-------|
| Total memories | 3,412 | 2,661 |
| Junk entries removed | — | 751 |
| Cross-context leaks | Frequent | None observed |
| Memories per conversation | 5-15 (too many) | 1-3 (targeted) |

## Gotchas & Lessons Learned

### JS vs Python field names (the #1 trap)

The Mem0 docs show Python config everywhere:
```python
# Python (DON'T use these in OpenClaw config)
api_key = "..."
openai_base_url = "..."
```

The OpenClaw plugin uses the **JS library**, which expects **camelCase**:
```json
// JavaScript (USE these in openclaw.json)
"apiKey": "...",
"baseURL": "..."
```

This mismatch caused hours of debugging. If your memories aren't being stored, check your field names first.

### Qdrant version matters

The `mem0ai` JS client v1.x is built against Qdrant client v1.14. Using Qdrant server v1.17+ causes:
```
Error: Version mismatch: expected ≤1.14, got 1.17
```

Pin to `qdrant/qdrant:v1.14.0`.

### Local LLMs for extraction don't work well

We tried `llama3.2` for memory extraction. It works ~60% of the time — the other 40%, it returns malformed JSON or misses key facts. GPT-4o-mini via OpenRouter is cheap enough (~$0.001/extraction) that it's not worth fighting local models for this.

Embeddings via Ollama work perfectly though — that's the expensive part anyway.

### LaunchAgent + env vars

If OpenClaw runs as a macOS LaunchAgent (daemon), environment variables set in `.zshrc` won't be available. You may need to hardcode the OpenRouter API key directly in `openclaw.json` rather than using env var references. This is a macOS-specific gotcha.

### Collection already exists

If you change embedding models (e.g., nomic-embed-text → bge-m3), you need to delete and recreate the Qdrant collection because dimensions changed:

```bash
curl -X DELETE http://localhost:6333/collections/openmemory
# Then restart OpenClaw — the plugin auto-creates the collection
```

## OpenMemory Docker Dashboard (Blocked)

The official OpenMemory Docker dashboard (API + UI containers) **does not work** with Ollama/local setups due to upstream bugs:

| Issue | Status | Problem |
|-------|--------|---------|
| [#3238](https://github.com/mem0ai/mem0/issues/3238) | Open | No `vector_store` config API route — hardcoded to `mem0_store` hostname |
| [#3439](https://github.com/mem0ai/mem0/issues/3439) | Open | `OPENAI_API_KEY` required even with Ollama; embedding dims hardcoded to 1536 |
| [#3447](https://github.com/mem0ai/mem0/issues/3447) | Open | UI has no vector store settings page |

The `docker-compose.yml` in this repo is preserved for when these get fixed. Until then, use the standalone `dashboard.html` or the agent's built-in `memory_*` tools.

**To check if upstream is fixed:**
```bash
docker compose up -d
curl http://localhost:8765/api/v1/config/mem0/vector_store
# If this returns 200 with config, the bugs are fixed
```

## File Reference

| File | Purpose |
|------|---------|
| `README.md` | This file |
| `dashboard.html` | Standalone memory browser (open in browser) |
| `migrate.py` | Bulk import markdown files → Qdrant |
| `mem0-cleanup.py` | Periodic junk memory cleanup (cron-friendly, backs up before deleting) |
| `requirements.txt` | Python deps for migrate.py |
| `docker-compose.yml` | Full OpenMemory stack (blocked, saved for later) |
| `default_config.json` | Config for the Docker stack (not needed for plugin mode) |
| `.env.example` | Env vars for the Docker stack |

## Alternatives Considered

| Approach | Verdict |
|----------|---------|
| OpenMemory Docker (API + UI) | Blocked by upstream bugs — no local Ollama support |
| Mem0 Cloud (hosted) | Works but sends all memories to mem0.ai servers — defeats the purpose |
| ChromaDB instead of Qdrant | Mem0 JS client doesn't support Chroma |
| Weaviate instead of Qdrant | More complex setup, no clear advantage for this use case |
| Raw pgvector | Would work but need to manage Postgres + lose Mem0's extraction pipeline |

## License

MIT — do whatever you want with it.
