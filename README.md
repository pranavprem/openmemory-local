# OpenMemory Local — Self-Hosted AI Memory with Ollama

Fully local, private AI memory stack. No cloud, no API keys, no data leaves your machine.

Run [OpenMemory](https://github.com/mem0ai/mem0) backed by Ollama for LLM and embeddings, Qdrant for vector storage — all on your own hardware.

## Architecture

```
┌─────────────────────────────────────┐
│         OpenMemory UI (:3000)       │
└──────────────┬──────────────────────┘
               │
┌──────────────▼──────────────────────┐
│       OpenMemory API (:8765)        │
└──────┬───────────────────┬──────────┘
       │                   │
┌──────▼──────┐    ┌───────▼─────────┐
│   Ollama    │    │  Qdrant (:6333) │
│  (Host)     │    │  (Docker)       │
│             │    │                 │
│ - llama3.2  │    │  Vector DB      │
│ - nomic-    │    │  persistent     │
│   embed-text│    │  storage        │
└─────────────┘    └─────────────────┘
```

Ollama runs on the host machine; Docker containers reach it via `host.docker.internal` (macOS Docker Desktop).

## Prerequisites

- **Docker** (with Docker Compose)
- **Ollama** installed and running on the host — [ollama.com](https://ollama.com)

## Quick Start

1. **Clone the repo**

   ```bash
   git clone https://github.com/pranav/openmemory-local.git
   cd openmemory-local
   ```

2. **Pull the Ollama models**

   ```bash
   ollama pull llama3.2 && ollama pull nomic-embed-text
   ```

3. **Create your `.env` file**

   ```bash
   cp .env.example .env
   ```

   Edit `.env` if you want to change the user name or API key.

4. **Start the stack**

   ```bash
   docker compose up -d
   ```

5. **Open the dashboard**

   - UI: [http://localhost:3000](http://localhost:3000)
   - API: [http://localhost:8765](http://localhost:8765)

## OpenClaw Integration

### Option A: Official Mem0 Plugin (open-source mode)

Install the plugin:

```bash
openclaw plugins install @mem0/openclaw-mem0
```

Add to your `openclaw.json` under `plugins.entries`:

```json
"openclaw-mem0": {
  "enabled": true,
  "config": {
    "mode": "open-source",
    "userId": "pranav",
    "oss": {
      "embedder": {
        "provider": "ollama",
        "config": { "model": "nomic-embed-text", "ollama_base_url": "http://localhost:11434" }
      },
      "vectorStore": {
        "provider": "qdrant",
        "config": { "host": "localhost", "port": 6333, "embedding_model_dims": 768 }
      },
      "llm": {
        "provider": "ollama",
        "config": { "model": "llama3.2", "ollama_base_url": "http://localhost:11434" }
      }
    }
  }
}
```

This uses the `mem0ai` library directly — no separate server needed, but shares the same Qdrant instance.

### Option B: Community REST Plugin (connects to OpenMemory API)

If you want the full OpenMemory dashboard + API, use the community plugin that talks to the running server:

```json
"memory-mem0": {
  "enabled": true,
  "config": {
    "baseUrl": "http://127.0.0.1:8765",
    "userId": "pranav",
    "autoCapture": true,
    "autoRecall": true,
    "recallLimit": 5,
    "recallThreshold": 0.4
  }
}
```

### Claude Code Integration

Add OpenMemory as an MCP server in `~/.claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "openmemory": {
      "url": "http://localhost:8765/mcp",
      "env": {
        "API_KEY": "openmemory-local"
      }
    }
  }
}
```

All approaches connect to the same local stack — no data leaves your machine.

## Verify It's Working

**Check the API health:**

```bash
curl http://localhost:8765/health
```

**Add a test memory:**

```bash
curl -X POST http://localhost:8765/v1/memories/ \
  -H "Content-Type: application/json" \
  -H "x-api-key: openmemory-local" \
  -d '{
    "text": "The user prefers dark mode in all applications.",
    "user_id": "pranav",
    "agent_id": "test"
  }'
```

**Search memories:**

```bash
curl -X POST http://localhost:8765/v1/memories/search/ \
  -H "Content-Type: application/json" \
  -H "x-api-key: openmemory-local" \
  -d '{
    "query": "What UI preferences does the user have?",
    "user_id": "pranav"
  }'
```

**Check Qdrant directly:**

```bash
curl http://localhost:6333/collections
```

## Troubleshooting

### Ollama not reachable from Docker

Containers use `host.docker.internal` to reach the host. This works out of the box on **macOS Docker Desktop**. If you see connection errors:

- Verify Ollama is running: `ollama list`
- Verify it's listening: `curl http://localhost:11434/api/tags`
- On Linux, you may need to add `extra_hosts: ["host.docker.internal:host-gateway"]` to the API service in `docker-compose.yml`

### Embedding dimension mismatch

The `nomic-embed-text` model produces 768-dimensional vectors. Both `default_config.json` entries (`embedding_dims` and `embedding_model_dims`) must be set to `768`. If you switch to a different embedding model, update both values and delete the existing Qdrant collection:

```bash
curl -X DELETE http://localhost:6333/collections/openmemory
docker compose restart openmemory-api
```

### Container can't find default_config.json

Make sure `default_config.json` is in the repo root (same directory as `docker-compose.yml`). The compose file mounts it into the container at `/app/default_config.json`.

### Port conflicts

If ports 3000, 6333, or 8765 are already in use, change the host-side port in `docker-compose.yml`:

```yaml
ports:
  - "3001:3000"  # map to a different host port
```

Update `NEXT_PUBLIC_API_URL` in `.env` accordingly if you change the API port.

### Resetting all data

```bash
docker compose down -v
docker compose up -d
```

The `-v` flag removes the Qdrant persistent volume, giving you a clean slate.
