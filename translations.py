import csv
import re
import unicodedata
from functools import lru_cache
from pathlib import Path


TRANSLATIONS_PATH = Path(__file__).with_name("translations.txt")

SUPPORTED_LANGUAGES = {"en", "fr", "nl", "de"}

LANGUAGE_NAMES = {
    "en": "English",
    "fr": "French",
    "nl": "Dutch",
    "de": "German",
}

UI_TEXT = {
    "cannot_answer": {
        "en": "The available RailPulse dataset cannot answer that question.",
        "fr": "Les données RailPulse disponibles ne permettent pas de répondre à cette question.",
        "nl": "De beschikbare RailPulse-gegevens kunnen deze vraag niet beantwoorden.",
        "de": "Die verfügbaren RailPulse-Daten können diese Frage nicht beantworten.",
    },
    "service_error": {
        "en": "The RailPulse service could not complete this request. Please try again.",
        "fr": "Le service RailPulse n'a pas pu traiter cette demande. Veuillez réessayer.",
        "nl": "De RailPulse-service kon deze aanvraag niet voltooien. Probeer het opnieuw.",
        "de": "Der RailPulse-Dienst konnte diese Anfrage nicht abschließen. Bitte versuchen Sie es erneut.",
    },
    "request_error": {
        "en": "RailPulse could not process that question. Please rephrase it.",
        "fr": "RailPulse n'a pas pu traiter cette question. Veuillez la reformuler.",
        "nl": "RailPulse kon die vraag niet verwerken. Formuleer de vraag anders.",
        "de": "RailPulse konnte diese Frage nicht verarbeiten. Bitte formulieren Sie sie um.",
    },
    "no_results": {
        "en": "The query was valid, but no matching records were found in the available dataset.",
        "fr": "La requête était valide, mais aucun enregistrement correspondant n'a été trouvé dans les données disponibles.",
        "nl": "De query was geldig, maar er zijn geen overeenkomende records gevonden in de beschikbare gegevens.",
        "de": "Die Abfrage war gültig, aber im verfügbaren Datensatz wurden keine passenden Einträge gefunden.",
    },
    "unsafe_request": {
        "en": "RailPulse only permits read-only questions. Requests to modify or delete data are blocked.",
        "fr": "RailPulse autorise uniquement les questions en lecture seule. Les demandes de modification ou de suppression sont bloquées.",
        "nl": "RailPulse staat alleen-lezenvragen toe. Verzoeken om gegevens te wijzigen of te verwijderen worden geblokkeerd.",
        "de": "RailPulse erlaubt nur schreibgeschützte Abfragen. Anforderungen zum Ändern oder Löschen von Daten werden blockiert.",
    },
    "show_sql": {
        "en": "Show SQL",
        "fr": "Afficher le SQL",
        "nl": "SQL tonen",
        "de": "SQL anzeigen",
    },
    "validated_sql": {
        "en": "Validated SQL",
        "fr": "SQL validé",
        "nl": "Gevalideerde SQL",
        "de": "Validiertes SQL",
    },
    "query_results": {
        "en": "Query results",
        "fr": "Résultats de la requête",
        "nl": "Queryresultaten",
        "de": "Abfrageergebnisse",
    },
    "no_sql": {
        "en": "No SQL is available for this response.",
        "fr": "Aucune requête SQL n'est disponible pour cette réponse.",
        "nl": "Voor dit antwoord is geen SQL beschikbaar.",
        "de": "Für diese Antwort ist kein SQL verfügbar.",
    },
}

LANGUAGE_MARKERS = {
    "en": {
        "what", "which", "where", "from", "according", "data",
        "delay", "delays", "delayed", "average", "scheduled",
        "departure", "departures", "route", "routes",
    },
    "fr": {
        "quel", "quelle", "quels", "quelles", "gare", "depuis",
        "retard", "retards", "ligne", "lignes", "sont", "moyenne",
        "depart", "departs", "supprime", "supprimer", "efface",
    },
    "nl": {
        "welke", "wat", "vanuit", "vertraging", "vertragingen",
        "trein", "treinen", "zijn", "meest", "gemiddeld",
        "vertrek", "vertrekken", "verwijder", "verwijderen", "wissen",
    },
    "de": {
        "welche", "was", "vom", "bahnhof", "verspatung",
        "verspatungen", "zuge", "strecken", "sind", "meisten",
        "durchschnitt", "abfahrt", "abfahrten", "losche", "loschen",
    },
}


