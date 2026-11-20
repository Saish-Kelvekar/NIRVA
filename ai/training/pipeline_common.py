"""Shared definitions for the NIRVA dataset pipeline.

Holds the canonical system prompt, example IDs, content hashes, the review
manifest format and message-structure checks used by:
generate_dataset.py, check_drafts.py, review_manifest.py,
approved_dataset.py and prepare_final_dataset.py.
"""

import hashlib
import json
import re
from pathlib import Path

from validate_facts import normalise_text

PROJECT_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_DIR / "data"

FACTS_PATH = DATA_DIR / "raw_facts.json"
DRAFTS_PATH = DATA_DIR / "generated_drafts.jsonl"
MANIFEST_PATH = DATA_DIR / "review_manifest.json"
APPROVED_PATH = DATA_DIR / "approved_train.jsonl"
ORIGINAL_TRAIN_PATH = DATA_DIR / "train.jsonl"
FINAL_PATH = DATA_DIR / "final_train.jsonl"

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

# The one system prompt used in every training example. This is the
# prompt generate_dataset.py has always used (after .strip()).
CANONICAL_SYSTEM_PROMPT = (
    "You are NIRVA, a local assistant focused on Dandeli,\n"
    "Uttara Kannada, Karnataka, India.\n"
    "\n"
    "Answer using reliable information.\n"
    "Do not invent facts or add unsupported details.\n"
    "If information is unavailable, acknowledge uncertainty.\n"
    "Politely decline unrelated questions."
)

# Older prompts that may be replaced by the canonical prompt during dataset
# building. Any prompt not listed here is rejected rather than replaced.
LEGACY_SYSTEM_PROMPTS = {
    # data/train.jsonl (original hand-written examples, incl. BEHAVIOUR001-003)
    "You are NIRVA, a local assistant focused on Dandeli, Karnataka, India. "
    "Answer Dandeli-related questions using reliable information. "
    "Do not invent facts. If information is unavailable, acknowledge "
    "uncertainty. Politely decline unrelated questions.",
}

# ---------------------------------------------------------------------------
# Review manifest
# ---------------------------------------------------------------------------

DECISIONS = {"unreviewed", "approved", "rejected"}
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")

MANIFEST_INSTRUCTIONS = [
    "One entry per draft example. Only entries with decision 'approved' enter approved_train.jsonl.",
    "decision: 'unreviewed' (default), 'approved' or 'rejected'.",
    "approved/rejected entries need 'reviewer' and 'reviewed_on' (YYYY-MM-DD).",
    "Before approving, check the answer against the source fact and its source_url.",
    "answer_edit_reason: fill ONLY if the answer intentionally differs from the source fact text; explain why it is still supported.",
    "Do not edit example_id, source_fact_id, question, answer or content_hash by hand. Run review_manifest.py sync instead.",
    "If a draft changes after review, content_hash no longer matches and the entry must be reviewed again.",
]


def make_example_id(source_fact_id, question):
    """Stable ID: fact ID plus a short hash of the normalised question."""
    digest = hashlib.sha256(normalise_text(question).encode("utf-8")).hexdigest()
    return f"{source_fact_id}-{digest[:8]}"


