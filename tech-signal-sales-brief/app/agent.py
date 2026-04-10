"""
Tech Signal Sales Brief — ADK Multi-Agent System

Uses a SequentialAgent to deterministically execute four pipeline stages:
  signal_scout  →  analyst  →  researcher  →  brief_generator

Data flows between agents via session state using output_key.
"""

import os
import google.auth
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.agents.llm_agent import LlmAgent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from app.tools.pipeline_tools import (
    search_developer_signals,
    cluster_and_rank_signals,
)

_, project_id = google.auth.default()
os.environ["GOOGLE_CLOUD_PROJECT"] = project_id
os.environ["GOOGLE_CLOUD_LOCATION"] = "global"
os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = "True"

MODEL = "gemini-3-flash-preview"

# ─── Stage 1: Signal Scout ───────────────────────────────────────────────────
signal_scout = LlmAgent(
    name="signal_scout",
    model=MODEL,
    instruction="""You are the Signal Scout agent. Your job is to discover developer
signals from GitHub Issues and Stack Overflow.

Take the user's request and:
1. Call search_developer_signals with the topic and relevant keywords
2. Summarize the findings briefly (count, sources, top themes)
3. Include the full raw JSON output in your response so the next agent can process it

Search broadly — for "BigQuery" also try "bq", "bigquery migration", etc.""",
    description="Searches GitHub and Stack Overflow for developer signals about a topic.",
    tools=[search_developer_signals],
    output_key="raw_signals",
)

# ─── Stage 2: Analyst ────────────────────────────────────────────────────────
analyst = LlmAgent(
    name="analyst",
    model=MODEL,
    instruction="""You are the Signal Analyst agent. You cluster and rank developer signals.

**Signals from previous step:**
{raw_signals}

Your task:
1. Extract the JSON signals data from the text above
2. Call cluster_and_rank_signals with the full JSON (must be valid JSON with a "signals" array)
3. Summarize the top clusters found: topic, priority score, member count
4. Include the full clusters JSON in your response for the next agent""",
    description="Clusters and ranks signals by engagement, recency, relevance, and commercial fit.",
    tools=[cluster_and_rank_signals],
    output_key="ranked_clusters",
)

# ─── Stage 3: Researcher ────────────────────────────────────────────────────
# NOTE: Developer Knowledge MCP can be added here as a tool once API permissions
# are configured. For now, uses Gemini's built-in Google Cloud knowledge.
researcher = LlmAgent(
    name="researcher",
    model=MODEL,
    instruction="""You are the Research agent. You are a Google Cloud expert who enriches
signal clusters with official Google Cloud product knowledge.

**Clusters from previous step:**
{ranked_clusters}

Select ONLY the top 3 highest-priority clusters. For each, produce a research packet containing:
- **topic**: the cluster topic
- **market_evidence**: what the developer signals show (use the cluster summary)
- **official_grounding**: your expert knowledge of relevant Google Cloud documentation,
  products, best practices, and migration guides that relate to this topic. Be specific —
  name actual products (BigQuery, Vertex AI, Cloud Run, etc.), reference real features,
  and cite known best practices.
- **gcp_angle**: how Google Cloud products specifically address this pain point,
  including competitive advantages
- **risks**: potential caveats, limitations, or considerations
- **confidence_score**: 0.0 to 1.0 based on signal volume and relevance

Present each research packet clearly formatted for the brief generator to consume.""",
    description="Enriches clusters with Google Cloud product expertise and official documentation knowledge.",
    output_key="research_packets",
)

# ─── Stage 4: Brief Generator ───────────────────────────────────────────────
brief_generator = LlmAgent(
    name="brief_generator",
    model=MODEL,
    instruction="""You are the Brief Generator. You produce a SHORT, high-density report.

CRITICAL: The entire output MUST fit on 2 printed pages. Be ruthlessly concise.
Use bullet points, not paragraphs. Every sentence must carry actionable information.

**Research packets from previous step:**
{research_packets}

Generate this EXACT structure:

# Top Signals This Week

For EACH of the top 3 topics (no more than 3), write ONE compact section:

## [Topic Name]
**Signal**: 1-2 sentences on what developers are saying (cite engagement numbers)
**Opportunity**: 1-2 sentences on the sales/business angle
**GCP Solution**: Name specific products and one concrete use case
**Talk Track**: One sentence a seller can say verbatim in a customer meeting
**Risk**: One sentence on caveats

---

Then end with:

# Recommended Actions
A numbered list of 3-5 specific next steps across all topics (who should do what by when).

RULES:
- Maximum 3 topics. Pick the highest-impact ones.
- No introductions, no conclusions, no filler.
- Each topic section must be 5-7 bullet points MAX.
- Use concrete numbers, product names, and specific examples from the signals.
- Total output: under 800 words.""",
    description="Generates a concise 2-page signal intelligence report.",
    output_key="final_briefs",
)

# ─── Pipeline Orchestrator ───────────────────────────────────────────────────
root_agent = SequentialAgent(
    name="tech_signal_pipeline",
    sub_agents=[signal_scout, analyst, researcher, brief_generator],
    description="Executes the full tech signal analysis pipeline: Scout → Analyze → Research → Generate briefs.",
)

app = App(
    root_agent=root_agent,
    name="app",
)
