import re



TABLE_REFERENCE_PATTERN = re.compile(
    r'\b(?:FROM|JOIN)\s+["`\[]?([A-Za-z_][A-Za-z0-9_]*)',
    re.IGNORECASE,
)


ALLOWED_TABLES = {
    "latest": {
        "latest_liveboard_status",
    },
    "historical": {
        "liveboard_analytics",
        "agencies",
        "routes",
        "service_exceptions",
        "services",
        "stations",
        "stop_times",
        "stops",
        "trips",
        "vehicles",
        "station_gtfs_map",
    },
}

FORBIDDEN_KEYWORDS = {
    "ALTER",
    "ATTACH",
    "CREATE",
    "DELETE",
    "DETACH",
    "DROP",
    "INSERT",
    "PRAGMA",
    "REINDEX",
    "UPDATE",
    "VACUUM",
}

def extract_table_names(sql: str) -> set[str]:
    """Extract table names referenced after FROM or JOIN."""
    return {
        match.group(1).lower()
        for match in TABLE_REFERENCE_PATTERN.finditer(sql)
    }

class SQLValidationError(ValueError):
    """Raised when generated SQL violates a safety rule."""

def normalize_sql(sql: str) -> str:
    """Trim whitespace and an optional final semicolon."""
    if not isinstance(sql, str):
        raise SQLValidationError("SQL must be a string.")

    normalized = sql.strip()

    if not normalized:
        raise SQLValidationError("SQL cannot be empty.")

    if normalized.endswith(";"):
        normalized = normalized[:-1].rstrip()

    return normalized

def validate_sql(sql: str, mode: str) -> str:
    """Validate and return safe normalized read-only SQL."""
    if mode not in ALLOWED_TABLES:
        raise SQLValidationError(
            f"Unknown chatbot mode: {mode}"
        )

    normalized = normalize_sql(sql)

    if (
        "--" in normalized
        or "/*" in normalized
        or "*/" in normalized
    ):
        raise SQLValidationError(
            "SQL comments are not allowed."
        )

    if ";" in normalized:
        raise SQLValidationError(
            "Multiple SQL statements are not allowed."
        )

    if not re.match(
        r"^(SELECT|WITH)\b",
        normalized,
        re.IGNORECASE,
    ):
        raise SQLValidationError(
            "Only SELECT queries are allowed."
        )

    tokens = set(
        re.findall(
            r"\b[A-Za-z_]+\b",
            normalized.upper(),
        )
    )

    blocked = tokens & FORBIDDEN_KEYWORDS

    if blocked:
        blocked_list = ", ".join(sorted(blocked))
        raise SQLValidationError(
            f"Forbidden SQL keyword(s): {blocked_list}"
        )

    table_names = extract_table_names(normalized)

    if not table_names:
        raise SQLValidationError(
            "The query must reference an approved table."
        )

    disallowed_tables = (
        table_names - ALLOWED_TABLES[mode]
    )

    if disallowed_tables:
        table_list = ", ".join(
            sorted(disallowed_tables)
        )
        raise SQLValidationError(
            f"Table(s) not allowed in {mode} mode: "
            f"{table_list}"
        )

    limit_match = re.search(
        r"\bLIMIT\s+(\d+)\b",
        normalized,
        re.IGNORECASE,
    )

    if limit_match:
        if int(limit_match.group(1)) > 100:
            raise SQLValidationError(
                "LIMIT cannot be greater than 100."
            )
    else:
        normalized += " LIMIT 100"

    return normalized
   
