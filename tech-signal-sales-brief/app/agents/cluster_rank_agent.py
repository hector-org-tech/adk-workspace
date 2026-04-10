import hashlib
from collections import defaultdict
from datetime import datetime, timezone
from app.schemas.signal import Signal
from app.schemas.cluster import SignalCluster


class ClusterRankAgent:
    def run(self, signals: list[Signal]) -> list[SignalCluster]:
        grouped: dict[str, list[Signal]] = defaultdict(list)

        for signal in signals:
            topic_key = self._normalize_topic(signal.title)
            grouped[topic_key].append(signal)

        clusters: list[SignalCluster] = []
        for topic, members in grouped.items():
            member_ids = [m.external_id for m in members]
            summary = members[0].title

            engagement = sum(m.engagement_score for m in members) / max(len(members), 1)
            recency = self._recency_score(members)
            relevance = self._relevance_score(topic)
            commercial_fit = self._commercial_fit_score(topic)

            priority = (
                0.20 * engagement
                + 0.20 * recency
                + 0.30 * relevance
                + 0.30 * commercial_fit
            )

            clusters.append(
                SignalCluster(
                    cluster_id=hashlib.md5(topic.encode()).hexdigest(),
                    topic=topic,
                    summary=summary,
                    member_signal_ids=member_ids,
                    engagement_score=engagement,
                    recency_score=recency,
                    relevance_score=relevance,
                    commercial_fit_score=commercial_fit,
                    priority_score=priority,
                )
            )

        clusters.sort(key=lambda x: x.priority_score, reverse=True)
        return clusters

    def _normalize_topic(self, title: str) -> str:
        return title.lower().strip()

    def _recency_score(self, members: list[Signal]) -> float:
        now = datetime.now(timezone.utc)
        avg_days = sum((now - m.created_at).days for m in members) / max(len(members), 1)
        return max(0.0, 10.0 - avg_days)

    def _relevance_score(self, topic: str) -> float:
        important_terms = ["bigquery", "vertex", "looker", "cloud run", "agent", "migration"]
        return float(sum(2 for t in important_terms if t in topic))

    def _commercial_fit_score(self, topic: str) -> float:
        commercial_terms = ["migration", "performance", "cost", "dashboard", "pipeline", "agent"]
        return float(sum(2 for t in commercial_terms if t in topic))