def content_hash(source_fact_id, question, answer):
    """Hash of what a reviewer checks. The system prompt is excluded."""
    payload = json.dumps([source_fact_id, question, answer], ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Loading helpers
# ---------------------------------------------------------------------------

def load_json(path):
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def load_jsonl(path):
    """Return a list of (line_number, record). Raises ValueError on bad JSON."""
    records = []
    with open(path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                records.append((line_number, json.loads(line)))
            except json.JSONDecodeError as error:
                raise ValueError(f"{Path(path).name} line {line_number}: invalid JSON ({error})")
    return records


def write_jsonl(path, records):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        for record in records:
            file.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_manifest(path):
    data = load_json(path)
    if not isinstance(data, dict) or not isinstance(data.get("examples"), list):
        raise ValueError(f"{path}: manifest must be an object with an 'examples' list")
    return data


def save_manifest(path, manifest):
    manifest["instructions"] = MANIFEST_INSTRUCTIONS
    ordered = {"instructions": manifest["instructions"], "examples": manifest["examples"]}
    with open(path, "w", encoding="utf-8") as file:
        json.dump(ordered, file, indent=2, ensure_ascii=False)
        file.write("\n")


# ---------------------------------------------------------------------------
# Example checks
# ---------------------------------------------------------------------------

def message_errors(record):
    """Return structural problems with a record's messages (empty if valid)."""
    messages = record.get("messages")
    if not isinstance(messages, list) or len(messages) != 3:
        return ["must have exactly 3 messages"]
    if not all(isinstance(m, dict) for m in messages):
        return ["each message must be an object"]
    roles = [m.get("role") for m in messages]
    if roles != ["system", "user", "assistant"]:
        return [f"roles must be system, user, assistant (got {roles})"]
    errors = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            errors.append(f"empty {message.get('role')} message")
    return errors


def system_prompt_kind(record):
    """Return 'canonical', 'legacy' or 'unknown'."""
    prompt = record["messages"][0]["content"]
    if prompt == CANONICAL_SYSTEM_PROMPT:
        return "canonical"
    if prompt in LEGACY_SYSTEM_PROMPTS:
        return "legacy"
    return "unknown"


def with_canonical_prompt(record):
    """Copy of record using the canonical prompt. Only known prompts are migrated."""
    kind = system_prompt_kind(record)
    if kind == "unknown":
        raise ValueError("unknown system prompt; add it to LEGACY_SYSTEM_PROMPTS only after review")
    migrated = json.loads(json.dumps(record))
    migrated["messages"][0]["content"] = CANONICAL_SYSTEM_PROMPT
    return migrated


def question_of(record):
    return record["messages"][1]["content"]


def answer_of(record):
    return record["messages"][2]["content"]


def example_id_of(record):
    """Explicit example_id if present, otherwise the derived stable ID."""
    return record.get("example_id") or make_example_id(
        record.get("source_fact_id", ""), question_of(record)
    )


def record_hash(record):
    return content_hash(record.get("source_fact_id"), question_of(record), answer_of(record))


def manifest_entry_errors(entry):
    """Problems with a single manifest entry's own fields."""
    errors = []
    decision = entry.get("decision")
    if decision not in DECISIONS:
        errors.append(f"invalid decision {decision!r} (allowed: {', '.join(sorted(DECISIONS))})")
    if decision in {"approved", "rejected"}:
        if not str(entry.get("reviewer", "")).strip():
            errors.append(f"decision '{decision}' needs a reviewer")
        if not DATE_PATTERN.match(str(entry.get("reviewed_on", ""))):
            errors.append(f"decision '{decision}' needs reviewed_on as YYYY-MM-DD")
    reason = entry.get("answer_edit_reason", "")
    if not isinstance(reason, str):
        errors.append("answer_edit_reason must be a string")
    return errors


def index_manifest(manifest):
    """Return (entries_by_id, errors) with per-entry validation."""
    by_id = {}
    errors = []
    for position, entry in enumerate(manifest["examples"], start=1):
        if not isinstance(entry, dict):
            errors.append(f"manifest entry {position}: must be an object")
            continue
        example_id = entry.get("example_id")
        if not example_id:
            errors.append(f"manifest entry {position}: missing example_id")
            continue
        if example_id in by_id:
            errors.append(f"manifest: duplicate example_id {example_id}")
            continue
        by_id[example_id] = entry
        for problem in manifest_entry_errors(entry):
            errors.append(f"manifest {example_id}: {problem}")
    return by_id, errors


def answer_check(record, fact_text, entry):
    """Classify a draft answer against its source fact.

    Returns 'exact', 'reviewed_edit' or 'mismatch'. A difference counts as a
    reviewed edit only when the manifest entry gives a reason AND its
    content_hash still matches the draft, i.e. the reason was recorded for
    exactly this answer.
    """
    if answer_of(record).strip() == fact_text.strip():
        return "exact"
    if (
        entry
        and str(entry.get("answer_edit_reason", "")).strip()
        and entry.get("content_hash") == record_hash(record)
    ):
        return "reviewed_edit"
    return "mismatch"
