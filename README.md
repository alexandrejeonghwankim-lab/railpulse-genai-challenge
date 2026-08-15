# RailPulse GenAI Challenge

RailPulse Consultant is a multilingual railway operations assistant built
for the Sprint 4 GenAI challenge. It translates natural-language questions
into validated, read-only SQLite queries and turns the returned rows into a
concise operational finding and tactical recommendation.

The application extends the Sprint 3 Azure SQL and Power BI project. Azure
was used as the original data source, but normal development and the final
demo run entirely against a local SQLite backup to avoid ongoing cloud cost.

## MVP Status

The four required capabilities are implemented:

- **Text-to-SQL:** Groq generates SQLite queries from user questions with
  temperature `0`, schema grounding, validation, and one controlled retry.
- **RailPulse consulting:** Answers contain a direct database-grounded
  finding and a brief recommendation.
- **Metric conversion:** Delays stored in seconds are systematically
  expressed in minutes.
- **Chat interface:** Chainlit provides data-mode and language controls,
  result tables, follow-up context, and optional validated SQL display.

The project also includes a strict SQL safety layer, multilingual station
resolution, local database export tooling, and localized failure messages.

## Main Features

- Latest Operations and Historical Insights modes.
- English, Dutch, French, and German questions and answers.
- Automatic question-language detection or explicit language selection.
- Short, mode-specific conversation context for follow-up references.
- Dynamic city-level station resolution derived from GTFS translations.
- Read-only SQLite runtime with no Azure dependency.
- Approved-table allowlists, forbidden-keyword checks, one-statement
  enforcement, and a maximum result limit.
- SQL hidden by default and available through a per-response toggle.
- Clear responses for unsupported, unsafe, empty-result, and service-error
  cases.

## Data Modes

### Latest Operations

Uses `latest_liveboard_status`, a fixed snapshot of observed departures from
**29 July through 4 August 2026**. It is not a live feed. Recommendations
therefore concern future monitoring, review, and planning rather than
intervention in departures that have already occurred.

Suitable questions include:

```text
Which departures had the longest delays?
Which stations had the highest average delay?
Which origin-to-destination routes had the highest average delay?
```

### Historical Insights

Uses historical operational observations and static GTFS tables for delay,
station, route, trip, and stop analysis.

Suitable questions include:

```text
What are the most scheduled routes from Antwerp Central?
Which routes are most scheduled across Antwerp?
Welke routes zijn het meeste gepland vanuit Antwerpen?
```

An exact station such as `Antwerpen-Centraal` remains an exact-station
request. A city reference such as `Antwerpen`, `Anvers`, or `Antwerp` is
resolved to verified parent stations, and route results remain grouped by
both station and route.

`scheduled_trips` counts distinct GTFS trip definitions in the exported
timetable. It is not automatically a count of departures on a selected day.

## Architecture

```text
User question
    -> Chainlit mode and language settings
    -> bounded conversation and station resolution
    -> Groq Text-to-SQL generation
    -> SQL validation and controlled retry
    -> read-only local SQLite execution
    -> localized rows
    -> grounded RailPulse recommendation
```

Primary modules:

```text
app.py                 Chainlit interface and session state
assistant.py           End-to-end orchestration and controlled retries
database.py            Read-only SQLite access and station verification
sql_guard.py           SQL safety and table allowlists
prompts.py             Schemas and mode-specific prompt rules
llm_client.py          Groq client
translations.py        Language, station, and result localization
translations.txt       GTFS translation source
azure_database.py      Optional legacy Azure connection helper
azure_export.py        One-time Azure-to-SQLite export utility
```

## Requirements

- Python 3.13
- Internet access for Groq
- A Groq developer API key
- The exported `railpulse.db` file

Python 3.13 is recommended for this project because the Chainlit frontend
did not serve correctly in the previously tested Python 3.14 environment.

## Installation

Open PowerShell in the repository root:

