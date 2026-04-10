"""
Batch entry point for the Tech Signal Sales Brief pipeline.

Reads today's schedule, runs the ADK multi-agent pipeline, generates a PDF
report, and emails it to the configured recipients.

Usage:
    # Run today's scheduled analysis
    uv run python batch_main.py

    # Override the day (useful for testing or catch-up)
    SCHEDULE_DAY=friday uv run python batch_main.py

    # Override the prompt entirely
    SCHEDULE_PROMPT="Analyze BigQuery cost optimization signals" uv run python batch_main.py

    # Skip email and just save PDF locally
    BATCH_SKIP_EMAIL=true uv run python batch_main.py
"""

import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("batch_main")

SCHEDULES_PATH = Path(__file__).parent / "config" / "schedules.yaml"
OUTPUT_DIR = Path(__file__).parent / "output"

# Vertex AI pricing for gemini-3-flash-preview (USD per 1M tokens)
# Update these if pricing changes: https://cloud.google.com/vertex-ai/generative-ai/pricing
PRICE_INPUT_PER_1M = 0.50
PRICE_OUTPUT_PER_1M = 3.00
MODEL_NAME = "gemini-3-flash-preview"


def load_schedule() -> dict:
    """Load the schedule config and return today's entry."""
    with open(SCHEDULES_PATH) as f:
        config = yaml.safe_load(f)

    defaults = config.get("defaults", {})
    schedules = config.get("schedules", {})

    override_day = os.environ.get("SCHEDULE_DAY", "").lower().strip()
    if override_day:
        day = override_day
    else:
        day = datetime.now(timezone.utc).strftime("%A").lower()

    if day not in schedules:
        logger.warning("No schedule for '%s', falling back to friday (weekly roundup)", day)
        day = "friday"

    today = schedules[day]

    override_prompt = os.environ.get("SCHEDULE_PROMPT", "").strip()
    if override_prompt:
        today["prompt"] = override_prompt
        logger.info("Using SCHEDULE_PROMPT override")

    today.setdefault("recipients", defaults.get("recipients", []))
    today.setdefault("name", defaults.get("report_title", "Signal Report"))

    logger.info("Schedule: %s (%s)", today["name"], day)
    logger.info("Profiles: %s", today.get("profiles", []))
    logger.info("Recipients: %s", today["recipients"])

    return today


async def run_pipeline(prompt: str) -> tuple[str, dict]:
    """Run the ADK multi-agent pipeline and return the final briefs markdown + usage stats."""
    import google.auth
    from google.adk.agents.run_config import RunConfig, StreamingMode
    from google.adk.runners import Runner
    from google.adk.sessions import InMemorySessionService
    from google.genai import types

    _, project_id = google.auth.default()
    os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id)
    os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")

    from app.agent import root_agent

    session_service = InMemorySessionService()
    session = await session_service.create_session(
        user_id="batch_job", app_name="batch"
    )

    runner = Runner(
        agent=root_agent, session_service=session_service, app_name="batch"
    )

    message = types.Content(
        role="user", parts=[types.Part.from_text(text=prompt)]
    )

    logger.info("Starting pipeline with prompt: %.120s...", prompt)

    final_text_parts: list[str] = []
    total_input_tokens = 0
    total_output_tokens = 0

    async for event in runner.run_async(
        new_message=message,
        user_id="batch_job",
        session_id=session.id,
        run_config=RunConfig(streaming_mode=StreamingMode.NONE),
    ):
        if event.usage_metadata:
            total_input_tokens += event.usage_metadata.prompt_token_count or 0
            total_output_tokens += event.usage_metadata.candidates_token_count or 0

        if event.content and event.content.parts:
            for part in event.content.parts:
                if part.text:
                    final_text_parts.append(part.text)

    updated_session = await session_service.get_session(
        user_id="batch_job", app_name="batch", session_id=session.id
    )

    briefs = ""
    if updated_session and updated_session.state:
        briefs = updated_session.state.get("final_briefs", "")

    if not briefs and final_text_parts:
        briefs = final_text_parts[-1]

    if not briefs:
        raise RuntimeError("Pipeline completed but produced no output")

    total_tokens = total_input_tokens + total_output_tokens
    cost = (total_input_tokens / 1_000_000 * PRICE_INPUT_PER_1M) + (
        total_output_tokens / 1_000_000 * PRICE_OUTPUT_PER_1M
    )

    usage = {
        "input_tokens": total_input_tokens,
        "output_tokens": total_output_tokens,
        "total_tokens": total_tokens,
        "estimated_cost": cost,
        "model": MODEL_NAME,
    }

    logger.info(
        "Pipeline complete — %d chars, %s input tokens, %s output tokens, est. $%.4f",
        len(briefs),
        f"{total_input_tokens:,}",
        f"{total_output_tokens:,}",
        cost,
    )
    return briefs, usage


