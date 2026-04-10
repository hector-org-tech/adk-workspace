import os
import httpx
from datetime import datetime, timedelta, timezone
from app.schemas.signal import Signal


STACKEXCHANGE_API = "https://api.stackexchange.com/2.3/search/advanced"


async def search_stackexchange(
    keywords: list[str],
    tags: list[str],
    lookback_days: int,
    max_results_per_query: int,
    min_score: int = 0,
) -> list[Signal]:
    api_key = os.environ["STACKEXCHANGE_API_KEY"]
    fromdate = int((datetime.now(timezone.utc) - timedelta(days=lookback_days)).timestamp())

    results: list[Signal] = []

    async with httpx.AsyncClient(timeout=30) as client:
        for kw in keywords:
            resp = await client.get(
                STACKEXCHANGE_API,
                params={
                    "site": "stackoverflow",
                    "q": kw,
                    "fromdate": fromdate,
                    "pagesize": max_results_per_query,
                    "order": "desc",
                    "sort": "activity",
                    "key": api_key,
                    "tagged": ";".join(tags) if tags else None,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("items", []):
                score = item.get("score", 0)
                if score < min_score:
                    continue

                results.append(
                    Signal(
                        source="stackexchange",
                        external_id=str(item["question_id"]),
                        title=item["title"],
                        url=item["link"],
                        author=(item.get("owner") or {}).get("display_name"),
                        created_at=datetime.fromtimestamp(item["creation_date"], tz=timezone.utc),
                        tags=item.get("tags", []),
                        raw_text=item.get("title", ""),
                        engagement_score=float(score + item.get("answer_count", 0)),
                        metadata={
                            "view_count": item.get("view_count", 0),
                            "is_answered": item.get("is_answered", False),
                            "answer_count": item.get("answer_count", 0),
                        },
                    )
                )

    return results