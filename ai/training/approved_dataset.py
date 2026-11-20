"""Build approved_train.jsonl from drafts that a person explicitly approved.

An example enters the output only if ALL of the following hold:
  - its review manifest entry has decision "approved", with reviewer and date;
  - the manifest content_hash still matches the draft (no change after review);
  - its source fact exists and has status "verified";
  - its answer equals the fact text, or the manifest records an
    answer_edit_reason for exactly this answer.

Unreviewed and rejected drafts are always excluded. The drafts file is
read-only here. Approved examples whose fact is no longer verified are left
out with a warning, so downgraded facts never reach training.

Usage:
    python ai/training/approved_dataset.py --dry-run
    python ai/training/approved_dataset.py --overwrite
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

from pipeline_common import (
    APPROVED_PATH,
    CANONICAL_SYSTEM_PROMPT,
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
    record_hash,
    system_prompt_kind,
    with_canonical_prompt,
    write_jsonl,
)
from validate_facts import normalise_text, validate_facts


def build(drafts_paths, manifest_path, facts_path):
    """Return (approved_records, errors, warnings, stats)."""
    errors, warnings = [], []

    facts = load_json(facts_path)
    fact_errors, _ = validate_facts(facts)
    errors += [f"facts: {e}" for e in fact_errors]
    facts_by_id = {f["id"]: f for f in facts if isinstance(f, dict) and "id" in f}

    manifest = load_manifest(manifest_path)
    entries, manifest_errors = index_manifest(manifest)
    errors += manifest_errors

    drafts = {}
    for path in drafts_paths:
        for line_number, record in load_jsonl(path):
            where = f"{Path(path).name} line {line_number}"
            problems = message_errors(record)
            if problems:
                errors.append(f"{where}: {'; '.join(problems)}")
                continue
            if record.get("status") != "needs_review":
                errors.append(f"{where}: draft status must be 'needs_review'")
            if system_prompt_kind(record) == "unknown":
                errors.append(f"{where}: unknown system prompt")
            example_id = example_id_of(record)
            if example_id in drafts:
                errors.append(f"{where}: duplicate example_id {example_id}")
                continue
            drafts[example_id] = record

    decisions = Counter(entry.get("decision") for entry in entries.values())
    approved, seen_questions = [], {}
    excluded_unverified = 0

    for example_id, entry in entries.items():
        if entry.get("decision") != "approved":
            continue
        record = drafts.get(example_id)
        if record is None:
            errors.append(f"{example_id}: approved in manifest but no matching draft")
            continue
        if entry.get("content_hash") != record_hash(record):
            errors.append(f"{example_id}: draft changed after approval; review it again")
            continue

        fact_id = record.get("source_fact_id")
        fact = facts_by_id.get(fact_id)
        if fact is None:
            errors.append(f"{example_id}: unknown source fact {fact_id!r}")
            continue
        if fact.get("status") != "verified":
            warnings.append(
                f"{example_id}: excluded, source fact {fact_id} has status {fact.get('status')!r}"
            )
            excluded_unverified += 1
            continue
        if answer_check(record, fact["fact"], entry) == "mismatch":
            errors.append(
                f"{example_id}: answer differs from {fact_id} and no answer_edit_reason is recorded"
            )
            continue

        key = normalise_text(question_of(record))
        if key in seen_questions:
            errors.append(f"{example_id}: duplicate question (also {seen_questions[key]})")
            continue
        seen_questions[key] = example_id

        output = with_canonical_prompt(record)
        output["example_id"] = example_id
        output["status"] = "approved"
        approved.append(output)

    if any(r["messages"][0]["content"] != CANONICAL_SYSTEM_PROMPT for r in approved):
        errors.append("internal: non-canonical system prompt in output")

    stats = {
        "drafts": len(drafts),
        "manifest": len(entries),
        "decisions": decisions,
        "excluded_unverified": excluded_unverified,
        "not_in_manifest": sum(1 for eid in drafts if eid not in entries),
    }
    return approved, errors, warnings, stats


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Build approved_train.jsonl from the review manifest.")
    parser.add_argument("--drafts", type=Path, nargs="+", default=[DRAFTS_PATH])
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--facts", type=Path, default=FACTS_PATH)
    parser.add_argument("--output", type=Path, default=APPROVED_PATH)
    parser.add_argument("--overwrite", action="store_true", help="Replace an existing output file")
    parser.add_argument("--dry-run", action="store_true", help="Validate and report only")
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if not args.manifest.exists():
        print(f"Review manifest not found: {args.manifest}")
        print("Run: python ai/training/review_manifest.py sync")
        return 1

    approved, errors, warnings, stats = build(args.drafts, args.manifest, args.facts)

    print("\nNIRVA APPROVAL BUILD")
    print("-" * 35)
    print("Draft examples:", stats["drafts"])
    print("Manifest entries:", stats["manifest"])
    for decision in ("approved", "rejected", "unreviewed"):
        print(f"  {decision}: {stats['decisions'].get(decision, 0)}")
    print("Drafts missing from manifest (excluded):", stats["not_in_manifest"])
    print("Approved but fact not verified (excluded):", stats["excluded_unverified"])
    print("Examples selected for output:", len(approved))

    for warning in warnings:
        print("WARNING:", warning)

    if errors:
        print(f"\nAPPROVAL FAILED with {len(errors)} error(s); nothing written:")
        for error in errors:
            print("-", error)
        return 1

    if not approved:
        print("\nNo approved examples; nothing written.")
        return 1

    if args.dry_run:
        print("\nDry run: nothing written.")
        return 0

    if args.output.exists() and not args.overwrite:
        print(f"\nOutput exists: {args.output}")
        print("Use --overwrite to replace it, or --output for a new file.")
        return 1

    write_jsonl(args.output, approved)
    print("\nAPPROVAL COMPLETE")
    print("Output:", args.output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
