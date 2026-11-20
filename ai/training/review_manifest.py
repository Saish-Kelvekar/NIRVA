"""Maintain the human review manifest for NIRVA draft examples.

The manifest (data/review_manifest.json) records one review decision per
draft example. It never approves anything by itself: new drafts are added
as "unreviewed", and only a person sets "approved" or "rejected".

Commands:
    sync    Add drafts that are missing from the manifest as "unreviewed".
            Refreshes text and hashes of unreviewed entries whose draft changed.
            Never changes an approved or rejected entry; reports it as stale.
    status  Show review counts and stale or orphaned entries.
    set     Record a decision for one or more example IDs.

Examples:
    python ai/training/review_manifest.py sync
    python ai/training/review_manifest.py status
    python ai/training/review_manifest.py set --decision approved --reviewer "Your Name" FACT001-1a2b3c4d
    python ai/training/review_manifest.py set --decision rejected --reviewer "Your Name" --notes "why" FACT009-...
"""

import argparse
import sys
from collections import Counter
from datetime import date
from pathlib import Path

from pipeline_common import (
    DECISIONS,
    DRAFTS_PATH,
    MANIFEST_PATH,
    answer_of,
    example_id_of,
    index_manifest,
    load_jsonl,
    load_manifest,
    message_errors,
    question_of,
    record_hash,
    save_manifest,
)


def load_drafts(paths):
    drafts = {}
    errors = []
    for path in paths:
        for line_number, record in load_jsonl(path):
            problems = message_errors(record)
            if problems:
                errors.append(f"{Path(path).name} line {line_number}: {'; '.join(problems)}")
                continue
            example_id = example_id_of(record)
            if example_id in drafts:
                errors.append(f"{Path(path).name} line {line_number}: duplicate example_id {example_id}")
                continue
            drafts[example_id] = record
    return drafts, errors


def new_entry(example_id, record):
    return {
        "example_id": example_id,
        "source_fact_id": record.get("source_fact_id"),
        "question": question_of(record),
        "answer": answer_of(record),
        "decision": "unreviewed",
        "reviewer": "",
        "reviewed_on": "",
        "notes": "",
        "answer_edit_reason": "",
        "content_hash": record_hash(record),
    }


def open_manifest(path):
    if Path(path).exists():
        return load_manifest(path)
    return {"examples": []}


def cmd_sync(args):
    drafts, draft_errors = load_drafts(args.drafts)
    if draft_errors:
        print("Draft errors; manifest not changed:")
        for error in draft_errors:
            print("-", error)
        return 1

    manifest = open_manifest(args.manifest)
    by_id, manifest_errors = index_manifest(manifest)
    if manifest_errors:
        print("Manifest errors; fix them before syncing:")
        for error in manifest_errors:
            print("-", error)
        return 1

    added, refreshed, stale = [], [], []
    for example_id, record in drafts.items():
        entry = by_id.get(example_id)
        if entry is None:
            manifest["examples"].append(new_entry(example_id, record))
            added.append(example_id)
        elif entry.get("content_hash") != record_hash(record):
            if entry.get("decision") == "unreviewed" and not entry.get("answer_edit_reason"):
                entry.update(
                    source_fact_id=record.get("source_fact_id"),
                    question=question_of(record),
                    answer=answer_of(record),
                    content_hash=record_hash(record),
                )
                refreshed.append(example_id)
            else:
                stale.append(example_id)

    orphans = [eid for eid in by_id if eid not in drafts]

    if args.dry_run:
        print("Dry run: manifest not written.")
    else:
        save_manifest(args.manifest, manifest)

    print(f"Added as unreviewed: {len(added)}")
    print(f"Refreshed unreviewed entries: {len(refreshed)}")
    for example_id in stale:
        print(f"STALE (draft changed after review, left untouched): {example_id}")
    for example_id in orphans:
        print(f"Not in the given draft files: {example_id}")
    print(f"Manifest entries: {len(manifest['examples'])}")
    return 0


def cmd_status(args):
    manifest = open_manifest(args.manifest)
    by_id, errors = index_manifest(manifest)
    drafts, draft_errors = load_drafts(args.drafts)
    errors += draft_errors

    counts = Counter(entry.get("decision") for entry in by_id.values())
    print("\nNIRVA REVIEW STATUS")
    print("-" * 35)
    print("Manifest:", args.manifest)
    print("Entries:", len(by_id))
    for decision in ("approved", "rejected", "unreviewed"):
        print(f"  {decision}: {counts.get(decision, 0)}")

    missing = [eid for eid in drafts if eid not in by_id]
    stale = [eid for eid, entry in by_id.items()
             if eid in drafts and entry.get("content_hash") != record_hash(drafts[eid])]
    orphans = [eid for eid in by_id if eid not in drafts]
    edits = [eid for eid, entry in by_id.items() if str(entry.get("answer_edit_reason", "")).strip()]

    print("Drafts not yet in manifest:", len(missing))
    print("Stale entries (draft changed since entry):", len(stale))
    for example_id in stale:
        print("  -", example_id)
    print("Entries with no matching draft:", len(orphans))
    print("Entries with a recorded answer_edit_reason:", len(edits))

    if errors:
        print("\nErrors:")
        for error in errors:
            print("-", error)
        return 1
    return 0


def cmd_set(args):
    manifest = open_manifest(args.manifest)
    by_id, errors = index_manifest(manifest)
    if errors:
        print("Manifest errors; fix them first:")
        for error in errors:
            print("-", error)
        return 1

    unknown = [eid for eid in args.example_ids if eid not in by_id]
    if unknown:
        print("Unknown example IDs (run sync first?):", ", ".join(unknown))
        return 1

    if args.decision != "unreviewed" and not args.reviewer.strip():
        print("--reviewer is required for approved/rejected decisions.")
        return 1

    for example_id in args.example_ids:
        entry = by_id[example_id]
        entry["decision"] = args.decision
        entry["reviewer"] = args.reviewer if args.decision != "unreviewed" else ""
        entry["reviewed_on"] = args.date if args.decision != "unreviewed" else ""
        if args.notes is not None:
            entry["notes"] = args.notes
        print(f"{example_id}: {args.decision}")

    save_manifest(args.manifest, manifest)
    return 0


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Maintain the NIRVA review manifest.")
    parser.add_argument("--manifest", type=Path, default=MANIFEST_PATH)
    parser.add_argument("--drafts", type=Path, action="append",
                        help="Draft file; repeat for several (default: data/generated_drafts.jsonl)")
    sub = parser.add_subparsers(dest="command", required=True)

    sync = sub.add_parser("sync", help="Add new drafts as unreviewed")
    sync.add_argument("--dry-run", action="store_true")

    sub.add_parser("status", help="Show review counts")

    setter = sub.add_parser("set", help="Record a review decision")
    setter.add_argument("--decision", choices=sorted(DECISIONS), required=True)
    setter.add_argument("--reviewer", default="")
    setter.add_argument("--date", default=date.today().isoformat())
    setter.add_argument("--notes", default=None)
    setter.add_argument("example_ids", nargs="+")

    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    args.drafts = args.drafts or [DRAFTS_PATH]
    handler = {"sync": cmd_sync, "status": cmd_status, "set": cmd_set}[args.command]
    return handler(args)


if __name__ == "__main__":
    sys.exit(main())
