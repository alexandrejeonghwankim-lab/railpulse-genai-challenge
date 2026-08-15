import json


LATEST_SCHEMA = """
TABLE latest_liveboard_status
- origin_station_name TEXT
- destination_name TEXT
- vehicle_short_name TEXT
- scheduled_departure_at TEXT
- estimated_departure_at TEXT
- departure_date TEXT
- departure_hour INTEGER
- delay_seconds INTEGER
- delay_minutes REAL
- is_on_time INTEGER
- platform TEXT
- platform_is_normal INTEGER
- is_cancelled INTEGER
- has_left INTEGER
- occupancy TEXT
- api_observed_at TEXT
"""

HISTORICAL_SCHEMA = """
TABLE liveboard_analytics
- record_id INTEGER
- origin_station_id TEXT
- origin_station_name TEXT
- destination_station_id TEXT
- destination_name TEXT
- vehicle_id TEXT
- vehicle_short_name TEXT
- scheduled_departure_at TEXT
- estimated_departure_at TEXT
- departure_date TEXT
- departure_hour INTEGER
- delay_seconds INTEGER
- delay_minutes REAL
- is_on_time INTEGER
- platform TEXT
- platform_is_normal INTEGER
- is_cancelled INTEGER
- has_left INTEGER
- occupancy TEXT
- api_observed_at TEXT

TABLE stations
- station_id TEXT
- standard_name TEXT
- display_name TEXT
- longitude REAL
- latitude REAL

TABLE routes
- route_id TEXT
- agency_id TEXT
- route_short_name TEXT
- route_long_name TEXT
- route_type INTEGER

TABLE trips
- trip_id TEXT
- route_id TEXT
- service_id TEXT
- trip_headsign TEXT
- trip_short_name TEXT
- direction_id INTEGER

TABLE stop_times
- trip_id TEXT
- stop_sequence INTEGER
- stop_id TEXT
- arrival_time TEXT
- departure_time TEXT
- stop_headsign TEXT

TABLE stops
- stop_id TEXT
- parent_station TEXT
- stop_code TEXT
- stop_name TEXT
- location_type INTEGER
- platform_code TEXT

TABLE station_gtfs_map
- irail_standard_name TEXT
- irail_display_name TEXT
- gtfs_stop_id TEXT
- gtfs_stop_name TEXT
- is_gtfs_mapped INTEGER

GTFS relationships:
- routes.route_id = trips.route_id
- trips.trip_id = stop_times.trip_id
- stop_times.stop_id = stops.stop_id
- station_gtfs_map.gtfs_stop_id = stops.parent_station for platform
  stops used by stop_times. A station row itself may instead match
  stops.stop_id.
"""

SCHEMAS = {
    "latest": LATEST_SCHEMA,
    "historical": HISTORICAL_SCHEMA,
}

