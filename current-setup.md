# Neo's Memory Architecture — Technical Overview

## Summary
A hybrid memory system combining **Mem0** (semantic AI memory with auto-capture) and **QMD** (local markdown search) running on a Mac mini M4 (24GB RAM). All processing is local except extraction LLM calls, which route through OpenRouter.

---

## Architecture
```
                    ┌────────────────────────────┐
                    │     OpenClaw Gateway        │
                    │     (Claude Opus 4.6)       │
                    └─────┬──────────┬────────────┘
                          │          │
        ┌─────────────────▼──┐  ┌────▼──────────────────┐
        │  @mem0/openclaw-mem0│  │  QMD (memory.backend)  │
        │  plugin (v0.3.3)   │  │  vsearch mode           │
        │  open-source mode  │  │  MCPorter daemon        │
        └──┬─────┬─────┬────┘  └────┬───────────────────┘
           │     │     │            │
     ┌─────▼┐ ┌──▼──┐ ┌▼────────┐  ┌▼──────────────────┐
     │OpenR. │ │Ollama│ │Qdrant  │  │Local GGUF models   │
     │GPT-4o │ │bge-m3│ │v1.14.0 │  │embeddinggemma-300M │
     │-mini  │ │embed │ │Docker  │  │qwen3-reranker-0.6b │
     │(LLM)  │ │(local│ │:6333   │  │query-expansion-1.7B│
     └───────┘ └─────┘ └────────┘  └────────────────────┘
```

---

## Layer 1: Mem0 (Semantic AI Memory)

**Plugin:** `@mem0/openclaw-mem0` v0.3.3, open-source mode  
**Memory slot:** Takes over the `memory` plugin slot (replaces `memory-core` and `memory-lancedb`)

**Components:**
- **Extraction LLM:** `openai/gpt-4o-mini` via OpenRouter (`baseURL: https://openrouter.ai/api/v1`) — extracts atomic facts from conversations
- **Embeddings:** Ollama `bge-m3` (1024 dimensions, fully local)
- **Vector store:** Qdrant v1.14.0 running as a Docker container on port 6333, collection `memories`

**How it works:**
1. **Auto-recall** — before each agent turn, the plugin searches Qdrant for memories relevant to the current message and injects them as `<relevant-memories>` context
2. **Auto-capture** — after each agent turn, the conversation exchange is sent to GPT-4o-mini which extracts facts worth remembering. New facts are embedded via Ollama and stored in Qdrant. Duplicates are merged, outdated facts are updated.
3. **Agent tools** — 5 explicit tools: `memory_search`, `memory_store`, `memory_list`, `memory_get`, `memory_forget`

**Key config (openclaw.json):**
```json
"openclaw-mem0": {
  "enabled": true,
  "config": {
    "mode": "open-source",
    "userId": "pranav",
    "autoRecall": true,
    "autoCapture": true,
    "topK": 5,
    "oss": {
      "embedder": {
        "provider": "ollama",
        "config": { "model": "bge-m3" }
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
          "apiKey": "<openrouter-key>",
          "baseURL": "https://openrouter.ai/api/v1"
        }
      }
    }
  }
}
```

**⚠️ Gotcha:** The JS library uses `apiKey` and `baseURL` (camelCase), NOT the Python-style `api_key` and `openai_base_url` shown in Mem0's docs.

---

## Layer 2: QMD (Markdown File Search)

**Config:** `memory.backend: "qmd"`, vsearch mode, MCPorter daemon  
**What it indexes:** All `.md` files in `~/.openclaw/workspace/` (45 files, 64 chunks)

**Components:**
- **BM25** — keyword search via SQLite FTS5
- **Vector search** — embeddinggemma-300M GGUF model (328MB)
- **Query expansion** — fine-tuned 1.7B model generates alternative phrasings
- **LLM reranking** — qwen3-reranker-0.6b for precision boost
- All models run locally via node-llama-cpp (~2GB total)

**How it works:**
- Agent calls `qmd vsearch "query"` for semantic search over markdown files
- Returns raw text chunks with full context (not extracted facts)
- MCPorter daemon keeps models warm (no cold-start latency)
- Re-indexes every 5 minutes, re-embeds every 60 minutes
- Timeout: 120 seconds

---

## Layer 3: Markdown Files (Foundation)

**Files:**
- `MEMORY.md` — curated long-term memory (loaded on boot in main sessions only)
- `memory/YYYY-MM-DD.md` — daily logs (32 files spanning Feb 5 – Mar 15, 2026)
- `USER.md`, `TOOLS.md`, `SOUL.md`, `IDENTITY.md` — loaded every session via AGENTS.md rules
- `contacts.md`, `calendar.md`, `tasks.md` — reference files

**Who writes them:**
- Neo manually during conversations and heartbeats
- todo-updater cron (9 PM daily, writes notable events)
- Any cron/agent that discovers important information

---

## How They Work Together

| Need | Layer | Example |
|---|---|---|
| Quick recall during conversation | **Mem0 auto-recall** | `<relevant-memories>` injected before each turn |
| "What do I know about X?" | **Mem0 search** | `memory_search` tool → Qdrant vector similarity |
| "Show me the exact details" | **QMD** | `qmd vsearch` → raw markdown chunks with full context |
| "Remember this for later" | **Mem0 store** | `memory_store` → GPT-4o-mini extracts → Qdrant |
| Boot context | **Markdown files** | MEMORY.md, USER.md, SOUL.md loaded per AGENTS.md |

---

## Migration & Dashboard

**Initial migration:** Python script (`migrate.py`) read all 39 workspace .md files, chunked by `##` headers, sent through GPT-4o-mini for extraction → 175 memories in Qdrant.

**Dashboard:** Single HTML file (`dashboard.html`) that queries Qdrant REST API + Ollama embeddings directly. Shows all memories, semantic search, delete. No server needed.

**Repo:** `pranavprem/openmemory-local` on GitHub

---

## Costs

| Component | Cost |
|---|---|
| Ollama (bge-m3 embeddings) | Free (local) |
| QMD (all models) | Free (local, ~2GB GGUF models) |
| Qdrant | Free (Docker) |
| GPT-4o-mini extraction (auto-capture) | ~$0.001/turn via OpenRouter |
| Initial migration (175 memories) | ~$0.50 total |

---

## Planned Improvements

1. **Raw chunk storage** — add `--raw` flag to migrate.py to store full markdown chunks in Qdrant alongside extracted facts (no LLM, just embed + store)
2. **Nightly cron** — sync today's `memory/YYYY-MM-DD.md` raw chunks to Qdrant at 11 PM
3. **Custom extraction prompt** — configure mem0's `customPrompt` for richer auto-capture
4. **Periodic full re-sync** — weekly re-run of raw chunk migration for edited files

---

## Known Limitations

1. **Mem0 extraction loses detail** — atomic facts are compressed. Raw chunk storage (planned) will supplement this.
2. **OpenMemory Docker dashboard blocked** — upstream bugs [#3238](https://github.com/mem0ai/mem0/issues/3238), [#3439](https://github.com/mem0ai/mem0/issues/3439), [#3447](https://github.com/mem0ai/mem0/issues/3447) prevent running the full API+UI stack with Ollama
3. **Qdrant client/server version sensitivity** — must match within 1 minor version
4. **Ollama small LLMs can't do mem0 extraction** — llama3.2 fails at structured JSON output (known issues [#2030](https://github.com/mem0ai/mem0/issues/2030), [#2758](https://github.com/mem0ai/mem0/issues/2758))
