"""Automatic quality checks for generated NIRVA drafts.

Answers must match their source fact text exactly. A different answer is
accepted only as a *reviewed edit*: the review manifest entry for that
example gives an answer_edit_reason AND its content_hash matches the
current draft. Any other difference is an error.

Exit status: 0 when all checks pass, 1 otherwise. Manual review is still
required even when every check passes.

Usage:
    python ai/training/check_drafts.py [--drafts FILE ...] [--manifest FILE] [--facts FILE]
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

from pipeline_common import (
    DRAFTS_PATH,
    FACTS_PATH,
    MANIFEST_PATH,
    answer_check,
    example_id_of,
    index_manifest,
    load_json,
    load_jsonl,
    load_manifest,
    message_errors,
    question_of,
    system_prompt_kind,
)
from validate_facts import normalise_text


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Check generated drafts.")
    parser.add_argument("--drafts", type=Path, nargs="+", default=[DRAFTS_PATH])
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--facts", type=Path, default=FACTS_PATH)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    facts = {f["id"]: f for f in load_json(args.facts)}

    entries, errors = {}, []
    if args.manifest.exists():
        entries, manifest_errors = index_manifest(load_manifest(args.manifest))
        errors += manifest_errors
    else:
        print(f"Note: no review manifest at {args.manifest}; every answer must match its fact exactly.")

    total = 0
    example_ids = Counter()
    questions = {}
    prompt_kinds = Counter()
    reviewed_edits = []
    unverified = Counter()

    for path in args.drafts:
        for line_number, draft in load_jsonl(path):
            total += 1
            where = f"{Path(path).name} line {line_number}"

            problems = message_errors(draft)
            if problems:
                errors.append(f"{where}: {'; '.join(problems)}")
                continue

            example_id = example_id_of(draft)
            example_ids[example_id] += 1

            fact_id = draft.get("source_fact_id")
            fact = facts.get(fact_id)
            if fact is None:
                errors.append(f"{where}: unknown fact ID {fact_id!r}")
                continue
            if fact.get("status") != "verified":
                unverified[fact_id] += 1

            if draft.get("status") != "needs_review":
                errors.append(f"{where}: unexpected status {draft.get('status')!r}")

            kind = system_prompt_kind(draft)
            prompt_kinds[kind] += 1
            if kind == "unknown":
                errors.append(f"{where}: unknown system prompt")

            result = answer_check(draft, fact["fact"], entries.get(example_id))
            if result == "reviewed_edit":
                reviewed_edits.append(f"{where} ({example_id}): {entries[example_id]['answer_edit_reason']}")
            elif result == "mismatch":
                entry = entries.get(example_id)
                hint = ""
                if entry and str(entry.get("answer_edit_reason", "")).strip():
                    hint = " (an answer_edit_reason exists but the draft changed after it was recorded)"
                errors.append(f"{where} ({example_id}): answer differs from source fact {fact_id}{hint}")

            key = normalise_text(question_of(draft))
            if key in questions:
                errors.append(f"{where}: duplicate question (also {questions[key]}): {question_of(draft)}")
            else:
                questions[key] = where

    for example_id, count in example_ids.items():
        if count > 1:
            errors.append(f"duplicate example_id {example_id} ({count} drafts)")

    print("\nNIRVA DRAFT QUALITY CHECK")
    print("-" * 35)
    print("Total drafts:", total)
    print("Unique questions:", len(questions))
    print("Unique example IDs:", len(example_ids))
    print("System prompts:", dict(prompt_kinds))
    print("Drafts in manifest:", sum(1 for eid in example_ids if eid in entries))

    if reviewed_edits:
        print("\nReviewed answer edits (intentional, recorded in manifest):")
        for line in reviewed_edits:
            print("-", line)

    if unverified:
        print("\nDrafts whose source fact is not verified (excluded from approval):")
        for fact_id, count in sorted(unverified.items()):
            print(f"- {fact_id} ({facts[fact_id]['status']}): {count} draft(s)")

    if errors:
        print("\nIssues found:")
        for error in errors:
            print("-", error)
        return 1

    print("\nAll automatic checks passed!")
    print("Manual review is still required.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
