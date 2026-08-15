import sqlite3
import re
import unicodedata
from pathlib import Path

DATABASE_PATH = (
    Path(__file__).resolve().parent
    / "data"
    / "railpulse.db"
)

MAX_RESULT_ROWS = 100


def get_connection():
    """Open the local SQLite database in read-only mode."""
    if not DATABASE_PATH.exists():
        raise FileNotFoundError(
            f"SQLite database not found: {DATABASE_PATH}"
        )

    connection = sqlite3.connect(
        f"{DATABASE_PATH.as_uri()}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row

    return connection

def check_connection() -> bool:
    """Confirm that the local SQLite database is reachable."""
    connection = get_connection()

    try:
        row = connection.execute(
            "SELECT 1 AS connection_test;"
        ).fetchone()

        return row is not None and row["connection_test"] == 1
    finally:
        connection.close()

def quote_identifier(name: str) -> str:
    """Safely quote a SQLite identifier."""
    return '"' + name.replace('"', '""') + '"'


def get_schema() -> dict[str, list[dict]]:
    """Return the local SQLite table and column metadata."""
    connection = get_connection()

    try:
        table_rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name;
            """
        ).fetchall()

        schema = {}

        for table_row in table_rows:
            table_name = table_row["name"]
            quoted_table = quote_identifier(table_name)

            columns = connection.execute(
                f"PRAGMA table_info({quoted_table});"
            ).fetchall()

            schema[table_name] = [
                {
                    "name": column["name"],
                    "type": column["type"],
                    "nullable": not bool(column["notnull"]),
                    "primary_key": bool(column["pk"]),
                }
                for column in columns
            ]

        return schema
    finally:
        connection.close()


def execute_read_query(sql: str) -> list[dict]:
    """Execute validated read-only SQL and return limited rows."""
    connection = get_connection()

    try:
        cursor = connection.execute(sql)
        rows = cursor.fetchmany(MAX_RESULT_ROWS)

        return [
            dict(row)
            for row in rows
        ]
    finally:
        connection.close()


def _normalize_search_text(value: str) -> str:
    """Normalize user-facing names for boundary-safe matching."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_value = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return " ".join(re.findall(r"[a-z0-9]+", ascii_value))


def find_gtfs_station_group_by_display_prefix(
    question: str,
) -> list[str]:
    """Resolve an unambiguous display-name city prefix to GTFS stops."""
    normalized_question = f" {_normalize_search_text(question)} "
    connection = get_connection()

    try:
        mapping_rows = connection.execute(
            """
            SELECT DISTINCT irail_display_name, gtfs_stop_name
            FROM station_gtfs_map
            WHERE is_gtfs_mapped = 1
              AND irail_display_name IS NOT NULL
              AND gtfs_stop_name IS NOT NULL
            """
        ).fetchall()

        matched_prefixes: dict[str, set[str]] = {}

        for row in mapping_rows:
            display_prefix = row["irail_display_name"].split("-", 1)[0]
            canonical_prefix = row["gtfs_stop_name"].split("-", 1)[0]
            normalized_prefix = _normalize_search_text(display_prefix)

            if f" {normalized_prefix} " in normalized_question:
                matched_prefixes.setdefault(
                    normalized_prefix,
                    set(),
                ).add(canonical_prefix)

        if not matched_prefixes:
            return []

        longest_length = max(len(prefix) for prefix in matched_prefixes)
        canonical_prefixes = set().union(
            *(
                values
                for prefix, values in matched_prefixes.items()
                if len(prefix) == longest_length
            )
        )

        if len(canonical_prefixes) != 1:
            return []

        canonical_prefix = next(iter(canonical_prefixes))
        rows = connection.execute(
            """
            SELECT DISTINCT stop_name
            FROM stops
            WHERE location_type = 1
              AND (stop_name = ? OR stop_name LIKE ?)
            ORDER BY stop_name
            LIMIT 20
            """,
            (canonical_prefix, f"{canonical_prefix}-%"),
        ).fetchall()

        return [row["stop_name"] for row in rows]
    finally:
        connection.close()

def verify_gtfs_stations(
    station_names: list[str],
) -> list[str]:
    """Return canonical parent stations that exist in SQLite."""
    if not station_names:
        return []

    unique_names = list(dict.fromkeys(station_names))

    if len(unique_names) > 20:
        raise ValueError(
            "Station verification is limited to 20 names."
        )

    placeholders = ", ".join("?" for _ in unique_names)

    sql = f"""
        SELECT DISTINCT stop_name
        FROM stops
        WHERE location_type = 1
          AND stop_name IN ({placeholders})
        ORDER BY stop_name
    """

    connection = get_connection()

    try:
        rows = connection.execute(
            sql,
            unique_names,
        ).fetchall()

        return [row["stop_name"] for row in rows]
    finally:
        connection.close()

def find_gtfs_stations(search_name: str) -> list[str]:
    """Find canonical parent stations matching a city or station name."""
    connection = get_connection()

    try:
        rows = connection.execute(
            """
            SELECT DISTINCT stop_name
            FROM stops
            WHERE location_type = 1
              AND LOWER(stop_name) LIKE ?
            ORDER BY stop_name
            LIMIT 20
            """,
            (f"%{search_name.casefold()}%",),
        ).fetchall()

        return [row["stop_name"] for row in rows]
    finally:
        connection.close()