def normalize_name(value: str) -> str:
    """Normalize punctuation, accents, and case for alias matching."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    ascii_value = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return " ".join(re.findall(r"[a-z0-9]+", ascii_value))


@lru_cache(maxsize=1)
def _translation_data() -> tuple[dict, dict]:
    translations = {
        "stop_name": {},
        "trip_headsign": {},
    }
    alias_candidates: dict[str, set[str]] = {}

    with TRANSLATIONS_PATH.open(
        encoding="utf-8-sig",
        newline="",
    ) as translation_file:
        for row in csv.DictReader(translation_file):
            field_name = row["field_name"]
            canonical = row["field_value"].strip()
            language = row["language"].strip()
            translated = row["translation"].strip()

            if field_name not in translations or not canonical:
                continue

            language_values = translations[field_name].setdefault(
                canonical,
                {"fr": canonical},
            )

            if language in SUPPORTED_LANGUAGES and translated:
                language_values[language] = translated

            if field_name != "stop_name":
                continue

            aliases = {canonical, translated}
            aliases.update(
                part.strip()
                for part in translated.split("/")
                if part.strip()
            )

            for alias in aliases:
                normalized = normalize_name(alias)
                if len(normalized) >= 4:
                    alias_candidates.setdefault(
                        normalized,
                        set(),
                    ).add(canonical)

    aliases = {
        alias: next(iter(canonical_values))
        for alias, canonical_values in alias_candidates.items()
        if len(canonical_values) == 1
    }
    return translations, aliases


def detect_language(text: str) -> str:
    """Detect a supported language from distinctive question words."""
    normalized = normalize_name(text)
    tokens = set(normalized.split())
    scores = {
        language: len(tokens & markers)
        for language, markers in LANGUAGE_MARKERS.items()
    }
    highest_score = max(scores.values())

    if highest_score == 0:
        return "en"

    matches = [
        language
        for language, score in scores.items()
        if score == highest_score
    ]
    return matches[0] if len(matches) == 1 else "en"


def resolve_language(requested: str, question: str) -> str:
    """Resolve an explicit language or detect it from the question."""
    if requested == "auto":
        return detect_language(question)
    if requested not in SUPPORTED_LANGUAGES:
        raise ValueError(f"Unsupported language: {requested}")
    return requested


def get_ui_text(key: str, language: str) -> str:
    """Return localized fixed application text."""
    resolved = language if language in SUPPORTED_LANGUAGES else "en"
    return UI_TEXT[key][resolved]

@lru_cache(maxsize=1)
def build_station_prefix_index() -> dict[str, set[str]]:
    """Map multilingual location prefixes to canonical station names."""
    translations, _ = _translation_data()
    prefix_index: dict[str, set[str]] = {}

    for canonical, language_values in translations["stop_name"].items():
        names = {
            canonical,
            *language_values.values(),
        }

        for name in names:
            words = normalize_name(name).split()

            if not words:
                continue

            # Index one-, two-, and three-word location prefixes.
            maximum_size = min(3, len(words))

            for size in range(1, maximum_size + 1):
                prefix = " ".join(words[:size])
                prefix_index.setdefault(
                    prefix,
                    set(),
                ).add(canonical)

    return prefix_index


def find_station_group(question: str) -> list[str]:
    """Find canonical stations matching an ambiguous location."""
    question_words = normalize_name(question).split()
    prefix_index = build_station_prefix_index()

    # Search longer phrases before individual words.
    maximum_size = min(3, len(question_words))

    for size in range(maximum_size, 0, -1):
        for start in range(len(question_words) - size + 1):
            phrase = " ".join(
                question_words[start:start + size]
            )
            candidates = prefix_index.get(phrase, set())

            # Multiple matches indicate a city or station group.
            if len(candidates) > 1:
                return sorted(candidates)

    return []

def find_station_aliases(question: str) -> list[tuple[str, str]]:
    """Find translated station names and their canonical GTFS values."""
    _, aliases = _translation_data()
    normalized_question = f" {normalize_name(question)} "
    matches = []

    for alias in sorted(aliases, key=len, reverse=True):
        if f" {alias} " in normalized_question:
            canonical = aliases[alias]
            if not any(existing[1] == canonical for existing in matches):
                matches.append((alias, canonical))

    return matches


def add_canonical_station_context(question: str) -> str:
    """Append deterministic station-name mappings for SQL generation."""
    matches = find_station_aliases(question)
    if not matches:
        return question

    mappings = "\n".join(
        f'- User station name "{alias}" maps to canonical GTFS '
        f'field_value "{canonical}". Filter '
        f'station_gtfs_map.gtfs_stop_name using this canonical value.'
        for alias, canonical in matches
    )
    return (
        f"{question}\n\n"
        "Resolved station-name mappings:\n"
        f"{mappings}\n"
        "For these resolved mappings, filter gtfs_stop_name, not "
        "irail_display_name. Then join gtfs_stop_id to "
        "stops.parent_station."
    )


def translate_value(
    value: str,
    language: str,
    field_name: str,
) -> str:
    """Translate an exact canonical stop name or trip headsign."""
    translations, _ = _translation_data()
    values = translations.get(field_name, {}).get(value)
    if not values:
        return value
    return values.get(language) or values.get("fr") or value

def format_station_scope_message(
    station_names: list[str],
    language: str,
) -> str:
    """Explain which stations were included in a city-wide query."""
    joined_names = ", ".join(station_names)

    templates = {
        "en": "I interpreted the city as these stations: {stations}.",
        "fr": "J'ai interprété la ville comme ces gares : {stations}.",
        "nl": "Ik heb de stad geïnterpreteerd als deze stations: {stations}.",
        "de": "Ich habe die Stadt als diese Bahnhöfe interpretiert: {stations}.",
    }

    template = templates.get(language, templates["en"])
    return template.format(stations=joined_names)



def translate_rows(rows: list[dict], language: str) -> list[dict]:
    """Localize station names, route endpoints, and trip headsigns."""
    localized_rows = []

    for row in rows:
        localized = {}
        for key, value in row.items():
            if not isinstance(value, str):
                localized[key] = value
                continue

            key_lower = key.lower()
            if key_lower == "trip_headsign":
                localized[key] = translate_value(
                    value,
                    language,
                    "trip_headsign",
                )
            elif key_lower == "route_long_name" and " -- " in value:
                localized[key] = " -- ".join(
                    translate_value(part, language, "stop_name")
                    for part in value.split(" -- ")
                )
            elif any(
                marker in key_lower
                for marker in (
                    "station_name",
                    "stop_name",
                    "origin_name",
                    "destination_name",
                )
            ):
                localized[key] = translate_value(
                    value,
                    language,
                    "stop_name",
                )
            else:
                localized[key] = value

        localized_rows.append(localized)

    return localized_rows
