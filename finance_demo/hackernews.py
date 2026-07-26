from __future__ import annotations

import os
from typing import Any

import httpx

from finance_demo.seed import SEED_POSTS


class HackerNewsFinanceSource:
    """Credential-free Hacker News search with a resilient seed fallback."""

    endpoint = "https://hn.algolia.com/api/v1/search_by_date"

    async def search(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        search_query = query.get("text", "markets finance stocks earnings")
        limit = min(int(query.get("limit", 25)), 50)
        if os.getenv("FLOW_SOCIAL_MODE") == "seed":
            return [dict(post, collection_mode="seed") for post in SEED_POSTS[:limit]]
        try:
            async with httpx.AsyncClient(timeout=20) as client:
                response = await client.get(
                    self.endpoint,
                    params={
                        "query": search_query,
                        "tags": "story",
                        "hitsPerPage": limit,
                    },
                )
                response.raise_for_status()
                posts = [self._normalize(post) for post in response.json()["hits"]]
                if posts:
                    return posts
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            pass
        return [dict(post, collection_mode="seed-fallback") for post in SEED_POSTS[:limit]]

    @staticmethod
    def _normalize(post: dict[str, Any]) -> dict[str, Any]:
        post_id = post["objectID"]
        title = post.get("title") or "Untitled discussion"
        body = post.get("story_text") or ""
        return {
            "id": post_id,
            "subreddit": "hacker-news",
            "title": title,
            "body": body,
            "author": post.get("author"),
            "score": post.get("points") or 0,
            "created_utc": post["created_at_i"],
            "url": f"https://news.ycombinator.com/item?id={post_id}",
            "collection_mode": "hacker-news-algolia-api",
        }

    async def get(self, identifier: str) -> dict[str, Any] | None:
        posts = await self.search({"text": identifier})
        return next((post for post in posts if post["id"] == identifier), None)

    async def delta(self, cursor: str | None = None) -> dict[str, Any]:
        posts = await self.search({})
        since = float(cursor or 0)
        records = [post for post in posts if post["created_utc"] > since]
        next_cursor = str(max((post["created_utc"] for post in posts), default=since))
        return {"records": records, "cursor": next_cursor}
