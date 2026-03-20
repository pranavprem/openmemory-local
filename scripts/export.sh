#!/bin/bash
# Export local Qdrant data and SCP snapshot to NAS.
# Run this on the Mac mini. One command does everything.
#
# Usage: ./scripts/export.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
source "$PROJECT_DIR/.env"

EXPORT_DIR="/tmp/qdrant-export"
LOCAL_QDRANT="http://localhost:${QDRANT_PORT:-6333}"
NAS_TARGET="${NAS_USER}@${NAS_IP}"
COLLECTION="memories"

echo "🔄 Step 1: Creating Qdrant snapshot..."
mkdir -p "$EXPORT_DIR"

RESPONSE=$(curl -s -X POST "$LOCAL_QDRANT/collections/$COLLECTION/snapshots")
SNAPSHOT_NAME=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['name'])" 2>/dev/null)

if [ -z "$SNAPSHOT_NAME" ]; then
    echo "❌ Failed to create snapshot. Is local Qdrant running?"
    echo "   Response: $RESPONSE"
    exit 1
fi

echo "📥 Step 2: Downloading snapshot: $SNAPSHOT_NAME"
curl -s -o "$EXPORT_DIR/${COLLECTION}.snapshot" \
    "$LOCAL_QDRANT/collections/$COLLECTION/snapshots/$SNAPSHOT_NAME"

COUNT=$(curl -s "$LOCAL_QDRANT/collections/$COLLECTION" | python3 -c "import sys,json; print(json.load(sys.stdin)['result']['points_count'])")
echo "   ✅ $COUNT points exported"

# Cleanup snapshot from local Qdrant
curl -s -X DELETE "$LOCAL_QDRANT/collections/$COLLECTION/snapshots/$SNAPSHOT_NAME" > /dev/null

SIZE=$(du -sh "$EXPORT_DIR/${COLLECTION}.snapshot" | cut -f1)
echo ""
echo "📤 Step 3: Uploading snapshot to NAS ($SIZE)..."
ssh "$NAS_TARGET" "mkdir -p /tmp/qdrant-export"
scp "$EXPORT_DIR/${COLLECTION}.snapshot" "$NAS_TARGET:/tmp/qdrant-export/"

echo ""
echo "════════════════════════════════════════"
echo "✅ Export complete!"
echo "   $COUNT points → $NAS_TARGET:/tmp/qdrant-export/"
echo ""
echo "Now SSH to the NAS and run:"
echo "   cd ${NAS_DEPLOY_DIR} && make setup"
echo "════════════════════════════════════════"
