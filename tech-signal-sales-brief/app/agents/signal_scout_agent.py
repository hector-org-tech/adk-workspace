import asyncio
from app.schemas.signal import Signal
from app.schemas.config import SearchProfile
from app.tools.github_tool import search_github
from app.tools.stackexchange_tool import search_stackexchange


class SignalScoutAgent:
    async def run(self, profile: SearchProfile) -> list[Signal]:
        github_task = search_github(
            keywords=profile.keywords,
            keyword_groups=profile.keyword_groups,
            lookback_days=profile.github.lookback_days,
            max_results_per_query=profile.github.max_results_per_query,
            min_stars=profile.github.min_stars,
        )

        stackexchange_task = search_stackexchange(
            keywords=profile.keywords,
            tags=profile.stackexchange.tags,
            lookback_days=profile.stackexchange.lookback_days,
            max_results_per_query=profile.stackexchange.max_results_per_query,
            min_score=profile.stackexchange.min_score,
        )

        github_results, stackexchange_results = await asyncio.gather(
            github_task, stackexchange_task
        )

        return github_results + stackexchange_results