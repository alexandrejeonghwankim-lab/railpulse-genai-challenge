import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

from azure_database import get_connection


load_dotenv()

SQLITE_PATH = Path(__file__).parent / "data" / "railpulse.db"



AZURE_SOURCES = {
    "agencies": "dbo.agencies",
    "routes": "dbo.routes",
    "service_exceptions": "dbo.service_exceptions",
    "services": "dbo.services",
    "stop_times": "dbo.stop_times",
    "stops": "dbo.stops",
    "trips": "dbo.trips",
    "vehicles": "dbo.vehicles",
}

BATCH_SIZE = 1000

def normalize_value(value):
    """Convert Azure values into SQLite-compatible values."""
    if value is None:
        return None

    if isinstance(value, (datetime,date)):
        return value.isoformat()

    if isinstance(value, Decimal):
        return float(value)

    if isinstance(value, bool):
        return int(value)

    if isinstance(value, bytearray):
        return bytes(value)

    return value 

def sqlite_type(type_code):
    """Map a pyodbc result type to a SQLite column type."""
    if type_code is bool:
        return "INTEGER"

    if type_code is int:
        return "INTEGER"

    if type_code in (float, Decimal):
        return "REAL"

    if type_code in (datetime, date):
        return "TEXT"

    if type_code in (bytes, bytearray):
        return "BLOB"

    return "TEXT"

def quote_identifier(name):
    """Safely quote a SQLite table or column identifier."""
    return '"' + name.replace('"', '""') + '"'

def quote_azure_identifier(name):
    """Safely quote an Azure SQL column identifier."""
    return "[" + name.replace("]", "]]") + "]"


def build_export_query(azure_conn, azure_name):
    """Build a SELECT that converts datetimeoffset values to text."""
    cursor = azure_conn.cursor()

    cursor.execute(
        """
        SELECT
            column_name,
            data_type
        FROM information_schema.columns
        WHERE table_schema = PARSENAME(?, 2)
          AND table_name = PARSENAME(?, 1)
        ORDER BY ordinal_position;
        """,
        azure_name,
        azure_name,
    )

    columns = cursor.fetchall()
    cursor.close()

    if not columns:
        raise RuntimeError(
            f"No columns found for Azure source: {azure_name}"
        )

    expressions = []

    for column_name, data_type in columns:
        quoted_name = quote_azure_identifier(column_name)

        if data_type.lower() == "datetimeoffset":
            expressions.append(
                f"CONVERT(nvarchar(50), "
                f"{quoted_name}, 127) AS {quoted_name}"
            )
        else:
            expressions.append(quoted_name)

    return (
        f"SELECT {', '.join(expressions)} "
        f"FROM {azure_name};"
    )


def export_source(azure_conn, sqlite_conn, local_name, azure_name):
    """Copy one Azure table or view into one SQLite table."""
 
    export_query = build_export_query(
    azure_conn,
    azure_name,
)

    azure_cursor = azure_conn.cursor()
    azure_cursor.execute(export_query)

    description = azure_cursor.description
    column_names = [
        column[0]
        for column in description 
    ]

    column_definitions =  [
        f"{quote_identifier(column[0])} {sqlite_type(column[1])}"
        for column in description
    ]

    local_table = quote_identifier(local_name)

    sqlite_conn.execute(
        f"DROP TABLE IF EXISTS {local_table}"
    )

    sqlite_conn.execute(
        f"""
CREATE TABLE {local_table} (
            {', '.join(column_definitions)}
        )
        """
    )

    quoted_columns = " , ".join(
        quote_identifier(name)
        for name in column_names
    )

    placeholders = " , ".join(
        "?"
        for _ in column_names
    )

    insert_sql = f"""
INSERT INTO {local_table} ({quoted_columns}) VALUES ({placeholders})"""

    exported_count = 0
    while True:
        rows = azure_cursor.fetchmany(BATCH_SIZE)
        if not rows:
            break

        normalized_rows = [
            tuple(
                normalize_value(value) 
                for value in row)
            for row in rows
        ]

        sqlite_conn.executemany(insert_sql, normalized_rows)
        exported_count += len(normalized_rows)

    azure_cursor.close()
    return exported_count 

    
    
def validate_export(sqlite_conn, expected_counts):
    """Confirm that exported SQLite row counts match Azure counts."""
    results = {}

    for table_name, expected_count in expected_counts.items():
        local_table = quote_identifier(table_name)

        actual_count = sqlite_conn.execute(
            f"SELECT COUNT(*) FROM {local_table};"
        ).fetchone()[0]

        results[table_name] = {
            "expected": expected_count,
            "actual": actual_count,
            "matches": expected_count == actual_count,
        }

    return results

def export_all():
    """Export the approved Azure sources into one SQLite database."""
    SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)

    azure_conn = None
    sqlite_conn = None

    try:
        azure_conn = get_connection()
        sqlite_conn = sqlite3.connect(SQLITE_PATH)

        exported_counts = {}

        for local_name, azure_name in AZURE_SOURCES.items():
            print(f"Exporting {azure_name}...")

            row_count = export_source(
                azure_conn,
                sqlite_conn,
                local_name,
                azure_name,
            )

            sqlite_conn.commit()
            exported_counts[local_name] = row_count

            print(f"  Exported {row_count} rows.")

        validation = validate_export(
            sqlite_conn,
            exported_counts,
        )

        print("\nValidation:")

        for table_name, result in validation.items():
            status = "OK" if result["matches"] else "FAILED"

            print(
                f"  {table_name}: "
                f"{result['actual']} rows [{status}]"
            )

        if not all(
            result["matches"]
            for result in validation.values()
        ):
            raise RuntimeError(
                "One or more SQLite row counts did not match."
            )

        print(f"\nSQLite backup created at: {SQLITE_PATH}")

    finally:
        if sqlite_conn is not None:
            sqlite_conn.close()

        if azure_conn is not None:
            azure_conn.close() 

if __name__ == "__main__":
    export_all()