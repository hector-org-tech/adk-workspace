"""ADK-compatible tool functions for the signal analysis pipeline.

Each function takes simple string arguments (LLM-friendly) and returns
a JSON string result.
"""

import json
import logging
import re
from datetime import datetime, timezone

from app.schemas.signal import Signal
from app.schemas.config import SearchProfile, GithubConfig, StackExchangeConfig, OutputConfig
from app.agents.signal_scout_agent import SignalScoutAgent
from app.agents.cluster_rank_agent import ClusterRankAgent

logger = logging.getLogger(__name__)


def _extract_json(text: str):
    """Best-effort extraction of a JSON object or array from LLM output.

    Handles: raw JSON, markdown fenced blocks, trailing prose after the JSON.
    """
    text = text.strip()

    fenced = re.search(r"```(?:json)?\s*\n?([\s\S]*?)```", text)
    if fenced:
        text = fenced.group(1).strip()

    for start_char, end_char in [("{", "}"), ("[", "]")]:
        idx = text.find(start_char)
        if idx == -1:
            continue
        depth = 0
        in_string = False
        escape = False
        for i in range(idx, len(text)):
            c = text[i]
            if escape:
                escape = False
                continue
            if c == "\\":
                escape = True
                continue
            if c == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if c == start_char:
                depth += 1
            elif c == end_char:
                depth -= 1
                if depth == 0:
                    return json.loads(text[idx : i + 1])

    return json.loads(text)


async def search_developer_signals(topic: str, additional_keywords: str = "") -> str:
    """Search GitHub Issues and Stack Overflow for developer signals about a technology topic.

    Args:
        topic: The main technology topic to search for (e.g. "BigQuery migration", "Vertex AI agents").
        additional_keywords: Optional comma-separated extra keywords to broaden the search.

    Returns:
        A JSON summary of discovered signals including titles, sources, URLs, and engagement scores.
    """
    keywords = [topic]
    if additional_keywords:
        keywords.extend([k.strip() for k in additional_keywords.split(",") if k.strip()])

    profile = SearchProfile(
        profile_id="dynamic",
        keywords=keywords,
        keyword_groups=[],
        github=GithubConfig(lookback_days=14, max_results_per_query=15, min_stars=0),
        stackexchange=StackExchangeConfig(
            lookback_days=14, max_results_per_query=15, min_score=0, tags=[]
        ),
        output=OutputConfig(max_clusters=5, max_briefs=3),
    )

    scout = SignalScoutAgent()
    signals = await scout.run(profile)

    if not signals:
        return json.dumps({"status": "no_signals", "count": 0, "signals": []})

    return json.dumps(
        {
            "status": "ok",
            "count": len(signals),
            "signals": [
                {
                    "source": s.source,
                    "title": s.title,
                    "url": s.url,
                    "author": s.author,
                    "tags": s.tags,
                    "engagement_score": s.engagement_score,
                    "created_at": s.created_at.isoformat(),
                }
                for s in signals
            ],
        },
        default=str,
    )


def cluster_and_rank_signals(signals_json: str) -> str:
    """Group raw developer signals into topic clusters and rank them by priority.

    Args:
        signals_json: JSON string containing the signals array.

    Returns:
        A JSON summary of ranked clusters with topic, scores, and member signal count.
    """
    try:
        data = _extract_json(signals_json)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Failed to parse signals JSON: %s", e)
        return json.dumps({"status": "parse_error", "count": 0, "clusters": []})

    if isinstance(data, list):
        raw_signals = data
    elif isinstance(data, dict):
        raw_signals = data.get("signals", data.get("items", []))
    else:
        raw_signals = []

    if not raw_signals:
        return json.dumps({"status": "no_clusters", "count": 0, "clusters": []})

    signals = []
    for s in raw_signals:
        if not isinstance(s, dict):
            continue
        try:
            created = s.get("created_at", datetime.now(timezone.utc).isoformat())
            if isinstance(created, str):
                created = datetime.fromisoformat(created)

            signals.append(
                Signal(
                    source=s.get("source", "unknown"),
                    external_id=s.get("external_id", s.get("url", s.get("id", ""))),
                    title=s.get("title", "Untitled"),
                    url=s.get("url", s.get("html_url", "")),
                    author=s.get("author"),
                    created_at=created,
                    tags=s.get("tags", []),
                    raw_text=s.get("raw_text", s.get("title", "")),
                    engagement_score=float(s.get("engagement_score", 0.0)),
                )
            )
        except Exception as e:
            logger.warning("Skipping malformed signal entry: %s", e)
            continue

    ranker = ClusterRankAgent()
    clusters = ranker.run(signals)

    return json.dumps(
        {
            "status": "ok",
            "count": len(clusters),
            "clusters": [
                {
                    "cluster_id": c.cluster_id,
                    "topic": c.topic,
                    "summary": c.summary,
                    "member_count": len(c.member_signal_ids),
                    "priority_score": round(c.priority_score, 2),
                    "engagement_score": round(c.engagement_score, 2),
                    "recency_score": round(c.recency_score, 2),
                    "relevance_score": round(c.relevance_score, 2),
                    "commercial_fit_score": round(c.commercial_fit_score, 2),
                }
                for c in clusters[:10]
            ],
        }
    )
