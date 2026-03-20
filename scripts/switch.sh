#!/bin/bash
# Switch Mac mini to use NAS Qdrant instead of local.
# Does NOT clean up local Qdrant — do that later with 'make cleanup'.
#
# Usage: ./scripts/switch.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$PROJECT_DIR/.env"

NAS_QDRANT="http://${NAS_IP}:${QDRANT_PORT:-6333}"

echo "🔍 Step 1: Verifying NAS Qdrant is reachable..."
if ! curl -s --connect-timeout 3 "$NAS_QDRANT/healthz" > /dev/null 2>&1; then
    echo "   ❌ Can't reach Qdrant at $NAS_QDRANT"
    echo "   Is it running on the NAS? Try: ssh ${NAS_USER}@${NAS_IP} 'cd ${NAS_DEPLOY_DIR} && docker compose ps'"
    exit 1
fi

COUNT=$(curl -s "$NAS_QDRANT/collections/memories" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['points_count'])" 2>/dev/null || echo "0")
echo "   ✅ NAS Qdrant is up — $COUNT memories"

if [ "$COUNT" -eq 0 ]; then
    echo "   ⚠️  WARNING: NAS has 0 memories! Did you run 'make setup' on the NAS?"
    read -p "   Continue anyway? (y/N) " confirm
    [ "$confirm" = "y" ] || exit 1
fi

echo ""
echo "🔄 Step 2: Updating migrate.py → NAS..."
MIGRATE_PY="$PROJECT_DIR/migrate.py"
if [ -f "$MIGRATE_PY" ]; then
    sed -i '' "s|QDRANT_URL = \"http://localhost:${QDRANT_PORT:-6333}\"|QDRANT_URL = \"$NAS_QDRANT\"|" "$MIGRATE_PY"
    # Also handle if it was already pointing somewhere else
    sed -i '' "s|QDRANT_URL = \"http://127.0.0.1:${QDRANT_PORT:-6333}\"|QDRANT_URL = \"$NAS_QDRANT\"|" "$MIGRATE_PY"
    echo "   ✅ migrate.py now points to $NAS_QDRANT"
else
    echo "   ⚠️  migrate.py not found, skipping"
fi

echo ""
echo "════════════════════════════════════════"
echo "✅ Switch complete!"
echo ""
echo "migrate.py now targets NAS Qdrant."
echo ""
echo "⚠️  You still need to update the OpenClaw Mem0 plugin config:"
echo ""
echo "   Tell Neo to run:"
echo "   gateway config.patch → plugins.entries.openclaw-mem0.config.oss.vectorStore.config.host = \"${NAS_IP}\""
echo ""
echo "   Or manually edit ~/.openclaw/openclaw.json"
echo ""
echo "Local Qdrant is still running (not cleaned up)."
echo "After confirming NAS works for a day or two:"
echo "   make cleanup"
echo "════════════════════════════════════════"
