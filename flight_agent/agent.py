"""
Flight specialist agent with SerpApi Google Flights integration.
Architecture:
  - search_flights() → function tool that calls SerpApi and returns FlightSearchResponse
  - Aria (root agent) → receives structured data, responds in natural language
"""

import os
import requests
from urllib.parse import quote_plus
from google.adk.agents import LlmAgent
from google.genai import types
from pydantic import BaseModel, Field


# ─────────────────────────────────────────────
# 1. Pydantic output schema
# ─────────────────────────────────────────────

class FlightOption(BaseModel):
    airline: str = Field(description="Airline name (e.g., 'Copa Airlines')")
    flight_number: str = Field(default="Not specified", description="Flight number if available")
    origin: str = Field(description="Departure airport code (e.g., 'UIO')")
    destination: str = Field(description="Arrival airport code (e.g., 'YYZ')")
    departure_date: str = Field(description="Departure date in YYYY-MM-DD format")
    return_date: str = Field(default="Not specified", description="Return date for round trips")
    passengers: int = Field(description="Number of passengers")
    cabin_class: str = Field(default="Economy", description="Cabin class")
    stops: int = Field(description="Number of stops (0 = direct)")
    layover_city: str = Field(default="None", description="Layover city if applicable")
    duration: str = Field(description="Total flight duration (e.g., '10h 30m')")
    price_per_person: float = Field(description="Price per adult in USD, no dollar signs")
    total_price: float = Field(description="Total price for all passengers in USD")
    trip_type: str = Field(description="'one-way' or 'round-trip'")
    booking_url: str = Field(default="Not available", description="Direct booking URL")


class FlightSearchResponse(BaseModel):
    origin: str
    destination: str
    options: list[FlightOption]
    preference_used: str = Field(
        description="How options were ranked: cheapest, fastest, fewest_stops, best_value"
    )
    recommendation: str
    price_disclaimer: str = Field(
        default="Prices are live from Google Flights and may change at booking time."
    )
    cannot_book: str = Field(
        default=(
            "I can search and recommend flights but cannot book on your behalf. "
            "Please use the booking URL to complete your purchase."
        )
    )


# ─────────────────────────────────────────────
# 2. Helper functions
# ─────────────────────────────────────────────

def _minutes_to_duration(minutes: int) -> str:
    """Converts total minutes to a human-readable duration string."""
    if not minutes:
        return "Duration unknown"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins:02d}m"


def _error_response(origin: str, destination: str, message: str) -> dict:
    """Returns a standardized error response dict."""
    return {
        "origin": origin.upper(),
        "destination": destination.upper(),
        "options": [],
        "preference_used": "n/a",
        "recommendation": message,
        "price_disclaimer": "Live prices unavailable at this time.",
        "cannot_book": "I can search and recommend flights but cannot book on your behalf.",
    }


def _build_booking_url(
    google_flights_url: str,
    origin: str,
    destination: str,
    departure_date: str,
    return_date: str,
    passengers: int,
    cabin_class: str,
) -> str:
    """
    Builds a working Google Flights booking URL.

    Priority:
      1. Use google_flights_url from SerpApi search_metadata — this is
         the real Google Flights URL with correct tfs protobuf encoding,
         exact dates, cabin class, and passengers already set.
      2. Fall back to a pre-filled natural language search URL.
    """
    if google_flights_url:
        return google_flights_url

    # ── Fallback: natural language pre-filled search ──────────────────
    is_round_trip = bool(return_date and return_date != "Not specified")
    date_context = f"on {departure_date}"
    if is_round_trip:
        date_context += f" returning {return_date}"

    query = quote_plus(
        f"flights from {origin.upper()} to {destination.upper()} {date_context}"
    )

    return (
        f"https://www.google.com/travel/flights"
        f"?q={query}&hl=en&curr=USD"
    )

def _is_price_suspicious(
    total: float,
    passengers: int,
    typical: list,
) -> bool:
    """
    Returns True if the total price looks wrong.
    Cross-checks the parsed total against SerpApi's price_insights
    typical_price_range to catch any per-person vs total confusion.
    """
    if total <= 0:
        return True
    if not typical or len(typical) < 2:
        return False
    per_person = total / max(passengers, 1)
    typical_high = typical[1]
    # Flag if per-person cost is more than 1.5x the typical high-end price
    if typical_high > 0 and per_person > typical_high * 1.5:
        return True
    return False


