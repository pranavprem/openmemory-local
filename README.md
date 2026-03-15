# OpenMemory Local — Self-Hosted AI Memory with Ollama

> **Status (2026-03-15):** The OpenMemory Docker dashboard is **blocked** by upstream bugs. We're currently running Mem0 via the OpenClaw plugin directly (Option A below), with Qdrant standalone. See [Known Issues](#known-issues--upstream-bugs) for details.

## Current Setup (What's Actually Working)

```
┌──────────────────────────────────────────────┐
│              OpenClaw Gateway                 │
│  ┌─────────────────────────────────────────┐  │
│  │  @mem0/openclaw-mem0 plugin (v0.3.3)    │  │
│  │  - Auto-recall (before each turn)       │  │
│  │  - Auto-capture (after each turn)       │  │
│  │  - 5 agent tools (search/store/forget)  │  │
│  └────────┬───────────────────┬────────────┘  │
│           │                   │               │
│  ┌────────▼────────┐  ┌──────▼──────────┐    │
│  │  OpenRouter      │  │  Ollama (local) │    │
│  │  GPT-4o-mini     │  │  nomic-embed-   │    │
│  │  (extraction)    │  │  text (embed)   │    │
│  └─────────────────┘  └────────────────┘     │
└──────────────────────┬───────────────────────┘
                       │
              ┌────────▼────────┐
              │  Qdrant (:6333) │
              │  (Docker)       │
              │  v1.14.0        │
              └─────────────────┘
```

- **Extraction LLM:** GPT-4o-mini via OpenRouter (~$0.001/extraction)
- **Embeddings:** Ollama nomic-embed-text (free, local, 768 dims)
- **Vector store:** Qdrant v1.14.0 (Docker, persistent volume)
- **QMD** also runs alongside for markdown file search (vsearch mode)

## Prerequisites

- **Docker** — for Qdrant
- **Ollama** installed and running — [ollama.com](https://ollama.com)
- **OpenRouter API key** — [openrouter.ai](https://openrouter.ai) (for extraction LLM)
- **OpenClaw** — with the `@mem0/openclaw-mem0` plugin

## Quick Start (Current — Plugin Mode)

### 1. Start Qdrant

```bash
docker run -d --name qdrant \
  -p 6333:6333 \
  -v qdrant_data:/qdrant/storage \
  --restart unless-stopped \
  qdrant/qdrant:v1.14.0
```

### 2. Pull Ollama embedding model

```bash
ollama pull nomic-embed-text
```

### 3. Install the OpenClaw plugin

```bash
openclaw plugins install @mem0/openclaw-mem0
```

### 4. Configure in `openclaw.json`

Add under `plugins.entries`:

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
        "config": {
          "model": "nomic-embed-text",
          "ollama_base_url": "http://localhost:11434"
        }
      },
      "vectorStore": {
        "provider": "qdrant",
        "config": {
          "host": "localhost",
          "port": 6333,
          "collection_name": "openmemory",
          "embedding_model_dims": 768
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

> **⚠️ Important:** The JS library uses `apiKey` and `baseURL` (camelCase), NOT `api_key` and `openai_base_url` (Python snake_case). The Mem0 docs show Python config — the OpenClaw plugin uses the JS library.

### 5. Restart the gateway

```bash
openclaw gateway restart
```

### 6. Verify

```bash
# From chat, ask the agent to run:
# memory_store "Test memory: the sky is blue"
# memory_search "sky color"
# memory_list
```

## Dashboard

A single HTML file that talks directly to Qdrant + Ollama. No server needed.

```bash
open dashboard.html
```

Features:
- Dark mode UI
- Shows total memory count + Qdrant health
- Lists all stored memories with user, date, metadata
- **Semantic search** — embeds your query via Ollama, searches by vector similarity
- Delete individual memories
- Zero dependencies — just a browser

## Known Issues & Upstream Bugs

The OpenMemory Docker dashboard (API + UI) **does not work** with Ollama/local setups due to several upstream bugs:

### 🔴 Blocking Issues

1. **[#3238](https://github.com/mem0ai/mem0/issues/3238) — No vector_store config route**
   - The API only exposes PUT routes for `llm` and `embedder`, not `vector_store`
   - The hardcoded default uses `mem0_store` as the Qdrant hostname
   - Config PUT silently drops `vector_store` from the payload
   - Result: `"Failed to initialize memory client: [Errno -2] Name or service not known"`

2. **[#3439](https://github.com/mem0ai/mem0/issues/3439) — OpenMemory local Ollama broken**
   - `run.sh` calls a `/api/v1/config/mem0/vector_store` route that doesn't exist
   - `OPENAI_API_KEY` is required even when using Ollama (hardcoded `OpenAI()` client init)
   - Embedding dimensions default to 1536 (OpenAI) — Ollama models use 768
   - Community PR with fixes submitted but not merged

3. **[#3447](https://github.com/mem0ai/mem0/issues/3447) — UI missing vector store settings**
   - No way to configure vector store from the dashboard UI

### 🟡 Workarounds We Used

- Set `OPENAI_API_KEY=sk-unused-ollama-only` to bypass startup crash
- Renamed Qdrant service to `mem0_store` to match hardcoded default
- Still failed: memory client couldn't initialize due to embedding dim mismatch

### ✅ What Works Instead

The `@mem0/openclaw-mem0` plugin in open-source mode bypasses all of these issues because it uses the `mem0ai` JS library directly (not the Docker API server). The library properly supports Ollama + Qdrant configuration.

## Future: OpenMemory Dashboard Setup

Once the upstream bugs are fixed, this repo contains Docker Compose files to run the full stack:

```bash
cd ~/git/openmemory-local
cp .env.example .env
docker compose up -d
```

This will start:
- **Qdrant** (:6333) — vector storage
- **OpenMemory API** (:8765) — memory management
- **OpenMemory UI** (:3000) — dashboard for browsing/managing memories

### What to check before re-enabling:
1. [#3238](https://github.com/mem0ai/mem0/issues/3238) is merged — vector_store config route exists
2. [#3439](https://github.com/mem0ai/mem0/issues/3439) is merged — Ollama works without OpenAI key
3. Test with: `docker compose up -d && curl http://localhost:8765/api/v1/config/mem0/vector_store`
4. If working, switch OpenClaw plugin to Option B (REST plugin pointing at localhost:8765)

## Lessons Learned

- **JS vs Python field names:** The mem0 docs show Python config (`api_key`, `openai_base_url`). The OpenClaw plugin uses the JS library which expects `apiKey` and `baseURL`. This caused hours of debugging.
- **Ollama extraction quality:** Small local LLMs (llama3.2) don't reliably output the structured JSON format mem0 expects. GPT-4o-mini via OpenRouter is cheap (~$0.001/call) and works perfectly.
- **Qdrant version compatibility:** The mem0 JS client (v1.13) requires Qdrant ≤1.14. Running Qdrant latest (1.17) causes version mismatch errors.