```powershell
cd C:\BeCode_data\railpulse-genai-challenge
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks environment activation, the environment interpreter
can still be called directly:

```powershell
.\.venv\Scripts\python.exe --version
```

## Environment Configuration

Create the private environment file from the committed template:

```powershell
Copy-Item .env.example .env
```

Add the Groq credentials to `.env`:

```dotenv
GROQ_API_KEY=your_groq_api_key
GROQ_MODEL=llama-3.3-70b-versatile
```

`GROQ_MODEL` is optional and defaults to
`llama-3.3-70b-versatile`. Never commit `.env`.

`AZURE_SQL_CONNECTION_STRING` is needed only for the optional legacy export
utilities. Chainlit does not use Azure SQL at runtime.

## Local Database

Place the SQLite backup at:

```text
data/railpulse.db
```

The database is approximately 431 MB and is excluded from Git because it
exceeds GitHub's normal per-file size limit. Obtain the backup artifact
separately and keep the filename and location unchanged.

Verify it before starting Chainlit:

```powershell
python -c "from database import check_connection; print(check_connection())"
```

Expected output:

```text
True
```

## Run Chainlit

```powershell
.\.venv\Scripts\Activate.ps1
python -m chainlit run app.py
```

Open the URL printed in the terminal, normally:

```text
http://localhost:8000
```

For a fresh browser origin during troubleshooting:

```powershell
.\.venv\Scripts\python.exe -m chainlit run .\app.py --port 8001 --no-cache
```

Open the settings menu beside the message input to choose:

- Latest Operations or Historical Insights.
- Automatic or explicit response language.
- Optional technical details.

The **Show SQL** action displays the validated executed query beneath the
answer. Selecting the same action again removes that SQL message.

The in-application **Readme** contains a shorter stakeholder-facing usage
guide from `chainlit.md`.

## Conversation Context

Each mode retains the two most recent successful turns and at most five
rows per turn. Only validated SQL and database results enter this context;
generated recommendation prose is not reused as evidence.

Example:

```text
Which train had the longest delay?
Where did that train depart from and where was it going?
How many minutes was that train delayed?
```

Latest and Historical context remain separate. Starting a new browser chat
or restarting Chainlit clears the context.

## Multilingual Station Resolution

`translations.py` builds a cached multilingual station-prefix index from
`translations.txt`. Candidate canonical GTFS station names are verified
against SQLite before they reach Text-to-SQL.

The first English test revealed that the city-only form `Antwerp` was not
present in the GTFS translations. A secondary, database-driven resolver now
uses `station_gtfs_map` to map user-facing display prefixes to canonical
GTFS prefixes without maintaining a hardcoded city dictionary. Ambiguous
fallback mappings are rejected.

Verified city-wide questions in English, Dutch, French, and German resolve
to eight Antwerp stations and return localized station-and-route results.

## Safety And Failure Handling

The application uses several independent safeguards:

- SQLite is opened in read-only mode.
- Only one read query is accepted.
- Destructive keywords and multiple statements are rejected.
- Tables are restricted separately for each mode.
- Query results are limited to at most 100 rows.
- Explicit modification requests are blocked before a Groq call.
- Invalid generated SQL receives at most one controlled correction attempt.
- City-wide results require a non-empty `station_name` for every row.

The interface distinguishes:

- Questions that the available schema cannot answer.
- Valid queries with no matching rows.
- Unsafe modification requests.
- Request-processing and external-service failures.

## Verified Scenarios

The following workflows were tested against Groq and the local database:

- Latest individual delay ranking.
- Latest station and route averages in minutes.
- Latest follow-up reference resolution.
- Historical exact-station scheduled routes.
- Historical city-wide scheduled routes.
- English, Dutch, French, and German Antwerp city resolution.
- Unknown or unsupported questions.
- Modification requests such as `DELETE`, `DROP`, and `UPDATE ... SET`.
- Optional validated SQL display and removal.

The multilingual city regression verifies the expected language, eight
stations, validated SQLite SQL, `LIMIT 10`, localized results, and a
localized consultant answer.

## Data Limitations

- Latest Operations is a fixed historical snapshot, not current data.
- The assistant cannot predict future delays.
- Passenger counts and weather information are not available.
- The exported data does not provide verified causes for individual delays.
- Static GTFS trip counts do not prove that a trip operates on a particular
  date. Date-specific answers require `services` and `service_exceptions`.
- An empty query result means no matching exported rows were found; it does
  not prove that an event never occurred outside the dataset.
- Groq requires internet access and is subject to developer-tier limits.

## Development Verification

Compile the main modules:

```powershell
python -m py_compile app.py assistant.py database.py llm_client.py prompts.py sql_guard.py translations.py
```

Check the installed environment:

```powershell
python -m pip check
```

Before committing, verify that secrets and the large database are ignored:

```powershell
git check-ignore .env
git check-ignore data\railpulse.db
```

## Optional Azure Export

The application does not require Azure SQL. The retained
`azure_database.py` and `azure_export.py` files document the original
one-time export process. Running them again requires an active Azure SQL
database, `pyodbc`, a compatible Microsoft ODBC driver, and
`AZURE_SQL_CONNECTION_STRING` in `.env`.

## Project Documentation

- `Initial_plan.md` records architecture decisions, completed milestones,
  regressions, corrections, and remaining work.
- `chainlit.md` is the concise in-app usage and limitation guide.
- `README_DRAFT.md` preserves the pre-final documentation draft for review.
