# Tech Signal Sales Brief

A multi-agent pipeline that scans GitHub Issues and Stack Overflow for developer signals, clusters and ranks them by commercial relevance, enriches them with Google Cloud product knowledge, and generates a concise 2-page PDF intelligence report delivered via email.

Built with [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/) and powered by Gemini on Vertex AI.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Pipeline Stages](#pipeline-stages)
3. [Data Flow](#data-flow)
4. [Project Structure](#project-structure)
5. [Module Reference](#module-reference)
6. [Scoring Algorithm](#scoring-algorithm)
7. [Schedule Configuration](#schedule-configuration)
8. [Cost and Billing](#cost-and-billing)
9. [Prerequisites](#prerequisites)
10. [Quick Start](#quick-start)
11. [Commands](#commands)
12. [Environment Variables](#environment-variables)
13. [Cloud Run Job Deployment](#cloud-run-job-deployment)
14. [Email Configuration](#email-configuration)

---

## Architecture

```
                         ┌──────────────────────────────────────────────┐
                         │          config/schedules.yaml               │
                         │   (day-of-week prompt + profile selection)   │
                         └────────────────────┬─────────────────────────┘
                                              │
                                              ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                          batch_main.py (Entry Point)                             │
│                                                                                  │
│  1. Load today's schedule                                                        │
│  2. Run ADK SequentialAgent pipeline                                             │
│  3. Track token usage from event.usage_metadata                                  │
│  4. Append cost summary + score legend to output                                 │
│  5. Generate styled PDF via WeasyPrint                                           │
│  6. Send email with PDF attachment via SMTP                                      │
└──────────────────────────────────────────────────────────────────────────────────┘
                                              │
                    ┌─────────────────────────┼─────────────────────────┐
                    ▼                         ▼                         ▼
         ┌──────────────────┐    ┌──────────────────┐    ┌──────────────────┐
         │  GitHub Issues   │    │  Stack Overflow   │    │  Vertex AI       │
         │  API (httpx)     │    │  API (httpx)      │    │  Gemini API      │
         └──────────────────┘    └──────────────────┘    └──────────────────┘
```

The system uses ADK's `SequentialAgent` to deterministically execute four `LlmAgent` stages in order. Data flows between stages via session state using `output_key` — each agent writes its output to a named key, and the next agent reads it via `{key_name}` placeholders in its instructions.

---

## Pipeline Stages

```
┌─────────────┐     ┌──────────┐     ┌────────────┐     ┌─────────────────┐
│ Signal Scout │────▶│ Analyst  │────▶│ Researcher │────▶│ Brief Generator │
│              │     │          │     │            │     │                 │
│ GitHub +     │     │ Cluster  │     │ GCP expert │     │ 2-page report   │
│ Stack OF     │     │ & Rank   │     │ grounding  │     │ (max 800 words) │
└─────────────┘     └──────────┘     └────────────┘     └─────────────────┘
  output_key:         output_key:      output_key:        output_key:
  raw_signals         ranked_clusters  research_packets   final_briefs
```

| Stage | Agent | Model | Tools | What It Does |
|-------|-------|-------|-------|-------------|
| 1 | **Signal Scout** | gemini-3-flash-preview | `search_developer_signals` | Calls GitHub Issues API and Stack Overflow API via httpx. Searches with the topic keywords from the user prompt. Returns raw signal JSON with titles, URLs, engagement scores, and timestamps. |
| 2 | **Analyst** | gemini-3-flash-preview | `cluster_and_rank_signals` | Parses the raw signal JSON, groups signals by normalized topic title, and computes a weighted priority score for each cluster (see [Scoring Algorithm](#scoring-algorithm)). Returns ranked clusters JSON. |
| 3 | **Researcher** | gemini-3-flash-preview | *(none — uses Gemini's built-in knowledge)* | Selects the top 3 clusters and enriches each with Google Cloud product knowledge: specific products, features, best practices, competitive positioning, risks, and confidence scores. |
| 4 | **Brief Generator** | gemini-3-flash-preview | *(none)* | Produces a concise report (under 800 words) with exactly 3 topic sections, each containing Signal, Opportunity, GCP Solution, Talk Track, and Risk bullets. Ends with 3-5 recommended actions. |

---

## Data Flow

Each agent writes to session state via `output_key` and the next agent reads it via template placeholders:

```
User prompt ─────▶ signal_scout
                        │
                        │ output_key="raw_signals"
                        ▼
                   analyst reads {raw_signals}
                        │
                        │ output_key="ranked_clusters"
                        ▼
                   researcher reads {ranked_clusters}
                        │
                        │ output_key="research_packets"
                        ▼
                   brief_generator reads {research_packets}
                        │
                        │ output_key="final_briefs"
                        ▼
              batch_main.py reads session.state["final_briefs"]
                        │
                        ▼
               Markdown ──▶ PDF ──▶ Email
```

---

## Project Structure

```
tech-signal-sales-brief/
├── app/
│   ├── __init__.py
│   ├── agent.py                  # ADK SequentialAgent orchestrator (4 LlmAgent stages)
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── cluster_rank_agent.py # Topic clustering, scoring, and ranking logic
│   │   └── signal_scout_agent.py # Parallel GitHub + Stack Overflow search
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── cluster.py            # SignalCluster Pydantic model
│   │   ├── config.py             # SearchProfile, GithubConfig, StackExchangeConfig
│   │   └── signal.py             # Signal Pydantic model
│   ├── services/
│   │   ├── __init__.py
│   │   ├── email_sender.py       # SMTP email with PDF attachment
│   │   └── pdf_generator.py      # Markdown → HTML → styled PDF (WeasyPrint)
│   └── tools/
│       ├── __init__.py
│       ├── github_tool.py        # GitHub Issues search API client (httpx)
│       ├── pipeline_tools.py     # ADK-compatible tool wrappers + JSON extraction
│       └── stackexchange_tool.py # Stack Overflow search API client (httpx)
├── config/
│   └── schedules.yaml            # Day-of-week schedule (prompts, profiles, recipients)
├── tests/
│   └── integration/
│       └── test_agent.py         # Pipeline integration test
├── batch_main.py                 # Batch entry point (schedule → pipeline → PDF → email)
├── Dockerfile.batch              # Cloud Run Job Dockerfile (Python 3.12 + WeasyPrint deps)
├── Makefile                      # Development and batch commands
├── pyproject.toml                # Dependencies and project metadata
└── .env.example                  # Environment variable template
```

---

## Module Reference

### `app/agent.py` — Pipeline Orchestrator

Defines the four `LlmAgent` stages and wires them into a `SequentialAgent` named `tech_signal_pipeline`. Each agent uses `gemini-3-flash-preview` via Vertex AI. The module also creates an ADK `App` instance for the playground UI.

Key configuration:
- `MODEL = "gemini-3-flash-preview"` — shared across all stages
- `GOOGLE_GENAI_USE_VERTEXAI = "True"` — routes through Vertex AI (not AI Studio)
- `GOOGLE_CLOUD_LOCATION = "global"` — required for preview models

### `app/tools/pipeline_tools.py` — ADK Tool Wrappers

Contains the two functions registered as ADK tools:

- **`search_developer_signals(topic, additional_keywords)`** — Creates a `SearchProfile` with the given keywords, instantiates `SignalScoutAgent`, runs parallel GitHub + Stack Overflow searches, and returns JSON with signal metadata.
- **`cluster_and_rank_signals(signals_json)`** — Parses the signal JSON (handling LLM quirks like trailing prose, markdown fences, bare arrays), constructs `Signal` objects, runs `ClusterRankAgent`, and returns ranked clusters JSON.

Also includes `_extract_json()` — a robust JSON extractor that handles malformed LLM output by finding the first balanced `{}`/`[]` block in the text.

### `app/agents/signal_scout_agent.py` — Signal Discovery

Runs `search_github()` and `search_stackexchange()` in parallel using `asyncio.gather()`. Each API client uses httpx with a 30-second timeout and returns `Signal` objects.

### `app/agents/cluster_rank_agent.py` — Clustering and Scoring

Groups signals by normalized title, computes four sub-scores per cluster, and sorts by weighted priority. See [Scoring Algorithm](#scoring-algorithm) for details.

### `app/tools/github_tool.py` — GitHub API Client

Searches GitHub Issues using the `/search/issues` endpoint. Builds queries from keywords and keyword groups, applies a lookback window (`updated:>=YYYY-MM-DD`), and extracts engagement scores from comment counts. Requires a `GITHUB_TOKEN` with `public_repo` scope.

### `app/tools/stackexchange_tool.py` — Stack Overflow API Client

Searches Stack Overflow using the `/search/advanced` endpoint. Supports tag filtering, minimum score thresholds, and lookback windows. Extracts engagement scores from `score` + `answer_count`. Uses `STACKEXCHANGE_API_KEY` for higher rate limits.

### `app/services/pdf_generator.py` — PDF Generation

Converts markdown to HTML using `markdown2` (with tables, fenced-code-blocks, and header-ids extras), applies professional CSS styling (A4 page, Google Blue headings, table formatting, page numbers), and renders to PDF using WeasyPrint.

### `app/services/email_sender.py` — Email Delivery

Sends emails with PDF attachments via SMTP. Supports Gmail (App Passwords), corporate SMTP, and any STARTTLS-capable server. Configuration via `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` environment variables.

### `batch_main.py` — Batch Entry Point

Orchestrates the full batch run:
1. Loads today's schedule from `config/schedules.yaml`
2. Runs the ADK pipeline via `Runner.run_async()`
3. Tracks token usage from `event.usage_metadata` (input + output tokens)
4. Calculates estimated cost using Vertex AI pricing constants
5. Appends a cost summary table and score legend to the markdown
6. Generates a styled PDF and saves it to `output/`
7. Sends the PDF via email (unless `BATCH_SKIP_EMAIL=true`)

---

## Scoring Algorithm

The `ClusterRankAgent` computes a **Priority Score** for each signal cluster using four weighted components:

```
Priority = 0.20 * Engagement + 0.20 * Recency + 0.30 * Relevance + 0.30 * Commercial Fit
```

| Score | Weight | Calculation | Range |
|-------|--------|-------------|-------|
| **Engagement** | 20% | Average of `engagement_score` across signals in the cluster. For GitHub, this is the comment count. For Stack Overflow, it is the question score + answer count. | 0 to unbounded |
| **Recency** | 20% | `10 - avg_days_old`. Signals created today score 10; signals 10+ days old score 0. | 0 to 10 |
| **Relevance** | 30% | +2 for each GCP product term found in the topic title: `bigquery`, `vertex`, `looker`, `cloud run`, `agent`, `migration`. | 0 to 12 |
| **Commercial Fit** | 30% | +2 for each commercial intent term found in the topic title: `migration`, `performance`, `cost`, `dashboard`, `pipeline`, `agent`. | 0 to 12 |

Clusters are sorted by Priority Score (descending). The top 3 are selected by the Researcher agent for the final report.

The **Engagement Score** shown in the PDF report (e.g., "Engagement Score: 493+") is the raw average engagement across all signals in that cluster before weighting.

---

## Schedule Configuration

The batch job runs a different analysis focus each weekday, configured in `config/schedules.yaml`:

| Day | Focus Area | Search Profiles | Description |
|-----|-----------|----------------|-------------|
| **Monday** | Competitive Intelligence | `gcp_vs_aws`, `infrastructure` | GCP vs AWS migration pain points, pricing, feature gaps |
| **Tuesday** | Data & Analytics | `data_analytics` | BigQuery, Redshift, Snowflake, cost optimization |
| **Wednesday** | AI/ML & Agents | `ai_ml` | Vertex AI, Gemini, Bedrock, RAG, MLOps |
| **Thursday** | Infrastructure | `infrastructure`, `gcp_general` | Cloud Run, GKE, Lambda, containers, CI/CD |
| **Friday** | Weekly Roundup | All profiles | Comprehensive summary of the week's top signals |

Each schedule entry contains:
- **name**: Display name for the report header
- **prompt**: The full analysis prompt sent to the Signal Scout agent
- **profiles**: Which search keyword profiles to activate
- **recipients**: Inherited from `defaults.recipients` (configurable per day)

Override at runtime:
```bash
SCHEDULE_DAY=monday make batch          # Force a specific day
SCHEDULE_PROMPT="custom prompt" make batch  # Override the prompt entirely
```

---

## Cost and Billing

### How billing works

The pipeline uses **Vertex AI** (not the free-tier Gemini API from AI Studio). All Gemini API calls are authenticated via `gcloud auth application-default login` and billed to your **GCP project**.

| Component | Auth Method | Cost |
|-----------|------------|------|
| Gemini API (4 LLM calls) | Vertex AI via ADC | ~$0.24 per report |
| GitHub Issues API | `GITHUB_TOKEN` | Free |
| Stack Overflow API | `STACKEXCHANGE_API_KEY` | Free |
| Email (SMTP) | Gmail App Password | Free |

### Vertex AI pricing (gemini-3-flash-preview)

| Token Type | Price per 1M Tokens |
|-----------|-------------------|
| Input tokens | $0.50 |
| Output tokens | $3.00 |

Source: [Vertex AI Pricing](https://cloud.google.com/vertex-ai/generative-ai/pricing)

### Typical usage per report

| Metric | Typical Value |
|--------|--------------|
| Input tokens | ~250,000 |
| Output tokens | ~35,000 |
| Total tokens | ~285,000 |
| Estimated cost | ~$0.23 |
| Runtime | ~2 minutes |

### Monthly cost estimate

| Schedule | Reports/Month | Cost/Month |
|----------|--------------|------------|
| Weekdays only (Mon-Fri) | 22 | ~$5.10 |
| Daily (7 days) | 30 | ~$6.90 |

Costs appear in the **GCP Billing Console** under:
- **Service**: Vertex AI
- **SKU**: Gemini 3 Flash Preview — Input/Output tokens

Each generated PDF includes a **Report Generation Cost** table on the last page with exact token counts and estimated cost for that specific run.

### Pricing constants

Token pricing rates are defined as constants in `batch_main.py` for easy updates:
```python
PRICE_INPUT_PER_1M = 0.50   # USD per 1M input tokens
PRICE_OUTPUT_PER_1M = 3.00  # USD per 1M output tokens
```

---

## Prerequisites

- **Python 3.12+**
- **uv** — Python package manager ([install](https://docs.astral.sh/uv/getting-started/installation/))
- **Google Cloud SDK** — Authenticated with `gcloud auth application-default login`
- **GitHub Token** — Personal access token with `public_repo` scope ([create](https://github.com/settings/tokens))
- **Stack Exchange Key** — API key for higher rate limits ([register](https://stackapps.com/apps/oauth/register))
- **SMTP credentials** — For email delivery (Gmail App Password or corporate SMTP)

---

## Quick Start

```bash
# Install dependencies
make install

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your API keys and SMTP credentials

# Run the ADK playground (interactive development UI)
make playground

# Run the batch pipeline locally (saves PDF, skips email)
make batch-test

# Run with email delivery
make batch
```

---

## Commands

| Command | Description |
|---------|-------------|
| `make install` | Install all Python dependencies via uv |
| `make playground` | Launch ADK Web UI at `localhost:8501` for interactive testing |
| `make batch` | Run today's scheduled analysis, generate PDF, send email |
| `make batch-test` | Run Friday roundup, skip email, save PDF to `output/` |
| `make batch-day DAY=wednesday` | Run a specific day's schedule |
| `make test` | Run integration tests with pytest |

---

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | Yes | GitHub Personal Access Token (`public_repo` scope) |
| `STACKEXCHANGE_API_KEY` | Yes | Stack Exchange API key for Stack Overflow search |
| `SMTP_HOST` | For email | SMTP server hostname (e.g., `smtp.gmail.com`) |
| `SMTP_PORT` | For email | SMTP port (typically `587` for STARTTLS) |
| `SMTP_USER` | For email | SMTP username / sender email |
| `SMTP_PASSWORD` | For email | SMTP password (Gmail App Password for Gmail) |
| `SMTP_FROM` | No | Display "From" address (defaults to `SMTP_USER`) |
| `SCHEDULE_DAY` | No | Override the day of week (`monday` through `friday`) |
| `SCHEDULE_PROMPT` | No | Override the analysis prompt entirely |
| `BATCH_SKIP_EMAIL` | No | Set to `true` to skip email and only save PDF locally |

---

## Cloud Run Job Deployment

### Build and push the image

```bash
export PROJECT_ID=$(gcloud config get-value project)
export REGION=us-central1

gcloud builds submit \
  --tag ${REGION}-docker.pkg.dev/${PROJECT_ID}/signal-brief/batch:latest \
  --dockerfile Dockerfile.batch
```

### Create the Cloud Run Job

```bash
gcloud run jobs create signal-brief-daily \
  --image ${REGION}-docker.pkg.dev/${PROJECT_ID}/signal-brief/batch:latest \
  --region ${REGION} \
  --memory 2Gi \
  --cpu 1 \
  --timeout 900 \
  --set-env-vars "SMTP_HOST=smtp.gmail.com,SMTP_PORT=587" \
  --set-secrets "GITHUB_TOKEN=GITHUB_TOKEN:latest,STACKEXCHANGE_API_KEY=STACKEXCHANGE_API_KEY:latest,SMTP_USER=SMTP_USER:latest,SMTP_PASSWORD=SMTP_PASSWORD:latest"
```

### Schedule with Cloud Scheduler (weekdays at 8 AM UTC)

```bash
gcloud scheduler jobs create http signal-brief-scheduler \
  --schedule "0 8 * * 1-5" \
  --uri "https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT_ID}/jobs/signal-brief-daily:run" \
  --http-method POST \
  --oauth-service-account-email ${PROJECT_ID}-compute@developer.gserviceaccount.com
```

### Required IAM roles

The Cloud Run Job's service account needs:
- `roles/aiplatform.user` — Invoke Gemini via Vertex AI
- `roles/secretmanager.secretAccessor` — Read secrets for API keys and SMTP

---

## Email Configuration

The batch job sends PDF reports via SMTP. For **Gmail**, you need an App Password (regular passwords won't work):

1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Create a new app password named "Signal Brief"
3. Copy the 16-character password

Add to your `.env`:
```bash
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx
```

Recipients are configured in `config/schedules.yaml` under `defaults.recipients`. You can also set per-day recipients by adding a `recipients` list to any day's schedule entry.
