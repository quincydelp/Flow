from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EnrichedPost(BaseModel):
    post_id: str
    ticker: str | None = None
    topic: Literal[
        "earnings",
        "macro",
        "mergers",
        "regulation",
        "product",
        "market-structure",
        "other",
    ]
    sentiment: Literal["bullish", "bearish", "neutral", "mixed"]
    sentiment_score: float = Field(ge=-1, le=1)
    confidence: float = Field(ge=0, le=1)
    rationale: str
    claims: list[str] = Field(default_factory=list)


class GroundedBrief(BaseModel):
    answer: str
    cited_post_ids: list[str]
    caveats: list[str] = Field(default_factory=list)

