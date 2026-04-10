import os
import httpx
from datetime import datetime, timedelta, timezone
from app.schemas.signal import Signal


GITHUB_API = "https://api.github.com/search/issues"


def build_github_queries(keywords: list[str], keyword_groups: list[list[str]]) -> list[str]:
    queries = []

    for kw in keywords:
        queries.append(f'"{kw}" is:issue')

    for group in keyword_groups:
        joined = " ".join(f'"{x}"' for x in group)
        queries.append(f"{joined} is:issue")

    return queries


async def search_github(
    keywords: list[str],
    keyword_groups: list[list[str]],
    lookback_days: int,
    max_results_per_query: int,
    min_stars: int = 0,
) -> list[Signal]:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        return []

    since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).date().isoformat()

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }

    results: list[Signal] = []
    queries = build_github_queries(keywords, keyword_groups)

    async with httpx.AsyncClient(timeout=30) as client:
        for q in queries:
            full_q = f"{q} updated:>={since}"
            resp = await client.get(
                GITHUB_API,
                headers=headers,
                params={
                    "q": full_q,
                    "sort": "updated",
                    "order": "desc",
                    "per_page": max_results_per_query,
                },
            )
            resp.raise_for_status()
            data = resp.json()

            for item in data.get("items", []):
                labels = [x["name"] for x in item.get("labels", [])]
                results.append(
                    Signal(
                        source="github",
                        external_id=str(item["id"]),
                        title=item["title"],
                        url=item["html_url"],
                        author=(item.get("user") or {}).get("login"),
                        created_at=datetime.fromisoformat(
                            item["created_at"].replace("Z", "+00:00")
                        ),
                        tags=labels,
                        raw_text=item.get("body") or "",
                        engagement_score=float(item.get("comments", 0)),
                        metadata={
                            "state": item.get("state"),
                            "updated_at": item.get("updated_at"),
                            "score": item.get("score"),
                        },
                    )
                )

    return results