async def main() -> None:
    schedule = load_schedule()
    now = datetime.now(timezone.utc)

    logger.info("=" * 70)
    logger.info("TECH SIGNAL SALES BRIEF — BATCH RUN")
    logger.info("=" * 70)

    briefs_markdown, usage = await run_pipeline(schedule["prompt"])

    cost_section = f"""

---

## Report Generation Cost

| Metric | Value |
|--------|-------|
| Input tokens | {usage['input_tokens']:,} |
| Output tokens | {usage['output_tokens']:,} |
| Total tokens | {usage['total_tokens']:,} |
| Estimated cost | ${usage['estimated_cost']:.4f} |
| Model | {usage['model']} |

## How Scores Are Calculated

- **Engagement Score**: Average number of comments (GitHub) or upvotes (Stack Overflow) across signals in the cluster. Higher values indicate more developer activity around the topic.
- **Priority Score**: Weighted composite — Engagement (20%) + Recency (20%) + Relevance (30%) + Commercial Fit (30%).
- **Recency**: 10 minus the average age in days of signals (max 10). Newer signals score higher.
- **Relevance**: Keyword match against GCP product terms (BigQuery, Vertex AI, Cloud Run, Looker, etc.).
- **Commercial Fit**: Keyword match against commercial intent terms (migration, performance, cost, pipeline, etc.).
"""

    briefs_markdown += cost_section

    from app.services.pdf_generator import generate_pdf, save_pdf

    date_str = now.strftime("%Y-%m-%d")
    safe_name = schedule["name"].lower().replace(" ", "-").replace("/", "-")
    pdf_filename = f"signal-report-{safe_name}-{date_str}.pdf"

    pdf_bytes = generate_pdf(
        markdown_content=briefs_markdown,
        schedule_name=schedule["name"],
        report_date=now,
    )

    save_pdf(pdf_bytes, OUTPUT_DIR, pdf_filename)

    skip_email = os.environ.get("BATCH_SKIP_EMAIL", "").lower() in ("true", "1", "yes")
    recipients = schedule.get("recipients", [])

    if skip_email or not recipients:
        if not recipients:
            logger.warning("No recipients configured — skipping email")
        else:
            logger.info("BATCH_SKIP_EMAIL=true — skipping email")
    else:
        from app.services.email_sender import send_report_email

        subject = f"[Signal Report] {schedule['name']} — {now.strftime('%B %d, %Y')}"

        body = (
            f"Tech Signal Intelligence Report\n"
            f"{'=' * 40}\n\n"
            f"Report: {schedule['name']}\n"
            f"Date: {now.strftime('%B %d, %Y at %H:%M UTC')}\n\n"
            f"The full analysis is attached as a PDF.\n\n"
            f"This report was generated automatically by the Tech Signal Sales Brief pipeline.\n"
        )

        try:
            send_report_email(
                recipients=recipients,
                subject=subject,
                body_text=body,
                pdf_bytes=pdf_bytes,
                pdf_filename=pdf_filename,
            )
        except RuntimeError as e:
            logger.error("Email delivery failed: %s", e)
            logger.info("PDF saved locally at output/%s", pdf_filename)

    logger.info("=" * 70)
    logger.info("BATCH RUN COMPLETE — %s", pdf_filename)
    logger.info("=" * 70)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted")
        sys.exit(130)
    except Exception:
        logger.exception("Batch job failed")
        sys.exit(1)
