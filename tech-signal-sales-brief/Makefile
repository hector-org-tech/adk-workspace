
# ==============================================================================
# Installation & Setup
# ==============================================================================

install:
	@command -v uv >/dev/null 2>&1 || { echo "uv is not installed. Installing uv..."; curl -LsSf https://astral.sh/uv/0.8.13/install.sh | sh; source $HOME/.local/bin/env; }
	uv sync

# ==============================================================================
# Playground (local development with ADK Web UI)
# ==============================================================================

playground:
	uv run adk web . --port 8501 --reload_agents

# ==============================================================================
# Batch Job Targets
# ==============================================================================

# Run the batch pipeline (today's schedule -> PDF -> email)
batch:
	uv run python batch_main.py

# Run batch for a specific day (e.g. make batch-day DAY=friday)
batch-day:
	SCHEDULE_DAY=$(DAY) uv run python batch_main.py

# Run batch with skip email, save PDF locally
batch-test:
	BATCH_SKIP_EMAIL=true SCHEDULE_DAY=friday uv run python batch_main.py

# ==============================================================================
# Testing
# ==============================================================================

test:
	uv sync --dev
	uv run pytest tests/
