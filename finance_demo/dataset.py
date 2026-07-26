from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any


def database_path() -> Path:
    root = Path(os.getenv("FLOW_DATA_DIR", ".flow/finance"))
    root.mkdir(parents=True, exist_ok=True)
    return root / "signals.db"


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(database_path())
    connection.row_factory = sqlite3.Row
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS signals (
            post_id TEXT PRIMARY KEY,
            subreddit TEXT,
            title TEXT,
            body TEXT,
            url TEXT,
            score INTEGER,
            created_utc REAL,
            ticker TEXT,
            topic TEXT NOT NULL,
            sentiment TEXT NOT NULL,
            sentiment_score REAL NOT NULL,
            confidence REAL NOT NULL,
            rationale TEXT,
            claims_json TEXT NOT NULL
        )
        """
    )
    return connection


def upsert_signals(
    raw_posts: list[dict[str, Any]], enrichments: list[dict[str, Any]]
) -> dict[str, Any]:
    raw_by_id = {post["id"]: post for post in raw_posts}
    with connect() as connection:
        for enriched in enrichments:
            post = raw_by_id[enriched["post_id"]]
            connection.execute(
                """
                INSERT INTO signals VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(post_id) DO UPDATE SET
                  ticker=excluded.ticker, topic=excluded.topic,
                  sentiment=excluded.sentiment, sentiment_score=excluded.sentiment_score,
                  confidence=excluded.confidence, rationale=excluded.rationale,
                  claims_json=excluded.claims_json
                """,
                (
                    post["id"],
                    post["subreddit"],
                    post["title"],
                    post.get("body", ""),
                    post["url"],
                    post.get("score", 0),
                    post["created_utc"],
                    enriched.get("ticker"),
                    enriched["topic"],
                    enriched["sentiment"],
                    enriched["sentiment_score"],
                    enriched["confidence"],
                    enriched["rationale"],
                    json.dumps(enriched.get("claims", [])),
                ),
            )
    return {"rows_written": len(enrichments), "database": str(database_path())}


def dataset_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "rows": len(rows),
        "topics": dict(Counter(row["topic"] for row in rows)),
        "sentiment": dict(Counter(row["sentiment"] for row in rows)),
        "tickers": dict(Counter(row["ticker"] for row in rows if row.get("ticker"))),
    }


def search_signals(query: str, limit: int = 8) -> dict[str, Any]:
    terms = [term.lower() for term in query.split() if len(term) > 2]
    with connect() as connection:
        rows = [dict(row) for row in connection.execute("SELECT * FROM signals")]
    scored = []
    for row in rows:
        haystack = " ".join(str(value) for value in row.values()).lower()
        score = sum(term in haystack for term in terms)
        if score:
            scored.append((score, row))
    scored.sort(key=lambda item: (item[0], item[1]["created_utc"]), reverse=True)
    selected = [row for _, row in scored[:limit]]
    return {"query": query, "rows": selected, "retrieval": "deterministic lexical match"}
