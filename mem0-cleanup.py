#!/usr/bin/env python3
"""
Mem0 Memory Cleanup Script
Scans Qdrant for low-value memories and deletes them.
Run periodically via cron to keep memory store clean.
"""

import json
import os
import re
import sys
from datetime import datetime
import requests

QDRANT_URL = "http://localhost:6333"
COLLECTION = "memories"
BACKUP_DIR = os.path.expanduser("~/.openclaw/workspace/memory/mem0-backups")

# Patterns that indicate junk memories (case-insensitive regex)
JUNK_PATTERNS = [
    # Timestamps and dates stored as facts
    r"^the current (date|time|timestamp)",
    r"^\d{4}-\d{2}-\d{2}",
    r"^(compiled|noted|recorded|sent|message was sent) on",
    r"current time is",
    r"timestamp (noted|is|was)",
    
    # Heartbeat/system noise
    r"HEARTBEAT_OK",
    r"heartbeat (status|was|returned)",
    r"nothing needs attention",
    r"inbox (is |was )?clean",
    r"/tmp (directory )?(is |was )?clean",
    
    # Message metadata
    r"^the (sender|message|conversation)",
    r"sender (id|of|is|was)",
    r"message_id",
    r"untrusted metadata",
    r"sender.*username.*k4myk4z3",
    r"kamikaze.*sent a message",
    r"kamikaze.*username",
    r"^\[reply_to",
    
    # Transient observations
    r"plastic sheet(ing)?",
    r"wainscoting",
    r"poly sheeting",
    r"blue tape seal",
    r"containment (area|zone)",
    r"negative (air )?pressure",
    r"HEPA (vacuum|filter|air)",
    
    # Generic/useless
    r"^the (file|command|instruction|process|result|statement|scheduling)",
    r"^a (request|partial|performance|total|reminder|requirement|negative)",
    r"^an (additional|exec|alternative)",
    r"^it is tax season",
    r"^(run|deployment on|make) ",
    r"email was categorized as",
    r"signal(s)? openness",
    r"financial hardship has been reframed",
    r"oil surge",
    r"^the repo will use",
    r"^there will be",
    r"^the UI will",
    r"^compiled on",
    r"^the.*endpoint",
    r"docker(file)? has",
    r"retrospective agent",
    r"todo sync",
    r"task sync",
    
    # Conversation flow stored as memory
    r"kamikaze (asked|inquired|proposed|confirmed|expressed|was informed|was advised|mentioned|was told)",
    r"neo (highlighted|responded|is also part)",
    r"the sender (expressed|mentions|has no|cannot)",
    r"raki5216",
    
    # Duplicates of workspace files (huge multi-line blocks)
    r"^## (Access|Greenlight|Pending Morpheus|Entry Conditions|Paper Trading|Todo Sync|Task Sync|Media Server|Pranav\n|Abhinaya\n|Calendar|Context Bloat|Lessons Learned)",
    r"^# 2026-\d{2}-\d{2}",
    r"^# Calendar",
    
    # Transient project status / task snapshots
    r"tests are passing",
    r"ready to deploy",
    r"tasks? (that )?(should|need to) be updated",
    r"completed tasks today",
    r"room trash every",
    r"receipt should be",
    r"feeling good.*awake.*grateful",
    r"supports defense in depth",
    r"user is using scopes",
    r"perplexity (API|\$)",
    r"NAS.*specified to include",
    r"fixed config for",
    r"pranav-todo channel had",
    r"^(strike|delta).*(ATM|near|range|filter)",
    
    # Stale/one-time observations
    r"^(away automation|there is a media file)",
    r"correct duct type",
    r"strongest evidence",
    r"breach of contract claim",
    r"history of complaints",
    r"CSLB complaint is free",
    r"irbis hvac",
    r"flex vs alumaflex",
    r"wrong (material|duct)",
]

# Compile patterns
compiled = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in JUNK_PATTERNS]


def get_all_points():
    """Scroll through all points in the collection."""
    points = []
    offset = None
    while True:
        body = {"limit": 100, "with_payload": True}
        if offset:
            body["offset"] = offset
        resp = requests.post(f"{QDRANT_URL}/collections/{COLLECTION}/points/scroll", json=body)
        data = resp.json()
        batch = data["result"]["points"]
        points.extend(batch)
        offset = data["result"].get("next_page_offset")
        if not offset or not batch:
            break
    return points


def is_junk(text: str) -> bool:
    """Check if a memory text matches any junk pattern."""
    for pattern in compiled:
        if pattern.search(text):
            return True
    
    # Length-based heuristics
    if len(text) > 500:  # Very long memories are usually bulk dumps
        if text.count("\n") > 5:  # Multi-line blocks
            return True
    
    if len(text) < 20:  # Too short to be useful
        return True
    
    return False


def main():
    dry_run = "--dry-run" in sys.argv
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    
    print(f"Scanning Qdrant collection '{COLLECTION}'...")
    points = get_all_points()
    print(f"Found {len(points)} total memories")
    
    junk_ids = []
    kept = 0
    
    for point in points:
        payload = point.get("payload", {})
        # Mem0 stores the text in 'data' or 'memory' field
        text = payload.get("data", "") or payload.get("memory", "") or ""
        
        if is_junk(text):
            junk_ids.append(point["id"])
            if verbose:
                preview = text[:100].replace("\n", " ")
                print(f"  JUNK: {preview}...")
        else:
            kept += 1
            if verbose and "-vv" in sys.argv:
                preview = text[:100].replace("\n", " ")
                print(f"  KEEP: {preview}...")
    
    print(f"\nResults: {len(junk_ids)} junk, {kept} kept")
    
    if dry_run:
        print("DRY RUN — no deletions performed")
        return
    
    if not junk_ids:
        print("Nothing to delete!")
        return
    
    # Backup deleted memories before removing
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    backup_file = os.path.join(BACKUP_DIR, f"deleted_{timestamp}.jsonl")
    
    backed_up = 0
    with open(backup_file, "w") as f:
        for point in points:
            if point["id"] in junk_ids:
                payload = point.get("payload", {})
                text = payload.get("data", "") or payload.get("memory", "") or ""
                record = {
                    "id": point["id"],
                    "text": text,
                    "metadata": {k: v for k, v in payload.items() if k not in ("data", "memory")},
                }
                f.write(json.dumps(record) + "\n")
                backed_up += 1
    
    print(f"Backed up {backed_up} memories to {backup_file}")
    
    # Convert junk_ids to a set for O(1) lookup (it was already a list of IDs, not point dicts)
    junk_id_set = set(junk_ids)
    
    # Delete in batches of 100
    deleted = 0
    for i in range(0, len(junk_ids), 100):
        batch = junk_ids[i:i+100]
        resp = requests.post(
            f"{QDRANT_URL}/collections/{COLLECTION}/points/delete",
            json={"points": batch}
        )
        if resp.status_code == 200:
            deleted += len(batch)
            print(f"  Deleted batch {i//100 + 1}: {len(batch)} points")
        else:
            print(f"  ERROR deleting batch: {resp.text}")
    
    print(f"\nDone! Deleted {deleted} junk memories. {kept} remaining.")


if __name__ == "__main__":
    main()
