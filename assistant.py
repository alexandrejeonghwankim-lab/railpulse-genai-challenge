import re

from database import (
    execute_read_query,
    find_gtfs_station_group_by_display_prefix,
    verify_gtfs_stations,
)
from llm_client import generate_text
from prompts import (
    CONSULTANT_SYSTEM_PROMPT,
    SQL_SYSTEM_PROMPTS,
    build_answer_prompt,
    build_sql_prompt,
)
from sql_guard import SQLValidationError, validate_sql
from translations import (
    LANGUAGE_NAMES,
    add_canonical_station_context,
    find_station_aliases,
    find_station_group,
    get_ui_text,
    normalize_name,
    resolve_language,
    translate_rows,
    translate_value,
)


SUPPORTED_MODES = {
    "latest",
    "historical",
}

CANNOT_ANSWER = "CANNOT_ANSWER"

SQL_RETRY_INSTRUCTION = """
The previous response was invalid or incomplete.

Return one complete, concise SQLite SELECT query.
It must include FROM, use only approved tables and columns,
and include LIMIT no greater than 100.

Return only SQL or CANNOT_ANSWER.
""".strip()


class AssistantError(RuntimeError):
    """Raised when the chatbot workflow cannot complete."""


class UnsafeRequestError(AssistantError):
    """Raised when a user asks to modify the database."""


UNSAFE_REQUEST_PATTERN = re.compile(
    r"\b(delete|drop|truncate|insert|alter|"
    r"verwijder|verwijderen|wis|wissen|supprime|supprimer|efface|"
    r"lösche|löschen|losche|loschen|entferne|entfernen)\b|"
    r"\bupdate\s+[a-z0-9_]+\s+set\b|"
    r"\bcreate\s+(table|view|index)\b|"
    r"\breplace\s+into\b",
    re.IGNORECASE,
)

def validate_request(mode: str, question: str) -> str:
    """Validate mode and return a cleaned user question."""
    if mode not in SUPPORTED_MODES:
        raise AssistantError(
            f"Unknown chatbot mode: {mode}"
        )

    if not isinstance(question, str) or not question.strip():
        raise AssistantError(
            "Question cannot be empty."
        )

    cleaned_question = question.strip()

    if UNSAFE_REQUEST_PATTERN.search(
        normalize_name(cleaned_question)
    ):
        raise UnsafeRequestError(
            "Database modification requests are blocked."
        )

    return cleaned_question

def build_historical_station_scope(
    question: str,
    language: str,
) -> tuple[str, dict | None]:
    """Resolve an ambiguous city reference to verified stations."""
    if find_station_aliases(question):
        return question, None

    discovered = find_station_group(question)

    if not discovered:
        discovered = find_gtfs_station_group_by_display_prefix(
            question
        )

    verified = verify_gtfs_stations(discovered)

    if len(verified) < 2:
        return question, None

    canonical_list = "\n".join(
        f"- {station}" for station in verified
    )

    localized = [
        translate_value(
            station,
            language,
            "stop_name",
        )
        for station in verified
    ]

    enriched_question = f"""
{question}

Resolved city-wide station scope:
{canonical_list}

Use every supplied canonical parent station.
Match these values directly against the parent stops.stop_name column.
Join platform stops with platform.parent_station = parent.stop_id.
For route rankings, group by parent station and route.
Include parent.stop_name AS station_name in the result.
Do not use station_gtfs_map for this city-wide station list.
""".strip()

    scope = {
        "type": "city_wide",
        "canonical_stations": verified,
        "localized_stations": localized,
    }

    return enriched_question, scope


def clean_generated_sql(generated_sql: str) -> str:
    """Remove an optional SQL Markdown fence."""
    if not isinstance(generated_sql, str):
        raise AssistantError(
            "The model returned an invalid SQL response."
        )

    cleaned = generated_sql.strip()

    if cleaned.startswith("```sql") and cleaned.endswith("```"):
        cleaned = cleaned[6:-3].strip()
    elif cleaned.startswith("```") and cleaned.endswith("```"):
        cleaned = cleaned[3:-3].strip()

    return cleaned