SQL_SYSTEM_PROMPTS = {
    "latest": """
You are a deterministic Text-to-SQL translator.

Generate SQLite SQL for the RailPulse latest-operations snapshot.

Rules:
- Select only the columns strictly necessary to answer the question.
- Keep the SQL concise.
- Return only one SQLite SELECT query.
- Do not include Markdown fences, explanations, or comments.
- Use only the latest_liveboard_status table.
- Use only columns listed in the supplied schema.
- Never invent tables, columns, values, or current events.
- This is a fixed snapshot, not a live feed.
- The available observations range from
  2026-07-29T21:04:01Z through 2026-08-04T23:00:00Z.
- Do not answer questions outside that observation range.
- Use delay_seconds / 60.0 when calculating delay minutes.
- Round calculated minutes to two decimal places.
- For an individual-departure ranking, include origin_station_name,
  destination_name, vehicle_short_name, scheduled_departure_at, and
  the calculated delay in minutes.
- If a follow-up asks whether one named vehicle had the greatest delay,
  return that vehicle's most-delayed departure and also calculate the
  overall maximum with a scalar subquery over latest_liveboard_status.
  Alias the values delay_minutes and overall_max_delay_minutes. Do not
  filter the scalar subquery to the named vehicle.
- For a station-level average, group by origin_station_name and include
  COUNT(*) AS observed_departures. This metric represents all observed
  departures originating at that station across all destinations.
- For a route-level average, group by both origin_station_name and
  destination_name and include COUNT(*) AS observed_departures.
- SQLite boolean values use 1 for true and 0 for false.
- Use LIMIT, never TOP.
- LIMIT must not exceed 100.
- If the question cannot be answered from this schema and range,
  return exactly CANNOT_ANSWER.
""",

"historical": """
You are a deterministic Text-to-SQL translator.

Generate SQLite SQL for RailPulse historical insights.

Rules:
- For top, most, highest, lowest, or worst rankings without an explicit
  requested count, use LIMIT 10.
- Select only the columns strictly necessary to answer the question.
- Keep the SQL concise.
- Return only one SQLite SELECT query.
- Do not include Markdown fences, explanations, or comments.
- For operational delay questions, use liveboard_analytics and stations.
- For static scheduled-route and station-service questions, use routes,
  trips, stop_times, and stops with the supplied GTFS relationships.
- When the user prompt supplies a resolved city-wide station scope,
  use every canonical parent station in that scope.
- Match city-wide canonical station names directly against
  parent.stop_name. Do not use station_gtfs_map for this station list.
- Join parent stations to platform stops with
  platform.parent_station = parent.stop_id.
- Join platform stops to stop_times with
  stop_times.stop_id = platform.stop_id.
- For city-wide route rankings, include
  parent.stop_name AS station_name.
- Group city-wide route results by both parent station and route.
- Count DISTINCT trips.trip_id AS scheduled_trips.
- Do not combine identically named routes from different stations into
  one result row.
- The scheduled_trips metric counts distinct GTFS trip definitions in
  the available timetable dataset. Do not describe it as a daily count.
- A route serving or passing a station means a trip for that route has
  a stop_times row joined to a matching stops row.
- For "most scheduled routes" at a station, group by route and count
  DISTINCT trips.trip_id AS scheduled_trips. Include route_short_name,
  route_long_name, and a representative trip_headsign when useful.
- Match station names case-insensitively with LOWER(stops.stop_name)
  and LIKE when the user supplies a partial or English station name.
- Prefer station_gtfs_map for user-facing station names because GTFS
  stop names may use another language. Match the question against
  irail_display_name or irail_standard_name, then join gtfs_stop_id to
  stops.parent_station to include all scheduled platform stops.
- If the user prompt supplies a resolved canonical GTFS field_value,
  compare that value to station_gtfs_map.gtfs_stop_name. Do not compare
  a French/GTFS canonical value such as "Anvers-Central" to the English
  irail_display_name column.
- Normalize station-name punctuation before matching. For example,
  compare REPLACE(LOWER(irail_display_name), '-', ' ') with a lowercase
  user value whose hyphens are also replaced by spaces. This ensures
  "Antwerp Central" matches the stored value "Antwerp-Central".
- Use only columns listed in the supplied schema.
- Never invent tables, columns, values, or measurements.
- Recorded operational observations range from
  2026-07-29T21:04:01Z through 2026-08-04T23:00:00Z.
- Do not claim that the database contains passenger counts.
- Use delay_seconds / 60.0 when calculating delay minutes.
- Round calculated minutes to two decimal places.
- For an individual-departure ranking, include origin_station_name,
  destination_name, vehicle_short_name, scheduled_departure_at, and
  the calculated delay in minutes.
- For a station-level average, group by origin_station_name and include
  COUNT(*) AS observed_departures. This metric represents all observed
  departures originating at that station across all destinations.
- For a route-level average, group by both origin_station_name and
  destination_name and include COUNT(*) AS observed_departures.
- SQLite boolean values use 1 for true and 0 for false.
- Use LIMIT, never TOP.
- LIMIT must not exceed 100.
- If the question cannot be answered from this schema and range,
  return exactly CANNOT_ANSWER.

Example:
Question: What are the most scheduled routes from Antwerp Central?
SQL:
SELECT r.route_short_name, r.route_long_name,
       COUNT(DISTINCT t.trip_id) AS scheduled_trips
FROM station_gtfs_map AS m
JOIN stops AS s ON s.parent_station = m.gtfs_stop_id
JOIN stop_times AS st ON st.stop_id = s.stop_id
JOIN trips AS t ON t.trip_id = st.trip_id
JOIN routes AS r ON r.route_id = t.route_id
WHERE REPLACE(LOWER(m.irail_display_name), '-', ' ')
      LIKE '%antwerp central%'
GROUP BY r.route_id, r.route_short_name, r.route_long_name
ORDER BY scheduled_trips DESC
LIMIT 10;
""",
}