# ─────────────────────────────────────────────
# 3. SerpApi flight search tool
# ─────────────────────────────────────────────

def search_flights(
    origin: str,
    destination: str,
    departure_date: str,
    passengers: int,
    return_date: str = "",
    cabin_class: str = "economy",
    preference: str = "best_value",
) -> dict:
    """
    Searches for real-time flights using Google Flights via SerpApi.

    Args:
        origin: Departure airport IATA code (e.g., 'UIO', 'JFK', 'BOG').
        destination: Arrival airport IATA code (e.g., 'YYZ', 'MAD', 'MIA').
        departure_date: Departure date in YYYY-MM-DD format (e.g., '2025-08-15').
        passengers: Number of adult passengers (e.g., 2).
        return_date: Return date in YYYY-MM-DD format. Leave empty for one-way.
        cabin_class: 'economy', 'premium economy', 'business', or 'first'.
        preference: How to rank results — 'cheapest', 'fastest',
                    'fewest_stops', or 'best_value' (balances price + speed).

    Returns:
        dict: Structured FlightSearchResponse with top 3 options ranked
              by the user's preference, plus a tailored recommendation.
    """

    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        return _error_response(
            origin, destination,
            "SERPAPI_KEY environment variable not set. Please add it to your .env file."
        )

    # Map cabin class to SerpApi travel_class parameter
    # 1=Economy, 2=Premium Economy, 3=Business, 4=First
    cabin_map = {"economy": 1, "premium economy": 2, "business": 3, "first": 4}
    travel_class = cabin_map.get(cabin_class.lower(), 1)

    trip_type = "round-trip" if return_date else "one-way"
    # SerpApi type: 1=round-trip, 2=one-way
    flight_type = 1 if return_date else 2

    params = {
        "engine": "google_flights",
        "departure_id": origin.upper(),
        "arrival_id": destination.upper(),
        "outbound_date": departure_date,
        "adults": passengers,
        "travel_class": travel_class,
        "type": flight_type,
        "currency": "USD",
        "hl": "en",
        "deep_search": "true",  # Ensures departure_token and full data are returned
        "api_key": api_key,
    }
    if return_date:
        params["return_date"] = return_date

    try:
        response = requests.get(
            "https://serpapi.com/search",
            params=params,
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        google_flights_url = data.get("search_metadata", {}).get("google_flights_url", "")
    except requests.exceptions.Timeout:
        return _error_response(
            origin, destination,
            "Flight search timed out. Please try again in a moment."
        )
    except requests.exceptions.RequestException as e:
        return _error_response(origin, destination, f"Flight search failed: {str(e)}")

    if "error" in data:
        return _error_response(origin, destination, data["error"])

    # ── Price sanity check context ────────────────────────────────────
    price_insights = data.get("price_insights", {})
    typical_range = price_insights.get("typical_price_range", [])

    # ── Collect ALL flights before ranking ────────────────────────────
    # best_flights = Google's curated top picks
    # other_flights = remaining options
    raw_flights = data.get("best_flights", []) + data.get("other_flights", [])

    if not raw_flights:
        return {
            "origin": origin.upper(),
            "destination": destination.upper(),
            "options": [],
            "preference_used": preference,
            "recommendation": (
                f"No flights found from {origin.upper()} to {destination.upper()} "
                f"on {departure_date}. Try different dates or nearby airports."
            ),
            "price_disclaimer": "Prices are live from Google Flights and may change at booking time.",
            "cannot_book": "I can search and recommend flights but cannot book on your behalf.",
        }

    # ── Parse flights into FlightOption objects ───────────────────────
    all_options = []
    duration_map = {}  # option_index → raw minutes, for sorting

    for flight in raw_flights:
        legs = flight.get("flights", [])
        first_leg = legs[0] if legs else {}
        layovers = flight.get("layovers", [])
        layover_city = layovers[0].get("name", "None") if layovers else "None"
        total_minutes = flight.get("total_duration", 0)

        # SerpApi price = TOTAL for all passengers combined
        total_price = float(flight.get("price", 0))
        price_per_person = round(total_price / passengers, 2) if passengers > 0 else total_price

        # Build booking URL using departure_token when available
        departure_token = flight.get("departure_token", "")
        booking_url = _build_booking_url(
            google_flights_url=google_flights_url,   # ← real URL from SerpApi
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            passengers=passengers,
            cabin_class=cabin_class,
        )

        # Flag suspicious prices in recommendation (non-blocking)
        price_note = ""
        if _is_price_suspicious(total_price, passengers, typical_range):
            price_note = " ⚠️ Verify price on Google Flights before booking."

        try:
            option = FlightOption(
                airline=first_leg.get("airline", "Unknown airline"),
                flight_number=first_leg.get("flight_number", "Not specified"),
                origin=origin.upper(),
                destination=destination.upper(),
                departure_date=departure_date,
                return_date=return_date if return_date else "Not specified",
                passengers=passengers,
                cabin_class=cabin_class.capitalize(),
                stops=len(legs) - 1 if legs else 0,
                layover_city=layover_city,
                duration=_minutes_to_duration(total_minutes),
                price_per_person=price_per_person,
                total_price=total_price,
                trip_type=trip_type,
                booking_url=booking_url,
            )
            # Store raw minutes alongside option for sorting (not in schema)
            idx = len(all_options)
            duration_map[idx] = total_minutes
            all_options.append(option)
        except Exception:
            continue

    if not all_options:
        return _error_response(
            origin, destination,
            "Could not parse flight results. Please try again."
        )

    # ── Rank by user preference ───────────────────────────────────────
    preference = preference.lower().strip()

    if preference == "cheapest":
        ranked_with_idx = sorted(
            enumerate(all_options),
            key=lambda x: x[1].price_per_person
        )
        preference_label = "cheapest"
        rank_explanation = lambda o: f"${o.price_per_person:.2f}/person"

    elif preference == "fastest":
        ranked_with_idx = sorted(
            enumerate(all_options),
            key=lambda x: duration_map.get(x[0], 9999)
        )
        preference_label = "fastest"
        rank_explanation = lambda o: o.duration

    elif preference == "fewest_stops":
        ranked_with_idx = sorted(
            enumerate(all_options),
            key=lambda x: (x[1].stops, x[1].price_per_person)
        )
        preference_label = "fewest stops"
        rank_explanation = lambda o: (
            "direct" if o.stops == 0 else f"{o.stops} stop(s)"
        )

    else:  # best_value — weighted score: 60% price, 40% speed
        prices = [o.price_per_person for o in all_options]
        durations = [duration_map.get(i, 9999) for i in range(len(all_options))]
        min_price, max_price = min(prices), max(prices)
        min_dur, max_dur = min(durations), max(durations)

        def value_score(idx_option):
            idx, o = idx_option
            price_norm = (
                (o.price_per_person - min_price) / (max_price - min_price)
                if max_price != min_price else 0.0
            )
            dur_norm = (
                (duration_map.get(idx, 9999) - min_dur) / (max_dur - min_dur)
                if max_dur != min_dur else 0.0
            )
            return (0.6 * price_norm) + (0.4 * dur_norm)

        ranked_with_idx = sorted(enumerate(all_options), key=value_score)
        preference_label = "best value (price + speed)"
        rank_explanation = lambda o: f"${o.price_per_person:.2f}/person, {o.duration}"

    # Extract top 3 options after ranking
    top_3 = [option for _, option in ranked_with_idx[:3]]
    best = top_3[0]

    # Build tailored recommendation string
    stops_desc = (
        "direct" if best.stops == 0
        else f"{best.stops} stop(s) via {best.layover_city}"
    )
    recommendation = (
        f"Based on your preference for {preference_label}, the top pick is "
        f"{best.airline} — {rank_explanation(best)}, {stops_desc}, "
        f"${best.total_price:.2f} total (${best.price_per_person:.2f}/person) "
        f"for {passengers} passenger{'s' if passengers > 1 else ''}."
    )

    result = FlightSearchResponse(
        origin=origin.upper(),
        destination=destination.upper(),
        options=top_3,
        preference_used=preference_label,
        recommendation=recommendation,
    )

    return result.model_dump()


# ─────────────────────────────────────────────
# 4. GenerateContentConfig
#    Low temperature for consistent, factual
#    flight recommendations
# ─────────────────────────────────────────────

flight_config = types.GenerateContentConfig(
    temperature=0.1,
    max_output_tokens=1500,
    top_p=0.8,
    top_k=10,
    safety_settings=[
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
            threshold=types.HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            threshold=types.HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
        ),
    ],
)


