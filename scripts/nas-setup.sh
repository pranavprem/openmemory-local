#!/bin/bash
# Set up and import Qdrant on the NAS.
# Run this ON the NAS after cloning the repo and running export.sh from Mac.
#
# Usage: ./scripts/nas-setup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$PROJECT_DIR/.env"

QDRANT_URL="http://localhost:${QDRANT_PORT:-6333}"
SNAPSHOT_DIR="/tmp/qdrant-export"
COLLECTION="memories"

echo "🚀 Step 1: Starting Qdrant..."
cd "$PROJECT_DIR"

if [ "${MEMORY_MODE:-mem0}" = "openmemory" ]; then
    docker compose --profile openmemory up -d
else
    docker compose up -d qdrant
fi

echo "   ⏳ Waiting for Qdrant to be healthy..."
for i in $(seq 1 30); do
    if curl -s --connect-timeout 2 "$QDRANT_URL/healthz" > /dev/null 2>&1; then
        echo "   ✅ Qdrant is up!"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "   ❌ Qdrant didn't start in time. Check: docker compose logs qdrant"
        exit 1
    fi
    sleep 2
done

echo ""
echo "📦 Step 2: Importing snapshot..."
SNAPSHOT_FILE="$SNAPSHOT_DIR/${COLLECTION}.snapshot"

if [ ! -f "$SNAPSHOT_FILE" ]; then
    echo "   ❌ Snapshot not found: $SNAPSHOT_FILE"
    echo "   Did you run 'make export' on the Mac first?"
    exit 1
fi

RESPONSE=$(curl -s -X POST "$QDRANT_URL/collections/$COLLECTION/snapshots/upload" \
    -H "Content-Type: multipart/form-data" \
    -F "snapshot=@$SNAPSHOT_FILE")

STATUS=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin).get('status','unknown'))" 2>/dev/null || echo "unknown")

if [ "$STATUS" != "ok" ]; then
    echo "   ❌ Import failed!"
    echo "   Response: $RESPONSE"
    exit 1
fi

COUNT=$(curl -s "$QDRANT_URL/collections/$COLLECTION" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['points_count'])")

echo "   ✅ $COUNT points imported!"
echo ""

echo "🔍 Step 3: Verifying..."
echo "   Collections:"
curl -s "$QDRANT_URL/collections" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for c in data['result']['collections']:
    name = c['name']
    info = json.loads(open('/dev/stdin').read()) if False else None
    print(f'     - {name}')
" 2>/dev/null || true

# Show a few sample entries
curl -s "$QDRANT_URL/collections/$COLLECTION" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print(f'     - {COLLECTION}: {data[\"result\"][\"points_count\"]} points')
" 2>/dev/null

echo ""
echo "   Sample memories:"
curl -s "$QDRANT_URL/collections/$COLLECTION/points/scroll" \
    -H 'Content-Type: application/json' \
    -d '{"limit": 3, "with_payload": true}' | python3 -c "
import sys, json
data = json.load(sys.stdin)
for p in data['result']['points'][:3]:
    payload = p.get('payload', {})
    text = str(payload.get('data', payload.get('memory', payload.get('text', ''))))[:100]
    print(f'     • {text}')
" 2>/dev/null

echo ""
echo "════════════════════════════════════════"
echo "✅ NAS setup complete!"
echo "   Qdrant running at $QDRANT_URL with $COUNT memories."
echo ""
echo "Back on the Mac mini, run:"
echo "   make switch"
echo "════════════════════════════════════════"
