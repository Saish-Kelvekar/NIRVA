"""Validate the structure of NIRVA's curated fact file (data/raw_facts.json).

These checks cover structure and metadata only. A syntactically valid
source_url says nothing about whether the page exists or supports the fact.
A person must still check every fact against its source before marking it
"verified".

Usage:
    python ai/training/validate_facts.py [path/to/raw_facts.json]

Exit status: 0 when all checks pass, 1 when validation errors are found.
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

PROJECT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_FACTS_PATH = PROJECT_DIR / "data" / "raw_facts.json"

REQUIRED_FIELDS = (
    "id",
    "category",
    "fact",
    "source",
    "source_url",
    "confidence",
    "time_sensitive",
    "status",
)

VALID_CATEGORIES = {
    "attractions",
    "activities",
    "wildlife",
    "travel",
    "safety",
    "geography",
    "behaviour",
}

VALID_CONFIDENCE = {"high", "medium", "low"}

# verified:     a reviewer has confirmed that the cited source supports the fact.
# needs_review: candidate or flagged fact; excluded from dataset generation.
# rejected:     kept for the record, but must never be used.
VALID_STATUSES = {"verified", "needs_review", "rejected"}

FACT_ID_PATTERN = re.compile(r"^FACT\d{3,}$")


def normalise_text(text):
    """Lowercase, collapse whitespace and drop trailing punctuation."""
    return " ".join(text.lower().split()).rstrip(".!? ")


def is_non_empty_string(value):
    return isinstance(value, str) and bool(value.strip())


def validate_facts(facts):
    """Return (errors, warnings) for a list of fact records."""
    errors = []
    warnings = []

    if not isinstance(facts, list):
        return ["Top-level JSON value must be a list of facts."], warnings

    ids = Counter()
    descriptions = {}

    for index, fact in enumerate(facts, start=1):
        if not isinstance(fact, dict):
            errors.append(f"Entry {index}: must be a JSON object.")
            continue

        label = f"Entry {index} ({fact.get('id', 'no id')})"

        for field in REQUIRED_FIELDS:
            if field not in fact:
                errors.append(f"{label}: missing required field '{field}'.")

        fact_id = fact.get("id")
        if "id" in fact:
            if not is_non_empty_string(fact_id):
                errors.append(f"{label}: 'id' must be a non-empty string.")
            else:
                ids[fact_id] += 1
                if not FACT_ID_PATTERN.match(fact_id):
                    warnings.append(
                        f"{label}: id does not follow the FACTnnn convention."
                    )

        if "fact" in fact:
            text = fact["fact"]
            if not is_non_empty_string(text):
                errors.append(f"{label}: 'fact' must be a non-empty string.")
            else:
                key = normalise_text(text)
                if key in descriptions:
                    errors.append(
                        f"{label}: duplicate fact description "
                        f"(same as {descriptions[key]})."
                    )
                else:
                    descriptions[key] = fact_id

        if "category" in fact and fact["category"] not in VALID_CATEGORIES:
            errors.append(
                f"{label}: invalid category {fact['category']!r}. "
                f"Allowed: {', '.join(sorted(VALID_CATEGORIES))}."
            )

        if "confidence" in fact and fact["confidence"] not in VALID_CONFIDENCE:
            errors.append(
                f"{label}: invalid confidence {fact['confidence']!r}. "
                f"Allowed: {', '.join(sorted(VALID_CONFIDENCE))}."
            )

        # bool check must be strict: "true", 1 and 0 are not accepted.
        if "time_sensitive" in fact and not isinstance(fact["time_sensitive"], bool):
            errors.append(
                f"{label}: 'time_sensitive' must be true or false, "
                f"got {fact['time_sensitive']!r}."
            )

        if "status" in fact and fact["status"] not in VALID_STATUSES:
            errors.append(
                f"{label}: invalid status {fact['status']!r}. "
                f"Allowed: {', '.join(sorted(VALID_STATUSES))}."
            )

        if "source" in fact and not is_non_empty_string(fact["source"]):
            errors.append(f"{label}: 'source' must be a non-empty string.")

        if "source_url" in fact:
            url = fact["source_url"]
            if not is_non_empty_string(url):
                errors.append(f"{label}: 'source_url' must be a non-empty string.")
            else:
                parsed = urlparse(url.strip())
                # Format check only; this does not prove the page supports the fact.
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    errors.append(
                        f"{label}: 'source_url' is not a well-formed http(s) URL."
                    )

        if fact.get("status") == "verified" and fact.get("confidence") == "low":
            warnings.append(f"{label}: verified fact has low confidence.")

    for fact_id, count in ids.items():
        if count > 1:
            errors.append(f"Duplicate fact ID {fact_id!r} appears {count} times.")

    return errors, warnings


def load_facts(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def main(argv):
    path = Path(argv[1]) if len(argv) > 1 else DEFAULT_FACTS_PATH

    try:
        facts = load_facts(path)
    except FileNotFoundError:
        print(f"ERROR: fact file not found: {path}")
        return 1
    except json.JSONDecodeError as error:
        print(f"ERROR: invalid JSON in {path}: {error}")
        return 1

    errors, warnings = validate_facts(facts)

    print("\nNIRVA FACT VALIDATION")
    print("-" * 35)
    print("File:", path)

    if isinstance(facts, list):
        print("Total facts:", len(facts))
        records = [f for f in facts if isinstance(f, dict)]
        for title, field in (("By status", "status"), ("By category", "category")):
            print(f"\n{title}:")
            for value, count in sorted(Counter(f.get(field) for f in records).items(), key=str):
                print(f"  {value}: {count}")
        print("\nTime-sensitive:", sum(1 for f in records if f.get("time_sensitive") is True))

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print("-", warning)

    if errors:
        print(f"\nValidation FAILED with {len(errors)} error(s):")
        for error in errors:
            print("-", error)
        return 1

    print("\nAll structural checks passed.")
    print("Note: URL checks are format-only. Source support must be confirmed manually.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
