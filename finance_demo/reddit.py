from __future__ import annotations

import os
import time
from typing import Any

import httpx

from finance_demo.seed import SEED_POSTS


class RedditFinanceSource:
    """Deterministic Reddit collector with an offline seed fallback."""

    def __init__(self) -> None:
        self.client_id = os.getenv("REDDIT_CLIENT_ID")
        self.client_secret = os.getenv("REDDIT_CLIENT_SECRET")
        self.user_agent = os.getenv(
            "REDDIT_USER_AGENT",
            "desktop:flow-finance-demo:v0.1 (by /u/your_username)",
        )

    async def search(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        subreddits = query.get("subreddits", ["stocks", "investing", "SecurityAnalysis"])
        limit = min(int(query.get("limit", 25)), 100)
        if not self.client_id or not self.client_secret:
            return [dict(post, collection_mode="seed") for post in SEED_POSTS[:limit]]

        token = await self._token()
        headers = {"Authorization": f"Bearer {token}", "User-Agent": self.user_agent}
        posts: list[dict[str, Any]] = []
        async with httpx.AsyncClient(timeout=20, headers=headers) as client:
            for subreddit in subreddits:
                response = await client.get(
                    f"https://oauth.reddit.com/r/{subreddit}/new",
                    params={"limit": limit, "raw_json": 1},
                )
                response.raise_for_status()
                for child in response.json()["data"]["children"]:
                    data = child["data"]
                    posts.append(
                        {
                            "id": data["id"],
                            "subreddit": data["subreddit"],
                            "title": data["title"],
                            "body": data.get("selftext", ""),
                            "author": data.get("author"),
                            "score": data.get("score", 0),
                            "created_utc": data["created_utc"],
                            "url": f"https://reddit.com{data['permalink']}",
                            "collection_mode": "reddit-oauth",
                        }
                    )
        posts.sort(key=lambda post: post["created_utc"], reverse=True)
        return posts[:limit]

    async def _token(self) -> str:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                "https://www.reddit.com/api/v1/access_token",
                data={"grant_type": "client_credentials"},
                auth=(self.client_id, self.client_secret),
                headers={"User-Agent": self.user_agent},
            )
            response.raise_for_status()
            return response.json()["access_token"]

    async def get(self, identifier: str) -> dict[str, Any] | None:
        return next((post for post in SEED_POSTS if post["id"] == identifier), None)

    async def delta(self, cursor: str | None = None) -> dict[str, Any]:
        posts = await self.search({})
        since = float(cursor or 0)
        records = [post for post in posts if post["created_utc"] > since]
        next_cursor = str(max((post["created_utc"] for post in posts), default=time.time()))
        return {"records": records, "cursor": next_cursor}

