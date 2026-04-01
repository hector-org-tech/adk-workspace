# ADK Workspace

A collection of AI agent projects built with [Google Agent Development Kit (ADK)](https://google.github.io/adk-docs/), showcasing different tool integrations and agent patterns using Gemini 2.5 Flash.

## Agents

### `flight_agent`
A real-time flight search assistant that integrates with Google Flights via the SerpApi API. It collects origin, destination, dates, passenger count, and cabin class, confirms details with the user, then returns ranked flight options (cheapest, fastest, fewest stops, or best value). Booking links are included in results.

- **Tools:** Custom `search_flights()` function backed by SerpApi
- **Requires:** `SERPAPI_KEY` environment variable

---

### `travel_agent`
A multi-tool trip planning assistant that coordinates flight search, hotel search, and budget calculation in sequence to produce a complete trip estimate.

- **Tools:** `search_flights()`, `search_hotels()`, `calculate_trip_budget()` (simulated data for Paris and Tokyo)

---

### `research_assistant`
A web research agent that uses Google Search to answer questions with current, sourced information. It cites sources and acknowledges when results are insufficient.

- **Tools:** Built-in `google_search` (requires Gemini 2.0+)

---

### `math_assistant`
A math helper that executes Python code directly to perform precise calculations — statistics, algebra, compound interest, and more. Shows step-by-step workings.

- **Tools:** Built-in `BuiltInCodeExecutor` (requires Gemini 2.0+)

---

### `geography_assistant`
Demonstrates MCP (Model Context Protocol) tool integration. The agent can list and read files from a restricted local directory (`./my_files`) using an MCP filesystem server.

- **Tools:** `McpToolset` with `list_directory` and `read_file` via `@modelcontextprotocol/server-filesystem`

---

### `my_first_agent`
A minimal, beginner-friendly ADK agent. A simple algebra tutor with no external tools — intended as a learning template for the core `LlmAgent` structure.

- **Tools:** None

---

## Tech Stack

| Layer | Details |
|---|---|
| Framework | Google ADK 1.27.3 |
| Model | Gemini 2.5 Flash (all agents) |
| Language | Python 3.12 |
| Tool types | Function tools, built-in tools, MCP tools |
| External APIs | SerpApi (flight data), Google Search |

## Getting Started

1. Clone the repo and navigate into an agent folder:
   ```bash
   cd flight_agent
   ```

2. Copy the environment file and add your API keys:
   ```bash
   cp .env.example .env
   ```

3. Run the agent with the ADK CLI:
   ```bash
   adk run agent.py
   ```

> Each agent folder is self-contained. Refer to the agent's source file for specific environment variable requirements.
