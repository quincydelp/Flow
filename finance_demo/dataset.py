from __future__ import annotations

import json
import os
import sqlite3
from collections import Counter
from datetime import UTC, datetime
from math import log1p
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
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS sentiment_indices (
            bucket TEXT NOT NULL,
            dimension TEXT NOT NULL,
            value TEXT NOT NULL,
            sentiment_index REAL NOT NULL,
            breadth REAL NOT NULL,
            confidence REAL NOT NULL,
            observations INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (bucket, dimension, value)
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


def merge_records(collections: list[list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Deterministically de-duplicate records from several collection sources."""
    merged: dict[str, dict[str, Any]] = {}
    for collection in collections:
        for record in collection:
            merged[record["id"]] = record
    return sorted(merged.values(), key=lambda row: row["created_utc"], reverse=True)


def build_sentiment_indices(
    rows: list[dict[str, Any]], raw_records: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    """Build confidence/attention-weighted daily topic and ticker indices."""
    if raw_records:
        raw_by_id = {record["id"]: record for record in raw_records}
        rows = [{**raw_by_id[row["post_id"]], **row} for row in rows]
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        bucket = datetime.fromtimestamp(row["created_utc"], UTC).date().isoformat()
        dimensions = [("topic", row["topic"])]
        if row.get("ticker"):
            dimensions.append(("ticker", row["ticker"]))
        for dimension, value in dimensions:
            groups.setdefault((bucket, dimension, value), []).append(row)

    indexed = []
    updated_at = datetime.now(UTC).isoformat()
    with connect() as connection:
        for (bucket, dimension, value), observations in sorted(groups.items()):
            weights = [
                max(float(row["confidence"]), 0.05) * (1 + log1p(max(row.get("score", 0), 0)))
                for row in observations
            ]
            weight_sum = sum(weights)
            sentiment_index = sum(
                float(row["sentiment_score"]) * weight
                for row, weight in zip(observations, weights, strict=True)
            ) / weight_sum
            bullish = sum(row["sentiment"] == "bullish" for row in observations)
            bearish = sum(row["sentiment"] == "bearish" for row in observations)
            breadth = (bullish - bearish) / len(observations)
            confidence = sum(float(row["confidence"]) for row in observations) / len(observations)
            index_row = {
                "bucket": bucket,
                "dimension": dimension,
                "value": value,
                "sentiment_index": round(sentiment_index, 4),
                "breadth": round(breadth, 4),
                "confidence": round(confidence, 4),
                "observations": len(observations),
                "updated_at": updated_at,
            }
            indexed.append(index_row)
            connection.execute(
                """
                INSERT INTO sentiment_indices VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(bucket, dimension, value) DO UPDATE SET
                  sentiment_index=excluded.sentiment_index,
                  breadth=excluded.breadth,
                  confidence=excluded.confidence,
                  observations=excluded.observations,
                  updated_at=excluded.updated_at
                """,
                tuple(index_row.values()),
            )
    return {"indices_written": len(indexed), "indices": indexed, "database": str(database_path())}


def list_sentiment_indices(limit: int = 100) -> list[dict[str, Any]]:
    with connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                """
                SELECT * FROM sentiment_indices
                ORDER BY bucket DESC, observations DESC, dimension, value
                LIMIT ?
                """,
                (limit,),
            )
        ]


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
