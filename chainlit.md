# RailPulse Consultant

RailPulse Consultant helps railway stakeholders explore operational and
timetable data using natural-language questions. It generates a read-only
SQL query, validates it, queries the local RailPulse database, and returns
a concise finding with a grounded recommendation.

## Choose The Data Mode

Open the settings menu beside the message input and select a mode.

### Latest Operations

Uses a fixed snapshot of observed departures from **29 July through
4 August 2026**. This is not a live feed, and recorded departures have
already occurred.

Example questions:

- Which departures had the longest delays?
- Which stations had the highest average delay?
- Which origin-to-destination routes had the highest average delay?

### Historical Insights

Uses exported operational records and static GTFS timetable data for
station, route, trip, and stop analysis.

Example questions:

- What are the most scheduled routes from Antwerp Central?
- Which routes are most scheduled across Antwerp?
- Welke routes zijn het meeste gepland vanuit Antwerpen?

When a city name represents multiple stations, RailPulse lists the
stations included in the analysis and keeps station-level results separate.

## Choose The Language

The settings menu provides automatic question-language detection plus
English, Nederlands, Français, and Deutsch. Automatic mode is recommended
for normal use. Select an explicit language when a short or ambiguous
question does not contain enough language clues.

Station names and route endpoints are localized when translations are
available. Official or international station names may remain bilingual.

## Inspect The SQL

Generated SQL is hidden by default. After a successful database question:

1. Select **Show SQL**, **SQL tonen**, or its translated equivalent.
2. The validated read-only query appears beneath the answer.
3. Select the same action again to remove the query.

The displayed SQL is the validated query that was executed against SQLite.

## Follow-Up Questions

RailPulse keeps a short, separate conversation context for each data mode.

```text
Which train had the longest delay?
Where did that train depart from and where was it going?
How many minutes was that train delayed?
```

Starting a new chat or restarting the application clears this context.

## Data Limitations

RailPulse can answer only from the exported local database.

- Latest Operations is a historical snapshot, not current railway data.
- The application cannot predict tomorrow's delays.
- Passenger counts and weather data are not available.
- The database does not provide verified causes for individual delays.
- `scheduled_trips` counts distinct GTFS trip definitions in the exported
  timetable; it is not automatically a daily departure count.
- Date-specific schedules require GTFS service calendars and exceptions.
- An empty result means a valid query found no matching exported records;
  it does not prove that the event never occurred outside this dataset.

## Safeguards

RailPulse uses safeguards to protect the database and keep answers grounded
in the available data. For this reason, not every request can be accepted.
Questions must be answerable from the RailPulse dataset and compatible with
read-only access.
