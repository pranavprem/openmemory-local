"""
Qdrant search proxy — accepts a text query, embeds via Ollama, searches Qdrant.
Runs as a tiny Flask app inside Docker. Solves CORS issues with browser dashboards.

POST /search  { "query": "water bill", "collection": "memories", "limit": 10 }
GET  /health
"""

import os
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

QDRANT_URL = os.environ.get("QDRANT_URL", "http://10.0.0.116:6333")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "bge-m3")
PORT = int(os.environ.get("PORT", "6380"))


def embed(text: str) -> list:
    resp = requests.post(
        f"{OLLAMA_URL}/api/embed",
        json={"model": EMBEDDING_MODEL, "input": text},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"][0]


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/search", methods=["POST"])
def search():
    data = request.json or {}
    query = data.get("query", "")
    collection = data.get("collection", "memories")
    limit = data.get("limit", 10)

    if not query:
        return jsonify({"error": "query is required"}), 400

    try:
        vector = embed(query)
    except Exception as e:
        return jsonify({"error": f"Embedding failed: {str(e)}"}), 502

    try:
        resp = requests.post(
            f"{QDRANT_URL}/collections/{collection}/points/search",
            json={"vector": vector, "limit": limit, "with_payload": True},
            timeout=10,
        )
        resp.raise_for_status()
        results = resp.json().get("result", [])
    except Exception as e:
        return jsonify({"error": f"Qdrant search failed: {str(e)}"}), 502

    formatted = []
    for r in results:
        payload = r.get("payload", {})
        formatted.append({
            "score": r.get("score", 0),
            "text": payload.get("data", payload.get("memory", payload.get("text", ""))),
            "metadata": {k: v for k, v in payload.items() if k not in ("data", "memory", "text")},
        })

    return jsonify({"results": formatted, "count": len(formatted)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
