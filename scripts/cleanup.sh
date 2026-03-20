#!/bin/bash
# Clean up local Qdrant after confirming NAS works.
# Run this ONLY after the NAS has been stable for a day or two.
#
# Usage: ./scripts/cleanup.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$PROJECT_DIR/.env"

NAS_QDRANT="http://${NAS_IP}:${QDRANT_PORT:-6333}"

echo "🔍 Pre-flight: Verifying NAS Qdrant..."
if ! curl -s --connect-timeout 3 "$NAS_QDRANT/healthz" > /dev/null 2>&1; then
    echo "   ❌ NAS Qdrant not reachable at $NAS_QDRANT"
    echo "   ABORTING — not safe to clean up local."
    exit 1
fi

COUNT=$(curl -s "$NAS_QDRANT/collections/memories" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['points_count'])" 2>/dev/null || echo "0")
echo "   NAS has $COUNT memories"

if [ "$COUNT" -lt 100 ]; then
    echo "   ❌ NAS has suspiciously few memories ($COUNT). ABORTING."
    exit 1
fi

echo ""
echo "🧹 This will:"
echo "   1. Stop local Qdrant container"
echo "   2. Remove local Qdrant container"
echo "   3. Remove the launchd auto-start agent"
echo "   (Docker volumes NOT removed — run 'docker volume rm qdrant_data' manually if desired)"
echo ""
read -p "Are you sure? (y/N) " confirm
[ "$confirm" = "y" ] || exit 0

echo ""
echo "🛑 Stopping local Qdrant..."
docker stop qdrant 2>/dev/null && echo "   ✅ Stopped" || echo "   (wasn't running)"
docker rm qdrant 2>/dev/null && echo "   ✅ Removed" || echo "   (already removed)"

echo ""
echo "🗑️  Removing launchd auto-start..."
PLIST="$HOME/Library/LaunchAgents/com.openmemory.qdrant.plist"
if [ -f "$PLIST" ]; then
    launchctl unload "$PLIST" 2>/dev/null || true
    rm "$PLIST"
    echo "   ✅ Removed $PLIST"
else
    echo "   (not found, skipping)"
fi

echo ""
echo "════════════════════════════════════════"
echo "✅ Cleanup complete!"
echo ""
echo "   To reclaim ~1.4GB disk space:"
echo "   docker volume rm qdrant_data openmemory-local_qdrant_data"
echo "════════════════════════════════════════"