def generate_sql(
    mode: str,
    question: str,
    correction: str | None = None,
    conversation_context: list[dict] | None = None,
) -> str | None:
    """Generate safe SQL, retrying once after invalid output."""
    user_prompt = build_sql_prompt(
        mode,
        question,
        conversation_context=conversation_context,
    )

    if correction:
        user_prompt = (
            f"{user_prompt}\n\n"
            "The previous validated query failed in SQLite.\n"
            f"{correction}\n"
            "Return a corrected query using only the supplied schema."
        )

    last_error = None

    for attempt in range(2):
        if attempt == 1:
            user_prompt = (
                f"{user_prompt}\n\n"
                f"{SQL_RETRY_INSTRUCTION}\n"
                f"Validation error: {last_error}"
            )

        generated_sql = generate_text(
            system_prompt=SQL_SYSTEM_PROMPTS[mode],
            user_prompt=user_prompt,
            temperature=0.0,
            max_tokens=800,
        )

        cleaned_sql = clean_generated_sql(
            generated_sql
        )

        if cleaned_sql.upper() == CANNOT_ANSWER:
            return None

        try:
            return validate_sql(
                cleaned_sql,
                mode,
            )
        except SQLValidationError as error:
            last_error = error

    raise AssistantError(
        "The model could not generate a valid SQL query."
    ) from last_error

def generate_consultant_answer(
    mode: str,
    question: str,
    sql: str,
    rows: list[dict],
    language: str,
) -> str:
    """Turn query results into a grounded recommendation."""
    answer_prompt = build_answer_prompt(
        mode=mode,
        question=question,
        sql=sql,
        rows=rows,
        response_language=LANGUAGE_NAMES[language],
    )

    return generate_text(
        system_prompt=CONSULTANT_SYSTEM_PROMPT,
        user_prompt=answer_prompt,
        temperature=0.2,
        max_tokens=500,
    )
def answer_question(
    mode: str,
    question: str,
    language: str = "auto",
    conversation_context: list[dict] | None = None,
) -> dict:
    """Run the complete RailPulse chatbot workflow."""
    cleaned_question = validate_request(
        mode,
        question,
    )
    resolved_language = resolve_language(
        language,
        cleaned_question,
    )
    station_scope = None

    if mode == "historical":
        scoped_question, station_scope = (
            build_historical_station_scope(
                cleaned_question,
                resolved_language,
            )
        )
    else:
        scoped_question = cleaned_question

    if station_scope:
        sql_question = scoped_question
    else:
        sql_question = add_canonical_station_context(
            scoped_question
        )

    correction = None
    execution_error = None

    for execution_attempt in range(2):
        safe_sql = generate_sql(
            mode,
            sql_question,
            correction=correction,
            conversation_context=conversation_context,
        )

        if safe_sql is None:
            return {
                "status": "cannot_answer",
                "mode": mode,
                "language": resolved_language,
                "question": cleaned_question,
                "sql": None,
                "rows": [],
                "answer": get_ui_text(
                    "cannot_answer",
                    resolved_language,
                ),
                "station_scope": station_scope,
            }

        try:
            rows = execute_read_query(safe_sql)
        except Exception as error:
            execution_error = error
            correction = (
                f"Failed SQL:\n{safe_sql}\n"
                f"SQLite error: {error}"
            )
        else:
            missing_station_names = (
                station_scope
                and rows
                and any(
                    not row.get("station_name")
                    for row in rows
                )
            )

            if missing_station_names:
                correction = (
                    "The city-wide query returned a missing station_name. "
                    "Select parent.stop_name AS station_name directly, "
                    "and group by parent.stop_id and parent.stop_name. "
                    "Do not select station_gtfs_map columns or nullable "
                    "expressions for station_name."
                )
                continue

            if rows or execution_attempt == 1:
                break

            correction = (
                f"The SQL executed but returned zero rows:\n{safe_sql}\n"
                "Check station-name punctuation and language mapping. "
                "Normalize hyphens and spaces with REPLACE and LOWER, "
                "and use station_gtfs_map for user-facing station names. "
                "When a canonical GTFS field_value was supplied, filter "
                "station_gtfs_map.gtfs_stop_name rather than "
                "irail_display_name."
            )
    else:
        raise AssistantError(
            "The generated query could not be executed after one retry."
        ) from execution_error

    if not rows:
        return {
            "status": "no_results",
            "mode": mode,
            "language": resolved_language,
            "question": cleaned_question,
            "sql": safe_sql,
            "rows": [],
            "answer": get_ui_text(
                "no_results",
                resolved_language,
            ),
            "station_scope": station_scope,
        }

    localized_rows = translate_rows(
        rows,
        resolved_language,
    )

    answer = generate_consultant_answer(
        mode=mode,
        question=cleaned_question,
        sql=safe_sql,
        rows=localized_rows,
        language=resolved_language,
    )

    return {
        "status": "success",
        "mode": mode,
        "language": resolved_language,
        "question": cleaned_question,
        "sql": safe_sql,
        "rows": localized_rows,
        "answer": answer,
        "station_scope": station_scope,
    }
