from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree import ElementTree

import httpx

from finance_demo.seed import SEED_POSTS


class GdeltFinanceSource:
    """Credential-free finance-news collection through GDELT DOC 2.0."""

    endpoint = "https://api.gdeltproject.org/api/v2/doc/doc"

    async def search(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        limit = min(int(query.get("limit", 25)), 50)
        if os.getenv("FLOW_SOCIAL_MODE") == "seed":
            return []
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.get(
                    self.endpoint,
                    params={
                        "query": query.get(
                            "text",
                            '(stocks OR earnings OR markets OR inflation) sourcelang:english',
                        ),
                        "mode": "artlist",
                        "format": "json",
                        "maxrecords": limit,
                        "timespan": query.get("timespan", "24h"),
                        "sort": "datedesc",
                    },
                )
                response.raise_for_status()
                articles = response.json().get("articles", [])
                if articles:
                    return [self._normalize(article) for article in articles]
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            pass
        return await self._google_news_fallback(query, limit)

    async def _google_news_fallback(
        self, query: dict[str, Any], limit: int
    ) -> list[dict[str, Any]]:
        try:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                response = await client.get(
                    "https://news.google.com/rss/search",
                    params={
                        "q": query.get("fallback_text", "stocks OR earnings OR markets when:1d"),
                        "hl": "en-US",
                        "gl": "US",
                        "ceid": "US:en",
                    },
                )
                response.raise_for_status()
            root = ElementTree.fromstring(response.content)
            return [
                self._normalize_rss(item)
                for item in root.findall("./channel/item")[:limit]
            ]
        except (httpx.HTTPError, ElementTree.ParseError, TypeError, ValueError):
            return []

    @staticmethod
    def _normalize(article: dict[str, Any]) -> dict[str, Any]:
        url = article["url"]
        seen_date = article.get("seendate", "")
        try:
            created = datetime.strptime(seen_date, "%Y%m%dT%H%M%SZ").replace(
                tzinfo=UTC
            ).timestamp()
        except ValueError:
            created = datetime.now(UTC).timestamp()
        return {
            "id": f"gdelt-{hashlib.sha256(url.encode()).hexdigest()[:16]}",
            "subreddit": "gdelt-news",
            "title": article.get("title") or "Untitled finance article",
            "body": (
                f"Source: {article.get('domain', 'unknown')}. "
                f"Language: {article.get('language', 'unknown')}."
            ),
            "author": article.get("domain"),
            "score": 0,
            "created_utc": created,
            "url": url,
            "collection_mode": "gdelt-doc-2-api",
        }

    @staticmethod
    def _normalize_rss(item: ElementTree.Element) -> dict[str, Any]:
        title = item.findtext("title") or "Untitled finance article"
        url = item.findtext("link") or ""
        source = item.findtext("source") or "Google News"
        published = parsedate_to_datetime(item.findtext("pubDate") or "").timestamp()
        return {
            "id": f"news-{hashlib.sha256(url.encode()).hexdigest()[:16]}",
            "subreddit": "finance-news",
            "title": title,
            "body": f"Publisher: {source}.",
            "author": source,
            "score": 0,
            "created_utc": published,
            "url": url,
            "collection_mode": "google-news-rss-fallback",
        }

    async def get(self, identifier: str) -> dict[str, Any] | None:
        records = await self.search({"text": identifier, "limit": 50})
        return next((record for record in records if record["id"] == identifier), None)

    async def delta(self, cursor: str | None = None) -> dict[str, Any]:
        records = await self.search({})
        since = float(cursor or 0)
        selected = [record for record in records if record["created_utc"] > since]
        next_cursor = str(max((row["created_utc"] for row in records), default=since))
        return {"records": selected, "cursor": next_cursor}
