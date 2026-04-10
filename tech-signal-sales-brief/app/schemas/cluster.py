from pydantic import BaseModel


class SignalCluster(BaseModel):
    cluster_id: str
    topic: str
    summary: str
    member_signal_ids: list[str]
    engagement_score: float
    recency_score: float
    relevance_score: float
    commercial_fit_score: float
    priority_score: float