import os
import time

import pyodbc


SQL_CONNECTION_STRING_SETTING = "AZURE_SQL_CONNECTION_STRING"

TRANSIENT_ERROR_CODES = (
    "40197",
    "40501",
    "40613",
    "49918",
    "49919",
    "49920",
)
def is_transient_database_error(error):
    """Return True when Azure SQL indicates a temporary problem."""

    error_message = str(error)

    return any(
        code in error_message
        for code in TRANSIENT_ERROR_CODES
    )


def get_connection(max_attempts=6,
    retry_delay_seconds=10,):
    """Create and return an Azure SQL connection."""
    connection_string = os.environ.get(
        SQL_CONNECTION_STRING_SETTING
    )

    if not connection_string:
        raise RuntimeError(
            f"Missing environment variable: "
            f"{SQL_CONNECTION_STRING_SETTING}"
        )

    for attempt in range(1, max_attempts + 1):
        try:
            return pyodbc.connect(
                connection_string,
                timeout=30,
            )
        except pyodbc.Error as error:
            final_attempt = attempt == max_attempts

            if (
                final_attempt
                or not is_transient_database_error(error)
            ):
                raise

            time.sleep(retry_delay_seconds)

    raise RuntimeError("Could not connect to Azure SQL.")

def check_connection() -> bool:
    """Run SELECT 1 and confirm the databse is reachable.""" 
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 AS connection_test")
        row = cursor.fetchone()    
        return row is not None and row[0] == 1
    
    finally:
        conn.close()

SCHEMA_QUERY = """
   SELECT 
        TABLE_SCHEMA,
        TABLE_NAME,
        COLUMN_NAME,
        DATA_TYPE,
        IS_NULLABLE
    FROM INFORMATION_SCHEMA.COLUMNS
    WHERE TABLE_SCHEMA = 'dbo'
    ORDER BY
        TABLE_NAME,
        ORDINAL_POSITION;

"""


def get_schema() -> list[dict]:
    """Return table and column metadata for the prompt and debugging. """
    
    conn = get_connection()
    

    try:
        cursor = conn.cursor()
        cursor.execute(SCHEMA_QUERY)
        column_names = [column[0] for column in cursor.description]
        rows = cursor.fetchall()
    

        return[
        dict(zip(column_names, row))
        for row in rows
    ]
    finally:
        conn.close()


