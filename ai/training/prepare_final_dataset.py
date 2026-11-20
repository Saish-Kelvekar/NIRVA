"""Combine approved knowledge examples and behaviour examples into final_train.jsonl.

Checks (any failure stops the build and nothing is written):
  - every record has a valid system/user/assistant structure;
  - every knowledge example has status "approved", a unique example_id, a
    verified source fact, and a matching "approved" entry in the review
    manifest with an unchanged content_hash;
  - behaviour examples (source_fact_id BEHAVIOUR...) come from train.jsonl;
  - no duplicate example IDs and no duplicate user questions;
  - every output record uses the canonical system prompt. Known legacy
    prompts are migrated; unknown prompts are rejected.

Counts are dynamic; there is no fixed expected size.

Usage:
    python ai/training/prepare_final_dataset.py --dry-run
    python ai/training/prepare_final_dataset.py --overwrite
"""

import argparse
import sys
from pathlib import Path

from pipeline_common import (
    APPROVED_PATH,
    CANONICAL_SYSTEM_PROMPT,
    FACTS_PATH,
    FINAL_PATH,
    MANIFEST_PATH,
    ORIGINAL_TRAIN_PATH,
    answer_check,
    example_id_of,
    index_manifest,
    load_json,
    load_jsonl,
    load_manifest,
    message_errors,
    question_of,
    record_hash,
    system_prompt_kind,
    with_canonical_prompt,
    write_jsonl,
)
from validate_facts import normalise_text


def build(approved_path, original_path, manifest_path, facts_path):
    errors = []
    migrated_prompts = 0

    facts_by_id = {f["id"]: f for f in load_json(facts_path) if isinstance(f, dict)}
    entries, manifest_errors = index_manifest(load_manifest(manifest_path))
    errors += manifest_errors

    knowledge = []
    for line_number, record in load_jsonl(approved_path):
        where = f"{Path(approved_path).name} line {line_number}"
        problems = message_errors(record)
        if problems:
            errors.append(f"{where}: {'; '.join(problems)}")
            continue
        if record.get("status") != "approved":
            errors.append(f"{where}: status is {record.get('status')!r}, expected 'approved'")
            continue
        example_id = record.get("example_id")
        if not example_id:
            errors.append(f"{where}: missing example_id (rebuild with approved_dataset.py)")
            continue
        entry = entries.get(example_id)
        if not entry or entry.get("decision") != "approved":
            errors.append(f"{where}: {example_id} is not approved in the review manifest")
            continue
        if entry.get("content_hash") != record_hash(record):
            errors.append(f"{where}: {example_id} differs from the reviewed content")
            continue
        fact = facts_by_id.get(record.get("source_fact_id"))
        if not fact:
            errors.append(f"{where}: unknown source fact {record.get('source_fact_id')!r}")
            continue
        if fact.get("status") != "verified":
            errors.append(f"{where}: source fact {fact['id']} is {fact.get('status')!r}, not verified")
            continue
        if answer_check(record, fact["fact"], entry) == "mismatch":
            errors.append(f"{where}: answer differs from {fact['id']} without a recorded reason")
            continue
        if system_prompt_kind(record) != "canonical":
            errors.append(f"{where}: approved example must already use the canonical prompt")
            continue
        knowledge.append(record)

    behaviour = []
    for line_number, record in load_jsonl(original_path):
        if not str(record.get("source_fact_id", "")).startswith("BEHAVIOUR"):
            continue
        where = f"{Path(original_path).name} line {line_number}"
        problems = message_errors(record)
        if problems:
            errors.append(f"{where}: {'; '.join(problems)}")
            continue
        kind = system_prompt_kind(record)
        if kind == "unknown":
            errors.append(f"{where}: unknown system prompt (not migrated)")
            continue
        if kind == "legacy":
            record = with_canonical_prompt(record)
            migrated_prompts += 1
        record.setdefault("example_id", example_id_of(record))
        behaviour.append(record)

    if not behaviour:
        errors.append(f"no behaviour examples found in {Path(original_path).name}")

    final_dataset = knowledge + behaviour

    seen_ids, seen_questions = {}, {}
    for record in final_dataset:
        example_id = record["example_id"]
        if example_id in seen_ids:
            errors.append(f"duplicate example_id {example_id}")
        seen_ids[example_id] = True
        key = normalise_text(question_of(record))
        if key in seen_questions:
            errors.append(f"duplicate question in {example_id} and {seen_questions[key]}: {question_of(record)}")
        seen_questions[key] = example_id

    prompts = {record["messages"][0]["content"] for record in final_dataset}
    if prompts - {CANONICAL_SYSTEM_PROMPT}:
        errors.append("final dataset contains a non-canonical system prompt")

    # Approval-stage metadata is not training data.
    output = []
    for record in final_dataset:
        clean = dict(record)
        clean.pop("status", None)
        output.append(clean)

    stats = {
        "knowledge": len(knowledge),
        "behaviour": len(behaviour),
        "migrated_prompts": migrated_prompts,
        "unique_questions": len(seen_questions),
        "system_prompts": len(prompts),
    }
    return output, errors, stats


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Build final_train.jsonl.")
    parser.add_argument("--approved", type=Path, default=APPROVED_PATH)
    parser.add_argument("--original", type=Path, default=ORIGINAL_TRAIN_PATH)
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--facts", type=Path, default=FACTS_PATH)
    parser.add_argument("--output", type=Path, default=FINAL_PATH)
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing output file")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report only")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    output, errors, stats = build(args.approved, args.original, args.manifest, args.facts)

    print("\nNIRVA FINAL DATASET")
    print("-" * 35)
    print("Knowledge examples:", stats["knowledge"])
    print("Behaviour examples:", stats["behaviour"])
    print("Legacy system prompts migrated:", stats["migrated_prompts"])
    print("Total examples:", len(output))
    print("Unique questions:", stats["unique_questions"])
    print("Distinct system prompts:", stats["system_prompts"])

    if errors:
        print(f"\nFINAL DATASET FAILED with {len(errors)} error(s); nothing written:")
        for error in errors:
            print("-", error)
        return 1

    if args.dry_run:
        print("\nDry run: nothing written.")
        return 0

    if args.output.exists() and not args.overwrite:
        print(f"\nOutput exists: {args.output}")
        print("Use --overwrite to replace it, or --output for a new file.")
        return 1

    write_jsonl(args.output, output)
    print("\nFINAL DATASET CREATED")
    print("Output:", args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
