from __future__ import annotations

import ast
import json
import os
import re
from dataclasses import dataclass
from typing import Any

from finance_demo.models import EnrichedPost, GroundedBrief


@dataclass
class AgentResult:
    output: Any


class StructuredAgent:
    def __init__(self, output_type: type, instructions: str) -> None:
        self.output_type = output_type
        self.instructions = instructions
        self._agent = None
        if os.getenv("OPENAI_API_KEY"):
            from pydantic_ai import Agent

            self._agent = Agent(
                os.getenv("FLOW_MODEL", "openai:gpt-5-mini"),
                output_type=output_type,
                instructions=instructions,
            )

    async def run(self, prompt: str, **_: Any) -> Any:
        if self._agent:
            return await self._agent.run(prompt)
        return AgentResult(output=self.mock(prompt))

    def mock(self, prompt: str) -> Any:
        raise NotImplementedError


class EnrichmentAgent(StructuredAgent):
    def __init__(self) -> None:
        super().__init__(
            EnrichedPost,
            "Create a finance research dataset row from one social post. Separate claims from "
            "facts, avoid investment advice, and return calibrated sentiment and confidence.",
        )

    def mock(self, prompt: str) -> EnrichedPost:
        post = _json_from_prompt(prompt)
        text = f"{post.get('title', '')} {post.get('body', '')}".lower()
        symbols = ["NVDA", "TSLA", "AAPL", "MSFT", "META"]
        ticker = next(
            (symbol for symbol in symbols if symbol.lower() in text),
            None,
        )
        bullish = ["tight capacity", "positive", "stabilizing", "support", "growth"]
        bearish = ["pressure", "risk", "weak", "inflation", "restrictive"]
        score = sum(term in text for term in bullish) - sum(term in text for term in bearish)
        sentiment = "bullish" if score > 0 else "bearish" if score < 0 else "neutral"
        topic = (
            "macro"
            if any(term in text for term in ["inflation", "rate", "fed"])
            else "earnings"
            if any(term in text for term in ["margin", "quarter", "filing"])
            else "market-structure"
        )
        return EnrichedPost(
            post_id=post["id"],
            ticker=ticker,
            topic=topic,
            sentiment=sentiment,
            sentiment_score=max(-1, min(1, score / 2)),
            confidence=0.62,
            rationale=(
                "Deterministic demo classification; configure OPENAI_API_KEY for agent output."
            ),
            claims=[post.get("title", "")],
        )


class BriefingAgent(StructuredAgent):
    def __init__(self) -> None:
        super().__init__(
            GroundedBrief,
            "Answer only from the supplied retrieved dataset rows. Cite post IDs in the answer, "
            "state uncertainty, and never present social sentiment as verified financial fact.",
        )

    def mock(self, prompt: str) -> GroundedBrief:
        context = _json_from_prompt(prompt)
        rows = context.get("rows", [])
        ids = [row["post_id"] for row in rows]
        summary = "; ".join(
            f"{row.get('ticker') or row.get('topic')}: {row['sentiment']} "
            f"({row['post_id']})"
            for row in rows[:5]
        )
        return GroundedBrief(
            answer=f"Retrieved social-finance signals: {summary or 'no matching records'}.",
            cited_post_ids=ids[:5],
            caveats=["Social posts are unverified and are not investment advice."],
        )


def _json_from_prompt(prompt: str) -> dict[str, Any]:
    match = re.search(r"<context>(.*)</context>", prompt, re.DOTALL)
    if not match:
        match = re.search(r"<post>(.*)</post>", prompt, re.DOTALL)
    if not match:
        return {}
    payload = match.group(1)
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return ast.literal_eval(payload)