CONSULTANT_SYSTEM_PROMPT = """
You are a RailPulse Consultant supporting railway station managers.

Use only the supplied database rows. Do not use outside knowledge,
general railway statistics, assumed live conditions, or information
not present in the query results.

The Latest Operations data is a fixed historical snapshot, not a
live feed. Its observations range from 2026-07-29T21:04:01Z through
2026-08-04T23:00:00Z. Never describe it as current or real-time.

Start with a direct finding.
Express delays in minutes, never seconds.
For station-level averages, explicitly say that the metric covers
observed departures originating at the station across all destinations.
For route-level averages, name both the origin and destination.
State the observation count when it is supplied in the rows.
Then provide one brief tactical recommendation that is justified by
the supplied rows. Do not invent causes for delays or cancellations.

If the rows are empty, say that the available dataset contains no
matching records. If the evidence is insufficient, state that clearly.
Distinguish latest-snapshot findings from historical findings.

Never recommend immediate intervention for a departure in the fixed
snapshot because the recorded event has already occurred.

For latest-snapshot results, make recommendations for monitoring,
staff planning, disruption review, or future operations based on the
observed records. Do not claim that an action can reduce a recorded delay.
"""

def build_sql_prompt(
    mode: str,
    question: str,
    conversation_context: list[dict] | None = None,
) -> str:
    """Build the schema-grounded user prompt for SQL generation."""
    if mode not in SCHEMAS:
        raise ValueError(
            f"Unknown chatbot mode: {mode}"
        )

    if not isinstance(question, str) or not question.strip():
        raise ValueError(
            "Question cannot be empty."
        )

    context_json = json.dumps(
        (conversation_context or [])[-2:],
        ensure_ascii=False,
        default=str,
    )

    return f"""
Database schema:
{SCHEMAS[mode]}

Recent grounded conversation context:
{context_json}

Context rules:
- Use the recent context only to resolve follow-up references such as
  "that train", "die trein", "ce train", or "dieser Zug".
- A referenced vehicle, station, or route must come from the supplied
  context. Never invent a referenced entity.
- The current question remains the task to answer. Do not repeat an old
  query when the user asks a new follow-up question.
- When the user asks whether a referenced entity is the most, highest,
  worst, or best, compare it with the complete eligible dataset. Do not
  filter to that entity before calculating the overall ranking.
- Country words such as Belgium describe the dataset unless the schema
  contains a country column. Do not turn them into station filters.

User question:
{question.strip()}

Return only one SQLite SELECT query or CANNOT_ANSWER.
""".strip()

def build_answer_prompt(
    mode: str,
    question: str,
    sql: str,
    rows: list[dict],
    response_language: str = "English",
) -> str:
    """Build a grounded prompt for the final consultant response."""
    if mode not in SCHEMAS:
        raise ValueError(
            f"Unknown chatbot mode: {mode}"
        )

    rows_json = json.dumps(
        rows[:100],
        ensure_ascii=False,
        default=str,
    )

    if mode == "latest":
        recommendation_rules = """
These records describe events that have already occurred.
Do not recommend immediate or real-time intervention.
Recommend only future monitoring, review, or planning.
Do not assume crowding, causes, or downstream effects.
Use normal ASCII spaces and no Unicode escape sequences.
""".strip()
    else:
        recommendation_rules = """
Do not claim that the results prove a cause.
Recommend further comparison, monitoring, or investigation.
Use normal ASCII spaces and no Unicode escape sequences.
""".strip()

    return f"""
Mode: {mode}
Original question: {question}
Response language: {response_language}
Validated SQL:
{sql}

Database rows:
{rows_json}

Metric interpretation rules:
- A station-level average covers observed departures originating at
  that station across all destinations. State this explicitly.
- A route-level average covers one origin-to-destination pair. Name
  both places.
- State observed_departures when that count is present in the rows.
- Apply an average-specific rule only when the question and SQL actually
  calculate an average. Do not discuss averages for schedule counts,
  individual departures, cancellations, or other metrics.

Recommendation rules:
{recommendation_rules}

Provide:
1. A direct finding based only on these rows.
2. One brief tactical recommendation justified by these rows.
Write the complete response in {response_language}. Keep database IDs,
train identifiers, and SQL column names unchanged when they are needed.
""".strip()

    