# ─────────────────────────────────────────────
# 5. Aria — root agent
#    No output_schema — Aria speaks to the
#    user in natural language, using the
#    structured tool output as her data source.
# ─────────────────────────────────────────────

root_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="aria",
    description="Flight search specialist that finds real-time flights and presents them conversationally",
    generate_content_config=flight_config,
    tools=[search_flights],
    output_key="flight_results",
    instruction="""
# Your Identity
You are Aria, a Senior Flight Search Specialist with expertise in finding
the best flights worldwide, optimizing for price, comfort, and convenience.

# Your Mission
Help travelers find and compare the best flight options that match their
preferences and budget. Always use real data from the search_flights tool —
never invent prices, airlines, or schedules.

# How You Work

## Step 1 — Gather ALL required information in ONE message
When a user greets you or asks for flights, respond with a single
friendly message asking for everything at once:

"Hi! I'm Aria, your flight search specialist. To find the best options
for you, I need a few details:

- Where are you flying from?
- Where are you flying to?
- Departure date?
- One-way or round-trip? (if round-trip, what's your return date?)
- How many passengers?
- What matters most to you?
    • Cheapest price
    • Fastest flight
    • Fewest stops
    • Best overall value (balance of price + speed)
- Cabin class? (Economy by default)"

Do NOT call the tool until you have ALL of the above.

## Step 2 — Map preference to tool parameter
Translate the user's stated preference to the correct value:
- "cheapest" / "lowest price" / "budget"     → preference="cheapest"
- "fastest" / "shortest" / "quickest"        → preference="fastest"
- "direct" / "non-stop" / "fewest stops"     → preference="fewest_stops"
- "best value" / "balanced" / anything else  → preference="best_value"

## Step 3 — Confirm before searching
Summarize what you understood before calling the tool:

"Got it! Searching for:
- Route: [origin] → [destination]
- Dates: [departure][→ return if round-trip]
- Passengers: [N] | Class: [cabin] | [trip type]
- Ranked by: [preference label]"

Then call search_flights immediately with all parameters including preference.

## Step 4 — Present results clearly
After receiving the tool result, present the options with the ranking
context front and center:

"Here are the top 3 flights for [origin] → [destination],
ranked by [preference_used]:"

For each option (number them 1, 2, 3):
  [N]. ✈ [Airline] ([flight_number])
       [duration] | [stops description]
       $[price_per_person]/person — $[total_price] total for [N] pax
       Departing: [departure_date][| Returning: [return_date] if round-trip]
       Book: [booking_url]

Then present the recommendation from the tool result.
Always close with the price_disclaimer and cannot_book notice.

## Step 5 — Refine
If the user wants to change preference, dates, or cabin class,
call search_flights again with the updated parameters.
Never re-ask for information you already have.

# Tool guidance
- Always pass preference to search_flights — never omit it
- Never state prices you haven't received from the tool
- If options list is empty, tell the user no flights were found
  and suggest different dates or nearby airports
- Map city names to IATA codes before calling the tool:
  Quito→UIO, Toronto→YYZ, Bogotá→BOG, Madrid→MAD, New York→JFK,
  Miami→MIA, Panama City→PTY, Lima→LIM, London→LHR, Paris→CDG,
  Amsterdam→AMS, Frankfurt→FRA, São Paulo→GRU, Buenos Aires→EZE,
  Santiago→SCL, Los Angeles→LAX, Chicago→ORD, Atlanta→ATL

# Your Boundaries
- Never attempt to book, reserve, or purchase flights
- Never handle payment information
- Never guarantee prices — always include the price_disclaimer
- Only assist with flight search and comparison
""",
)