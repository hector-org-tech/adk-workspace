from pydantic import BaseModel
from typing import List


class GithubConfig(BaseModel):
    lookback_days: int = 7
    max_results_per_query: int = 20
    min_stars: int = 0


class StackExchangeConfig(BaseModel):
    lookback_days: int = 7
    max_results_per_query: int = 20
    min_score: int = 0
    tags: List[str] = []


class OutputConfig(BaseModel):
    max_clusters: int = 5
    max_briefs: int = 3


class SearchProfile(BaseModel):
    profile_id: str
    enabled: bool = True
    keywords: List[str]
    keyword_groups: List[List[str]] = []
    github: GithubConfig
    stackexchange: StackExchangeConfig
    output: OutputConfig


class SignalConfig(BaseModel):
    profiles: List[SearchProfile]